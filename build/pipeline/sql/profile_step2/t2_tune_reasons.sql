-- Read only. Every FraudLogix decision / reason pair, rows and IPs, last 12 months vs all.
SELECT coalesce(nullif(access_control_decision, ''), '(empty)') AS decision,
       coalesce(nullif(access_control_reason_code, ''), '(empty)') AS reason,
       count(*) AS clicks, count(DISTINCT ip) AS ips,
       count_if(datetime >= current_timestamp - interval '365' day) AS clicks_12m,
       count_if(try_cast(revenue_cents AS double) > 0) AS clicks_with_revenue,
       min(date_pst) AS first_day, max(date_pst) AS last_day
FROM raw.raw_tune_clicks GROUP BY 1, 2 ORDER BY clicks DESC
