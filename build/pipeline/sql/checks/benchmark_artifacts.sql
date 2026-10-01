SELECT 'ip_geo' AS tbl, vendor, count(*) AS rows_, min(created_at) AS first_written, max(created_at) AS last_written FROM ipintel_curated.ip_geo GROUP BY vendor
UNION ALL SELECT 'ip_intelligence', vendor, count(*), min(created_at), max(created_at) FROM ipintel_curated.ip_intelligence GROUP BY vendor
UNION ALL SELECT 'ip_geo_analytics', vendor, count(*), NULL, NULL FROM ipintel_curated.ip_geo_analytics GROUP BY vendor
UNION ALL SELECT 'vendor_overview_geo', vendor, ips_tested, as_of_date, NULL FROM ipintel_curated.vendor_overview_geo
UNION ALL SELECT 'vendor_overview_proxy', vendor, ips_tested, as_of_date, NULL FROM ipintel_curated.vendor_overview_proxy
ORDER BY 1, 2
