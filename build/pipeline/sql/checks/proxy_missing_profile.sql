-- Session IPs with no proxy answer from any vendor: what are they? (read only)
WITH ans AS (SELECT ip_address, count_if(is_proxy IS NOT NULL) n_ans FROM ipintel_curated.ip_intelligence GROUP BY 1),
known AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_resolved),
s AS (SELECT session_ip ip, max(session_date) last_date FROM unified.unified_session_summary
      WHERE nullif(session_ip,'') IS NOT NULL GROUP BY 1),
m AS (SELECT s.*, (k.ip_address IS NOT NULL) in_tables,
             CASE WHEN strpos(s.ip, ':') > 0 THEN 'ipv6'
                  WHEN NOT regexp_like(s.ip, '^\d{1,3}(\.\d{1,3}){3}$') THEN 'not_an_ip'
                  WHEN regexp_like(s.ip, '^(10\.|127\.|0\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|22[4-9]\.|2[3-5]\d\.)') THEN 'private_or_reserved'
                  ELSE 'public_ipv4' END AS kind
      FROM s LEFT JOIN ans a ON a.ip_address = s.ip LEFT JOIN known k ON k.ip_address = s.ip
      WHERE coalesce(a.n_ans, 0) = 0)
SELECT CASE WHEN last_date >= date '2026-06-18' THEN 'last 90 days' ELSE 'older' END AS period, kind, in_tables, count(*) ips
FROM m GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
