"""Read only on source tables. Builds a short-lived staging table of truth IPs (stg_*, removed at the end),
then tests every bot signal against it. Output: x2_signal_vs_truth.out"""
import os, sys
os.environ["AWS_PROFILE"] = "ipintel-builder"; os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import common as c
sql = open(os.path.join(os.path.dirname(__file__), "x2_signal_vs_truth.sql"), encoding="utf-8").read()
st = c.Staging("step2_profile")
try:
    truth = st.ctas("truth", """
SELECT s.ip, bool_or(l.expected_revenue > 0) AS paid, bool_or(CAST(l.fake AS varchar) IN ('true', '1', 't')) AS fake
FROM (SELECT trim(session_ip) AS ip, session_id FROM unified.unified_session_summary
      WHERE regexp_like(trim(session_ip), '^\d{1,3}(\.\d{1,3}){3}$')) s
JOIN sampledb.revenue_leads_plus l ON l.utm_content = s.session_id
GROUP BY 1 HAVING bool_or(l.expected_revenue > 0) OR bool_or(CAST(l.fake AS varchar) IN ('true', '1', 't'))""")
    body = sql[sql.index("sb AS"):]
    body = body.replace("(SELECT ip FROM truth)", "(SELECT ip FROM %s)" % truth).replace("FROM truth t", "FROM %s t" % truth)
    q = "WITH sess AS (SELECT trim(session_ip) AS ip, session_id, is_bot_click FROM unified.unified_session_summary), " + body
    rows = c.rows(q, timeout_s=900)
    out = [" | ".join(str(v) for v in r.values()) for r in rows]
    print("columns:", " | ".join(rows[0].keys()) if rows else "")
    print("\n".join(out))
finally:
    st.cleanup()
