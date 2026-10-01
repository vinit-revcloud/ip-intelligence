WITH per_ip AS (
  SELECT ip_address,
         max(CASE WHEN vendor = 'proxycheck_io' THEN 1 ELSE 0 END) AS has_pc,
         sum(CASE WHEN vendor <> 'proxycheck_io' AND has_answer THEN 1 ELSE 0 END) AS answered,
         sum(CASE WHEN vendor <> 'proxycheck_io' AND has_answer AND flagged THEN 1 ELSE 0 END) AS flagged_by
  FROM ipintel_curated.ip_intelligence_analytics
  GROUP BY ip_address
),
cls AS (
  SELECT p.*, CASE WHEN answered = 0 THEN '1 no vendor answered'
                   WHEN flagged_by > 0 AND flagged_by < answered THEN '2 vendors disagree'
                   WHEN flagged_by > 0 THEN '3 flagged, not confirmed'
                   ELSE '4 all say clean' END AS conclusion,
         coalesce(pool.last_seen >= date '2026-06-16', false) AS seen_90d
  FROM per_ip p LEFT JOIN ipintel_curated.ip_pool pool ON pool.ip_address = p.ip_address
)
SELECT conclusion, seen_90d, count(*) AS ips, sum(has_pc) AS already_have_proxycheck, count(*) - sum(has_pc) AS still_to_ask
FROM cls GROUP BY 1, 2 ORDER BY 1, 2
