WITH occ AS (SELECT ip_address, max(last_seen) ls, array_join(array_agg(DISTINCT base_table), '+') bt FROM ipintel_curated.ip_occurrences GROUP BY 1),
w AS (SELECT r.*, o.bt FROM ipintel_curated.ip_resolved r JOIN occ o ON o.ip_address = r.ip_address WHERE o.ls >= date '2026-08-17')
SELECT 'status' k, proxy_status v, count(*) n FROM w GROUP BY 2
UNION ALL SELECT 'flag', f, n FROM (SELECT 'flagged' f, count_if(flagged) n FROM w UNION ALL SELECT 'vpn', count_if(is_vpn) FROM w
  UNION ALL SELECT 'proxy', count_if(is_proxy) FROM w UNION ALL SELECT 'tor', count_if(is_tor) FROM w UNION ALL SELECT 'datacenter', count_if(is_datacenter) FROM w
  UNION ALL SELECT 'bot', count_if(is_bot) FROM w UNION ALL SELECT 'compromised', count_if(is_compromised) FROM w UNION ALL SELECT 'total', count(*) FROM w)
UNION ALL SELECT 'flagged_by_table', bt, count_if(flagged) FROM w GROUP BY 2
UNION ALL SELECT 'table_total', bt, count(*) FROM w GROUP BY 2
UNION ALL SELECT 'top_flagged_isp', isp, n FROM (SELECT isp, count(*) n FROM w WHERE flagged GROUP BY 1 ORDER BY 2 DESC LIMIT 8)
UNION ALL SELECT 'risk_band', CASE WHEN proxycheck_risk_score >= 67 THEN 'high 67-100' WHEN proxycheck_risk_score >= 34 THEN 'medium 34-66' WHEN proxycheck_risk_score IS NOT NULL THEN 'low 0-33' ELSE 'none' END, count(*) FROM w GROUP BY 2
ORDER BY 1, 3 DESC
