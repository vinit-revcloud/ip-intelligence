CREATE TABLE ipintel_curated.intel_src
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/curated/intel_src/d=2026-09-11/') AS

-- IP2Proxy PX12, joined over the whole pool through prefix16.
-- Absence from PX12 is recorded as "no answer", not as "not a proxy". That was
-- the rule the benchmark was measured under and changing it here would silently
-- restate every proxy metric in the product.
WITH px AS (
  SELECT p.ip_address, x.proxy_type, x.usage_type, x.isp, x.asn, x.threat,
         x.fraud_score, x.ip_from
  FROM ipintel_curated.ip_pool p
  LEFT JOIN ipintel_curated.px12_bucketed x
    ON x.prefix16 = p.prefix16
   AND p.ip_num BETWEEN x.ip_from AND x.ip_to
),
pxn AS (
  SELECT ip_address, CAST('ip2proxy_px12' AS varchar) AS vendor,
    (ip_from IS NOT NULL) AS has_answer,
    CASE WHEN ip_from IS NOT NULL THEN true END AS is_proxy,
    CASE WHEN ip_from IS NOT NULL THEN proxy_type = 'VPN' END AS is_vpn,
    CASE WHEN ip_from IS NOT NULL THEN proxy_type = 'TOR' END AS is_tor,
    CASE WHEN ip_from IS NOT NULL THEN usage_type IN ('DCH','CDN') END AS is_datacenter,
    CAST(NULL AS boolean) AS is_bot,
    CAST(NULL AS boolean) AS is_compromised,
    CAST(NULL AS boolean) AS is_scraper,
    CAST(NULL AS boolean) AS is_anonymous,
    -- threat carries SCANNER, BOTNET and SPAM on 51,002 ranges. It is recorded
    -- here so it is not thrown away, but it is not wired to is_bot: that would
    -- change what the column means partway through the product's life.
    CASE WHEN ip_from IS NOT NULL THEN
      concat(coalesce(nullif(proxy_type,'-'),'-'), '/', coalesce(nullif(usage_type,'-'),'-'),
             CASE WHEN threat IS NOT NULL AND threat <> '-' THEN concat('/', threat) ELSE '' END)
    END AS fraud_reason,
    false AS is_masked_device,
    CASE WHEN ip_from IS NOT NULL THEN fraud_score END AS risk_score,
    CASE WHEN ip_from IS NOT NULL THEN nullif(isp,'-') END AS isp,
    CASE WHEN ip_from IS NOT NULL THEN nullif(asn,'-') END AS asn,
    CAST('2026-09-11T00:00:00Z' AS varchar) AS observed_at,
    CAST('2026-09-11T00:00:00Z' AS varchar) AS last_seen_at
  FROM px
),

-- FraudLogix, from the click stream we already hold. The latest decision per
-- address, never the full history: an address flagged once in 2023 and accepted
-- every time since is not a flagged address.
fl AS (
  SELECT ip, max_by(access_control_decision, datetime) AS dec,
         max_by(access_control_reason_code, datetime) AS rsn,
         max(datetime) AS at
  FROM raw.raw_tune_clicks
  WHERE ip IS NOT NULL AND length(ip) BETWEEN 7 AND 15 AND ip LIKE '%.%.%.%'
    AND coalesce(access_control_decision,'') <> ''
  GROUP BY ip
),
fln AS (
  SELECT f.ip AS ip_address, CAST('fraudlogix_tune' AS varchar) AS vendor,
    true AS has_answer,
    CASE WHEN dec <> 'FLAGGED' THEN false ELSE rsn IN ('PROXY','MOBILE_PROXY_SIGNALS') END AS is_proxy,
    CASE WHEN dec <> 'FLAGGED' THEN false ELSE rsn = 'VPN' END AS is_vpn,
    CASE WHEN dec <> 'FLAGGED' THEN false ELSE rsn IN ('TOR','TOR_EXIT_NODE') END AS is_tor,
    CASE WHEN dec <> 'FLAGGED' THEN false ELSE rsn = 'DATA_CENTER' END AS is_datacenter,
    CASE WHEN dec <> 'FLAGGED' THEN false ELSE rsn IN ('BOT_GENERATED','NON_HUMAN_SCRIPT') END AS is_bot,
    CAST(NULL AS boolean) AS is_compromised,
    CAST(NULL AS boolean) AS is_scraper,
    CAST(NULL AS boolean) AS is_anonymous,
    CASE WHEN dec <> 'FLAGGED' THEN 'ACCEPTED' ELSE rsn END AS fraud_reason,
    -- MASKED_DEVICES is a device-fingerprint signal, not a bot signal. 195
    -- confirmed humans carry it, so it sets none of the booleans above.
    (dec = 'FLAGGED' AND rsn = 'MASKED_DEVICES') AS is_masked_device,
    CAST(NULL AS integer) AS risk_score,
    CAST(NULL AS varchar) AS isp, CAST(NULL AS varchar) AS asn,
    CAST(at AS varchar) AS observed_at, CAST(at AS varchar) AS last_seen_at
  FROM fl f
  JOIN ipintel_curated.ip_pool p ON p.ip_address = f.ip
),

