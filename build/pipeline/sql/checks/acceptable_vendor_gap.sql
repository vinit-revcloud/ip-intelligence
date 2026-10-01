-- Read only. How many IPs still have no acceptable proxy answer?
-- Acceptable = FraudLogix decided, or proxycheck.io answered. IP2Proxy PX12 does not count: it only lists
-- known proxies, so its silence is not an answer.
WITH ans AS (
  SELECT ip_address,
         count_if(vendor = 'fraudlogix_tune' AND has_answer) AS fl,
         count_if(vendor = 'proxycheck_io' AND has_answer) AS pc,
         count_if(vendor = 'ip2proxy_px12' AND has_answer) AS px
  FROM ipintel_curated.ip_intelligence_analytics GROUP BY ip_address),
seen AS (SELECT ip_address, max(last_seen) AS last_seen FROM ipintel_curated.ip_occurrences GROUP BY ip_address),
j AS (
  SELECT s.ip_address, s.last_seen, coalesce(a.fl, 0) AS fl, coalesce(a.pc, 0) AS pc, coalesce(a.px, 0) AS px,
         CASE WHEN s.last_seen >= date_add('day', -7, current_date) THEN '1: last 7 days'
              WHEN s.last_seen >= date_add('day', -30, current_date) THEN '2: 8-30 days'
              WHEN s.last_seen >= date_add('day', -90, current_date) THEN '3: 31-90 days'
              WHEN s.last_seen >= date_add('day', -365, current_date) THEN '4: 91-365 days'
              WHEN s.last_seen IS NOT NULL THEN '5: over a year'
              ELSE '6: never seen in a base table' END AS age
  FROM seen s LEFT JOIN ans a ON a.ip_address = s.ip_address)
SELECT age,
       count(*) AS ips,
       count_if(fl > 0 OR pc > 0) AS acceptable_answer,
       count_if(fl = 0 AND pc = 0) AS missing,
       count_if(fl = 0 AND pc = 0 AND px > 0) AS missing_but_px12_only,
       count_if(fl > 0) AS fraudlogix,
       count_if(pc > 0) AS proxycheck
FROM j GROUP BY age
UNION ALL
SELECT '0: TOTAL', count(*), count_if(fl > 0 OR pc > 0), count_if(fl = 0 AND pc = 0),
       count_if(fl = 0 AND pc = 0 AND px > 0), count_if(fl > 0), count_if(pc > 0)
FROM j
ORDER BY 1
