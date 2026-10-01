-- Read only. Inputs for the is_bot fill rules.
SELECT 'px12 usage/threat' AS k, split_part(fraud_reason, '/', 2) AS a, coalesce(nullif(split_part(fraud_reason, '/', 3), ''), '-') AS b, count(*) AS n
FROM ipintel_curated.ip_intelligence_analytics WHERE vendor = 'ip2proxy_px12' AND has_answer GROUP BY 1, 2, 3
UNION ALL
SELECT 'proxycheck type', coalesce(fraud_reason, '(none)'), '', count(*) FROM ipintel_curated.ip_intelligence_analytics
WHERE vendor = 'proxycheck_io' GROUP BY 1, 2, 3
UNION ALL
SELECT 'fraudlogix reason', coalesce(fraud_reason, '(no decision)'), '', count(*) FROM ipintel_curated.ip_intelligence_analytics
WHERE vendor = 'fraudlogix_tune' GROUP BY 1, 2, 3
ORDER BY 1, 4 DESC
