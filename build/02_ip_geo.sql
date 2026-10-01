CREATE TABLE unified.ip_geo
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/unified/ip_geo/d=2026-09-11/',
      bucketed_by=ARRAY['ip_address'], bucket_count=64) AS
WITH db11 AS (
  -- The prefix16 join is what makes a range lookup over 4.96M addresses
  -- tractable: without it this is 4.96M x 3.01M. IP2Location ranges do not
  -- overlap, and a range spanning several /16s is stored once per /16, so
  -- exactly one range matches each address.
  SELECT p.ip_address, d.region_name, d.city_name, d.zip_code,
         d.latitude, d.longitude, d.time_zone
  FROM ipintel_curated.ip_pool p
  LEFT JOIN ipintel_curated.db11_bucketed d
    ON d.prefix16 = p.prefix16
   AND p.ip_num BETWEEN d.ip_from AND d.ip_to
)
-- IP2Location covers every address, so it is the one geo vendor that reaches
-- the whole pool. It writes '-' where it has no value, which is a null, not a
-- place name. When it has no region it has nothing at all, so the whole record
-- is nulled rather than leaving a stray coordinate behind.
SELECT
  ip_address,
  CAST('ip2location_db11' AS varchar) AS vendor,
  CASE WHEN region_name <> '-' THEN nullif(trim(region_name),'') END AS state,
  CASE WHEN region_name <> '-' THEN nullif(nullif(trim(city_name),''),'-') END AS city,
  CASE WHEN region_name <> '-' THEN nullif(nullif(trim(zip_code),''),'-') END AS zip_code,
  CASE WHEN region_name <> '-' THEN latitude END AS latitude,
  CASE WHEN region_name <> '-' THEN longitude END AS longitude,
  CASE WHEN region_name <> '-' THEN nullif(nullif(trim(time_zone),''),'-') END AS timezone,
  CAST('2026-09-11T00:00:00Z' AS varchar) AS created_at,
  CAST('2026-09-11T00:00:00Z' AS varchar) AS updated_at
FROM db11

UNION ALL

-- The API vendors only ever answered for the addresses they were asked about.
-- No row is written for the rest: absence means "never asked", which is a
-- different statement from a row full of nulls meaning "asked, no answer".
SELECT
  g.ip_address,
  CAST(g.vendor AS varchar),
  nullif(trim(g.state),''),
  nullif(trim(g.city),''),
  nullif(trim(g.zip_code),''),
  try_cast(g.latitude AS double),
  try_cast(g.longitude AS double),
  nullif(trim(g.timezone),''),
  CAST(g.observed_at AS varchar),
  CAST(g.observed_at AS varchar)
FROM ipintel_curated.ip_geo_observations g
JOIN ipintel_curated.ip_pool p ON p.ip_address = g.ip_address
WHERE g.vendor <> 'icloud_private_relay'
