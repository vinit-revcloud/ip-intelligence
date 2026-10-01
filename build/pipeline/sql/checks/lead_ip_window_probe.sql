WITH s AS (SELECT session_id, session_ip, session_date FROM unified.unified_session_summary
           WHERE session_date BETWEEN date '2026-09-16' - interval '90' day AND date '2026-09-16' - interval '7' day AND nullif(session_ip,'') IS NOT NULL),
l AS (SELECT utm_content, expected_revenue, date_pst FROM sampledb.revenue_leads_plus WHERE date_pst >= date '2026-09-16' - interval '90' day),
j AS (SELECT s.session_date, s.session_ip, l.expected_revenue FROM s JOIN l ON l.utm_content = s.session_id AND l.date_pst >= s.session_date),
d AS (SELECT session_date, count(DISTINCT session_ip) lead_ips, count(DISTINCT CASE WHEN expected_revenue > 0 THEN session_ip END) rev_ips FROM j GROUP BY 1)
SELECT session_date, lead_ips, rev_ips, sum(rev_ips) OVER (ORDER BY session_date DESC) cum_rev, sum(lead_ips) OVER (ORDER BY session_date DESC) cum_lead
FROM d ORDER BY session_date DESC
