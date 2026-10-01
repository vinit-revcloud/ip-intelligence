SELECT substr(created_at,1,10) d, 'ip_geo' t, count(*) n FROM ipintel_curated.ip_geo WHERE created_at >= '2026-08-15' GROUP BY 1
UNION ALL SELECT substr(created_at,1,10), 'ip_intelligence', count(*) FROM ipintel_curated.ip_intelligence WHERE created_at >= '2026-08-15' GROUP BY 1
UNION ALL SELECT substr(created_at,1,10), 'ip_geo_updated', count(*) FROM ipintel_curated.ip_geo WHERE updated_at >= '2026-09-12' AND substr(updated_at,1,10) <> substr(created_at,1,10) GROUP BY 1
UNION ALL SELECT cast(first_seen AS varchar), 'new_ips_first_seen', count(DISTINCT ip_address) FROM ipintel_curated.ip_occurrences WHERE first_seen >= date '2026-08-15' GROUP BY 1
ORDER BY 2,1
