"""The live lookup path: GET /lookup/{ip}.

    IP -> ip_geo, ip_intelligence and ip_occurrences
       -> a resolved answer for location and for proxy, built from every vendor's own row
       -> no answer, or answers that reach no conclusion? -> proxycheck.io, and keep the answer

Vendor rows are never changed to make them "correct". Each vendor keeps its own row, one per address
and vendor, so every answer stays traceable and the scorecards stay honest. The one answer to use is
worked out here, at read time, in `resolved`, and says which vendors it rests on.

Which rows are read: ipintel_curated.ip_geo, ip_intelligence and ip_occurrences only, in every mode.
They hold every address in the base tables (reconciled 14 September: 4,956,801 addresses, none
missing), are kept current by the daily jobs, and contain only vendors the system runs. The frozen
unified.* copy is not read: it still carries the benchmark-only vendors removed on 14 September, and
reading it would make a lookup disagree with ipintel_curated.ip_resolved.
Plus the latest answer this path fetched for the address, kept in S3 until the proxycheck job has
folded it into the tables (within a day).

When proxycheck.io is called (and only then is quota spent):
  * no location answer at all, or
  * no proxycheck answer yet and the other vendors give no conclusion: none answered, they disagree,
    or they flag the address with nothing confirming it.
  `?refresh=true` forces a call. Before any call: the pipeline must not be paused, and two queries are
  reserved in the shared daily counter the proxycheck job uses (vpn=3 charges proxy-and-VPN addresses
  twice). The raw answer is saved before it is used.
"""
import ipaddress
import json
import math
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import boto3

athena = boto3.client("athena")
_sm = boto3.client("secretsmanager")
_s3 = boto3.client("s3")
_state = boto3.resource("dynamodb").Table("ipintel-pipeline-state")

WORKGROUP = "ipintel"
CURATED = "ipintel_curated"
BUCKET = "datalake-landingzone-221490242148-us-west-2"
LIVE_PREFIX = "ip-intelligence/proxycheck/live"
SCORECARD_KEY = "ip-intelligence/serving/ipintel_curated/tbl_vendor_overview_geo.json"
USER_AGENT = "ipintel-lookup/2.0 (+ip-intelligence)"
PC_TIMEOUT_S = 8
POLL_BUDGET_S = 25
RESERVE_PER_ADDRESS = 2
CONFIG_TTL_S = 60
SCORECARD_TTL_S = 900
CACHE_DAYS = 30

_key_cache, _cfg_cache, _score_cache = {}, {}, {}

GEO_COLS = ["vendor", "state", "city", "zip_code", "latitude", "longitude", "timezone",
            "created_at", "updated_at"]
INTEL_COLS = ["vendor", "is_proxy", "is_vpn", "is_tor", "is_datacenter", "is_bot",
              "is_compromised", "is_scraper", "is_anonymous", "isp", "asn",
              "created_at", "updated_at"]
FLAGS = ["is_proxy", "is_vpn", "is_tor", "is_datacenter", "is_bot", "is_compromised", "is_scraper"]
NO_GEO_VOTE = {"geojs_io"}           # repeats MaxMind, so it never votes (same rule as the scorecards)
UNRESOLVED = {"no_answer", "vendors_disagree", "flagged_unconfirmed"}
# Same list as common.NON_PUBLIC_RANGES in the pipeline: no vendor has a record for these.
NON_PUBLIC = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
    "203.0.113.0/24", "224.0.0.0/3")]
REASON_TEXT = {
    "refresh": "refresh requested",
    "new_address": "the address is not in the IP tables",
    "no_location": "no vendor gave a location",
    "no_answer": "no vendor gave a proxy answer",
    "vendors_disagree": "the proxy vendors disagree",
    "flagged_unconfirmed": "flagged, with nothing confirming it",
    "location_disagree": "the location vendors disagree",
}


def is_public(ip):
    addr = ipaddress.ip_address(ip)
    return not any(addr in n for n in NON_PUBLIC)


