
WITH have AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_intelligence WHERE vendor = 'proxycheck_io'),
concl AS (
  SELECT ip_address,
         count_if(has_answer) AS answered,
         count_if(has_answer AND flagged) AS flagged_by,
         count_if(has_answer AND flagged AND known_infrastructure) AS confirmed_by
  FROM ipintel_curated.ip_intelligence_analytics WHERE vendor <> 'proxycheck_io' GROUP BY ip_address),
seen AS (SELECT ip_address, max(last_seen) AS last_seen FROM ipintel_curated.ip_occurrences GROUP BY ip_address),
ranked AS (
  SELECT g.ip_address, g.created_at, s.last_seen,
         CASE WHEN coalesce(k.answered, 0) = 0 THEN 'no_answer'
              WHEN k.flagged_by > 0 AND k.flagged_by < k.answered THEN 'vendors_disagree'
              WHEN k.flagged_by > 0 AND k.confirmed_by = 0 THEN 'flagged_unconfirmed'
              WHEN k.flagged_by > 0 THEN 'flagged_confirmed'
              ELSE 'clean_by_vendors' END AS conclusion
  FROM ipintel_curated.ip_geo g
  LEFT JOIN have h ON h.ip_address = g.ip_address
  LEFT JOIN concl k ON k.ip_address = g.ip_address
  LEFT JOIN seen s ON s.ip_address = g.ip_address
  WHERE g.vendor = 'ip2location_db11' AND h.ip_address IS NULL)
SELECT conclusion, recent, count(*) AS n FROM (SELECT ip_address, conclusion, (last_seen >= date '2026-06-17') AS recent FROM ranked
ORDER BY (substr(created_at, 1, 10) = '2026-09-15') DESC,
         (conclusion IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed')) DESC,
         (last_seen >= date_add('day', -90, date '2026-09-15')) DESC NULLS LAST,
         CASE conclusion WHEN 'vendors_disagree' THEN 1 WHEN 'flagged_unconfirmed' THEN 2 WHEN 'no_answer' THEN 3 ELSE 4 END,
         last_seen DESC NULLS LAST, ip_address
LIMIT 49504) GROUP BY conclusion, recent