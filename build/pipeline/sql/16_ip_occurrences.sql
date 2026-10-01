CREATE TABLE ipintel_curated.ip_occurrences (
  ip_address string,
  base_table string,
  source_table string,
  first_seen date,
  last_seen date,
  days_seen bigint,
  rows_seen bigint,
  updated_at string)
PARTITIONED BY (bucket(64, ip_address))
LOCATION 's3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/ip_occurrences/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet', 'write_compression'='snappy')
