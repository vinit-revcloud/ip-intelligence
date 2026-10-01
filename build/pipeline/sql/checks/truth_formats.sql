SELECT 'leads' k, count(*) n, count(DISTINCT ip_address) ips, count_if(has_full_address) full_addr,
  count(DISTINCT CASE WHEN has_full_address THEN ip_address END) full_ips, cast(null AS varchar) ex
FROM ipintel_curated.qualified_lead_ips
UNION ALL SELECT 'lead_state_len', length(lead_state), count(*), null, null, regexp_replace(max(lead_state),'[^ -~]','?') FROM ipintel_curated.qualified_lead_ips WHERE has_full_address GROUP BY length(lead_state)
UNION ALL SELECT 'lead_zip_len', length(lead_zip), count(*), null, null, regexp_replace(max(lead_zip),'[^ -~]','?') FROM ipintel_curated.qualified_lead_ips WHERE has_full_address GROUP BY length(lead_zip)
UNION ALL SELECT 'geo_state_len:'||vendor, length(state), count(*), null, null, regexp_replace(max(state),'[^ -~]','?') FROM ipintel_curated.ip_geo GROUP BY vendor, length(state)
UNION ALL SELECT 'geo_zip_len:'||vendor, length(zip_code), count(*), null, null, regexp_replace(max(zip_code),'[^ -~]','?') FROM ipintel_curated.ip_geo GROUP BY vendor, length(zip_code)
UNION ALL SELECT 'leads_with_db11', count(DISTINCT l.ip_address), null, null, null, null FROM ipintel_curated.qualified_lead_ips l JOIN ipintel_curated.ip_geo g ON g.ip_address=l.ip_address AND g.vendor='ip2location_db11' WHERE l.has_full_address
ORDER BY 1,2
