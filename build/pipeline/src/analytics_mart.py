"""traffic_analytics.json: the traffic-quality numbers the app shows (contract in LOVABLE_PROMPT_SAAS.md).

Reads only:
  - the three source tables: raw.raw_tune_clicks, unified.unified_session_summary,
    experimentation_tools.experiment_router_events;
  - the leads table sampledb.revenue_leads_plus;
  - the unified tables and ipintel_curated.ip_resolved / ip_occurrences / ip_intelligence_analytics.
Writes only a short-lived stg_ table in ipintel_curated (dropped at the end) and the JSON file.

Verdict per IP is the owner's step 2 standard:
  - bad: FraudLogix's latest decision FLAGGED for any reason, or proxycheck.io is_bot;
  - clean: either answered and neither is bad;
  - unknown: neither answered.
  IP2Proxy is supporting evidence only.
signal_type (for bad IPs) is a breakdown only: automation > behaviour > anonymiser (strongest reason wins).
"""
import common as c
import vendors

RULE_VERSION = "step2-2026-09-19"
WINDOW_DAYS = 30
ROW_CAP = 200          # rows per dimension (largest first)
TREND_CAP = 50         # rows per dimension that carry a daily trend
ANONYMISER = ("VPN", "PROXY", "MOBILE_PROXY_SIGNALS", "PROXYCHECK_IO:VPN", "PROXYCHECK_IO:PROXY",
              "PROXYCHECK_IO:MOBILE_PROXY_SIGNALS")
BEHAVIOUR = ("ABNORMAL_TRAFFIC_PATTERNS", "BASIC_FRAUD", "MASKED_DEVICES", "HIGH_RISK", "OTHER_REASON",
             "NOT_APPLICABLE", "8", "9", "10")
DIMENSIONS = ["affiliate", "offer", "advertiser", "utm_source", "utm_campaign", "experiment", "brand", "device",
              "browser", "os", "state", "source"]


def _signal_sql(col):
    """automation / behaviour / anonymiser for one bot_reason value (FraudLogix filled rows carry a prefix)."""
    base = "regexp_replace(%s, '^PROXYCHECK_IO:', '')" % col
    anon = ", ".join(c.lit(r) for r in ANONYMISER)
    beh = ", ".join(c.lit(r) for r in BEHAVIOUR)
    return (f"CASE WHEN {col} IN ({anon}) OR {base} IN ({anon}) THEN 'anonymiser' "
            f"WHEN {col} IN ({beh}) OR {base} IN ({beh}) THEN 'behaviour' ELSE 'automation' END")


