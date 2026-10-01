"""Keeps the IP Intelligence app's report data current in S3, with no manual step.

After every successful full unified publish this module:
  1. rebuilds the day-to-day snapshot files (coverage, location accuracy, proxy coverage, both vendor scorecards);
  2. takes the one-time analysis files as they are (lead_ips, lead_ip_analysis, session_ip_labels), uploaded once
     to serving/app/static/;
  3. writes all nine, plus manifest.json, to s3://<bucket>/ip-intelligence/serving/app/.

The app reads them from there. Reads tables only; writes only under ip-intelligence/serving/app/.
"""
import common as c
import completeness

APP = "%s/serving/app" % c.PREFIX
STATIC = ["lead_ips.json", "lead_ip_analysis.json", "session_ip_labels.json"]
ALL = STATIC + ["coverage.json", "geo_accuracy.json", "proxy_coverage.json",
                "vendor_overview_geo.json", "vendor_overview_proxy.json", "bad_signals.json", "traffic_analytics.json",
                "manifest.json"]
# Reasons that are proxy / VPN only: real customers use them (iCloud Private Relay, work VPNs), so the app can
# show a "strict" count without them. Everything else in bot_reason is a bot, fraud or infrastructure signal.
PROXY_ONLY = ("VPN", "PROXY", "MOBILE_PROXY_SIGNALS", "PROXYCHECK_IO:VPN", "PROXYCHECK_IO:PROXY")
# Measured 19 Sep 2026 on the leads table (sql/profile_step2/standard_check.py); refreshed by hand when re-measured.
TRUTH_TEST = {"measured_on": "2026-09-19", "paying_ips": 1044, "paying_marked_bad": 535,
              "paying_marked_bad_strict_max": 49, "fake_ips": 40, "fake_marked_bad": 24,
              "paying_bad_by_reason": {"VPN": 300, "PROXY": 185, "MASKED_DEVICES": 23, "ABNORMAL_TRAFFIC_PATTERNS": 16,
                                       "MOBILE_PROXY_SIGNALS": 5, "BASIC_FRAUD": 3, "BOT_GENERATED": 3, "SOCKS5": 2,
                                       "NON_HUMAN_SCRIPT": 1, "DATA_CENTER": 1}}


def bad_signals(now):
    """The step 2 standard (is_bot = bad signal) in numbers, for the app."""
    proxy_only = ", ".join(c.lit(r) for r in PROXY_ONLY)
    vendors = c.rows("""SELECT vendor, count(*) AS rows_, count_if(is_bot) AS bad, count_if(NOT is_bot) AS not_bad,
                               count_if(is_bot IS NULL) AS no_answer
                        FROM ipintel_curated.ip_intelligence GROUP BY 1 ORDER BY 1""")
    reasons = c.rows("""SELECT vendor, bot_reason AS reason, count(*) AS ips FROM ipintel_curated.ip_intelligence
                        WHERE is_bot GROUP BY 1, 2 ORDER BY 3 DESC""")
    per_ip = c.rows(f"""WITH p AS (
      SELECT ip_address,
             count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND is_bot IS NOT NULL) AS answered,
             bool_or(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND coalesce(is_bot, false)) AS bad,
             bool_or(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND coalesce(is_bot, false)
                     AND bot_reason NOT IN ({proxy_only})) AS bad_strict
      FROM ipintel_curated.ip_intelligence GROUP BY 1)
    SELECT count(*) AS ips, count_if(answered > 0) AS answered_ips, count_if(bad) AS bad_ips,
           count_if(bad_strict) AS bad_ips_strict, count_if(bad AND NOT bad_strict) AS proxy_vpn_only_ips
    FROM p""")[0]
    return {"as_of": now, "standard": "is_bot = bad signal (owner decision 19 Sep 2026): FraudLogix latest decision "
            "FLAGGED for any reason; proxycheck.io proxy, VPN, TOR, datacenter, compromised, scraper, any proxy/threat "
            "type, cloud network or risk 67+; IP2Proxy listed. An IP is bad if FraudLogix or proxycheck.io says so.",
            "proxy_only_reasons": list(PROXY_ONLY), "per_ip": per_ip, "vendors": vendors,
            "reasons": reasons, "truth_test": TRUTH_TEST}


def build():
    """Return {name: object} for every file that can be built."""
    now = c.now_iso()
    files = {}
    for name in STATIC:
        key = "%s/static/%s" % (APP, name)
        if c.s3_exists(key):
            files[name] = c.s3_get_json(key)
    files["coverage.json"] = c.s3_get_json("%s/serving/%s/enrichment_coverage.json" % (c.PREFIX, c.DB))
    files["geo_accuracy.json"] = c.s3_get_json("%s/serving/%s/geo_accuracy.json" % (c.PREFIX, c.DB))
    cov = c.rows("""WITH ans AS (SELECT ip_address, count_if(is_proxy IS NOT NULL) n, count_if(vendor = 'proxycheck_io') pc
                                 FROM ipintel_curated.ip_intelligence GROUP BY 1)
                    SELECT count(*) AS addresses, count_if(n > 0) AS with_proxy_answer, count_if(pc > 0) AS with_proxycheck
                    FROM ans""")[0]
    files["proxy_coverage.json"] = dict({"as_of": now}, **cov)
    try:   # completeness of the two tables; never blocks the export
        files["proxy_coverage.json"]["completeness"] = c.s3_get_json(completeness.KEY)
    except Exception:
        pass
    try:   # never blocks the export
        files["bad_signals.json"] = bad_signals(now)
    except Exception:
        pass
    try:   # traffic_analytics.json (analytics_mart); never blocks the export
        import analytics_mart
        files["traffic_analytics.json"] = analytics_mart.build()
    except Exception:
        pass
    for t in ("vendor_overview_geo", "vendor_overview_proxy"):
        files[t + ".json"] = {"as_of": now, "table": "unified." + t,
                              "rows": c.rows("SELECT * FROM ipintel_curated.%s ORDER BY vendor" % t)}
    files["manifest.json"] = {"as_of": now, "files": sorted(files) + ["manifest.json"]}
    return files


def run(trigger="after-publish"):
    files = build()
    for name, obj in files.items():
        if name != "manifest.json":
            c.s3_put_json("%s/%s" % (APP, name), obj)
    c.s3_put_json("%s/manifest.json" % APP, files["manifest.json"])   # last: marks a complete set
    missing = sorted(set(ALL) - set(files))
    result = {"at": c.now_iso(), "trigger": trigger, "files": sorted(files), "missing": missing,
              "status": "complete" if not missing else "missing " + ", ".join(missing)}
    c.update_item("app", "export", **result)
    if missing:
        c.alert("IP app snapshot incomplete", "Written to s3://%s/%s/ without: %s" % (c.BUCKET, APP, ", ".join(missing)))
    return result
