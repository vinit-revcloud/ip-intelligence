SELECT 'unified.ip_geo' t, count(*) n FROM unified.ip_geo
UNION ALL SELECT 'unified.ip_intelligence', count(*) FROM unified.ip_intelligence
UNION ALL SELECT 'unified.ip_geo_analytics', count(*) FROM unified.ip_geo_analytics
UNION ALL SELECT 'unified.ip_intelligence_analytics', count(*) FROM unified.ip_intelligence_analytics
UNION ALL SELECT 'curated.ip_intelligence', count(*) FROM ipintel_curated.ip_intelligence
UNION ALL SELECT 'curated.ip_resolved', count(*) FROM ipintel_curated.ip_resolved
