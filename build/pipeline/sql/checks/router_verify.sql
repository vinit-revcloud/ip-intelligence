-- Read only. After enabling the router source: are its IPs in the unified tables, and what do they have?
WITH r AS (SELECT DISTINCT trim(ip_address) AS ip FROM experimentation_tools.experiment_router_events
           WHERE regexp_like(trim(ip_address), '^\d{1,3}(\.\d{1,3}){3}$')),
g AS (SELECT DISTINCT ip_address FROM unified.ip_geo),
i AS (SELECT ip_address,
             count_if(vendor IN ('fraudlogix_tune','proxycheck_io') AND is_proxy IS NOT NULL) AS acceptable
      FROM unified.ip_intelligence GROUP BY ip_address),
o AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_occurrences WHERE base_table = 'router_events'),
q AS (SELECT DISTINCT ip_address FROM ipintel_curated.proxycheck_queue WHERE answered_at IS NULL)
SELECT count(*) AS router_ipv4,
       count_if(g.ip_address IS NOT NULL) AS in_unified_ip_geo,
       count_if(i.ip_address IS NOT NULL) AS in_unified_ip_intelligence,
       count_if(o.ip_address IS NOT NULL) AS has_router_occurrence,
       count_if(coalesce(i.acceptable, 0) > 0) AS acceptable_risk_answer,
       count_if(coalesce(i.acceptable, 0) = 0 AND q.ip_address IS NOT NULL) AS no_answer_but_queued,
       count_if(coalesce(i.acceptable, 0) = 0 AND q.ip_address IS NULL) AS no_answer_not_queued,
       (SELECT count(DISTINCT ip_address) FROM unified.ip_geo) AS unified_ip_geo_total
FROM r LEFT JOIN g ON g.ip_address = r.ip LEFT JOIN i ON i.ip_address = r.ip
       LEFT JOIN o ON o.ip_address = r.ip LEFT JOIN q ON q.ip_address = r.ip
