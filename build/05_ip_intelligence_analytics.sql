CREATE TABLE unified.ip_intelligence_analytics
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/unified/ip_intelligence_analytics/d=2026-09-11/',
      bucketed_by=ARRAY['ip_address'], bucket_count=64) AS
SELECT ip_address, vendor, has_answer, flagged,
  fraud_reason, is_masked_device, risk_score,
  known_infrastructure, infrastructure_list,
  CASE WHEN NOT has_answer THEN 'no_answer'
       WHEN flagged AND known_infrastructure THEN 'confirmed_by_published_range'
       WHEN flagged AND NOT known_infrastructure THEN 'unconfirmed_flag'
       WHEN NOT flagged AND known_infrastructure THEN 'missed_known_infrastructure'
       ELSE 'agreed_not_flagged' END AS verdict_class
FROM ipintel_curated.intel_src
