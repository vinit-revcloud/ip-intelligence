"""How each vendor is asked about a set of addresses.

The mappings for IP2Location, IP2Proxy and FraudLogix are the ones used to build the tables on
11 September, unchanged, so a row written today means exactly what a row written then meant.

Every lookup returns rows in one of two shapes:
  geo    ip_address, vendor, state, city, zip_code, latitude, longitude, timezone, seen_at
  intel  ip_address, vendor, has_answer, is_proxy, is_vpn, is_tor, is_datacenter, is_bot,
         is_compromised, is_scraper, is_anonymous, isp, asn, fraud_reason, is_masked_device,
         risk_score, seen_at
"""
import json
import time
import urllib.error
import urllib.request

from common import DB, lit, table_exists

USER_AGENT = "ipintel-pipeline/1.0 (+ip intelligence daily job)"

GEO_COLS = "ip_address, vendor, state, city, zip_code, latitude, longitude, timezone, seen_at"
INTEL_COLS = ("ip_address, vendor, has_answer, is_proxy, is_vpn, is_tor, is_datacenter, is_bot, "
              "is_compromised, is_scraper, is_anonymous, isp, asn, fraud_reason, is_masked_device, "
              "risk_score, seen_at")


# ---------------------------------------------------------------- downloaded databases

def db11_geo_sql(targets, seen_at):
    return f"""
SELECT n.ip_address, CAST('ip2location_db11' AS varchar) AS vendor,
  CASE WHEN d.region_name <> '-' THEN nullif(trim(d.region_name), '') END AS state,
  CASE WHEN d.region_name <> '-' THEN nullif(nullif(trim(d.city_name), ''), '-') END AS city,
  CASE WHEN d.region_name <> '-' THEN nullif(nullif(trim(d.zip_code), ''), '-') END AS zip_code,
  CASE WHEN d.region_name <> '-' THEN d.latitude END AS latitude,
  CASE WHEN d.region_name <> '-' THEN d.longitude END AS longitude,
  CASE WHEN d.region_name <> '-' THEN nullif(nullif(trim(d.time_zone), ''), '-') END AS timezone,
  {lit(seen_at)} AS seen_at
FROM {targets} n
LEFT JOIN {DB}.db11_bucketed d ON d.prefix16 = n.prefix16 AND n.ip_num BETWEEN d.ip_from AND d.ip_to"""


def px12_intel_sql(targets, seen_at):
    # Absence from PX12 is "no answer", not "not a proxy". This is the rule every existing
    # metric was measured under.
    return f"""
SELECT n.ip_address, CAST('ip2proxy_px12' AS varchar) AS vendor,
  (x.ip_from IS NOT NULL) AS has_answer,
  CASE WHEN x.ip_from IS NOT NULL THEN true END AS is_proxy,
  CASE WHEN x.ip_from IS NOT NULL THEN x.proxy_type = 'VPN' END AS is_vpn,
  CASE WHEN x.ip_from IS NOT NULL THEN x.proxy_type = 'TOR' END AS is_tor,
  CASE WHEN x.ip_from IS NOT NULL THEN regexp_like(coalesce(x.usage_type, '-'), '(^|/)(DCH|CDN)(/|$)') END AS is_datacenter,
  -- is_bot = bad signal (owner's step 2 standard, 19 Sep): every PX12 listing is a public proxy, VPN or datacenter
  -- address. Not listed: NULL, because absence from a proxy list is not an answer.
  CASE WHEN x.ip_from IS NOT NULL THEN true END AS is_bot,
  CAST(NULL AS boolean) AS is_compromised,
  CAST(NULL AS boolean) AS is_scraper, CAST(NULL AS boolean) AS is_anonymous,
  CASE WHEN x.ip_from IS NOT NULL THEN nullif(x.isp, '-') END AS isp,
  CASE WHEN x.ip_from IS NOT NULL THEN nullif(x.asn, '-') END AS asn,
  CASE WHEN x.ip_from IS NOT NULL THEN concat(coalesce(nullif(x.proxy_type, '-'), '-'), '/',
       coalesce(nullif(x.usage_type, '-'), '-'),
       CASE WHEN x.threat IS NOT NULL AND x.threat <> '-' THEN concat('/', x.threat) ELSE '' END) END AS fraud_reason,
  false AS is_masked_device,
  CASE WHEN x.ip_from IS NOT NULL THEN x.fraud_score END AS risk_score,
  {lit(seen_at)} AS seen_at
FROM {targets} n
LEFT JOIN {DB}.px12_bucketed x ON x.prefix16 = n.prefix16 AND n.ip_num BETWEEN x.ip_from AND x.ip_to"""


