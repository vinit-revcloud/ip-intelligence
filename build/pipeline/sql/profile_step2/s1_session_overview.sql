-- Read only. unified.unified_session_summary: size, span, the built-in bot / proxy fields, and value sets.
SELECT count(*) AS sessions, count(DISTINCT session_ip) AS ips, min(session_date) AS first_day, max(session_date) AS last_day,
       count_if(nullif(session_ip, '') IS NULL) AS no_ip,
       count_if(is_bot_click) AS bot_click_true, count_if(NOT is_bot_click) AS bot_click_false, count_if(is_bot_click IS NULL) AS bot_click_null,
       min(CASE WHEN is_bot_click IS NOT NULL THEN session_date END) AS bot_click_first_day,
       histogram(ip_is_proxy) AS ip_is_proxy_values, histogram(ip_is_vpn) AS ip_is_vpn_values,
       histogram(has_lead) AS has_lead_values, histogram(has_revenue) AS has_revenue_values,
       histogram(device_type) AS device_type_values,
       count_if(regexp_like(lower(browser_agent), 'bot|crawl|spider|headless|phantom|selenium|puppeteer|playwright|python|curl|wget|httpclient|java/|go-http|scrapy|lighthouse|preview')) AS ua_botlike,
       count_if(nullif(browser_agent, '') IS NULL) AS no_agent,
       approx_percentile(duration_seconds, ARRAY[0.1, 0.5, 0.9]) AS duration_p10_p50_p90,
       approx_percentile(event_count, ARRAY[0.1, 0.5, 0.9]) AS events_p10_p50_p90,
       count_if(duration_seconds = 0) AS zero_duration, count_if(event_count <= 1) AS one_event
FROM unified.unified_session_summary
