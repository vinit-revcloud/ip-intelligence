-- Read only. How many public IPv4 router IPs are new to our tables, and how recent they are.
WITH r AS (
  SELECT trim(ip_address) AS ip, max(server_timestamp_entry) AS last_seen, max(is_bot) AS router_bot
  FROM experimentation_tools.experiment_router_events
  WHERE regexp_like(trim(ip_address), '^\d{1,3}(\.\d{1,3}){3}$') GROUP BY trim(ip_address)),
have AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_geo),
pc AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_intelligence WHERE vendor = 'proxycheck_io')
SELECT count(*) AS router_ipv4,
       count_if(h.ip_address IS NOT NULL) AS already_in_our_tables,
       count_if(h.ip_address IS NULL) AS new_to_append,
       count_if(h.ip_address IS NULL AND r.last_seen >= current_timestamp - interval '30' day) AS new_seen_last_30d,
       count_if(p.ip_address IS NULL) AS without_proxycheck_answer,
       count_if(r.router_bot = 1) AS router_says_bot
FROM r LEFT JOIN have h ON h.ip_address = r.ip LEFT JOIN pc p ON p.ip_address = r.ip
