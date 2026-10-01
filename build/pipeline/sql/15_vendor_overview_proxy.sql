CREATE TABLE ipintel_curated.vendor_overview_proxy
WITH (table_type='ICEBERG', is_external=false, format='PARQUET', write_compression='SNAPPY', location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/vendor_overview_proxy/') AS
SELECT * FROM unified.vendor_overview_proxy
