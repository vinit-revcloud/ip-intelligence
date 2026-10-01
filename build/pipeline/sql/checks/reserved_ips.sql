WITH r AS (
  SELECT ip_address, proxy_status, geo_status,
         CAST(split_part(ip_address, '.', 1) AS integer) AS o1, CAST(split_part(ip_address, '.', 2) AS integer) AS o2
  FROM ipintel_curated.ip_resolved)
SELECT CASE WHEN o1 = 0 THEN '0.0.0.0/8 this network'
            WHEN o1 = 10 THEN '10/8 private'
            WHEN o1 = 100 AND o2 BETWEEN 64 AND 127 THEN '100.64/10 carrier NAT'
            WHEN o1 = 127 THEN '127/8 loopback'
            WHEN o1 = 169 AND o2 = 254 THEN '169.254/16 link-local'
            WHEN o1 = 172 AND o2 BETWEEN 16 AND 31 THEN '172.16/12 private'
            WHEN o1 = 192 AND o2 = 168 THEN '192.168/16 private'
            WHEN o1 >= 224 THEN '224+/4 multicast/reserved'
       END AS range_, count(*) AS ips, count_if(proxy_status IN ('no_answer','vendors_disagree','flagged_unconfirmed')) AS in_backfill_queue,
       count_if(geo_status <> 'no_answer') AS with_location
FROM r GROUP BY 1 ORDER BY 2 DESC
