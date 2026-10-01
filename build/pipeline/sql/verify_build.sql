SELECT 'ip_geo' AS t,
  (SELECT count(*) FROM ipintel_curated.ip_geo) AS new_rows,
  (SELECT count(*) FROM unified.ip_geo) AS unified_rows,
  (SELECT count_if(n > 1) FROM (SELECT count(*) n FROM ipintel_curated.ip_geo GROUP BY ip_address, vendor)) AS dup_pairs
UNION ALL SELECT 'ip_intelligence',
  (SELECT count(*) FROM ipintel_curated.ip_intelligence), (SELECT count(*) FROM unified.ip_intelligence),
  (SELECT count_if(n > 1) FROM (SELECT count(*) n FROM ipintel_curated.ip_intelligence GROUP BY ip_address, vendor))
UNION ALL SELECT 'ip_geo_analytics',
  (SELECT count(*) FROM ipintel_curated.ip_geo_analytics), (SELECT count(*) FROM unified.ip_geo_analytics),
  (SELECT count_if(n > 1) FROM (SELECT count(*) n FROM ipintel_curated.ip_geo_analytics GROUP BY ip_address, vendor))
UNION ALL SELECT 'ip_intelligence_analytics',
  (SELECT count(*) FROM ipintel_curated.ip_intelligence_analytics), (SELECT count(*) FROM unified.ip_intelligence_analytics),
  (SELECT count_if(n > 1) FROM (SELECT count(*) n FROM ipintel_curated.ip_intelligence_analytics GROUP BY ip_address, vendor))
UNION ALL SELECT 'vendor_overview_geo',
  (SELECT count(*) FROM ipintel_curated.vendor_overview_geo), (SELECT count(*) FROM unified.vendor_overview_geo), 0
UNION ALL SELECT 'vendor_overview_proxy',
  (SELECT count(*) FROM ipintel_curated.vendor_overview_proxy), (SELECT count(*) FROM unified.vendor_overview_proxy), 0
