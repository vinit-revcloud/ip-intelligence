SELECT ip_address FROM ipintel_curated.ip_resolved WHERE proxy_status = 'flagged_unconfirmed' AND geo_status = 'single_source' ORDER BY last_seen DESC LIMIT 1
