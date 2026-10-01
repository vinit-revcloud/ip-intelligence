-- Read only. Which user agents does the router call bot? Top 25 agents among is_bot = 1, with how often they are also is_bot = 0.
SELECT substr(user_agent, 1, 140) AS agent, count_if(is_bot = 1) AS bot_events, count_if(is_bot = 0) AS not_bot_events,
       count(DISTINCT ip_address) AS ips
FROM experimentation_tools.experiment_router_events
GROUP BY 1 HAVING count_if(is_bot = 1) > 0 ORDER BY bot_events DESC LIMIT 25