def needs_proxycheck(ip, in_tables, geo, proxy, has_pc, refresh=False):
    """The one rule for when proxycheck.io is asked, returned as a reason code or None.

    The pipeline applies the same rule to addresses from new base-table rows (pcqueue.reason_sql), so an
    address is treated the same whether it arrives by API call or by a base-table insert."""
    if not is_public(ip):
        return None
    if refresh:
        return "refresh"
    if has_pc:
        return None
    if not in_tables:
        return "new_address"
    if geo["status"] == "no_answer":
        return "no_location"
    if proxy["status"] in UNRESOLVED:
        return proxy["status"]
    if geo["status"] == "vendors_disagree":
        return "location_disagree"
    return None


def _lit(v):
    return "'" + str(v).replace("'", "''") + "'"


def _cast(value, kind):
    """Athena returns text. Rebuild real types, and keep NULL as None: the booleans are tri-state."""
    if value is None:
        return None
    k = kind.lower()
    if k == "boolean":
        return value == "true"
    if k in ("tinyint", "smallint", "integer", "int", "bigint"):
        return int(value)
    if k in ("float", "real", "double", "decimal"):
        return float(value)
    return value


def _run(sql):
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP)["QueryExecutionId"]
    deadline = time.time() + POLL_BUDGET_S
    delay = 0.12
    while time.time() < deadline:
        ex = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        st = ex["Status"]["State"]
        if st == "SUCCEEDED":
            return _rows(athena.get_query_results(QueryExecutionId=qid, MaxResults=100))
        if st in ("FAILED", "CANCELLED"):
            raise RuntimeError(ex["Status"].get("StateChangeReason", st))
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)
    raise TimeoutError(qid)


def _rows(result):
    meta = result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
    names = [c["Name"] for c in meta]
    kinds = [c["Type"] for c in meta]
    out = []
    for r in result["ResultSet"]["Rows"][1:]:          # first row is the header
        data = r.get("Data", [])
        out.append({n: _cast((data[i] if i < len(data) else {}).get("VarCharValue"), kinds[i])
                    for i, n in enumerate(names)})
    return out


# ---------------------------------------------------------------- settings

def _config():
    """Safety state and the proxycheck job's settings, cached for a minute per container."""
    if _cfg_cache.get("at", 0) > time.time() - CONFIG_TTL_S:
        return _cfg_cache["safety"], _cfg_cache["job"]
    safety = _state.get_item(Key={"pk": "safety", "sk": "state"}).get("Item") or {}
    job = _state.get_item(Key={"pk": "job", "sk": "proxycheck-daily"}).get("Item") or {}
    _cfg_cache.update(at=time.time(), safety=safety, job=job)
    return safety, job


def read_mode():
    return "live" if _config()[0].get("mode") == "live" else "shadow"


def _geo_scores():
    """Location scorecard score per vendor, from the file the daily job exports. Cached 15 minutes."""
    if _score_cache.get("at", 0) > time.time() - SCORECARD_TTL_S:
        return _score_cache["scores"]
    try:
        d = json.loads(_s3.get_object(Bucket=BUCKET, Key=SCORECARD_KEY)["Body"].read())
        scores = {r["vendor"]: float(r.get("score") or 0) for r in d.get("rows", [])}
    except Exception:
        scores = _score_cache.get("scores", {})
    _score_cache.update(at=time.time(), scores=scores)
    return scores


# ---------------------------------------------------------------- reading the tables

def _select(table, cols, dbs, ip):
    parts = ["SELECT %d AS pref, %s FROM %s.%s WHERE ip_address = %s" % (i, ", ".join(cols), db, table, _lit(ip))
             for i, db in enumerate(dbs)]
    return " UNION ALL ".join(parts)


def _one_per_vendor(rows, dbs):
    """Per vendor, the row from the first database in `dbs` that has one; within it the latest."""
    best = {}
    for r in rows:
        v = r["vendor"]
        key = (-r.pop("pref"), r.get("updated_at") or "")
        if v not in best or key > best[v][0]:
            best[v] = (key, r)
    out = []
    for v in sorted(best):
        key, r = best[v]
        r["table"] = "%s.%s" % (dbs[-key[0]], "ip_geo" if "state" in r else "ip_intelligence")
        out.append(r)
    return out


