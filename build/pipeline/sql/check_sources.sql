SELECT
  (SELECT count(*) FROM ipintel_curated.pc_live) AS live_proxycheck_rows,
  (SELECT count(*) FROM ipintel_curated.pc_live l
     WHERE NOT EXISTS (SELECT 1 FROM unified.ip_intelligence u WHERE u.ip_address = l.ip_address AND u.vendor = 'proxycheck_io')) AS live_rows_not_yet_in_unified,
  (SELECT count(DISTINCT ip) FROM raw.raw_tune_clicks
     WHERE ip IS NOT NULL AND length(ip) BETWEEN 7 AND 15 AND ip LIKE '%.%.%.%') AS tune_ips_all,
  (SELECT count(DISTINCT ip_address) FROM unified.ip_intelligence WHERE vendor = 'fraudlogix_tune') AS tune_ips_with_a_decision
