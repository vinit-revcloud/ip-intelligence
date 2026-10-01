SELECT reason, count(*) AS addresses FROM (
WITH new AS (
  SELECT ip_address FROM ipintel_curated.ip_geo WHERE vendor = 'ip2location_db11' AND created_at >= '2026-09-15T00:00:00Z'),
touched AS (
  SELECT ip_address FROM ipintel_curated.ip_occurrences WHERE updated_at >= '2026-09-15T00:00:00Z'
  UNION SELECT ip_address FROM new)
SELECT r.ip_address, CASE WHEN r.proxy_decided_by = 'proxycheck_io' THEN NULL
       WHEN NOT (NOT (try_cast(split_part(r.ip_address, '.', 1) AS integer) IN (0, 10, 127) OR try_cast(split_part(r.ip_address, '.', 1) AS integer) >= 224 OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 100 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) BETWEEN 64 AND 127) OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 169 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) = 254) OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 172 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) BETWEEN 16 AND 31) OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 192 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) = 168) OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 192 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) = 0 AND try_cast(split_part(r.ip_address, '.', 3) AS integer) IN (0, 2)) OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 198 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) IN (18, 19)) OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 198 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) = 51 AND try_cast(split_part(r.ip_address, '.', 3) AS integer) = 100) OR (try_cast(split_part(r.ip_address, '.', 1) AS integer) = 203 AND try_cast(split_part(r.ip_address, '.', 2) AS integer) = 0 AND try_cast(split_part(r.ip_address, '.', 3) AS integer) = 113))) THEN NULL
       WHEN n.ip_address IS NOT NULL THEN 'new_address'
       WHEN r.geo_status = 'no_answer' THEN 'no_location'
       WHEN r.proxy_status IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed') THEN r.proxy_status
       WHEN r.geo_status = 'vendors_disagree' THEN 'location_disagree'
  END AS reason
FROM touched t
JOIN ipintel_curated.ip_resolved r ON r.ip_address = t.ip_address
LEFT JOIN new n ON n.ip_address = t.ip_address) WHERE reason IS NOT NULL GROUP BY reason ORDER BY 2 DESC