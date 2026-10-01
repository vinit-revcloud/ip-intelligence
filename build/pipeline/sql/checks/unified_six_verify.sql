SELECT 'ip_geo' t, (SELECT count(*) FROM unified.ip_geo) u, (SELECT count(*) FROM ipintel_curated.ip_geo) c
UNION ALL SELECT 'ip_intelligence', (SELECT count(*) FROM unified.ip_intelligence), (SELECT count(*) FROM ipintel_curated.ip_intelligence)
UNION ALL SELECT 'ip_geo_analytics', (SELECT count(*) FROM unified.ip_geo_analytics), (SELECT count(*) FROM ipintel_curated.ip_geo_analytics)
UNION ALL SELECT 'ip_intelligence_analytics', (SELECT count(*) FROM unified.ip_intelligence_analytics), (SELECT count(*) FROM ipintel_curated.ip_intelligence_analytics)
UNION ALL SELECT 'vendor_overview_geo', (SELECT count(*) FROM unified.vendor_overview_geo), (SELECT count(*) FROM ipintel_curated.vendor_overview_geo)
UNION ALL SELECT 'vendor_overview_proxy', (SELECT count(*) FROM unified.vendor_overview_proxy), (SELECT count(*) FROM ipintel_curated.vendor_overview_proxy)
UNION ALL SELECT 'overview_geo vendors+as_of: ' || (SELECT array_join(array_agg(vendor || '@' || as_of_date ORDER BY vendor), ' ') FROM unified.vendor_overview_geo), null, null
UNION ALL SELECT 'overview_proxy vendors+as_of: ' || (SELECT array_join(array_agg(vendor || '@' || as_of_date ORDER BY vendor), ' ') FROM unified.vendor_overview_proxy), null, null
UNION ALL SELECT 'geo_analytics vendors: ' || (SELECT array_join(array_agg(DISTINCT vendor), ' ') FROM unified.ip_geo_analytics), null, null
