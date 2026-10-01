-- Read only. Step 1 acceptance: every public IP in our data lake has a reliable, filled answer.
-- Reliable = FraudLogix decided, or proxycheck.io answered (IP2Proxy does not count). Run on the live unified tables.
WITH src AS (   -- every IP in the three source tables
  SELECT DISTINCT trim(ip) AS ip FROM raw.raw_tune_clicks WHERE nullif(trim(ip), '') IS NOT NULL
  UNION SELECT DISTINCT trim(session_ip) FROM unified.unified_session_summary WHERE nullif(trim(session_ip), '') IS NOT NULL
  UNION SELECT DISTINCT trim(ip_address) FROM experimentation_tools.experiment_router_events WHERE nullif(trim(ip_address), '') IS NOT NULL),
pub AS (SELECT ip FROM src WHERE regexp_like(ip, '^\d{1,3}(\.\d{1,3}){3}$') AND NOT (try_cast(split_part(ip, '.', 1) AS integer) IN (0, 10, 127) OR try_cast(split_part(ip, '.', 1) AS integer) >= 224 OR (try_cast(split_part(ip, '.', 1) AS integer) = 100 AND try_cast(split_part(ip, '.', 2) AS integer) BETWEEN 64 AND 127) OR (try_cast(split_part(ip, '.', 1) AS integer) = 169 AND try_cast(split_part(ip, '.', 2) AS integer) = 254) OR (try_cast(split_part(ip, '.', 1) AS integer) = 172 AND try_cast(split_part(ip, '.', 2) AS integer) BETWEEN 16 AND 31) OR (try_cast(split_part(ip, '.', 1) AS integer) = 192 AND try_cast(split_part(ip, '.', 2) AS integer) = 168) OR (try_cast(split_part(ip, '.', 1) AS integer) = 192 AND try_cast(split_part(ip, '.', 2) AS integer) = 0 AND try_cast(split_part(ip, '.', 3) AS integer) IN (0, 2)) OR (try_cast(split_part(ip, '.', 1) AS integer) = 198 AND try_cast(split_part(ip, '.', 2) AS integer) IN (18, 19)) OR (try_cast(split_part(ip, '.', 1) AS integer) = 198 AND try_cast(split_part(ip, '.', 2) AS integer) = 51 AND try_cast(split_part(ip, '.', 3) AS integer) = 100) OR (try_cast(split_part(ip, '.', 1) AS integer) = 203 AND try_cast(split_part(ip, '.', 2) AS integer) = 0 AND try_cast(split_part(ip, '.', 3) AS integer) = 113))),
intel AS (
  SELECT ip_address,
         count_if(vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL) AS fl,
         count_if(vendor = 'proxycheck_io' AND is_proxy IS NOT NULL) AS pc
  FROM unified.ip_intelligence GROUP BY ip_address),
geo AS (
  SELECT ip_address, count_if(nullif(state, '') IS NOT NULL OR nullif(city, '') IS NOT NULL) AS filled
  FROM unified.ip_geo GROUP BY ip_address)
SELECT '1. public IPv4 in the 3 source tables' AS check_, count(*) AS value FROM pub
UNION ALL SELECT '2. of those, missing from unified.ip_geo', count_if(g.ip_address IS NULL) FROM pub p LEFT JOIN geo g ON g.ip_address = p.ip
UNION ALL SELECT '3. of those, missing from unified.ip_intelligence', count_if(i.ip_address IS NULL) FROM pub p LEFT JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '4. UNRESOLVED: no FraudLogix decision and no proxycheck.io answer', count_if(coalesce(i.fl, 0) = 0 AND coalesce(i.pc, 0) = 0) FROM pub p LEFT JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '5. resolved by FraudLogix', count_if(i.fl > 0) FROM pub p JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '6. resolved by proxycheck.io only', count_if(i.fl = 0 AND i.pc > 0) FROM pub p JOIN intel i ON i.ip_address = p.ip
UNION ALL SELECT '7. no usable location (state or city) from any vendor', count_if(coalesce(g.filled, 0) = 0) FROM pub p LEFT JOIN geo g ON g.ip_address = p.ip
UNION ALL SELECT '8. FraudLogix rows with proxy/vpn/tor/datacenter empty', count(*) FROM unified.ip_intelligence
  WHERE vendor = 'fraudlogix_tune' AND (is_proxy IS NULL OR is_vpn IS NULL OR is_tor IS NULL OR is_datacenter IS NULL)
UNION ALL SELECT '9. proxycheck.io rows with any flag column empty (except is_bot)', count(*) FROM unified.ip_intelligence
  WHERE vendor = 'proxycheck_io' AND (is_proxy IS NULL OR is_vpn IS NULL OR is_tor IS NULL OR is_datacenter IS NULL
        OR is_compromised IS NULL OR is_scraper IS NULL OR is_anonymous IS NULL)
UNION ALL SELECT '10. proxycheck.io rows with ISP empty (proxycheck.io gave none)', count(*) FROM unified.ip_intelligence
  WHERE vendor = 'proxycheck_io' AND nullif(isp, '') IS NULL
UNION ALL SELECT '11. FraudLogix rows filled from proxycheck.io (is_bot left empty)', count(*) FROM ipintel_curated.ip_intelligence_analytics
  WHERE vendor = 'fraudlogix_tune' AND fraud_reason = 'FILLED_FROM_PROXYCHECK_IO'
UNION ALL SELECT '12. rows unified.ip_intelligence', count(*) FROM unified.ip_intelligence
UNION ALL SELECT '13. rows ipintel_curated.ip_intelligence (must equal 12)', count(*) FROM ipintel_curated.ip_intelligence
UNION ALL SELECT '14. rows unified.ip_geo', count(*) FROM unified.ip_geo
UNION ALL SELECT '15. rows ipintel_curated.ip_geo (must equal 14)', count(*) FROM ipintel_curated.ip_geo
UNION ALL SELECT '16. duplicate (ip, vendor) in unified.ip_intelligence', count(*) FROM
  (SELECT ip_address, vendor FROM unified.ip_intelligence GROUP BY 1, 2 HAVING count(*) > 1)
ORDER BY 1
