SELECT 'addresses' AS k, CAST(count(*) AS varchar) AS v FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'ip_geo rows', CAST(count(*) AS varchar) FROM ipintel_curated.ip_geo
UNION ALL SELECT 'ip_intelligence rows', CAST(count(*) AS varchar) FROM ipintel_curated.ip_intelligence
UNION ALL SELECT 'ip_occurrences rows', CAST(count(*) AS varchar) FROM ipintel_curated.ip_occurrences
UNION ALL SELECT 'proxycheck answers', CAST(count(*) AS varchar) FROM ipintel_curated.ip_intelligence WHERE vendor = 'proxycheck_io'
UNION ALL SELECT 'no conclusion', CAST(count_if(proxy_status IN ('no_answer','vendors_disagree','flagged_unconfirmed')) AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'no conclusion seen 90d', CAST(count_if(proxy_status IN ('no_answer','vendors_disagree','flagged_unconfirmed') AND last_seen >= date '2026-06-17') AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'clean_by_vendors', CAST(count_if(proxy_status = 'clean_by_vendors') AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'decided by proxycheck', CAST(count_if(proxy_decided_by = 'proxycheck_io') AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'flagged true', CAST(count_if(flagged) AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'geo agreed', CAST(count_if(geo_status = 'agreed') AS varchar) FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'queue rows', CAST(count(*) AS varchar) FROM ipintel_curated.proxycheck_queue
UNION ALL SELECT 'resolved last update', max(updated_at) FROM ipintel_curated.ip_resolved
