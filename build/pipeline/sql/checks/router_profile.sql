-- Read only. Profile of the new IP source experimentation_tools.experiment_router_events.
WITH r AS (SELECT * FROM experimentation_tools.experiment_router_events),
k AS (
  SELECT ip_address AS ip, server_timestamp_entry AS ts,
    CASE WHEN ip_address IS NULL OR trim(ip_address) = '' THEN 'empty'
         WHEN strpos(ip_address, ',') > 0 THEN 'list_of_ips'
         WHEN strpos(ip_address, ':') > 0 THEN 'ipv6'
         WHEN NOT regexp_like(trim(ip_address), '^\d{1,3}(\.\d{1,3}){3}$') THEN 'not_an_ip'
         WHEN regexp_like(trim(ip_address), '^(10\.|127\.|0\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|22[4-9]\.|2[3-5]\d\.)') THEN 'private_or_reserved'
         ELSE 'public_ipv4' END AS kind
  FROM r)
SELECT 'rows' AS metric, CAST(count(*) AS varchar) AS value FROM r
UNION ALL SELECT 'distinct ip_address', CAST(count(DISTINCT ip_address) AS varchar) FROM r
UNION ALL SELECT 'first server_timestamp_entry', CAST(min(server_timestamp_entry) AS varchar) FROM r
UNION ALL SELECT 'last server_timestamp_entry', CAST(max(server_timestamp_entry) AS varchar) FROM r
UNION ALL SELECT 'rows with null timestamp', CAST(count_if(server_timestamp_entry IS NULL) AS varchar) FROM r
UNION ALL SELECT 'rows in last 24h', CAST(count_if(server_timestamp_entry >= current_timestamp - interval '1' day) AS varchar) FROM r
UNION ALL SELECT 'rows in last 30 days', CAST(count_if(server_timestamp_entry >= current_timestamp - interval '30' day) AS varchar) FROM r
UNION ALL SELECT 'duplicate router_event_id', CAST(count(*) - count(DISTINCT router_event_id) AS varchar) FROM r
UNION ALL SELECT 'is_bot = 1 rows', CAST(count_if(is_bot = 1) AS varchar) FROM r
UNION ALL SELECT 'is_bot null rows', CAST(count_if(is_bot IS NULL) AS varchar) FROM r
UNION ALL SELECT 'distinct experiment_id', CAST(count(DISTINCT experiment_id) AS varchar) FROM r
UNION ALL SELECT 'ip kind: ' || kind, CAST(count(*) AS varchar) FROM k GROUP BY kind
UNION ALL SELECT 'distinct ip kind: ' || kind, CAST(count(DISTINCT ip) AS varchar) FROM k GROUP BY kind
UNION ALL SELECT 'ip has leading/trailing space', CAST(count_if(ip <> trim(ip)) AS varchar) FROM k
UNION ALL SELECT 'ip uppercase letters', CAST(count_if(ip <> lower(ip)) AS varchar) FROM k
ORDER BY 1
