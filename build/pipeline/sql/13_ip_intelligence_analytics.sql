CREATE TABLE ipintel_curated.ip_intelligence_analytics
WITH (table_type='ICEBERG', is_external=false, format='PARQUET', write_compression='SNAPPY', location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/ip_intelligence_analytics/', partitioning=ARRAY['bucket(ip_address, 64)']) AS
WITH known AS (
  SELECT ip_address, bool_or(known_infrastructure) AS known_infrastructure, max(infrastructure_list) AS infrastructure_list
  FROM unified.ip_intelligence_analytics GROUP BY ip_address
),
base AS (
  SELECT CAST(ip_address AS varchar) AS ip_address, CAST(vendor AS varchar) AS vendor, has_answer, flagged,
         CAST(fraud_reason AS varchar) AS fraud_reason, is_masked_device, risk_score,
         known_infrastructure, CAST(infrastructure_list AS varchar) AS infrastructure_list,
         CAST(verdict_class AS varchar) AS verdict_class
  FROM unified.ip_intelligence_analytics
),
-- analytics rows for the rows added in 11_ip_intelligence that have none yet
added AS (
  SELECT i.ip_address, i.vendor,
         (i.is_proxy IS NOT NULL OR i.is_vpn IS NOT NULL OR i.is_datacenter IS NOT NULL OR i.is_bot IS NOT NULL) AS has_answer,
         (coalesce(i.is_proxy,false) OR coalesce(i.is_vpn,false) OR coalesce(i.is_tor,false) OR coalesce(i.is_datacenter,false)
          OR coalesce(i.is_bot,false) OR coalesce(i.is_compromised,false) OR coalesce(i.is_scraper,false)) AS flagged,
         CAST(NULL AS varchar) AS fraud_reason, false AS is_masked_device, CAST(NULL AS integer) AS risk_score,
         coalesce(k.known_infrastructure, false) AS known_infrastructure, k.infrastructure_list
  FROM ipintel_curated.ip_intelligence i
  LEFT JOIN known k ON k.ip_address = i.ip_address
  WHERE NOT EXISTS (SELECT 1 FROM base b WHERE b.ip_address = i.ip_address AND b.vendor = i.vendor)
)
SELECT * FROM base
UNION ALL
SELECT ip_address, vendor, has_answer, flagged, fraud_reason, is_masked_device, risk_score,
       known_infrastructure, infrastructure_list,
       CASE WHEN NOT has_answer THEN 'no_answer'
            WHEN flagged AND known_infrastructure THEN 'confirmed_by_published_range'
            WHEN flagged THEN 'unconfirmed_flag'
            WHEN known_infrastructure THEN 'missed_known_infrastructure'
            ELSE 'agreed_not_flagged' END
FROM added
