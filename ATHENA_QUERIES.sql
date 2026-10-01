-- =====================================================================
-- IP Intelligence — Athena queries
-- Read-only. Four tables, all under `unified`.
--
--   unified.vendor_overview_geo     one row per geo vendor
--   unified.vendor_overview_proxy   one row per risk vendor
--   unified.ip_geo                  one row per (IP, geo vendor)
--   unified.ip_intelligence         one row per (IP, risk vendor)
--
-- Region us-west-2 · account 221490242148 · workgroup `ipintel`
-- =====================================================================


-- =====================================================================
-- 1. VENDOR OVERVIEW — GEO
-- Two metric groups, deliberately separate:
--   AGREEMENT = does this vendor match the majority of OTHER vendors
--   TRUTH     = does it match the qualified lead's OWN address
-- They answer different questions. Never sum or average them together.
-- score = agreement x fill_rate, so a vendor must be both present and
-- consistent to rank well.
-- =====================================================================
SELECT vendor,
       fill_rate_pct,
       state_fill_pct, city_fill_pct, zip_fill_pct,
       state_agreement_pct, city_agreement_pct, zip_agreement_pct,
       agreement_pct,
       state_truth_pct, city_truth_pct, zip_truth_pct,
       cost_per_1k,
       score,
       excluded_from_voting,
       as_of_date
FROM unified.vendor_overview_geo
ORDER BY score DESC;


-- =====================================================================
-- 2. VENDOR OVERVIEW — PROXY
-- false_positive_rate_pct is EXACT: every IP in the pool produced a
-- qualified lead, so it is a confirmed human and any bot flag is wrong.
-- precision_bot_pct / recall_bot_pct are always NULL — with no true bots
-- in the pool there is no denominator. Never display those as 0%.
-- =====================================================================
SELECT vendor,
       answered, fill_rate_pct,
       flagged, detection_rate_pct,
       bot_flagged, bot_identification_pct,
       false_positive_rate_pct,
       true_positive, infra_in_scope,
       precision_infra_pct, recall_infra_pct,
       masked_device_flags,
       precision_bot_pct, recall_bot_pct, bot_metric_status,
       cost_per_1k,
       score,
       as_of_date
FROM unified.vendor_overview_proxy
ORDER BY score DESC;


-- =====================================================================
-- 3. IP GEO — the console projection
-- =====================================================================
SELECT ip_address,
       vendor,
       state,
       city,
       zip_code,
       latitude,
       longitude,
       timezone,
       observed_at AS created_at,
       valid_from  AS updated_at
FROM unified.ip_geo
ORDER BY ip_address, vendor;


-- =====================================================================
-- 4. IP INTELLIGENCE — the console projection
-- Tri-state booleans: TRUE = affirmed, FALSE = the vendor explicitly
-- said no, NULL = the vendor said nothing. NULL is NOT a "no".
-- An all-FALSE row is FraudLogix ACCEPTED; an all-NULL row is a vendor
-- with no opinion. Those are different facts.
-- =====================================================================
SELECT ip_address,
       vendor,
       is_proxy,
       is_vpn,
       is_tor,
       is_datacenter,
       is_bot,
       isp,
       asn,
       observed_at AS created_at,
       valid_from  AS updated_at
FROM unified.ip_intelligence
ORDER BY ip_address, vendor;


-- =====================================================================
-- 5. DISAGREEMENTS ONLY
-- The question this console exists to answer. Returns EVERY row of any
-- IP where the vendors that answered did not all return the same state,
-- city or ZIP. Nulls are ignored — a vendor with no answer is not a
-- disagreement.
-- Currently 2,025 of 2,105 IPs (96.2%) disagree on at least one field.
-- =====================================================================
WITH answered AS (
  SELECT ip_address,
         lower(trim(state))  AS st,
         lower(trim(city))   AS ct,
         trim(zip_code)      AS zp
  FROM unified.ip_geo
  WHERE has_answer
),
disputed AS (
  SELECT ip_address
  FROM answered
  GROUP BY ip_address
  HAVING count(DISTINCT st) > 1
      OR count(DISTINCT ct) > 1
      OR count(DISTINCT zp) > 1
)
SELECT g.ip_address, g.vendor, g.state, g.city, g.zip_code,
       g.observed_at AS created_at, g.valid_from AS updated_at
FROM unified.ip_geo g
JOIN disputed d ON d.ip_address = g.ip_address
ORDER BY g.ip_address, g.vendor;


-- =====================================================================
-- 6. ONE IP, EVERY VENDOR — the drill-down
-- =====================================================================
SELECT vendor, state, city, zip_code, latitude, longitude,
       observed_at AS created_at
FROM unified.ip_geo
WHERE ip_address = '146.75.164.0'
ORDER BY vendor;

SELECT vendor, is_proxy, is_vpn, is_tor, is_datacenter, is_bot, isp, asn,
       observed_at AS created_at
FROM unified.ip_intelligence
WHERE ip_address = '146.75.164.0'
ORDER BY vendor;


-- =====================================================================
-- 7. COVERAGE CHECKS
-- =====================================================================
-- Rows, IPs and vendors in each table
SELECT 'ip_geo' AS table_name,
       count(*) AS rows, count(DISTINCT ip_address) AS ips, count(DISTINCT vendor) AS vendors
FROM unified.ip_geo
UNION ALL
SELECT 'ip_intelligence', count(*), count(DISTINCT ip_address), count(DISTINCT vendor)
FROM unified.ip_intelligence;

-- Who answered, per geo vendor
SELECT vendor,
       count(*) AS ips,
       sum(CASE WHEN has_answer THEN 1 ELSE 0 END) AS answered,
       sum(CASE WHEN state    IS NOT NULL THEN 1 ELSE 0 END) AS has_state,
       sum(CASE WHEN city     IS NOT NULL THEN 1 ELSE 0 END) AS has_city,
       sum(CASE WHEN zip_code IS NOT NULL THEN 1 ELSE 0 END) AS has_zip
FROM unified.ip_geo
GROUP BY vendor
ORDER BY answered DESC;

-- Verdict breakdown per risk vendor.
-- 'no_answer' means the vendor was asked and returned nothing — it is
-- NOT a clean verdict.
SELECT vendor, verdict_class, count(*) AS n
FROM unified.ip_intelligence
GROUP BY vendor, verdict_class
ORDER BY vendor, n DESC;

-- FraudLogix reason mapping. Expect ACCEPTED with no flags of any kind,
-- MASKED_DEVICES with is_masked_device only (it is a device-fingerprint
-- signal, not a bot signal), NON_HUMAN_SCRIPT and BOT_GENERATED with
-- is_bot only.
SELECT fraud_reason,
       count(*) AS n,
       sum(CASE WHEN is_proxy        THEN 1 ELSE 0 END) AS proxy,
       sum(CASE WHEN is_bot          THEN 1 ELSE 0 END) AS bot,
       sum(CASE WHEN is_masked_device THEN 1 ELSE 0 END) AS masked_device
FROM unified.ip_intelligence
WHERE vendor = 'fraudlogix_tune'
GROUP BY fraud_reason
ORDER BY n DESC;
