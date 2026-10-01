-- Read only. Does FraudLogix give the same IP different answers over time?
WITH d AS (SELECT ip, access_control_decision AS dec, access_control_reason_code AS rsn, datetime
           FROM raw.raw_tune_clicks WHERE coalesce(access_control_decision, '') <> '' AND nullif(ip, '') IS NOT NULL),
p AS (SELECT ip, count(*) AS n, count(DISTINCT dec) AS decs, count(DISTINCT coalesce(rsn, '-')) AS rsns,
             count(DISTINCT date(datetime)) AS days,
             max_by(dec, datetime) AS last_dec, max_by(rsn, datetime) AS last_rsn,
             count_if(rsn IN ('BOT_GENERATED','NON_HUMAN_SCRIPT','DATA_CENTER','SPOOFED','TOR','TOR_EXIT_NODE')) AS bot_clicks
      FROM d GROUP BY ip)
SELECT count(*) AS decided_ips,
       count_if(n = 1) AS one_click, count_if(n BETWEEN 2 AND 10) AS clicks_2_10, count_if(n > 10) AS clicks_over_10,
       count_if(decs > 1) AS ips_with_mixed_decisions,
       count_if(rsns > 1) AS ips_with_mixed_reasons,
       count_if(bot_clicks > 0) AS ips_ever_bot_reason,
       count_if(bot_clicks > 0 AND NOT (last_rsn IN ('BOT_GENERATED','NON_HUMAN_SCRIPT','DATA_CENTER','SPOOFED','TOR','TOR_EXIT_NODE') AND last_dec = 'FLAGGED')) AS ever_bot_but_latest_not_bot,
       approx_percentile(n, ARRAY[0.5, 0.9, 0.99]) AS clicks_per_ip_p50_p90_p99,
       max(n) AS max_clicks_one_ip
FROM p