def _events_sql(start, end):
    s, e = c.lit(start), c.lit(end)
    pub = lambda col: c.public_ipv4_sql(col)
    return f"""
WITH ev AS (
  SELECT date_pst AS d, 'clicks' AS source, trim(ip) AS ip, CAST(NULL AS varchar) AS session_id,
         nullif(affiliate_id, '') AS affiliate, nullif(offer_id, '') AS offer, nullif(advertiser_id, '') AS advertiser,
         CAST(NULL AS varchar) AS utm_source, CAST(NULL AS varchar) AS utm_campaign, CAST(NULL AS varchar) AS experiment,
         CAST(NULL AS varchar) AS brand, nullif(device_brand, '') AS device, CAST(NULL AS varchar) AS browser,
         nullif(device_os, '') AS os
  FROM raw.raw_tune_clicks WHERE date_pst BETWEEN date {s} AND date {e} AND nullif(trim(ip), '') IS NOT NULL
  UNION ALL
  SELECT session_date, 'sessions', trim(session_ip), session_id,
         NULL, NULL, NULL, nullif(last_utm_source, ''), nullif(last_utm_campaign, ''), nullif(experiment_id, ''),
         nullif(page_brand, ''), nullif(device_type, ''), nullif(browser_name, ''), nullif(os_platform, '')
  FROM unified.unified_session_summary WHERE session_date BETWEEN date {s} AND date {e} AND nullif(trim(session_ip), '') IS NOT NULL
  UNION ALL
  SELECT CAST(server_timestamp_entry AS date), 'router', trim(ip_address), NULL,
         NULL, NULL, NULL, nullif(utm_source, ''), nullif(utm_campaign, ''), CAST(experiment_id AS varchar),
         NULL, nullif(device_type, ''), NULL, nullif(device_os, '')
  FROM experimentation_tools.experiment_router_events
  WHERE CAST(server_timestamp_entry AS date) BETWEEN date {s} AND date {e} AND nullif(trim(ip_address), '') IS NOT NULL),
pub AS (SELECT * FROM ev WHERE regexp_like(ip, '^\\d{{1,3}}(\\.\\d{{1,3}}){{3}}$') AND {pub('ip')}),
ips AS (SELECT DISTINCT ip FROM pub),
v AS (
  SELECT i.ip_address AS ip,
         count_if(i.vendor IN ('fraudlogix_tune', 'proxycheck_io') AND i.is_bot IS NOT NULL) AS answered,
         bool_or(i.vendor IN ('fraudlogix_tune', 'proxycheck_io') AND coalesce(i.is_bot, false)) AS bad,
         max(CASE WHEN i.vendor IN ('fraudlogix_tune', 'proxycheck_io') AND i.is_bot THEN
               CASE {_signal_sql('i.bot_reason')} WHEN 'automation' THEN 3 WHEN 'behaviour' THEN 2 ELSE 1 END END) AS sig
  FROM unified.ip_intelligence i WHERE i.ip_address IN (SELECT ip FROM ips) GROUP BY i.ip_address),
l AS (SELECT utm_content AS session_id, count(DISTINCT id) AS leads, sum(coalesce(expected_revenue, 0)) AS revenue
      FROM sampledb.revenue_leads_plus WHERE date_pst >= date {s} GROUP BY 1)
SELECT p.d, p.source, p.ip, p.affiliate, p.offer, p.advertiser, p.utm_source, p.utm_campaign, p.experiment,
       p.brand, p.device, p.browser, p.os, r.state, r.geo_status,
       CASE WHEN coalesce(v.answered, 0) = 0 THEN 'unknown' WHEN v.bad THEN 'bad' ELSE 'clean' END AS verdict,
       CASE v.sig WHEN 3 THEN 'automation' WHEN 2 THEN 'behaviour' WHEN 1 THEN 'anonymiser' END AS signal_type,
       coalesce(l.leads, 0) AS leads, coalesce(l.revenue, 0) AS revenue,
       (p.source = 'sessions') AS is_session
FROM pub p
LEFT JOIN v ON v.ip = p.ip
LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = p.ip
LEFT JOIN l ON l.session_id = p.session_id"""


# per-group metrics, reused for overview, dimensions and days
METRICS = """count(*) AS events, count(DISTINCT ip) AS unique_ips,
  round(100.0 * count_if(verdict = 'bad') / count(*), 2) AS bad_pct,
  round(100.0 * count_if(verdict = 'bad' AND signal_type <> 'anonymiser') / count(*), 2) AS strict_bad_pct,
  round(100.0 * count_if(verdict = 'clean') / count(*), 2) AS clean_pct,
  round(100.0 * count_if(verdict = 'unknown') / count(*), 2) AS unknown_pct,
  round(100.0 * count_if(signal_type = 'automation') / count(*), 2) AS sig_automation,
  round(100.0 * count_if(signal_type = 'behaviour') / count(*), 2) AS sig_behaviour,
  round(100.0 * count_if(signal_type = 'anonymiser') / count(*), 2) AS sig_anonymiser,
  sum(leads) AS leads, count_if(is_session) AS session_events, round(sum(revenue), 2) AS revenue"""


def _shape(r):
    """One metrics row into the contract's shape."""
    sess = r.pop("session_events")
    out = {k: r[k] for k in r if not k.startswith("sig_")}
    out["bad_by_signal"] = {"automation": r["sig_automation"], "behaviour": r["sig_behaviour"],
                            "anonymiser": r["sig_anonymiser"]}
    out["quality_score"] = round(100 - (r["bad_pct"] or 0), 2)
    out["lead_rate_pct"] = round(100.0 * r["leads"] / sess, 3) if sess else None   # sessions only can hold leads
    return out