def fraudlogix_intel_sql(targets, tune_version_clause):
    """The latest decision per address. MASKED_DEVICES is a device fingerprint signal, not a bot
    signal, so it sets none of the flags. An address with clicks but no decision gets a row with
    no answer."""
    return f"""
WITH t AS (
  SELECT ip, datetime, access_control_decision AS dec, access_control_reason_code AS rsn
  FROM raw.raw_tune_clicks {tune_version_clause}
  WHERE ip IN (SELECT ip_address FROM {targets})
),
-- Latest decided click wins. Two clicks can share the exact same timestamp with different decisions; the tie is
-- broken the same way every run (FLAGGED first, then reason), and decision and reason always come from one click.
k AS (
  SELECT ip, datetime, dec, rsn,
         format_datetime(datetime, 'yyyy-MM-dd HH:mm:ss.SSSSSS') || '|' || CASE WHEN dec = 'FLAGGED' THEN '1' ELSE '0' END
           || '|' || coalesce(rsn, '') AS pick
  FROM t WHERE coalesce(dec, '') <> ''
),
decided AS (
  SELECT ip, max_by(dec, pick) AS dec, max_by(rsn, pick) AS rsn, max(datetime) AS at
  FROM k GROUP BY ip
),
clicked AS (SELECT ip, max(datetime) AS at FROM t GROUP BY ip)
SELECT c.ip AS ip_address, CAST('fraudlogix_tune' AS varchar) AS vendor,
  (d.ip IS NOT NULL) AS has_answer,
  CASE WHEN d.ip IS NULL THEN NULL WHEN d.dec <> 'FLAGGED' THEN false ELSE d.rsn IN ('PROXY', 'MOBILE_PROXY_SIGNALS') END AS is_proxy,
  CASE WHEN d.ip IS NULL THEN NULL WHEN d.dec <> 'FLAGGED' THEN false ELSE d.rsn = 'VPN' END AS is_vpn,
  CASE WHEN d.ip IS NULL THEN NULL WHEN d.dec <> 'FLAGGED' THEN false ELSE d.rsn IN ('TOR', 'TOR_EXIT_NODE') END AS is_tor,
  CASE WHEN d.ip IS NULL THEN NULL WHEN d.dec <> 'FLAGGED' THEN false ELSE d.rsn = 'DATA_CENTER' END AS is_datacenter,
  -- is_bot = bad signal (owner's step 2 standard, 19 Sep): the latest decision is FLAGGED, for ANY reason
  -- (bot, script, abnormal traffic, basic fraud, proxy, VPN, masked device, ...). Accepted: false. No decision: NULL.
  CASE WHEN d.ip IS NULL THEN NULL ELSE d.dec = 'FLAGGED' END AS is_bot,
  CAST(NULL AS boolean) AS is_compromised, CAST(NULL AS boolean) AS is_scraper, CAST(NULL AS boolean) AS is_anonymous,
  CAST(NULL AS varchar) AS isp, CAST(NULL AS varchar) AS asn,
  CASE WHEN d.ip IS NULL THEN NULL WHEN d.dec <> 'FLAGGED' THEN 'ACCEPTED' ELSE d.rsn END AS fraud_reason,
  coalesce(d.dec = 'FLAGGED' AND d.rsn = 'MASKED_DEVICES', false) AS is_masked_device,
  CAST(NULL AS integer) AS risk_score,
  -- raw_tune_clicks.datetime is Pacific wall-clock time (it always equals date_pst, and each 6-hourly load's
  -- newest click is 7-8 hours "before" the load was written). Stored as UTC ISO like every other vendor.
  date_format(with_timezone(coalesce(d.at, c.at), 'America/Los_Angeles') AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%i:%sZ') AS seen_at
FROM clicked c LEFT JOIN decided d ON d.ip = c.ip"""


# Databases in the plan that are loaded separately. Until their tables exist the job records the
# vendor as not loaded yet and carries on.
OPTIONAL_GEO_DATABASES = {
    "maxmind_geolite2": "geolite2_bucketed",
    "dbip_combined": "dbip_bucketed",
}
OPTIONAL_INTEL_DATABASES = {
    "authoritative_lists": "range_lists_bucketed",
}


