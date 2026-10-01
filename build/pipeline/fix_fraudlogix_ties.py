"""One-off (21 Sep 2026): re-read FraudLogix's latest decision, with the fixed tie-break, for every IP whose latest
decided clicks share one timestamp but disagree. Uses the pipeline's own steps (vendors.fraudlogix_intel_sql,
apply.merge_intel / refresh_intel_analytics / refresh_flag_columns). Writes ipintel_curated only; unified follows at
the next publish. Rollback: the snapshot ids printed first."""
import os
import sys
os.environ["AWS_PROFILE"] = "ipintel-builder"
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
import apply
import common as c
import vendors as v

print("rollback snapshots: intel", apply.latest_snapshot("ip_intelligence"),
      "analytics", apply.latest_snapshot("ip_intelligence_analytics"))
st = c.Staging(c.new_run_id("fl-ties"))
try:
    targets = st.ctas("targets", """
WITH d AS (SELECT ip, datetime, access_control_decision AS dec, coalesce(access_control_reason_code, '') AS rsn
           FROM raw.raw_tune_clicks WHERE coalesce(access_control_decision, '') <> ''),
last AS (SELECT ip, max(datetime) AS at FROM d GROUP BY ip)
SELECT d.ip AS ip_address FROM d JOIN last l ON l.ip = d.ip AND l.at = d.datetime
GROUP BY d.ip HAVING count(DISTINCT d.dec || '|' || d.rsn) > 1""")
    n = c.scalar("SELECT count(*) FROM %s" % targets)
    print("IPs with a tie at their latest decision:", n)
    if n:
        stg = st.ctas("fl", v.fraudlogix_intel_sql(targets, ""))
        print("plan:", apply.plan_changes(stg, "ip_intelligence", apply.INTEL_FIELDS))
        apply.merge_intel(stg)
        apply.refresh_intel_analytics(stg)
        print("flag columns changed:", apply.refresh_flag_columns())
        print(apply.flag_column_checks())
finally:
    st.cleanup()
