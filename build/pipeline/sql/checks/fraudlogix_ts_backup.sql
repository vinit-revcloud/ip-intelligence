UNLOAD (SELECT ip_address, vendor, created_at, updated_at FROM ipintel_curated.ip_intelligence WHERE vendor = 'fraudlogix_tune')
TO 's3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/archive/fraudlogix-timestamps-before-utc-2026-09-15/'
WITH (format = 'PARQUET')
