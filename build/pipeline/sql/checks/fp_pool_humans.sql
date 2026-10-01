WITH pool AS (
  SELECT ip_address FROM ipintel_curated.ip_intelligence_analytics
  WHERE vendor IN ('fraudlogix_tune', 'ip2proxy_px12', 'proxycheck_io') GROUP BY ip_address HAVING count(DISTINCT vendor) = 3),
humans AS (SELECT DISTINCT ip_address FROM ipintel_curated.qualified_lead_ips)
SELECT (SELECT count(*) FROM pool) AS pool, count(*) AS pool_humans,
       count_if(i.vendor = 'fraudlogix_tune' AND i.is_bot) AS fraudlogix_bot_on_humans,
       count_if(i.vendor = 'fraudlogix_tune' AND i.is_bot IS NOT NULL) AS fraudlogix_answered_humans,
       count_if(a.vendor = 'fraudlogix_tune' AND a.flagged) AS fraudlogix_any_flag_on_humans,
       count_if(a.vendor = 'proxycheck_io' AND a.flagged) AS proxycheck_any_flag_on_humans
FROM pool p JOIN humans h ON h.ip_address = p.ip_address
JOIN ipintel_curated.ip_intelligence_analytics a ON a.ip_address = p.ip_address
JOIN ipintel_curated.ip_intelligence i ON i.ip_address = a.ip_address AND i.vendor = a.vendor
