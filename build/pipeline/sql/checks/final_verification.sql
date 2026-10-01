-- Read only. Final acceptance of the two unified tables after step 3 (19 Sep 2026).
WITH src AS (
  SELECT DISTINCT trim(ip) AS ip FROM raw.raw_tune_clicks WHERE nullif(trim(ip), '') IS NOT NULL
  UNION SELECT DISTINCT trim(session_ip) FROM unified.unified_session_summary WHERE nullif(trim(session_ip), '') IS NOT NULL
  UNION SELECT DISTINCT trim(ip_address) FROM experimentation_tools.experiment_router_events WHERE nullif(trim(ip_address), '') IS NOT NULL),
pub AS (SELECT ip FROM src WHERE regexp_like(ip, '^\d{1,3}(\.\d{1,3}){3}$') AND NOT (try_cast(split_part(ip, '.', 1) AS integer) IN (0, 10, 127) OR try_cast(split_part(ip, '.', 1) AS integer) >= 224 OR (try_cast(split_part(ip, '.', 1) AS integer) = 100 AND try_cast(split_part(ip, '.', 2) AS integer) BETWEEN 64 AND 127) OR (try_cast(split_part(ip, '.', 1) AS integer) = 169 AND try_cast(split_part(ip, '.', 2) AS integer) = 254) OR (try_cast(split_part(ip, '.', 1) AS integer) = 172 AND try_cast(split_part(ip, '.', 2) AS integer) BETWEEN 16 AND 31) OR (try_cast(split_part(ip, '.', 1) AS integer) = 192 AND try_cast(split_part(ip, '.', 2) AS integer) = 168) OR (try_cast(split_part(ip, '.', 1) AS integer) = 192 AND try_cast(split_part(ip, '.', 2) AS integer) = 0 AND try_cast(split_part(ip, '.', 3) AS integer) IN (0, 2)) OR (try_cast(split_part(ip, '.', 1) AS integer) = 198 AND try_cast(split_part(ip, '.', 2) AS integer) IN (18, 19)) OR (try_cast(split_part(ip, '.', 1) AS integer) = 198 AND try_cast(split_part(ip, '.', 2) AS integer) = 51 AND try_cast(split_part(ip, '.', 3) AS integer) = 100) OR (try_cast(split_part(ip, '.', 1) AS integer) = 203 AND try_cast(split_part(ip, '.', 2) AS integer) = 0 AND try_cast(split_part(ip, '.', 3) AS integer) = 113))),
intel AS (SELECT ip_address, count_if(vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL) AS fl,
                 count_if(vendor = 'proxycheck_io' AND is_proxy IS NOT NULL) AS pc,
                 bool_or(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND coalesce(is_bot, false)) AS bad
          FROM unified.ip_intelligence GROUP BY ip_address),
geo AS (SELECT DISTINCT ip_address FROM unified.ip_geo)
SELECT '01 public IPv4 in the 3 sources' AS check_, count(*) AS value FROM pub
UNION ALL SELECT '02 missing from unified.ip_geo', count_if(g.ip_address IS NULL) FROM pub p LEFT JOIN geo g ON g.ip_address = p.ip
UNION ALL SELECT '03 missing from unified.ip_intelligence', count_if(i.ip_address IS NULL) FROM pub p LEFT JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '04 UNRESOLVED (no FraudLogix decision, no proxycheck.io)', count_if(coalesce(i.fl, 0) = 0 AND coalesce(i.pc, 0) = 0) FROM pub p LEFT JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '05 with a proxycheck.io answer', count_if(i.pc > 0) FROM pub p JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '06 WITHOUT a proxycheck.io answer', count_if(coalesce(i.pc, 0) = 0) FROM pub p LEFT JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '07 with a FraudLogix decision', count_if(i.fl > 0) FROM pub p JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '08 bad (step 2 standard, FL or PC)', count_if(i.bad) FROM pub p JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '09 FraudLogix rows with core flags empty', count(*) FROM unified.ip_intelligence WHERE vendor = 'fraudlogix_tune' AND (is_proxy IS NULL OR is_vpn IS NULL OR is_tor IS NULL OR is_datacenter IS NULL)
UNION ALL SELECT '10 FraudLogix rows with is_bot empty', count(*) FROM unified.ip_intelligence WHERE vendor = 'fraudlogix_tune' AND is_bot IS NULL
UNION ALL SELECT '11 FraudLogix rows with ISP empty', count(*) FROM unified.ip_intelligence WHERE vendor = 'fraudlogix_tune' AND nullif(isp, '') IS NULL
UNION ALL SELECT '12 proxycheck.io rows with a flag empty', count(*) FROM unified.ip_intelligence WHERE vendor = 'proxycheck_io' AND (is_proxy IS NULL OR is_vpn IS NULL OR is_tor IS NULL OR is_datacenter IS NULL OR is_bot IS NULL OR is_compromised IS NULL OR is_scraper IS NULL OR is_anonymous IS NULL)
UNION ALL SELECT '13 answered rows with is_flagged/flagged_reason empty', count(*) FROM unified.ip_intelligence WHERE vendor IN ('fraudlogix_tune', 'proxycheck_io') AND (is_flagged IS NULL OR flagged_reason IS NULL)
UNION ALL SELECT '14 is_bot differs from is_flagged', count(*) FROM unified.ip_intelligence WHERE is_bot IS DISTINCT FROM is_flagged
UNION ALL SELECT '15 bad rows without a reason', count(*) FROM unified.ip_intelligence WHERE is_bot AND (bot_reason IS NULL OR bot_reason = 'NOT_BOT')
UNION ALL SELECT '16 duplicate (ip, vendor) in unified.ip_intelligence', count(*) FROM (SELECT ip_address, vendor FROM unified.ip_intelligence GROUP BY 1, 2 HAVING count(*) > 1)
UNION ALL SELECT '17 duplicate (ip, vendor) in unified.ip_geo', count(*) FROM (SELECT ip_address, vendor FROM unified.ip_geo GROUP BY 1, 2 HAVING count(*) > 1)
UNION ALL SELECT '18 rows unified.ip_intelligence', count(*) FROM unified.ip_intelligence
UNION ALL SELECT '19 rows ipintel_curated.ip_intelligence (= 18)', count(*) FROM ipintel_curated.ip_intelligence
UNION ALL SELECT '20 rows unified.ip_geo', count(*) FROM unified.ip_geo
UNION ALL SELECT '21 rows ipintel_curated.ip_geo (= 20)', count(*) FROM ipintel_curated.ip_geo
ORDER BY 1