def scoreable(vendor_ids):
    """Vendors the pipeline really asks about new addresses. A database that is not loaded yet answers
    nothing new, and keeping it would cap the scorecard pool at the addresses it answered once."""
    optional = dict(OPTIONAL_GEO_DATABASES, **OPTIONAL_INTEL_DATABASES)
    return [x for x in vendor_ids if x != "geojs_io" and (x not in optional or table_exists(optional[x]))]


def range_geo_sql(vendor, table, targets, seen_at):
    return f"""
SELECT n.ip_address, CAST({lit(vendor)} AS varchar) AS vendor,
  nullif(trim(r.state), '') AS state, nullif(trim(r.city), '') AS city, nullif(trim(r.zip_code), '') AS zip_code,
  r.latitude, r.longitude, nullif(trim(r.timezone), '') AS timezone, {lit(seen_at)} AS seen_at
FROM {targets} n
LEFT JOIN {DB}.{table} r ON r.prefix16 = n.prefix16 AND n.ip_num BETWEEN r.ip_from AND r.ip_to"""


def range_lists_intel_sql(table, targets, seen_at):
    return f"""
SELECT n.ip_address, CAST('authoritative_lists' AS varchar) AS vendor, true AS has_answer,
  coalesce(bool_or(r.is_proxy), false) AS is_proxy, coalesce(bool_or(r.is_vpn), false) AS is_vpn,
  coalesce(bool_or(r.is_tor), false) AS is_tor, coalesce(bool_or(r.is_datacenter), false) AS is_datacenter,
  CAST(NULL AS boolean) AS is_bot, CAST(NULL AS boolean) AS is_compromised,
  CAST(NULL AS boolean) AS is_scraper, CAST(NULL AS boolean) AS is_anonymous,
  CAST(NULL AS varchar) AS isp, CAST(NULL AS varchar) AS asn,
  array_join(array_agg(DISTINCT r.list_name) FILTER (WHERE r.list_name IS NOT NULL), ',') AS fraud_reason,
  false AS is_masked_device, CAST(NULL AS integer) AS risk_score, {lit(seen_at)} AS seen_at
FROM {targets} n
LEFT JOIN {DB}.{table} r ON r.prefix16 = n.prefix16 AND n.ip_num BETWEEN r.ip_from AND r.ip_to
GROUP BY n.ip_address"""


# ---------------------------------------------------------------- free web APIs

class Throttled(Exception):
    pass


def _get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise Throttled("HTTP %d" % e.code)
        raise


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ask_ipinfo(ip):
    d = _get_json("https://ipinfo.io/%s/json" % ip)
    if d.get("bogon") or d.get("error"):
        return None
    lat, lon = (d.get("loc") or ",").split(",")[:2] if d.get("loc") else (None, None)
    return {"state": d.get("region") or None, "city": d.get("city") or None, "zip_code": d.get("postal") or None,
            "latitude": _float(lat), "longitude": _float(lon), "timezone": d.get("timezone") or None}


def ask_ipwho(ip):
    d = _get_json("https://ipwho.is/%s" % ip)
    if not d.get("success"):
        msg = (d.get("message") or "").lower()
        if "limit" in msg or "rate" in msg:
            raise Throttled(d.get("message"))
        return None
    return {"state": d.get("region") or None, "city": d.get("city") or None, "zip_code": d.get("postal") or None,
            "latitude": _float(d.get("latitude")), "longitude": _float(d.get("longitude")),
            "timezone": (d.get("timezone") or {}).get("id")}


WEB_GEO_VENDORS = {"ipinfo_io": ask_ipinfo, "ipwho_is": ask_ipwho}


def ask_web_vendor(vendor, ips, seen_at, deadline, per_second=3.0):
    """Ask one free web API about each address until it refuses, runs out of addresses, or time
    runs short. Returns (rows, asked, stopped_reason). Addresses it did not reach are simply asked
    tomorrow, because tomorrow's list is 'addresses this vendor has no row for'."""
    fn = WEB_GEO_VENDORS[vendor]
    out, gap, stopped = [], 1.0 / per_second, None
    for ip in ips:
        if time.time() > deadline:
            stopped = "time budget reached"
            break
        t0 = time.time()
        try:
            ans = fn(ip)
        except Throttled as e:
            stopped = "vendor refused further requests (%s)" % e
            break
        except Exception as e:
            stopped = "vendor error (%s)" % type(e).__name__
            break
        row = {"ip_address": ip, "vendor": vendor, "seen_at": seen_at,
               "state": None, "city": None, "zip_code": None, "latitude": None, "longitude": None, "timezone": None}
        if ans:
            row.update(ans)
        out.append(row)
        time.sleep(max(0.0, gap - (time.time() - t0)))
    return out, len(out), stopped


