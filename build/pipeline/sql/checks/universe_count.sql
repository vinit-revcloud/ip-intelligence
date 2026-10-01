-- Read only. Where the ~4.96M unique IPs come from, and why ip_geo and ip_intelligence differ by one.
WITH clicks AS (SELECT DISTINCT ip FROM raw.raw_tune_clicks WHERE nullif(ip,'') IS NOT NULL),
sess AS (SELECT DISTINCT session_ip AS ip FROM unified.unified_session_summary WHERE nullif(session_ip,'') IS NOT NULL),
u AS (SELECT ip FROM clicks UNION SELECT ip FROM sess),
g AS (SELECT DISTINCT ip_address FROM unified.ip_geo),
i AS (SELECT DISTINCT ip_address FROM unified.ip_intelligence)
SELECT 'distinct IPs in raw_tune_clicks' AS k, count(*) AS n FROM clicks
UNION ALL SELECT 'distinct IPs in unified_session_summary', count(*) FROM sess
UNION ALL SELECT 'union of both (the universe)', count(*) FROM u
UNION ALL SELECT 'universe: IPv4 format', count_if(regexp_like(ip, '^\d{1,3}(\.\d{1,3}){3}$')) FROM u
UNION ALL SELECT 'universe: not IPv4 (IPv6 / junk)', count_if(NOT regexp_like(ip, '^\d{1,3}(\.\d{1,3}){3}$')) FROM u
UNION ALL SELECT 'unique IPs in unified.ip_geo', count(*) FROM g
UNION ALL SELECT 'unique IPs in unified.ip_intelligence', count(*) FROM i
UNION ALL SELECT 'in ip_intelligence but not ip_geo', count(*) FROM i WHERE ip_address NOT IN (SELECT ip_address FROM g)
UNION ALL SELECT 'in ip_geo but not ip_intelligence', count(*) FROM g WHERE ip_address NOT IN (SELECT ip_address FROM i)
UNION ALL SELECT 'universe IPv4 not in ip_geo', count(*) FROM u
  WHERE regexp_like(ip, '^\d{1,3}(\.\d{1,3}){3}$') AND ip NOT IN (SELECT ip_address FROM g)
