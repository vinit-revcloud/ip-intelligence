-- Read only. Per IP: do the built-in bot fields (session is_bot_click, router is_bot) agree with each other
-- and with the vendor is_bot in unified.ip_intelligence? And how do they relate to revenue (known humans)?
WITH s AS (SELECT trim(session_ip) AS ip, bool_or(is_bot_click) AS s_bot, bool_or(NOT is_bot_click) AS s_notbot,
                  bool_or(has_revenue IN ('true', 'on', '1', 'yes')) AS paid
           FROM unified.unified_session_summary WHERE nullif(trim(session_ip), '') IS NOT NULL GROUP BY 1),
r AS (SELECT trim(ip_address) AS ip, bool_or(is_bot = 1) AS r_bot, bool_or(is_bot = 0) AS r_notbot
      FROM experimentation_tools.experiment_router_events WHERE nullif(trim(ip_address), '') IS NOT NULL GROUP BY 1),
v AS (SELECT ip_address AS ip,
             max(CASE WHEN vendor = 'fraudlogix_tune' THEN CAST(is_bot AS integer) END) AS fl_bot,
             max(CASE WHEN vendor = 'proxycheck_io' THEN CAST(is_bot AS integer) END) AS pc_bot
      FROM unified.ip_intelligence GROUP BY 1),
j AS (SELECT coalesce(s.ip, r.ip) AS ip, s.s_bot, s.s_notbot, s.paid, r.r_bot, r.r_notbot, v.fl_bot, v.pc_bot
      FROM s FULL JOIN r ON r.ip = s.ip LEFT JOIN v ON v.ip = coalesce(s.ip, r.ip))
SELECT CASE WHEN s_bot IS NULL THEN 'no session' WHEN s_bot AND s_notbot THEN 'session mixed' WHEN s_bot THEN 'session bot' ELSE 'session not bot' END AS session_says,
       CASE WHEN r_bot IS NULL THEN 'no router' WHEN r_bot AND r_notbot THEN 'router mixed' WHEN r_bot THEN 'router bot' ELSE 'router not bot' END AS router_says,
       count(*) AS ips, count_if(paid) AS paying_ips,
       count_if(fl_bot = 1) AS fl_bot, count_if(fl_bot = 0) AS fl_not_bot,
       count_if(pc_bot = 1) AS pc_bot, count_if(pc_bot = 0) AS pc_not_bot
FROM j GROUP BY 1, 2 ORDER BY ips DESC
