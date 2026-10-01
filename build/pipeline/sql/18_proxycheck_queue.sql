CREATE TABLE ipintel_curated.proxycheck_queue (
  ip_address string,
  reason string,
  source string,
  queued_at string,
  queued_by_run string,
  answered_at string,
  outcome string)
PARTITIONED BY (bucket(16, ip_address))
LOCATION 's3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/proxycheck_queue/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet', 'write_compression'='snappy')
