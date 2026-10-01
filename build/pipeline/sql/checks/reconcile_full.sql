WITH src AS (
  SELECT DISTINCT ip FROM (
    SELECT CAST(session_ip AS varchar) AS ip FROM unified.unified_session_summary
    UNION ALL SELECT CAST(ip AS varchar) FROM raw.raw_tune_clicks)
  WHERE regexp_like(ip, '^(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])(\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])){3}$')
),
tune AS (SELECT DISTINCT CAST(ip AS varchar) AS ip FROM raw.raw_tune_clicks),
geo AS (SELECT ip_address, count_if(vendor = 'ip2location_db11') AS db11, count(*) AS n, count(DISTINCT vendor) AS v FROM ipintel_curated.ip_geo GROUP BY 1),
intel AS (SELECT ip_address, count_if(vendor = 'ip2proxy_px12') AS px12, count_if(vendor = 'fraudlogix_tune') AS fl, count(*) AS n, count(DISTINCT vendor) AS v FROM ipintel_curated.ip_intelligence GROUP BY 1),
ia AS (SELECT count(*) AS n FROM ipintel_curated.ip_intelligence_analytics),
occ AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_occurrences)
SELECT
  (SELECT count(*) FROM src) AS source_ips,
  (SELECT count(*) FROM src s LEFT JOIN geo g ON g.ip_address = s.ip WHERE coalesce(g.db11, 0) = 0) AS missing_ip2location,
  (SELECT count(*) FROM src s LEFT JOIN intel i ON i.ip_address = s.ip WHERE coalesce(i.px12, 0) = 0) AS missing_ip2proxy,
  (SELECT count(*) FROM tune t JOIN src s ON s.ip = t.ip LEFT JOIN intel i ON i.ip_address = t.ip WHERE coalesce(i.fl, 0) = 0) AS tune_ips_missing_fraudlogix,
  (SELECT count(*) FROM src s LEFT JOIN occ o ON o.ip_address = s.ip WHERE o.ip_address IS NULL) AS missing_occurrences,
  (SELECT count(*) FROM geo WHERE n <> v) AS geo_dup_ips,
  (SELECT count(*) FROM intel WHERE n <> v) AS intel_dup_ips,
  (SELECT count(*) FROM ipintel_curated.ip_intelligence) AS intel_rows,
  (SELECT n FROM ia) AS intel_analytics_rows,
  (SELECT count(*) FROM ipintel_curated.ip_intelligence i LEFT JOIN ipintel_curated.ip_intelligence_analytics a
     ON a.ip_address = i.ip_address AND a.vendor = i.vendor WHERE a.ip_address IS NULL) AS intel_rows_without_analytics
