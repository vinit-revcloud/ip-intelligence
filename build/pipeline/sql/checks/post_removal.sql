SELECT 'overview_geo' AS k, array_join(array_agg(vendor || ':' || CAST(ips_tested AS varchar) || ':' || as_of_date), ' ') AS v FROM ipintel_curated.vendor_overview_geo
UNION ALL SELECT 'overview_proxy_rows', CAST(count(*) AS varchar) FROM ipintel_curated.vendor_overview_proxy
UNION ALL SELECT 'resolved_published_range', CAST(count_if(proxy_status = 'confirmed_by_published_range') AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'resolved_decided_by_removed', CAST(count_if(geo_decided_by IN ('maxmind_geolite2','dbip_combined','geojs_io') OR strpos(geo_agreeing_vendors, 'maxmind') > 0 OR strpos(geo_agreeing_vendors, 'dbip') > 0 OR strpos(proxy_agreeing_vendors, 'authoritative') > 0) AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'resolved_last_update', max(updated_at) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'intel_analytics_known_infra', CAST(count_if(known_infrastructure OR infrastructure_list IS NOT NULL OR verdict_class = 'confirmed_by_published_range') AS varchar) FROM ipintel_curated.ip_intelligence_analytics
UNION ALL SELECT 'geo_analytics_removed_vendors', CAST(count_if(vendor IN ('maxmind_geolite2','dbip_combined','geojs_io')) AS varchar) FROM ipintel_curated.ip_geo_analytics
UNION ALL SELECT 'geo_analytics_rows', CAST(count(*) AS varchar) FROM ipintel_curated.ip_geo_analytics
UNION ALL SELECT 'staging_tables_left', CAST(count(*) AS varchar) FROM information_schema.tables WHERE table_schema = 'ipintel_curated' AND table_name LIKE 'stg_%'
