SELECT 'geo' AS t, vendor, count(*) AS rows_, count_if(state IS NOT NULL OR city IS NOT NULL) AS answered FROM ipintel_curated.ip_geo GROUP BY vendor
UNION ALL
SELECT 'intel', vendor, count(*), count_if(is_proxy IS NOT NULL) FROM ipintel_curated.ip_intelligence GROUP BY vendor
UNION ALL
SELECT 'geo_analytics', 'all', count(*), count(DISTINCT ip_address) FROM ipintel_curated.ip_geo_analytics
ORDER BY 1, 2
