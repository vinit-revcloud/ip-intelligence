CREATE TABLE ipintel_curated.ip_geo
WITH (table_type='ICEBERG', is_external=false, format='PARQUET', write_compression='SNAPPY', location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/ip_geo/', partitioning=ARRAY['bucket(ip_address, 64)']) AS
SELECT CAST(ip_address AS varchar) AS ip_address, CAST(vendor AS varchar) AS vendor,
       CAST(state AS varchar) AS state, CAST(city AS varchar) AS city, CAST(zip_code AS varchar) AS zip_code,
       CAST(latitude AS double) AS latitude, CAST(longitude AS double) AS longitude,
       CAST(timezone AS varchar) AS timezone,
       CAST(created_at AS varchar) AS created_at, CAST(updated_at AS varchar) AS updated_at
FROM unified.ip_geo
