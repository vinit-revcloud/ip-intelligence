"""One-time: remove the vendors that only ever ran in the 8-10 September benchmark.

Approved by the owner on 14 September 2026: MaxMind GeoLite2, DB-IP and GeoJS (location) and the
published cloud ranges (authoritative_lists) answered 2,105 addresses once and never again. Their rows
are removed from the project's own ipintel_curated tables so every row comes from a vendor the daily
system runs. ipinfo.io, ipwho.is and proxycheck.io answers from that period are real answers from vendors
that still run, and are kept.

Runs as ipintel-builder in ipintel_etl. Touches only ipintel_curated and the project S3 folder. Every row
removed is first written as JSON under ip-intelligence/archive/benchmark-vendors-2026-09-14/.

usage: AWS_PROFILE=ipintel-builder python remove_benchmark_vendors.py
"""
import os
import sys

os.environ.setdefault("AWS_PROFILE", "ipintel-builder")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import boto3  # noqa: E402

import apply  # noqa: E402
import common as c  # noqa: E402
import resolved  # noqa: E402
import vendors as v  # noqa: E402

GEO_REMOVED = ["maxmind_geolite2", "dbip_combined", "geojs_io"]
INTEL_REMOVED = ["authoritative_lists"]
ARCHIVE = "s3://%s/%s/archive/benchmark-vendors-2026-09-14" % (c.BUCKET, c.PREFIX)
RUN_ID = "remove-benchmark-vendors-20260914"
NOW = c.now_iso()


def say(msg):
    print(msg, flush=True)


def counts():
    return {r["t"] + ":" + r["vendor"]: r["n"] for r in c.rows(f"""
SELECT 'ip_geo' AS t, vendor, count(*) AS n FROM {c.DB}.ip_geo GROUP BY 2
UNION ALL SELECT 'ip_geo_analytics', vendor, count(*) FROM {c.DB}.ip_geo_analytics GROUP BY 2
UNION ALL SELECT 'ip_intelligence', vendor, count(*) FROM {c.DB}.ip_intelligence GROUP BY 2
UNION ALL SELECT 'ip_intelligence_analytics', vendor, count(*) FROM {c.DB}.ip_intelligence_analytics GROUP BY 2
UNION ALL SELECT 'vendor_overview_geo', vendor, count(*) FROM {c.DB}.vendor_overview_geo GROUP BY 2
UNION ALL SELECT 'vendor_overview_proxy', vendor, count(*) FROM {c.DB}.vendor_overview_proxy GROUP BY 2""")}


