WITH src AS (
  SELECT 'session_summary' AS base_table, CAST(session_ip AS varchar) AS ip, try_cast(session_date AS date) AS d FROM unified.unified_session_summary
  UNION ALL
  SELECT 'tune_clicks', CAST(ip AS varchar), try_cast(datetime AS date) FROM raw.raw_tune_clicks
),
agg AS (
  SELECT ip, base_table, min(d) AS first_seen, max(d) AS last_seen, count(DISTINCT d) AS days_seen, count(*) AS rows_seen
  FROM src WHERE regexp_like(ip, '^[0-9]{1,3}(\.[0-9]{1,3}){3}$') GROUP BY 1, 2
)
SELECT base_table, count(*) AS ips, sum(rows_seen) AS rows_, min(first_seen) AS earliest, max(last_seen) AS latest,
       count_if(last_seen >= current_date - interval '90' day) AS seen_90d
FROM agg GROUP BY 1
