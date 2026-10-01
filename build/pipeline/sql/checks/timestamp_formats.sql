WITH f AS (
  SELECT 'ip_geo' AS t, vendor, created_at AS v, 'created_at' AS col FROM ipintel_curated.ip_geo
  UNION ALL SELECT 'ip_geo', vendor, updated_at, 'updated_at' FROM ipintel_curated.ip_geo
  UNION ALL SELECT 'ip_intelligence', vendor, created_at, 'created_at' FROM ipintel_curated.ip_intelligence
  UNION ALL SELECT 'ip_intelligence', vendor, updated_at, 'updated_at' FROM ipintel_curated.ip_intelligence
  UNION ALL SELECT 'ip_occurrences', base_table, updated_at, 'updated_at' FROM ipintel_curated.ip_occurrences
  UNION ALL SELECT 'ip_resolved', 'all', updated_at, 'updated_at' FROM ipintel_curated.ip_resolved)
SELECT t, vendor, col,
       CASE WHEN v IS NULL THEN 'NULL'
            WHEN regexp_like(v, '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$') THEN 'ISO  YYYY-MM-DDTHH:MM:SSZ'
            WHEN regexp_like(v, '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+$') THEN 'SPACE YYYY-MM-DD HH:MM:SS.ffffff'
            ELSE 'OTHER' END AS format,
       count(*) AS rows_, min(v) AS example
FROM f GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4
