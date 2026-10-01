-- Read only. For recent sessions: can the IP be resolved today by an acceptable vendor?
-- Acceptable = FraudLogix decided, or proxycheck.io answered (IP2Proxy PX12 does not count).
-- 'unified' shows what the teammate's API can see; 'curated' is our working copy (published after each run).
WITH s AS (
  SELECT session_id, session_ip AS ip, session_date
  FROM unified.unified_session_summary
  WHERE session_date >= date_add('day', -45, current_date) AND nullif(session_ip, '') IS NOT NULL),
u AS (
  SELECT ip_address,
         count_if(vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL) AS fl,
         count_if(vendor = 'proxycheck_io' AND is_proxy IS NOT NULL) AS pc
  FROM unified.ip_intelligence GROUP BY ip_address),
k AS (
  SELECT ip_address,
         count_if(vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL) AS fl,
         count_if(vendor = 'proxycheck_io' AND is_proxy IS NOT NULL) AS pc
  FROM ipintel_curated.ip_intelligence GROUP BY ip_address)
SELECT
  CASE WHEN session_date >= date_add('day', -30, current_date) THEN 'last 30 days' ELSE 'days 31-45' END AS window,
  count(*) AS sessions,
  count(DISTINCT s.ip) AS ips,
  count_if(coalesce(u.fl, 0) > 0) AS unified_fraudlogix,
  count_if(coalesce(u.fl, 0) = 0 AND coalesce(u.pc, 0) > 0) AS unified_proxycheck_only,
  count_if(coalesce(u.fl, 0) = 0 AND coalesce(u.pc, 0) = 0) AS unified_unresolved,
  count_if(coalesce(k.fl, 0) = 0 AND coalesce(k.pc, 0) = 0) AS curated_unresolved
FROM s LEFT JOIN u ON u.ip_address = s.ip LEFT JOIN k ON k.ip_address = s.ip
GROUP BY 1 ORDER BY 1
