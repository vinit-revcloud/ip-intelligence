-- Read only. Is every IP in our data lake present AND usable in the two tables?
-- Usable risk  = at least one vendor row where is_proxy is filled, from FraudLogix or proxycheck.io
--                (IP2Proxy PX12 only lists known proxies, so its silence is not an answer).
-- Usable location = at least one vendor row with a state or a city.
WITH base AS (   -- every IP our pipeline has ever seen in a base table
  SELECT ip_address, max(last_seen) AS last_seen FROM ipintel_curated.ip_occurrences GROUP BY ip_address),
risk AS (
  SELECT ip_address,
         count(*) AS rows_any,
         count_if(is_proxy IS NOT NULL) AS rows_filled,
         count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND is_proxy IS NOT NULL) AS rows_acceptable,
         count_if(vendor = 'ip2proxy_px12' AND is_proxy IS NOT NULL) AS rows_px12
  FROM ipintel_curated.ip_intelligence GROUP BY ip_address),
geo AS (
  SELECT ip_address, count(*) AS rows_any,
         count_if(nullif(state, '') IS NOT NULL OR nullif(city, '') IS NOT NULL) AS rows_filled
  FROM ipintel_curated.ip_geo GROUP BY ip_address),
j AS (
  SELECT b.ip_address, b.last_seen,
         NOT (try_cast(split_part(b.ip_address, '.', 1) AS integer) IN (0, 10, 127) OR try_cast(split_part(b.ip_address, '.', 1) AS integer) >= 224 OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 100 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) BETWEEN 64 AND 127) OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 169 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) = 254) OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 172 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) BETWEEN 16 AND 31) OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 192 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) = 168) OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 192 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) = 0 AND try_cast(split_part(b.ip_address, '.', 3) AS integer) IN (0, 2)) OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 198 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) IN (18, 19)) OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 198 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) = 51 AND try_cast(split_part(b.ip_address, '.', 3) AS integer) = 100) OR (try_cast(split_part(b.ip_address, '.', 1) AS integer) = 203 AND try_cast(split_part(b.ip_address, '.', 2) AS integer) = 0 AND try_cast(split_part(b.ip_address, '.', 3) AS integer) = 113)) AS is_public,
         coalesce(r.rows_any, 0) AS risk_rows, coalesce(r.rows_filled, 0) AS risk_filled,
         coalesce(r.rows_acceptable, 0) AS risk_acceptable, coalesce(r.rows_px12, 0) AS risk_px12,
         coalesce(g.rows_any, 0) AS geo_rows, coalesce(g.rows_filled, 0) AS geo_filled
  FROM base b LEFT JOIN risk r ON r.ip_address = b.ip_address LEFT JOIN geo g ON g.ip_address = b.ip_address),
state AS (
  SELECT *,
    CASE WHEN NOT is_public THEN 'z: private or reserved (no vendor can answer)'
         WHEN risk_rows = 0 AND geo_rows = 0 THEN 'a: no row in either table'
         WHEN risk_rows = 0 THEN 'b: no risk row at all'
         WHEN risk_filled = 0 THEN 'c: risk rows exist but every field is empty'
         WHEN risk_acceptable = 0 AND risk_px12 > 0 THEN 'd: only IP2Proxy answered'
         WHEN risk_acceptable = 0 THEN 'e: no acceptable risk answer'
         WHEN geo_filled = 0 THEN 'f: risk fine, no usable location'
         ELSE 'g: complete' END AS completeness
  FROM j)
SELECT completeness,
       count(*) AS ips,
       count_if(last_seen >= date_add('day', -30, current_date)) AS seen_last_30d,
       count_if(last_seen >= date_add('day', -90, current_date)) AS seen_last_90d,
       min(last_seen) AS oldest_last_seen, max(last_seen) AS newest_last_seen
FROM state GROUP BY completeness ORDER BY completeness
