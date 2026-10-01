CREATE TABLE ipintel_curated.ip_pool
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/curated/ip_pool/d=2026-09-11/') AS
WITH s AS (
  SELECT session_ip AS ip, session_date AS d
  FROM unified.unified_session_summary
  WHERE session_ip IS NOT NULL AND session_date IS NOT NULL
    AND length(session_ip) BETWEEN 7 AND 15 AND session_ip LIKE '%.%.%.%'
),
t AS (
  SELECT ip, CAST(datetime AS date) AS d
  FROM raw.raw_tune_clicks
  WHERE ip IS NOT NULL AND datetime IS NOT NULL
    AND length(ip) BETWEEN 7 AND 15 AND ip LIKE '%.%.%.%'
),
a AS (SELECT ip, d FROM s UNION ALL SELECT ip, d FROM t),
agg AS (
  SELECT ip,
         min(d) AS first_seen,
         max(d) AS last_seen,
         CAST(count(DISTINCT d) AS integer) AS days_seen,
         CAST(count(*) AS integer) AS hits
  FROM a
  GROUP BY ip
),
-- try_cast is the validity test. A malformed octet becomes NULL and the row is
-- dropped below, which is why no regex is needed here. A heredoc mangled an
-- IPv4 regex earlier in this project and a vendor silently returned zero rows
-- for a whole run, so the arithmetic does the validating instead.
num AS (
  SELECT ip, first_seen, last_seen, days_seen, hits,
         try_cast(split_part(ip,'.',1) AS bigint) AS o1,
         try_cast(split_part(ip,'.',2) AS bigint) AS o2,
         try_cast(split_part(ip,'.',3) AS bigint) AS o3,
         try_cast(split_part(ip,'.',4) AS bigint) AS o4
  FROM agg
)
SELECT
  ip AS ip_address,
  o1*16777216 + o2*65536 + o3*256 + o4 AS ip_num,
  o1*256 + o2                          AS prefix16,
  CAST(o1 AS integer)                  AS octet1,
  first_seen, last_seen, days_seen, hits,
  (last_seen >= current_date - interval '90' day) AS is_active
FROM num
WHERE o1 IS NOT NULL AND o2 IS NOT NULL AND o3 IS NOT NULL AND o4 IS NOT NULL
  AND o1 BETWEEN 0 AND 255 AND o2 BETWEEN 0 AND 255
  AND o3 BETWEEN 0 AND 255 AND o4 BETWEEN 0 AND 255
