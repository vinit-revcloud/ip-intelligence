SELECT ip_address, geo_status, geo_decided_by, proxy_status, flagged, is_tor, is_vpn, proxy_decided_by, proxycheck_risk_score, seen_in_base_tables, updated_at
FROM ipintel_curated.ip_resolved WHERE ip_address IN ('185.220.101.1', '152.232.101.74')
UNION ALL SELECT 'timestamps', CAST(count_if(updated_at = '2026-09-14T21:30:00Z') AS varchar), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL FROM ipintel_curated.ip_resolved