# ---------------------------------------------------------------- proxycheck.io

# Bad-signal types (owner's step 2 standard, 19 Sep): every proxy protocol, VPN, TOR, compromised server, scraper,
# hosting and proxycheck.io's inference engine. Business / Residential / Wireless are network types, not signals.
BOT_TYPES = {"socks", "socks4", "socks4a", "socks5", "socks5h", "http", "https", "shadowsocks", "openvpn", "vpn",
             "compromised server", "tor", "hosting", "scraper", "inference engine"}
HIGH_RISK = 67          # proxycheck.io: 67-100 = "very dangerous"
# Cloud and server-hosting networks (AWS, Google Cloud, Azure, DigitalOcean, Hetzner, OVH, Linode, Vultr, Alibaba,
# Oracle, Leaseweb, Contabo, Aruba, DataCamp, M247, UK-2). A person does not browse from a cloud server. Tested on
# 18 Sep: 0 of 427 paying customers. Deliberately excluded: Akamai, Cloudflare and Fastly (they carry iCloud Private
# Relay), Google AS15169 and general carriers such as Cogent AS174 (both carry ordinary customer traffic).
CLOUD_ASNS = {"AS16509", "AS14618", "AS8075", "AS396982", "AS14061", "AS24940", "AS16276", "AS63949", "AS20473",
              "AS45102", "AS31898", "AS8560", "AS51167", "AS12876", "AS212238", "AS9009", "AS60068"}


def proxycheck_intel_row(ip, raw, now):
    """proxycheck's answer mapped onto ip_intelligence.

    Only the Hosting type counts as datacenter. Business was counted too until 14 September; a test
    of 400 real addresses showed Business is mostly home and office broadband (Charter, Cox, AT&T,
    CenturyLink, Verizon Business), so counting it would call real people datacenter traffic.
    """
    t = (raw.get("type") or "").strip()
    tl = t.lower()
    proxy = raw.get("proxy") == "yes"
    vpn = raw.get("vpn") == "yes"
    anon = (raw.get("operator") or {}).get("anonymity")
    seen = raw.get("last seen unix")
    updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(seen))) if seen else now
    risk = raw.get("risk")
    return {
        "ip_address": ip, "vendor": "proxycheck_io", "has_answer": True,
        "is_proxy": proxy, "is_vpn": vpn, "is_tor": tl == "tor",
        "is_datacenter": tl == "hosting",
        # proxycheck.io has no bot field. Open proxies (SOCKS/HTTP), compromised servers, scrapers, Tor and hosting are
        # automated relays, not people: 2 of 427 paying customers (18 Sep test). Business, Residential and
        # Wireless are ordinary connections, so False. Business alone would hit 21% of paying customers.
        # is_bot = bad signal (owner's step 2 standard, 19 Sep): proxy or VPN, a bad type, a cloud network, or risk 67+.
        "is_bot": (proxy or vpn or tl in BOT_TYPES or (raw.get("asn") or "").upper() in CLOUD_ASNS
                   or (str(risk).isdigit() and int(risk) >= HIGH_RISK)),
        "is_compromised": tl == "compromised server",
        "is_scraper": tl == "scraper",
        "is_anonymous": bool(anon) or proxy or vpn,
        "isp": raw.get("provider") or None, "asn": raw.get("asn") or None,
        "fraud_reason": t or None, "is_masked_device": False,
        "risk_score": int(risk) if str(risk).isdigit() else None,
        "seen_at": updated,
    }


def proxycheck_geo_row(ip, raw, now):
    return {"ip_address": ip, "vendor": "proxycheck_io", "seen_at": now,
            "state": raw.get("region") or None, "city": raw.get("city") or None,
            "zip_code": raw.get("postcode") or None, "latitude": _float(raw.get("latitude")),
            "longitude": _float(raw.get("longitude")), "timezone": raw.get("timezone") or None}


INTEL_JSON_DDL = ("ip_address string, vendor string, has_answer boolean, is_proxy boolean, is_vpn boolean, "
                  "is_tor boolean, is_datacenter boolean, is_bot boolean, is_compromised boolean, "
                  "is_scraper boolean, is_anonymous boolean, isp string, asn string, fraud_reason string, "
                  "is_masked_device boolean, risk_score int, seen_at string")
GEO_JSON_DDL = ("ip_address string, vendor string, state string, city string, zip_code string, "
                "latitude double, longitude double, timezone string, seen_at string")
