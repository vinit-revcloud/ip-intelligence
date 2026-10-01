-- Read only. raw.raw_tune_clicks: size, time span, FraudLogix decision coverage by month.
SELECT date_format(datetime, '%Y-%m') AS month, count(*) AS clicks, count(DISTINCT ip) AS ips,
       count_if(coalesce(access_control_decision, '') = '') AS no_decision,
       count_if(access_control_decision = 'FLAGGED') AS flagged,
       count_if(access_control_decision NOT IN ('FLAGGED', '')) AS other_decision,
       arbitrary(CASE WHEN access_control_decision NOT IN ('FLAGGED', '') THEN access_control_decision END) AS other_value,
       count_if(regexp_like(lower(user_agent), 'bot|crawl|spider|headless|phantom|selenium|puppeteer|playwright|python|curl|wget|httpclient|java/|go-http|scrapy|lighthouse|preview')) AS ua_botlike,
       count_if(try_cast(revenue_cents AS double) > 0) AS with_revenue
FROM raw.raw_tune_clicks GROUP BY 1 ORDER BY 1
