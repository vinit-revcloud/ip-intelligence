WITH d AS (
  SELECT g.ip_address, count(DISTINCT lower(trim(g.state))) AS states, count(DISTINCT g.vendor) AS vendors
  FROM ipintel_curated.ip_resolved r
  JOIN ipintel_curated.ip_geo g ON g.ip_address = r.ip_address
  WHERE r.geo_status = 'vendors_disagree' AND nullif(trim(g.state), '') IS NOT NULL
  GROUP BY 1)
SELECT count(*) AS disagreeing_addresses, count_if(states = 1) AS same_state_different_city, count_if(states > 1) AS different_state
FROM d
