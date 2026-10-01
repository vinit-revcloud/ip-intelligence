WITH new AS (SELECT ip_address FROM ipintel_curated.ip_geo WHERE vendor = 'ip2location_db11' AND created_at >= '2026-09-15T00:00:00Z'),
touched AS (SELECT ip_address FROM ipintel_curated.ip_occurrences WHERE updated_at >= '2026-09-15T00:00:00Z' UNION SELECT ip_address FROM new)
SELECT (n.ip_address IS NOT NULL) AS new_today, (r.proxy_decided_by = 'proxycheck_io') AS proxycheck_answered,
       r.proxy_status, r.geo_status, count(*) AS addresses,
       count_if(i.created_at >= '2026-09-15T00:00:00Z') AS proxycheck_answered_today
FROM touched t JOIN ipintel_curated.ip_resolved r ON r.ip_address = t.ip_address
LEFT JOIN new n ON n.ip_address = t.ip_address
LEFT JOIN ipintel_curated.ip_intelligence i ON i.ip_address = t.ip_address AND i.vendor = 'proxycheck_io'
GROUP BY 1, 2, 3, 4 ORDER BY 5 DESC
