-- Read only. What is is_bot_click? How it relates to behaviour, leads, revenue, and the session's IP.
SELECT CAST(is_bot_click AS varchar) AS is_bot_click, count(*) AS sessions, count(DISTINCT session_ip) AS ips,
       count_if(has_lead IN ('true', 'on', '1', 'yes')) AS with_lead,
       count_if(has_revenue IN ('true', 'on', '1', 'yes')) AS with_revenue,
       count_if(regexp_like(lower(browser_agent), 'bot|crawl|spider|headless|phantom|selenium|puppeteer|playwright|python|curl|wget|httpclient|java/|go-http|scrapy|lighthouse|preview')) AS ua_botlike,
       approx_percentile(duration_seconds, 0.5) AS median_duration, approx_percentile(event_count, 0.5) AS median_events,
       count_if(nullif(clickids_json, '') IS NOT NULL AND clickids_json NOT IN ('[]', '{}')) AS with_click_ids,
       arbitrary(clickids_json) AS click_ids_example
FROM unified.unified_session_summary GROUP BY 1
