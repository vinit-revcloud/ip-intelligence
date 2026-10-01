SELECT CASE WHEN is_vpn THEN 'vpn' WHEN is_proxy THEN 'proxy (not vpn)' WHEN is_compromised THEN 'compromised' ELSE 'other' END AS kind,
       count(*) AS flagged_addresses
FROM ipintel_curated.ip_resolved
WHERE flagged AND isp IN ('Comcast Cable Communications, LLC', 'AT&T Enterprises, LLC', 'Verizon Business', 'Charter Communications Inc', 'Cox Communications Inc.')
GROUP BY 1 ORDER BY 2 DESC
