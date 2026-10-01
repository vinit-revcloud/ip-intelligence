SELECT 'proxy' AS side, proxy_status AS status, count(*) AS ips, count_if(last_seen >= date '2026-06-16') AS seen_90d FROM ipintel_curated.ip_resolved GROUP BY 2
UNION ALL
SELECT 'geo', geo_status, count(*), count_if(last_seen >= date '2026-06-16') FROM ipintel_curated.ip_resolved GROUP BY 2
UNION ALL
SELECT 'total', 'rows / distinct', count(*), count(DISTINCT ip_address) FROM ipintel_curated.ip_resolved
ORDER BY 1, 3 DESC
