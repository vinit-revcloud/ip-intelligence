SELECT 'unified.ip_geo' k, count(*) a, count_if(vendor='proxycheck_io') b, count(*) - count(DISTINCT ip_address||'|'||vendor) c, max(updated_at) d FROM unified.ip_geo
UNION ALL SELECT 'curated.ip_geo', count(*), count_if(vendor='proxycheck_io'), count(*) - count(DISTINCT ip_address||'|'||vendor), max(updated_at) FROM ipintel_curated.ip_geo
UNION ALL SELECT 'unified.ip_intelligence', count(*), count_if(vendor='proxycheck_io'), count(*) - count(DISTINCT ip_address||'|'||vendor), max(updated_at) FROM unified.ip_intelligence
UNION ALL SELECT 'curated.ip_intelligence', count(*), count_if(vendor='proxycheck_io'), count(*) - count(DISTINCT ip_address||'|'||vendor), max(updated_at) FROM ipintel_curated.ip_intelligence
UNION ALL SELECT 'ip_resolved rows / distinct / flagged', count(*), count(DISTINCT ip_address), count_if(flagged), max(updated_at) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'queue:'||reason||':'||coalesce(outcome,'waiting'), count(*), null, null, max(answered_at) FROM ipintel_curated.proxycheck_queue GROUP BY reason, outcome
UNION ALL SELECT 'geo addresses without resolved', count(*), null, null, null FROM (SELECT DISTINCT ip_address FROM ipintel_curated.ip_geo) g LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address=g.ip_address WHERE r.ip_address IS NULL
UNION ALL SELECT 'occurrences max last_seen:'||base_table, count(DISTINCT ip_address), null, null, cast(max(last_seen) AS varchar) FROM ipintel_curated.ip_occurrences GROUP BY base_table
ORDER BY 1