def build(end=None):
    end = end or c.scalar("SELECT CAST(current_date - interval '1' day AS varchar)")
    start = c.scalar("SELECT CAST(date %s - interval '%d' day AS varchar)" % (c.lit(end), WINDOW_DAYS - 1))
    st = c.Staging(c.new_run_id("analytics"))
    try:
        ev = st.ctas("events", _events_sql(start, end))
        out = {"as_of": c.now_iso(), "rule_version": RULE_VERSION,
               "window": {"start": start, "end": end, "days": WINDOW_DAYS},
               "notes": ["Leads and revenue come from website sessions matched to the leads table "
                         "(utm_content = session_id); clicks and router events cannot be matched to leads, so "
                         "lead_rate_pct is over session visits only and is null where a row has no sessions.",
                         "Affiliate, offer and advertiser exist only on TUNE clicks."]}

        # overview
        ov = _shape(c.rows("SELECT %s FROM %s" % (METRICS, ev))[0])
        firsts = c.rows(f"""
WITH f AS (SELECT ip_address, min(first_seen) AS fs FROM ipintel_curated.ip_occurrences GROUP BY 1),
e AS (SELECT DISTINCT ip, d FROM {ev})
SELECT count(DISTINCT CASE WHEN f.fs >= date {c.lit(start)} THEN e.ip END) AS new_ips FROM e LEFT JOIN f ON f.ip_address = e.ip""")[0]
        ov["new_ips"] = firsts["new_ips"]
        ov["returning_ips"] = ov["unique_ips"] - firsts["new_ips"]
        days = c.rows(f"""
WITH f AS (SELECT ip_address, min(first_seen) AS fs FROM ipintel_curated.ip_occurrences GROUP BY 1)
SELECT CAST(e.d AS varchar) AS d, count(*) AS events, count(DISTINCT e.ip) AS unique_ips,
       count(DISTINCT CASE WHEN f.fs = e.d THEN e.ip END) AS new_ips,
       round(100.0 * count_if(e.verdict = 'bad') / count(*), 2) AS bad_pct
FROM {ev} e LEFT JOIN f ON f.ip_address = e.ip GROUP BY e.d ORDER BY e.d""")
        ov["by_day"] = days
        out["overview"] = ov

        # dimensions
        dims = {}
        for dim in DIMENSIONS:
            col = "source" if dim == "source" else dim
            rows = [_shape(r) for r in c.rows(f"""
SELECT {col} AS key, {METRICS} FROM {ev} WHERE {col} IS NOT NULL GROUP BY {col}
ORDER BY count(*) DESC LIMIT {ROW_CAP}""")]
            top = [r["key"] for r in rows[:TREND_CAP]]
            trend = {}
            if top:
                for t in c.rows(f"""
SELECT {col} AS key, CAST(d AS varchar) AS d, count(*) AS events,
       round(100.0 * count_if(verdict = 'bad') / count(*), 2) AS bad_pct
FROM {ev} WHERE {col} IN ({", ".join(c.lit(k) for k in top)}) GROUP BY 1, 2 ORDER BY 1, 2"""):
                    trend.setdefault(t["key"], []).append({"d": t["d"], "bad_pct": t["bad_pct"], "events": t["events"]})
            for r in rows:
                r["trend"] = trend.get(r["key"], [])
            dims[dim] = rows
        out["by_dimension"] = dims

        # reasons (bad rows of FraudLogix and proxycheck.io, for IPs in the window)
        reason_src = f"""
SELECT i.ip_address, i.vendor, i.bot_reason AS reason, {_signal_sql('i.bot_reason')} AS signal_type
FROM unified.ip_intelligence i
WHERE i.vendor IN ('fraudlogix_tune', 'proxycheck_io') AND i.is_bot
  AND i.ip_address IN (SELECT DISTINCT ip FROM {ev})"""
        mix = c.rows(f"""
WITH r AS ({reason_src}), e AS (SELECT ip, count(*) AS n FROM {ev} GROUP BY ip)
SELECT r.reason, r.vendor, r.signal_type, count(DISTINCT r.ip_address) AS ips, sum(e.n) AS events
FROM r JOIN e ON e.ip = r.ip_address GROUP BY 1, 2, 3 ORDER BY ips DESC""")
        top_reasons = [m["reason"] for m in mix[:6]]
        by_day = c.rows(f"""
WITH r AS ({reason_src})
SELECT CAST(e.d AS varchar) AS d, CASE WHEN r.reason IN ({", ".join(c.lit(x) for x in top_reasons) or "''"}) THEN r.reason ELSE 'OTHER' END AS reason,
       count(DISTINCT e.ip) AS ips
FROM {ev} e JOIN r ON r.ip_address = e.ip GROUP BY 1, 2 ORDER BY 1, 2""")
        out["reasons"] = {"mix": mix, "by_day": by_day}

        # network (unique IPs in the window)
        clouds = ", ".join(c.lit(a) for a in sorted(vendors.CLOUD_ASNS))
        net_src = f"""
WITH w AS (SELECT DISTINCT ip, verdict FROM {ev}),
e AS (SELECT ip, count(*) AS n FROM {ev} GROUP BY ip),
pc AS (SELECT i.ip_address, i.asn, i.isp, i.is_vpn, i.is_proxy, i.is_tor, i.is_datacenter,
              CASE WHEN lower(coalesce(a.fraud_reason, '')) IN ('residential', 'business', 'wireless', 'hosting')
                   THEN a.fraud_reason ELSE 'Unknown' END AS connection_type
       FROM unified.ip_intelligence i
       JOIN ipintel_curated.ip_intelligence_analytics a ON a.ip_address = i.ip_address AND a.vendor = i.vendor
       WHERE i.vendor = 'proxycheck_io' AND i.ip_address IN (SELECT ip FROM w)),
fl AS (SELECT ip_address, bool_or(is_vpn) AS vpn, bool_or(is_proxy) AS proxy, bool_or(is_tor) AS tor,
              bool_or(is_datacenter) AS dc
       FROM unified.ip_intelligence WHERE vendor IN ('fraudlogix_tune', 'proxycheck_io')
         AND ip_address IN (SELECT ip FROM w) GROUP BY 1)"""
        shares = c.rows(f"""{net_src}
SELECT round(100.0 * count_if(upper(coalesce(pc.asn, '')) IN ({clouds})) / count(*), 2) AS cloud_pct,
       round(100.0 * count_if(fl.dc) / count(*), 2) AS datacenter_pct,
       round(100.0 * count_if(fl.vpn) / count(*), 2) AS vpn_pct,
       round(100.0 * count_if(fl.proxy) / count(*), 2) AS proxy_pct,
       round(100.0 * count_if(pc.connection_type = 'Wireless') / count(*), 2) AS mobile_pct,
       round(100.0 * count_if(fl.tor) / count(*), 2) AS tor_pct
FROM w LEFT JOIN pc ON pc.ip_address = w.ip LEFT JOIN fl ON fl.ip_address = w.ip""")[0]
        top_asn = c.rows(f"""{net_src}
SELECT pc.asn, arbitrary(pc.isp) AS provider, arbitrary(pc.connection_type) AS connection_type,
       count(DISTINCT w.ip) AS ips, sum(e.n) AS events,
       round(100.0 * count_if(w.verdict = 'bad') / count(*), 2) AS bad_pct,
       upper(pc.asn) IN ({clouds}) AS is_cloud
FROM w JOIN pc ON pc.ip_address = w.ip JOIN e ON e.ip = w.ip
WHERE pc.asn IS NOT NULL GROUP BY pc.asn ORDER BY ips DESC LIMIT 100""")
        out["network"] = {"shares": shares, "top_asn": top_asn}

        # geography
        states = c.rows(f"""
SELECT state, count(*) AS events, count(DISTINCT ip) AS ips,
       round(100.0 * count_if(verdict = 'bad') / count(*), 2) AS bad_pct
FROM {ev} WHERE state IS NOT NULL GROUP BY 1 ORDER BY events DESC""")
        conf = {r["geo_status"]: r["ips"] for r in c.rows(
            "SELECT geo_status, count(DISTINCT ip) AS ips FROM %s WHERE geo_status IS NOT NULL GROUP BY 1" % ev)}
        out["geo"] = {"states": states,
                      "confidence": {k: conf.get(k, 0) for k in
                                     ("agreed", "nearby", "same_state", "vendors_disagree", "single_source")}}

        # outcomes (session visits only: the only ones that can be matched to leads)
        def outcome(group):
            return c.rows(f"""
SELECT {group} AS k, count(*) AS events, sum(leads) AS leads,
       round(100.0 * sum(leads) / count(*), 3) AS lead_rate_pct, round(sum(revenue), 2) AS revenue,
       round(1000.0 * sum(revenue) / count(*), 2) AS revenue_per_1k
FROM {ev} WHERE is_session AND {group} IS NOT NULL GROUP BY 1""")
        by_verdict = [dict(verdict=r.pop("k"), **r) for r in outcome("verdict")]
        by_signal = [dict(signal_type=r.pop("k"), **{k: r[k] for k in ("events", "leads", "lead_rate_pct")})
                     for r in outcome("signal_type")]
        bad_events = c.scalar("SELECT count_if(verdict = 'bad') FROM %s" % ev)
        out["outcomes"] = {"by_verdict": by_verdict, "by_signal": by_signal,
                           "by_utm_source": [r for r in dims["utm_source"] if r["leads"]],
                           "wasted": {"bad_events": bad_events}}
        return out
    finally:
        st.cleanup()
