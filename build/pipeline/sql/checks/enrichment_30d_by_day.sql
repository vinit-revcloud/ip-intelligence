WITH occ AS (SELECT ip_address, min(first_seen) first_seen, max(last_seen) last_seen FROM ipintel_curated.ip_occurrences GROUP BY ip_address)
SELECT o.last_seen, count(*) ips,
  sum(CASE WHEN o.first_seen = o.last_seen THEN 1 ELSE 0 END) new_that_day,
  sum(CASE WHEN r.proxy_status IN ('no_answer','vendors_disagree','flagged_unconfirmed') THEN 1 ELSE 0 END) proxy_no_conclusion,
  sum(CASE WHEN r.proxy_decided_by LIKE '%proxycheck%' THEN 1 ELSE 0 END) proxycheck_answered,
  sum(CASE WHEN r.geo_status NOT IN ('agreed','single_vendor') THEN 1 ELSE 0 END) geo_not_agreed
FROM occ o JOIN ipintel_curated.ip_resolved r ON r.ip_address = o.ip_address
WHERE o.last_seen >= date '2026-09-15' - interval '30' day
GROUP BY 1 ORDER BY 1
