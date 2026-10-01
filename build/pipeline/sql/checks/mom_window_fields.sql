WITH w AS (SELECT * FROM unified.unified_session_summary WHERE session_date BETWEEN date '2026-09-04' AND date '2026-09-09' AND nullif(session_ip,'') IS NOT NULL),
l AS (SELECT l.* FROM sampledb.revenue_leads_plus l JOIN w ON w.session_id = l.utm_content WHERE l.date_pst >= date '2026-08-01')
SELECT 'session ip_is_proxy values' k, array_join(array_agg(DISTINCT coalesce(ip_is_proxy,'null')), ',') v FROM w
UNION ALL SELECT 'session ip_is_vpn values', array_join(array_agg(DISTINCT coalesce(ip_is_vpn,'null')), ',') FROM w
UNION ALL SELECT 'session ip_region filled', cast(count_if(nullif(ip_region_name,'') IS NOT NULL) AS varchar) || ' of ' || cast(count(*) AS varchar) FROM w
UNION ALL SELECT 'lead state/city/zip filled', cast(count_if(nullif(state_name,'') IS NOT NULL) AS varchar)||'/'||cast(count_if(nullif(city_name,'') IS NOT NULL) AS varchar)||'/'||cast(count_if(nullif(zip_code,'') IS NOT NULL) AS varchar)||' of '||cast(count(*) AS varchar) FROM l
UNION ALL SELECT 'leads per session ip in tables', cast(count_if(r.ip_address IS NOT NULL) AS varchar) || ' of ' || cast(count(*) AS varchar) FROM (SELECT DISTINCT session_ip FROM w) x LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = x.session_ip
UNION ALL SELECT 'window ips with proxycheck', cast(count(*) AS varchar) FROM (SELECT DISTINCT session_ip FROM w) x JOIN ipintel_curated.ip_intelligence i ON i.ip_address = x.session_ip AND i.vendor = 'proxycheck_io'
UNION ALL SELECT 'window ips with fraudlogix', cast(count(*) AS varchar) FROM (SELECT DISTINCT session_ip FROM w) x JOIN ipintel_curated.ip_intelligence i ON i.ip_address = x.session_ip AND i.vendor = 'fraudlogix_tune' AND i.is_proxy IS NOT NULL
