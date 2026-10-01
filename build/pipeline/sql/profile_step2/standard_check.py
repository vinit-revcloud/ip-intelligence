"""Read only on source tables (temporary stg_ table removed at the end). Step 2 standard: counts per vendor,
bad IPs per IP, and how many paying / fake IPs the standard marks."""
import os, sys
os.environ["AWS_PROFILE"] = "ipintel-builder"; os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import common as c
for r in c.rows("""SELECT vendor, count(*) n, count_if(is_bot) bad, count_if(NOT is_bot) not_bad, count_if(is_bot IS NULL) empty
                   FROM ipintel_curated.ip_intelligence GROUP BY 1 ORDER BY 1"""):
    print(r)
print(c.rows("""WITH p AS (SELECT ip_address, bool_or(vendor IN ('fraudlogix_tune','proxycheck_io') AND is_bot) bad,
                   count_if(vendor IN ('fraudlogix_tune','proxycheck_io') AND is_bot IS NOT NULL) answered FROM ipintel_curated.ip_intelligence GROUP BY 1)
                SELECT count(*) ips, count_if(answered > 0) answered, count_if(bad) bad_ips FROM p""")[0])
st = c.Staging("step2_standard")
try:
    truth = st.ctas("truth", """
SELECT s.ip, bool_or(l.expected_revenue > 0) AS paid, bool_or(CAST(l.fake AS varchar) IN ('true', '1', 't')) AS fake
FROM (SELECT trim(session_ip) AS ip, session_id FROM unified.unified_session_summary
      WHERE regexp_like(trim(session_ip), '^\d{1,3}(\.\d{1,3}){3}$')) s
JOIN sampledb.revenue_leads_plus l ON l.utm_content = s.session_id
GROUP BY 1 HAVING bool_or(l.expected_revenue > 0) OR bool_or(CAST(l.fake AS varchar) IN ('true', '1', 't'))""")
    for r in c.rows(f"""WITH p AS (SELECT ip_address, bool_or(vendor IN ('fraudlogix_tune','proxycheck_io') AND is_bot) bad
                        FROM ipintel_curated.ip_intelligence WHERE ip_address IN (SELECT ip FROM {truth}) GROUP BY 1)
      SELECT count_if(t.paid) paying, count_if(t.paid AND p.bad) paying_bad, count_if(t.fake) fake, count_if(t.fake AND p.bad) fake_bad
      FROM {truth} t LEFT JOIN p ON p.ip_address = t.ip"""):
        print(r)
    for r in c.rows(f"""SELECT i.bot_reason, count(DISTINCT i.ip_address) paying_ips FROM ipintel_curated.ip_intelligence i
      WHERE i.is_bot AND i.vendor IN ('fraudlogix_tune','proxycheck_io') AND i.ip_address IN (SELECT ip FROM {truth} WHERE paid)
      GROUP BY 1 ORDER BY 2 DESC LIMIT 12"""):
        print(r)
finally:
    st.cleanup()
