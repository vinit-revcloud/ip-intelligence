-- Read only. experimentation_tools.experiment_router_events: size, span, is_bot values and what goes with them.
SELECT CAST(is_bot AS varchar) AS is_bot, count(*) AS events, count(DISTINCT ip_address) AS ips,
       min(server_timestamp_entry) AS first_ts, max(server_timestamp_entry) AS last_ts,
       count_if(regexp_like(lower(user_agent), 'bot|crawl|spider|headless|phantom|selenium|puppeteer|playwright|python|curl|wget|httpclient|java/|go-http|scrapy|lighthouse|preview')) AS ua_botlike,
       count_if(nullif(user_agent, '') IS NULL) AS no_agent,
       histogram(device_type) AS device_types,
       count_if(is_error = 1) AS errors, count_if(is_experiment_found = 1) AS experiment_found,
       count_if(NOT regexp_like(coalesce(ip_address, ''), '^\d{1,3}(\.\d{1,3}){3}$')) AS not_ipv4
FROM experimentation_tools.experiment_router_events GROUP BY 1
