-- Read only. Fill rate per vendor and column, over every address in the tables.
WITH n AS (SELECT count(DISTINCT ip_address) AS ips FROM ipintel_curated.ip_geo)
SELECT 'risk' AS t, vendor, count(*) AS rows_, round(100.0*count(*)/max(n.ips),1) AS row_cover_pct,
  round(100.0*count_if(is_proxy IS NOT NULL)/max(n.ips),1) AS proxy_pct,
  round(100.0*count_if(is_vpn IS NOT NULL)/max(n.ips),1) AS vpn_pct,
  round(100.0*count_if(is_tor IS NOT NULL)/max(n.ips),1) AS tor_pct,
  round(100.0*count_if(is_datacenter IS NOT NULL)/max(n.ips),1) AS dc_pct,
  round(100.0*count_if(is_bot IS NOT NULL)/max(n.ips),1) AS bot_pct,
  round(100.0*count_if(is_compromised IS NOT NULL)/max(n.ips),1) AS comp_pct,
  round(100.0*count_if(nullif(isp,'') IS NOT NULL)/max(n.ips),1) AS isp_pct,
  round(100.0*count_if(nullif(asn,'') IS NOT NULL)/max(n.ips),1) AS asn_pct
FROM ipintel_curated.ip_intelligence CROSS JOIN n GROUP BY vendor
UNION ALL
SELECT 'geo', vendor, count(*), round(100.0*count(*)/max(n.ips),1),
  round(100.0*count_if(nullif(state,'') IS NOT NULL)/max(n.ips),1),
  round(100.0*count_if(nullif(city,'') IS NOT NULL)/max(n.ips),1),
  round(100.0*count_if(nullif(zip_code,'') IS NOT NULL)/max(n.ips),1),
  round(100.0*count_if(latitude IS NOT NULL)/max(n.ips),1),
  round(100.0*count_if(nullif(timezone,'') IS NOT NULL)/max(n.ips),1), NULL, NULL, NULL
FROM ipintel_curated.ip_geo CROSS JOIN n GROUP BY vendor
ORDER BY 1, 2
