"""Read only on source tables. Tests the proxycheck.io Scraper type as a bot rule on paying IPs (known humans).
Uses a temporary stg_ table that is removed at the end."""
import os, sys
os.environ["AWS_PROFILE"] = "ipintel-builder"; os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import common as c
st = c.Staging("step2_scraper")
try:
    truth = st.ctas("truth", """
SELECT s.ip, bool_or(l.expected_revenue > 0) AS paid, bool_or(CAST(l.fake AS varchar) IN ('true', '1', 't')) AS fake
FROM (SELECT trim(session_ip) AS ip, session_id FROM unified.unified_session_summary
      WHERE regexp_like(trim(session_ip), '^\d{1,3}(\.\d{1,3}){3}$')) s
JOIN sampledb.revenue_leads_plus l ON l.utm_content = s.session_id
GROUP BY 1 HAVING bool_or(l.expected_revenue > 0) OR bool_or(CAST(l.fake AS varchar) IN ('true', '1', 't'))""")
    for r in c.rows(f"""
SELECT count(*) AS pc_rows, count_if(is_scraper) AS scraper_rows, count_if(is_scraper AND NOT is_bot) AS scraper_not_yet_bot,
       count_if(is_scraper AND ip_address IN (SELECT ip FROM {truth} WHERE paid)) AS paying_scraper,
       (SELECT count(*) FROM {truth} t JOIN unified.ip_intelligence i ON i.ip_address = t.ip AND i.vendor = 'proxycheck_io' WHERE t.paid) AS paying_with_pc,
       count_if(is_scraper AND ip_address IN (SELECT ip FROM {truth} WHERE fake)) AS fake_scraper
FROM unified.ip_intelligence WHERE vendor = 'proxycheck_io'""", timeout_s=600):
        print(r)
finally:
    st.cleanup()
