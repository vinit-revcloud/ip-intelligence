WITH s AS (SELECT session_id, session_ip, session_date FROM unified.unified_session_summary
           WHERE session_date BETWEEN date '2026-06-18' AND date '2026-09-09' AND nullif(session_ip,'') IS NOT NULL),
l AS (SELECT utm_content, date_pst FROM sampledb.revenue_leads_plus WHERE date_pst >= date '2026-06-18'),
ips AS (SELECT DISTINCT s.session_ip ip FROM s JOIN l ON l.utm_content = s.session_id AND l.date_pst >= s.session_date)
SELECT ip FROM ips WHERE NOT EXISTS (SELECT 1 FROM ipintel_curated.ip_intelligence i WHERE i.ip_address = ips.ip AND i.vendor = 'proxycheck_io')
