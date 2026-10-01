CREATE TABLE ipintel_curated.ip_intelligence
WITH (table_type='ICEBERG', is_external=false, format='PARQUET', write_compression='SNAPPY', location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/ip_intelligence/', partitioning=ARRAY['bucket(ip_address, 64)']) AS
WITH base AS (
  SELECT CAST(ip_address AS varchar) AS ip_address, CAST(vendor AS varchar) AS vendor,
         is_proxy, is_vpn, is_tor, is_datacenter, is_bot, is_compromised, is_scraper, is_anonymous,
         CAST(isp AS varchar) AS isp, CAST(asn AS varchar) AS asn,
         CAST(created_at AS varchar) AS created_at, CAST(updated_at AS varchar) AS updated_at
  FROM unified.ip_intelligence
),
-- proxycheck answers the live lookup wrote after 11 September
live AS (
  SELECT l.ip_address, 'proxycheck_io', l.is_proxy, l.is_vpn, l.is_tor, l.is_datacenter, l.is_bot,
         l.is_compromised, l.is_scraper, l.is_anonymous, l.isp, l.asn, l.created_at, l.updated_at
  FROM ipintel_curated.pc_live l
  WHERE NOT EXISTS (SELECT 1 FROM base b WHERE b.ip_address = l.ip_address AND b.vendor = 'proxycheck_io')
),
-- FraudLogix was asked about every address in tune clicks. Where it never gave a decision,
-- record that as "no answer" rather than leaving no row, so it can never read as "never asked".
tune_ips AS (
  SELECT ip, max(datetime) AS last_click,
         count_if(coalesce(access_control_decision, '') <> '') AS decisions
  FROM raw.raw_tune_clicks
  WHERE ip IS NOT NULL AND length(ip) BETWEEN 7 AND 15 AND ip LIKE '%.%.%.%'
  GROUP BY ip
),
silent AS (
  SELECT t.ip, 'fraudlogix_tune',
         CAST(NULL AS boolean), CAST(NULL AS boolean), CAST(NULL AS boolean), CAST(NULL AS boolean),
         CAST(NULL AS boolean), CAST(NULL AS boolean), CAST(NULL AS boolean), CAST(NULL AS boolean),
         CAST(NULL AS varchar), CAST(NULL AS varchar),
         CAST(t.last_click AS varchar), CAST(t.last_click AS varchar)
  FROM tune_ips t
  JOIN ipintel_curated.ip_pool p ON p.ip_address = t.ip
  WHERE t.decisions = 0
    AND NOT EXISTS (SELECT 1 FROM base b WHERE b.ip_address = t.ip AND b.vendor = 'fraudlogix_tune')
)
SELECT * FROM base UNION ALL SELECT * FROM live UNION ALL SELECT * FROM silent
