CREATE TABLE ipintel_curated.ip_geo_analytics
WITH (table_type='ICEBERG', is_external=false, format='PARQUET', write_compression='SNAPPY', location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/ip_geo_analytics/', partitioning=ARRAY['bucket(ip_address, 64)']) AS
SELECT CAST(ip_address AS varchar) AS ip_address, CAST(vendor AS varchar) AS vendor, has_answer,
       CAST(consensus_state AS varchar) AS consensus_state, CAST(consensus_city AS varchar) AS consensus_city,
       CAST(consensus_zip AS varchar) AS consensus_zip,
       state_votes, city_votes, zip_votes,
       state_matches_consensus, city_matches_consensus, zip_matches_consensus,
       CAST(truth_state AS varchar) AS truth_state, CAST(truth_city AS varchar) AS truth_city,
       CAST(truth_zip AS varchar) AS truth_zip,
       state_matches_truth, city_matches_truth, zip_matches_truth,
       row_agreement_pct, row_truth_agreement_pct
FROM unified.ip_geo_analytics
