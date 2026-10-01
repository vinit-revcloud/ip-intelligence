WITH k AS (
  SELECT ip_address, count_if(has_answer) AS answered, count_if(has_answer AND flagged) AS flagged_by,
         max(CASE WHEN vendor = 'proxycheck_io' THEN 1 ELSE 0 END) AS pc
  FROM ipintel_curated.ip_intelligence_analytics GROUP BY ip_address)
SELECT * FROM (SELECT 'flagged_unconfirmed' AS kind, ip_address FROM k WHERE pc = 0 AND flagged_by > 0 AND flagged_by = answered LIMIT 1)
UNION ALL SELECT * FROM (SELECT 'clean', ip_address FROM k WHERE pc = 0 AND answered > 0 AND flagged_by = 0 LIMIT 1)
UNION ALL SELECT * FROM (SELECT 'with_proxycheck', ip_address FROM k WHERE pc = 1 AND answered >= 2 LIMIT 1)