def main():
    geo_in, intel_in = apply._in_list(GEO_REMOVED), apply._in_list(INTEL_REMOVED)
    before = counts()
    say("before: %s" % before)

    staging = c.Staging(RUN_ID)
    try:
        # 1. the addresses whose analytics depended on a removed vendor
        affected = staging.ctas("affected", f"""
SELECT DISTINCT ip_address FROM {c.DB}.ip_geo WHERE vendor IN ({geo_in})
UNION SELECT DISTINCT ip_address FROM {c.DB}.ip_intelligence WHERE vendor IN ({intel_in})""")
        say("affected addresses: %s" % c.scalar("SELECT count(*) FROM %s" % affected))

        # 2. backups, before anything is removed
        c.delete_prefix("%s/archive/benchmark-vendors-2026-09-14/" % c.PREFIX)
        for name, sql in [
            ("ip_geo", f"SELECT * FROM {c.DB}.ip_geo WHERE vendor IN ({geo_in})"),
            ("ip_geo_analytics", f"SELECT * FROM {c.DB}.ip_geo_analytics WHERE ip_address IN (SELECT ip_address FROM {affected})"),
            ("ip_intelligence", f"SELECT * FROM {c.DB}.ip_intelligence WHERE vendor IN ({intel_in})"),
            ("ip_intelligence_analytics", f"SELECT * FROM {c.DB}.ip_intelligence_analytics WHERE vendor IN ({intel_in}) OR known_infrastructure OR infrastructure_list IS NOT NULL"),
            ("vendor_overview_geo", f"SELECT * FROM {c.DB}.vendor_overview_geo"),
            ("vendor_overview_proxy", f"SELECT * FROM {c.DB}.vendor_overview_proxy"),
        ]:
            c.run(f"UNLOAD ({sql}) TO '{ARCHIVE}/{name}/' WITH (format = 'JSON', compression = 'NONE')")
            say("backed up %s" % name)

        # 3. remove the rows
        c.run(f"DELETE FROM {c.DB}.ip_geo WHERE vendor IN ({geo_in})")
        c.run(f"DELETE FROM {c.DB}.ip_intelligence WHERE vendor IN ({intel_in})")
        c.run(f"DELETE FROM {c.DB}.ip_intelligence_analytics WHERE vendor IN ({intel_in})")
        # Without the published ranges nothing is known infrastructure, so the verdict follows the flag alone:
        # the same result refresh_intel_analytics gives when no authoritative_lists row exists.
        c.run(f"""UPDATE {c.DB}.ip_intelligence_analytics
SET known_infrastructure = false, infrastructure_list = NULL,
    verdict_class = CASE WHEN NOT has_answer THEN 'no_answer' WHEN flagged THEN 'unconfirmed_flag' ELSE 'agreed_not_flagged' END
WHERE known_infrastructure OR infrastructure_list IS NOT NULL""")
        c.run(f"DELETE FROM {c.DB}.ip_geo_analytics WHERE ip_address IN (SELECT ip_address FROM {affected})")
        apply.refresh_geo_analytics(affected)
        c.run(f"DELETE FROM {c.DB}.vendor_overview_geo WHERE vendor IN ({geo_in})")
        # Every proxy scorecard row was computed on the benchmark pool. The daily jobs rewrite it as soon as
        # 1,000 addresses have been asked of every running risk vendor (the first proxycheck backfill).
        c.run(f"DELETE FROM {c.DB}.vendor_overview_proxy")
        say("rows removed and analytics recomputed")

        # 4. switch the vendors off in the registry, so no job or page treats them as running
        reg = boto3.Session(profile_name="ipintel-builder", region_name="us-west-2").resource("dynamodb").Table("ipintel-sources")
        for vid in GEO_REMOVED + INTEL_REMOVED:
            reg.update_item(Key={"id": vid}, UpdateExpression="SET enabled = :f, note = :n, updated_at = :u",
                            ExpressionAttributeValues={":f": False, ":u": NOW,
                                                       ":n": "Switched off 14 Sep 2026: only ever ran in the benchmark. "
                                                             "Rows removed; copy in ip-intelligence/archive/benchmark-vendors-2026-09-14/"})
        say("registry updated")

        # 5. scorecards, exports and resolved answers from running vendors only
        items = reg.scan()["Items"]
        enabled = lambda cap: sorted(i["id"] for i in items if i.get("enabled") and cap in (i.get("capabilities") or []))
        geo_pool, geo_done = apply.refresh_geo_scorecard(staging, v.scoreable(enabled("geo")))
        proxy_pool, proxy_done = apply.refresh_proxy_scorecard(staging, enabled("risk"))
        apply.export_scorecards()
        changed, total = resolved.refresh(staging, NOW)
        say("geo scorecard pool %s recalculated=%s; proxy pool %s recalculated=%s; resolved changed %s of %s"
            % (geo_pool, geo_done, proxy_pool, proxy_done, changed, total))
    finally:
        staging.cleanup()

    after = counts()
    say("after: %s" % after)
    left = {k: n for k, n in after.items() if k.split(":")[1] in GEO_REMOVED + INTEL_REMOVED}
    say("rows left for removed vendors: %s" % (left or "none"))
    for check in resolved.checks():
        say("%s %s %s" % ("PASS" if check["passed"] else "FAIL", check["name"], check["detail"] or ""))


if __name__ == "__main__":
    main()
