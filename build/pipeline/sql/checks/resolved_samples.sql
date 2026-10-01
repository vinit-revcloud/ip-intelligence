SELECT ip_address, geo_status, state, city, geo_decided_by, geo_agreeing_vendors, proxy_status, flagged, proxy_decided_by, proxy_agreeing_vendors, isp
FROM ipintel_curated.ip_resolved
WHERE ip_address IN ('74.47.226.105', '47.152.75.118', '152.232.101.74', '9.9.9.9', '8.8.8.8')
   OR ip_address IN (SELECT min(ip_address) FROM ipintel_curated.ip_resolved GROUP BY geo_status, proxy_status)