def _cache_key(ip):
    return "%s/by-ip/%s.json" % (LIVE_PREFIX, ip)


def _cached_answer(ip):
    """The latest proxycheck answer this path fetched, if it is recent. None when there is none."""
    try:
        obj = _s3.get_object(Bucket=BUCKET, Key=_cache_key(ip))
    except _s3.exceptions.NoSuchKey:
        return None
    except Exception:
        return None
    d = json.loads(obj["Body"].read())
    if d.get("fetched_epoch", 0) < time.time() - CACHE_DAYS * 86400:
        return None
    return d


# ---------------------------------------------------------------- proxycheck

def _pc_key(secret_name):
    if secret_name not in _key_cache:
        _key_cache[secret_name] = _sm.get_secret_value(SecretId=secret_name)["SecretString"].strip()
    return _key_cache[secret_name]


def _reserve(daily_limit, n=RESERVE_PER_ADDRESS):
    """Take n queries from the shared counter. False when the account's daily limit would be passed."""
    date = time.strftime("%Y-%m-%d", time.gmtime())
    try:
        _state.update_item(
            Key={"pk": "quota", "sk": date},
            UpdateExpression="SET reserved = if_not_exists(reserved, :z) + :n, "
                             "live_reserved = if_not_exists(live_reserved, :z) + :n, expires_at = :exp",
            ConditionExpression="attribute_not_exists(reserved) OR reserved <= :cap",
            ExpressionAttributeValues={":z": 0, ":n": n, ":cap": daily_limit - n,
                                       ":exp": int(time.time()) + 8 * 86400})
        return True
    except _state.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def _proxycheck(key, ip):
    """One live lookup, with the same flags the daily job uses."""
    url = ("https://proxycheck.io/v2/?key=" + urllib.parse.quote(key)
           + "&vpn=3&asn=1&risk=1&seen=1&days=90")
    body = urllib.parse.urlencode({"ips": ip}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    d = json.loads(urllib.request.urlopen(req, timeout=PC_TIMEOUT_S).read())
    # "warning" still carries the full record. Only a denial or an error is fatal.
    if d.get("status") not in ("ok", "warning"):
        raise RuntimeError(d.get("message") or f"proxycheck status {d.get('status')}")
    v = d.get(ip)
    if not isinstance(v, dict):
        raise RuntimeError(d.get("message") or "proxycheck returned no record for this address")
    return v, (d.get("message") if d.get("status") == "warning" else None)


def _ts(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _intel_row(raw, fetched):
    """Same mapping as vendors.proxycheck_intel_row in the daily job. Only Hosting counts as datacenter:
    Business is mostly home and office broadband (Charter, Cox, AT&T, CenturyLink, Verizon Business)."""
    tl = (raw.get("type") or "").strip().lower()
    proxy = raw.get("proxy") == "yes"
    vpn = raw.get("vpn") == "yes"
    anon = (raw.get("operator") or {}).get("anonymity")
    seen = raw.get("last seen unix")
    return {"vendor": "proxycheck_io", "is_proxy": proxy, "is_vpn": vpn, "is_tor": tl == "tor",
            "is_datacenter": tl == "hosting", "is_bot": None, "is_compromised": tl == "compromised server",
            "is_scraper": tl == "scraper", "is_anonymous": bool(anon) or proxy or vpn,
            "isp": raw.get("provider") or None, "asn": raw.get("asn") or None,
            "created_at": _ts(fetched), "updated_at": _ts(int(seen)) if seen else _ts(fetched),
            "table": "proxycheck.io (fetched live, added to the tables by the next proxycheck job)"}


def _geo_row(raw, fetched):
    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    return {"vendor": "proxycheck_io", "state": raw.get("region") or None, "city": raw.get("city") or None,
            "zip_code": raw.get("postcode") or None, "latitude": num(raw.get("latitude")),
            "longitude": num(raw.get("longitude")), "timezone": raw.get("timezone") or None,
            "created_at": _ts(fetched), "updated_at": _ts(fetched),
            "table": "proxycheck.io (fetched live, added to the tables by the next proxycheck job)"}


def _save_answer(ip, raw, fetched):
    """Two copies, both before the answer is used: one for the proxycheck job to fold into the tables,
    one keyed by address so the next lookup finds it at once."""
    body = json.dumps({ip: raw}).encode()
    day = time.strftime("%Y-%m-%d", time.gmtime(fetched))
    _s3.put_object(Bucket=BUCKET, Key="%s/dt=%s/%d-%s.json" % (LIVE_PREFIX, day, int(fetched * 1000), ip),
                   Body=body, ContentType="application/json")
    _s3.put_object(Bucket=BUCKET, Key=_cache_key(ip), ContentType="application/json",
                   Body=json.dumps({"fetched_epoch": int(fetched), "raw": raw}).encode())


# ---------------------------------------------------------------- the resolved answer

# Which vendor to believe when location vendors disagree. Measured on 2,105 customers' own postal
# addresses (build/pipeline/sql/checks/geo_conflict_truth.sql and a before/after replay, 16 Sep 2026):
#   states differ   ipinfo.io beat IP2Location 80:4 and proxycheck.io 53:25; ipwho.is beat IP2Location 76:6
#                   and proxycheck.io 47:25; ipinfo.io beat ipwho.is 9:3; where only IP2Location and
#                   proxycheck.io answer, IP2Location was right 76 times to proxycheck.io's 42
#   same state,     ipinfo.io 10 vs IP2Location 5; IP2Location 13 vs ipwho.is 11; ipinfo.io 14 vs ipwho.is 8;
#   cities differ   every vendor beat proxycheck.io (IP2Location 90:47)
# resolved.py uses the same lists.
STATE_PRIORITY = ["ipinfo_io", "ipwho_is", "ip2location_db11", "proxycheck_io"]
CITY_PRIORITY = ["ipinfo_io", "ip2location_db11", "ipwho_is", "proxycheck_io"]
NEARBY_KM = 25.0
_CITY_WORDS = {"saint": "st", "mount": "mt", "fort": "ft"}


def _rank(order, vendor):
    return (order.index(vendor) if vendor in order else len(order), vendor)


def _ascii(s):
    return re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", s or "").lower())


def _norm_state(s):
    return " ".join(_ascii(s).split()) or None


def _norm_city(s):
    """Same city under different spellings: accents and punctuation dropped, Saint/Mount/Fort shortened,
    a trailing City or Township dropped, spaces removed. "St. Louis" = "Saint Louis", "LaGrange" = "La Grange"."""
    words = [_CITY_WORDS.get(w, w) for w in _ascii(s).split()]
    if len(words) > 1 and words[-1] in ("city", "township"):
        words = words[:-1]
    return "".join(words) or None


def _km(a, b):
    if None in (a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude")):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _has_geo(r):
    return bool((r.get("state") or "").strip() or (r.get("city") or "").strip() or r.get("latitude") is not None)


def resolve_geo(rows):
    """One location per address, in this order:
      agreed        two or more vendors name the same state and city
      single_source only one vendor answered
      nearby        two or more vendors name the same state, and two of them are within 25 km
      same_state    two or more vendors name the same state, cities further apart
      vendors_disagree  no two vendors name the same state
    The fields come from the agreeing vendors (agreed), from the vendors in the agreed state, best city vendor
    first (nearby, same_state), or from the best state vendor (single_source, vendors_disagree).
    resolved.py applies the same rules in SQL for ipintel_curated.ip_resolved."""
    answered = [r for r in rows if _has_geo(r)]
    if not answered:
        return {"status": "no_answer", "state": None, "city": None, "zip_code": None, "latitude": None,
                "longitude": None, "timezone": None, "decided_by": None, "agreeing_vendors": [],
                "vendors_answered": 0}
    voting = [r for r in answered if r["vendor"] not in NO_GEO_VOTE] or answered
    voters = len([r for r in answered if r["vendor"] not in NO_GEO_VOTE])
    by_state = lambda r: _rank(STATE_PRIORITY, r["vendor"])
    by_city = lambda r: _rank(CITY_PRIORITY, r["vendor"])
    groups, states = {}, {}
    for r in voting:
        ns = _norm_state(r.get("state"))
        groups.setdefault((ns, _norm_city(r.get("city"))), []).append(r)
        if ns:
            states.setdefault(ns, []).append(r)
    best_group = min(groups.values(), key=lambda g: (-len(g), min(by_state(r) for r in g)))
    best_state = min(states.values(), key=lambda g: (-len(g), min(by_state(r) for r in g))) if states else []
    if len(best_group) >= 2:
        status, members = "agreed", best_group
        pick = min(best_group, key=by_city)
    elif voters <= 1:
        pick = min(voting, key=by_state)
        status, members = "single_source", [pick]
    elif len(best_state) >= 2:
        near = any((_km(a, b) or NEARBY_KM + 1) <= NEARBY_KM
                   for i, a in enumerate(best_state) for b in best_state[i + 1:])
        status, members = ("nearby" if near else "same_state"), best_state
        pick = min(best_state, key=by_city)
    else:
        pick = min(voting, key=by_state)
        status, members = "vendors_disagree", [pick]
    return {"status": status, "state": pick.get("state"), "city": pick.get("city"),
            "zip_code": pick.get("zip_code"), "latitude": pick.get("latitude"),
            "longitude": pick.get("longitude"), "timezone": pick.get("timezone"),
            "decided_by": pick["vendor"], "agreeing_vendors": sorted(r["vendor"] for r in members),
            "vendors_answered": len(answered)}


def _flagged(r):
    return any(r.get(f) for f in FLAGS)


def resolve_proxy(rows):
    """proxycheck.io decides when it has answered: it is the one source checked against live traffic
    and it answers every address. Without it, the other vendors decide only when they agree the address
    is clean, or when a flag is confirmed by a published infrastructure range."""
    answered = [r for r in rows if r.get("is_proxy") is not None]
    pc = next((r for r in answered if r["vendor"] == "proxycheck_io"), None)
    others = [r for r in answered if r["vendor"] != "proxycheck_io"]
    blank = {f: None for f in FLAGS + ["is_anonymous"]}
    if pc:
        agree = sorted(r["vendor"] for r in others if _flagged(r) == _flagged(pc))
        status = "confirmed" if agree else ("proxycheck_only" if not others else "proxycheck_overrides")
        out = {f: pc.get(f) for f in FLAGS + ["is_anonymous"]}
        out.update(status=status, flagged=_flagged(pc), decided_by="proxycheck_io", agreeing_vendors=agree)
    elif not others:
        out = dict(blank, status="no_answer", flagged=None, decided_by=None, agreeing_vendors=[])
    else:
        flagged = [r for r in others if _flagged(r)]
        lists = next((r for r in others if r["vendor"] == "authoritative_lists" and _flagged(r)), None)
        if not flagged:
            out = {f: False for f in FLAGS + ["is_anonymous"]}
            out.update(status="clean_by_vendors", flagged=False, decided_by="all answering vendors",
                       agreeing_vendors=sorted(r["vendor"] for r in others))
        elif len(flagged) < len(others):
            out = dict(blank, status="vendors_disagree", flagged=None, decided_by=None, agreeing_vendors=[])
        elif lists:
            out = {f: lists.get(f) for f in FLAGS + ["is_anonymous"]}
            out.update(status="confirmed_by_published_range", flagged=True, decided_by="authoritative_lists",
                       agreeing_vendors=sorted(r["vendor"] for r in flagged))
        else:
            out = dict(blank, status="flagged_unconfirmed", flagged=None, decided_by=None,
                       agreeing_vendors=sorted(r["vendor"] for r in flagged))
    out["vendors_answered"] = len(answered)
    isp = next((r for r in ([pc] if pc else []) + sorted(others, key=lambda r: r["vendor"]) if r.get("isp")), None)
    out["isp"], out["asn"] = (isp or {}).get("isp"), (isp or {}).get("asn")
    return out


# ---------------------------------------------------------------- the endpoint

def serve(ip, refresh=False):
    """Handle one /lookup/{ip}. Returns (status_code, body)."""
    t0 = time.time()
    safety, job = _config()
    mode = "live" if safety.get("mode") == "live" else "shadow"
    dbs = [CURATED]
    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            fg = ex.submit(_run, _select("ip_geo", GEO_COLS, dbs, ip))
            fi = ex.submit(_run, _select("ip_intelligence", INTEL_COLS, dbs, ip))
            fo = ex.submit(_run, "SELECT base_table, source_table, CAST(first_seen AS varchar) AS first_seen, "
                                 "CAST(last_seen AS varchar) AS last_seen, days_seen, rows_seen "
                                 "FROM %s.ip_occurrences WHERE ip_address = %s ORDER BY last_seen DESC"
                                 % (CURATED, _lit(ip)))
            fc = ex.submit(_cached_answer, ip)
            geo_rows = _one_per_vendor(fg.result(), dbs)
            intel_rows = _one_per_vendor(fi.result(), dbs)
            occurrences = fo.result()
            cached = fc.result()
    except TimeoutError:
        return 504, {"error": "lookup timed out", "ip": ip}
    except RuntimeError as e:
        return 502, {"error": "athena rejected the lookup", "detail": str(e)}

    in_tables = bool(geo_rows or intel_rows)
    # A recent live answer not yet folded into the tables counts as proxycheck's row.
    if cached and not any(r["vendor"] == "proxycheck_io" for r in intel_rows):
        intel_rows.append(_intel_row(cached["raw"], cached["fetched_epoch"]))
        if not any(r["vendor"] == "proxycheck_io" for r in geo_rows):
            geo_rows.append(_geo_row(cached["raw"], cached["fetched_epoch"]))

    geo = resolve_geo(geo_rows)
    proxy = resolve_proxy(intel_rows)
    has_pc = any(r["vendor"] == "proxycheck_io" and r.get("is_proxy") is not None for r in intel_rows)
    # Once proxycheck has answered an address it is not asked again unless refresh is requested, even
    # if its answer had no location: asking again would return the same thing and cost a query.
    reason_code = needs_proxycheck(ip, in_tables, geo, proxy, has_pc, refresh)
    reason = REASON_TEXT.get(reason_code)
    out_public = is_public(ip)

    out = {"ip": ip, "mode": mode, "public_address": out_public,
           "seen_in_base_tables": bool(occurrences), "occurrences": occurrences,
           "resolved": {"geo": geo, "proxy": proxy},
           "vendors": {"geo": geo_rows, "proxy": intel_rows},
           "proxycheck": {"called": False, "reason": reason, "reason_code": reason_code}}

    if reason:
        pc_out = out["proxycheck"]
        if safety.get("paused"):
            pc_out["error"] = "The pipeline is paused, so proxycheck.io was not called."
        else:
            secret = job.get("key_secret") or "ipintel/proxycheck"
            try:
                key = _pc_key(secret)
            except Exception:
                key = None
                pc_out["error"] = "no proxycheck credential at %s" % secret
            if key and not _reserve(int(job.get("daily_limit") or 1000)):
                pc_out["error"] = "proxycheck.io daily limit reached; no query was sent."
            elif key:
                try:
                    raw, warning = _proxycheck(key, ip)
                    fetched = time.time()
                    pc_out.update(called=True, risk_score=raw.get("risk"), type=raw.get("type") or None)
                    if warning:
                        pc_out["vendor_warning"] = warning
                    try:
                        _save_answer(ip, raw, fetched)
                        pc_out["saved"] = True
                    except Exception as e:
                        pc_out.update(saved=False, save_error="%s: %s" % (type(e).__name__, e))
                    intel_rows = [r for r in intel_rows if r["vendor"] != "proxycheck_io"] + [_intel_row(raw, fetched)]
                    geo_rows = [r for r in geo_rows if r["vendor"] != "proxycheck_io"] + [_geo_row(raw, fetched)]
                    out["vendors"] = {"geo": geo_rows, "proxy": intel_rows}
                    out["resolved"] = {"geo": resolve_geo(geo_rows), "proxy": resolve_proxy(intel_rows)}
                except Exception as e:
                    pc_out["error"] = "%s: %s" % (type(e).__name__, e)

    out["found"] = bool(geo_rows or intel_rows)
    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    return 200, out
