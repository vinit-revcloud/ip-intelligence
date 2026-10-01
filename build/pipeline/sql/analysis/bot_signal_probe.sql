-- Read only. What the session behaviour columns look like, for sessions in the MoM window.
WITH s AS (
  SELECT * FROM unified.unified_session_summary
  WHERE session_date BETWEEN date '2026-06-18' AND date '2026-09-09' AND nullif(session_ip, '') IS NOT NULL)
SELECT
  count(*) AS sessions,
  arbitrary(typeof(duration_seconds)) AS t_dur, arbitrary(typeof(event_count)) AS t_ev, arbitrary(typeof(screen_width)) AS t_sw,
  arbitrary(typeof(has_otp_verified)) AS t_otp, arbitrary(typeof(is_bot_click)) AS t_bot,
  approx_percentile(CAST(duration_seconds AS double), ARRAY[0.1, 0.25, 0.5, 0.9]) AS dur_pcts,
  approx_percentile(CAST(event_count AS double), ARRAY[0.1, 0.25, 0.5, 0.9]) AS ev_pcts,
  count_if(duration_seconds IS NULL) AS dur_null,
  count_if(screen_width IS NULL OR CAST(screen_width AS varchar) IN ('', '0')) AS no_screen,
  count_if(nullif(browser_agent, '') IS NULL) AS no_agent,
  count_if(regexp_like(lower(browser_agent), 'bot|crawl|spider|headless|phantom|selenium|puppeteer|playwright|python|curl|wget|httpclient|java/|go-http|scrapy|lighthouse|preview')) AS agent_botlike,
  count_if(CAST(has_otp_verified AS varchar) = 'true') AS otp,
  count_if(nullif(consent_trustedform_url, '') IS NOT NULL) AS trustedform,
  count_if(nullif(consent_journaya_id, '') IS NOT NULL) AS jornaya,
  count_if(CAST(has_partial_lead AS varchar) = 'true') AS partial_lead,
  count_if(CAST(has_lead AS varchar) = 'true') AS has_lead,
  count_if(CAST(is_bot_click AS varchar) = 'true') AS bot_click,
  count_if(nullif(timezone, '') IS NULL) AS no_tz,
  arbitrary(timezone) AS tz_example, arbitrary(ip_time_zone) AS iptz_example,
  arbitrary(device_type) AS device_example, arbitrary(CAST(screen_width AS varchar)) AS sw_example,
  arbitrary(CAST(has_otp_verified AS varchar)) AS otp_example
FROM s
