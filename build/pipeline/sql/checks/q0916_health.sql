SELECT 'geo_dupes' AS k, count(*) AS n FROM (SELECT ip_address, vendor FROM ipintel_curated.ip_geo GROUP BY 1,2 HAVING count(*)>1)
UNION ALL SELECT 'intel_dupes', count(*) FROM (SELECT ip_address, vendor FROM ipintel_curated.ip_intelligence GROUP BY 1,2 HAVING count(*)>1)
UNION ALL SELECT 'geo_not_resolved', count(*) FROM (SELECT DISTINCT ip_address FROM ipintel_curated.ip_geo) g WHERE NOT EXISTS (SELECT 1 FROM ipintel_curated.ip_resolved r WHERE r.ip_address=g.ip_address)
UNION ALL SELECT 'intel_not_resolved', count(*) FROM (SELECT DISTINCT ip_address FROM ipintel_curated.ip_intelligence) g WHERE NOT EXISTS (SELECT 1 FROM ipintel_curated.ip_resolved r WHERE r.ip_address=g.ip_address)
UNION ALL SELECT 'unified_pc_rows', count(*) FROM unified.ip_intelligence WHERE vendor='proxycheck_io'
UNION ALL SELECT 'curated_pc_rows', count(*) FROM ipintel_curated.ip_intelligence WHERE vendor='proxycheck_io';