au AS (
  SELECT o.ip_address, CAST('authoritative_lists' AS varchar) AS vendor, true AS has_answer,
    o.is_proxy = 'true' AS is_proxy, o.is_vpn = 'true' AS is_vpn, o.is_tor = 'true' AS is_tor,
    o.is_datacenter = 'true' AS is_datacenter,
    CAST(NULL AS boolean) AS is_bot, CAST(NULL AS boolean) AS is_compromised,
    CAST(NULL AS boolean) AS is_scraper, CAST(NULL AS boolean) AS is_anonymous,
    nullif(o.fraud_reason,'') AS fraud_reason, false AS is_masked_device,
    CAST(NULL AS integer) AS risk_score,
    CAST(NULL AS varchar) AS isp, CAST(NULL AS varchar) AS asn,
    CAST(o.observed_at AS varchar) AS observed_at, CAST(o.observed_at AS varchar) AS last_seen_at
  FROM ipintel_curated.ip_intel_observations o
  JOIN ipintel_curated.ip_pool p ON p.ip_address = o.ip_address
  WHERE o.vendor = 'authoritative_lists'
),

-- Rows proxycheck wrote through the live miss path. They are snapshotted before
-- every rebuild and folded back in here, so a rebuild can never spend quota
-- twice on an address already answered.
pc AS (
  SELECT ip_address, CAST('proxycheck_io' AS varchar) AS vendor, true AS has_answer,
    is_proxy, is_vpn, is_tor, is_datacenter, is_bot, is_compromised, is_scraper, is_anonymous,
    CAST(NULL AS varchar) AS fraud_reason, false AS is_masked_device,
    CAST(NULL AS integer) AS risk_score, isp, asn,
    created_at AS observed_at, updated_at AS last_seen_at
  FROM ipintel_curated.pc_live
),

allo AS (
  SELECT * FROM pxn UNION ALL SELECT * FROM fln
  UNION ALL SELECT * FROM au UNION ALL SELECT * FROM pc
),

-- The published-range reference, used to judge whether a flag was justified.
-- It only exists for the addresses the benchmark covered, so known_infrastructure
-- is false for the rest. False here means "no reference", which is why
-- verdict_class reports no_answer rather than a verdict when nothing answered.
val AS (
  SELECT ip_address, (coalesce(is_proxy,false) OR coalesce(is_datacenter,false)) AS known_infrastructure,
         fraud_reason AS infrastructure_list
  FROM au
)
SELECT a.ip_address, a.vendor, a.has_answer,
  a.is_proxy, a.is_vpn, a.is_tor, a.is_datacenter, a.is_bot,
  a.is_compromised, a.is_scraper, a.is_anonymous,
  a.fraud_reason, a.is_masked_device, a.risk_score, a.isp, a.asn,
  a.observed_at, a.last_seen_at,
  coalesce(v.known_infrastructure, false) AS known_infrastructure,
  v.infrastructure_list,
  (coalesce(a.is_proxy,false) OR coalesce(a.is_vpn,false) OR coalesce(a.is_tor,false)
   OR coalesce(a.is_datacenter,false) OR coalesce(a.is_bot,false)
   OR coalesce(a.is_compromised,false) OR coalesce(a.is_scraper,false)) AS flagged
FROM allo a
LEFT JOIN val v ON v.ip_address = a.ip_address
