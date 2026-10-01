-- Read only. The few addresses that are in our tables but not (or no longer) in the two base tables.
WITH u AS (SELECT ip FROM raw.raw_tune_clicks UNION SELECT session_ip FROM unified.unified_session_summary),
g AS (SELECT DISTINCT ip_address FROM unified.ip_geo),
i AS (SELECT ip_address, array_join(array_agg(DISTINCT vendor), ',') AS vendors, max(created_at) AS created
      FROM unified.ip_intelligence GROUP BY ip_address)
SELECT 'in ip_intelligence only' AS k, i.ip_address, i.vendors, i.created FROM i
  WHERE i.ip_address NOT IN (SELECT ip_address FROM g)
UNION ALL
SELECT 'in tables, not in base tables now', g.ip_address, NULL, NULL FROM g WHERE g.ip_address NOT IN (SELECT ip FROM u WHERE ip IS NOT NULL)
