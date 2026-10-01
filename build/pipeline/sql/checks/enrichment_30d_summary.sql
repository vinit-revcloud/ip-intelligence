WITH occ AS (
  SELECT ip_address, min(first_seen) first_seen, max(last_seen) last_seen, array_join(array_agg(DISTINCT base_table), ',') tables
  FROM ipintel_curated.ip_occurrences GROUP BY ip_address),
w AS (SELECT o.*, r.geo_status, r.proxy_status, r.proxy_decided_by
      FROM occ o JOIN ipintel_curated.ip_resolved r ON r.ip_address = o.ip_address
      WHERE o.last_seen >= date '2026-09-15' - interval '30' day)
SELECT 'all_30d' k, geo_status, proxy_status, count(*) n,
       sum(CASE WHEN proxy_decided_by LIKE '%proxycheck%' THEN 1 ELSE 0 END) pc,
       sum(CASE WHEN first_seen >= date '2026-09-15' - interval '30' day THEN 1 ELSE 0 END) first_seen_in_30d
FROM w GROUP BY 1,2,3 ORDER BY n DESC
