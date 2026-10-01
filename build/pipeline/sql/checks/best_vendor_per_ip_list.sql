-- Read only. One row per IP: the risk vendor and the location vendor with the most columns filled.
-- Ties go to the more accurate vendor (risk: FraudLogix, proxycheck.io, IP2Proxy; location: proxycheck.io, DB11, others).
WITH risk AS (
  SELECT ip_address, vendor,
    (CASE WHEN is_proxy IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN is_vpn IS NOT NULL THEN 1 ELSE 0 END
   + CASE WHEN is_tor IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN is_datacenter IS NOT NULL THEN 1 ELSE 0 END
   + CASE WHEN is_bot IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN is_compromised IS NOT NULL THEN 1 ELSE 0 END
   + CASE WHEN is_scraper IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN is_anonymous IS NOT NULL THEN 1 ELSE 0 END
   + CASE WHEN nullif(isp, '') IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN nullif(asn, '') IS NOT NULL THEN 1 ELSE 0 END) AS filled,
    CASE vendor WHEN 'fraudlogix_tune' THEN 1 WHEN 'proxycheck_io' THEN 2 ELSE 3 END AS pref
  FROM unified.ip_intelligence),
best_risk AS (
  SELECT ip_address, vendor AS best_risk_vendor, filled AS risk_columns_filled FROM (
    SELECT *, row_number() OVER (PARTITION BY ip_address ORDER BY filled DESC, pref) AS rn FROM risk) WHERE rn = 1),
geo AS (
  SELECT ip_address, vendor,
    (CASE WHEN nullif(state, '') IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN nullif(city, '') IS NOT NULL THEN 1 ELSE 0 END
   + CASE WHEN nullif(zip_code, '') IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END
   + CASE WHEN longitude IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN nullif(timezone, '') IS NOT NULL THEN 1 ELSE 0 END) AS filled,
    CASE vendor WHEN 'proxycheck_io' THEN 1 WHEN 'ip2location_db11' THEN 2 ELSE 3 END AS pref
  FROM unified.ip_geo),
best_geo AS (
  SELECT ip_address, vendor AS best_geo_vendor, filled AS geo_columns_filled FROM (
    SELECT *, row_number() OVER (PARTITION BY ip_address ORDER BY filled DESC, pref) AS rn FROM geo) WHERE rn = 1)
SELECT coalesce(r.ip_address, g.ip_address) AS ip_address,
       r.best_risk_vendor, r.risk_columns_filled,   -- out of 10: proxy, vpn, tor, datacenter, bot, compromised, scraper, anonymous, isp, asn
       g.best_geo_vendor, g.geo_columns_filled      -- out of 6: state, city, zip, latitude, longitude, timezone
FROM best_risk r FULL JOIN best_geo g ON g.ip_address = r.ip_address
