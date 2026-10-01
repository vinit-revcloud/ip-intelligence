WITH occ AS (SELECT ip_address, max(last_seen) ls FROM ipintel_curated.ip_occurrences GROUP BY 1)
SELECT r.geo_status, count(*) n,
  count_if(NOT EXISTS (SELECT 1 FROM ipintel_curated.ip_geo g WHERE g.ip_address = r.ip_address AND g.vendor IN ('ipinfo_io','ipwho_is'))) without_web_vote
FROM ipintel_curated.ip_resolved r JOIN occ o ON o.ip_address = r.ip_address
WHERE o.ls >= date '2026-08-17' GROUP BY 1 ORDER BY 2 DESC
