WITH s AS (SELECT DISTINCT session_ip ip FROM unified.unified_session_summary
           WHERE session_date BETWEEN date '2026-09-16' - interval '90' day AND date '2026-09-16' - interval '7' day AND nullif(session_ip,'') IS NOT NULL)
SELECT count(*) ips, count_if(p.ip_address IS NULL) without_proxycheck
FROM s LEFT JOIN (SELECT DISTINCT ip_address FROM ipintel_curated.ip_intelligence WHERE vendor='proxycheck_io') p ON p.ip_address = s.ip
