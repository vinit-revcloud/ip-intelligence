CREATE TABLE unified.ip_intelligence
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/unified/ip_intelligence/d=2026-09-11/',
      bucketed_by=ARRAY['ip_address'], bucket_count=64) AS
SELECT ip_address, vendor,
       is_proxy, is_vpn, is_tor, is_datacenter, is_bot,
       is_compromised, is_scraper, is_anonymous,
       isp, asn,
       observed_at  AS created_at,
       last_seen_at AS updated_at
FROM ipintel_curated.intel_src
