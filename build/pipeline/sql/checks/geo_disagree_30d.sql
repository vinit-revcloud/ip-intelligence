WITH occ AS (SELECT ip_address, max(last_seen) ls FROM ipintel_curated.ip_occurrences GROUP BY 1),
w AS (SELECT r.ip_address FROM ipintel_curated.ip_resolved r JOIN occ o ON o.ip_address=r.ip_address
      WHERE o.ls >= date '2026-08-17' AND r.geo_status NOT IN ('agreed','single_source')),
d AS (SELECT g.ip_address, g.state, g.city, g.latitude lat, g.longitude lon FROM ipintel_curated.ip_geo g JOIN w ON w.ip_address=g.ip_address WHERE g.vendor='ip2location_db11'),
p AS (SELECT g.ip_address, g.state, g.city, g.latitude lat, g.longitude lon FROM ipintel_curated.ip_geo g JOIN w ON w.ip_address=g.ip_address WHERE g.vendor='proxycheck_io'),
x AS (SELECT d.ip_address,
  lower(d.state)=lower(p.state) same_state,
  lower(normalize(d.state, NFD)) = lower(normalize(p.state, NFD)) st_raw,
  regexp_replace(lower(normalize(d.city,NFKD)),'[^a-z]','') = regexp_replace(lower(normalize(p.city,NFKD)),'[^a-z]','') same_city_norm,
  d.city IS NULL OR p.city IS NULL OR d.state IS NULL OR p.state IS NULL missing,
  2*6371*asin(sqrt(power(sin(radians(p.lat-d.lat)/2),2)+cos(radians(d.lat))*cos(radians(p.lat))*power(sin(radians(p.lon-d.lon)/2),2))) km,
  d.state ds, p.state ps, d.city dc, p.city pc
  FROM d JOIN p ON p.ip_address=d.ip_address)
SELECT CASE WHEN missing THEN 'a_missing_field'
            WHEN same_city_norm AND same_state THEN 'b_same_city_after_normalising'
            WHEN same_state AND km <= 25 THEN 'c_same_state_within_25km'
            WHEN same_state AND km <= 50 THEN 'd_same_state_25_50km'
            WHEN same_state AND km <= 100 THEN 'e_same_state_50_100km'
            WHEN same_state THEN 'f_same_state_over_100km'
            WHEN km <= 50 THEN 'g_diff_state_name_within_50km'
            ELSE 'h_different_state_far' END bucket,
  count(*) n, approx_percentile(km, 0.5) med_km,
  regexp_replace(normalize(array_join(slice(array_agg(ds||'/'||dc||' vs '||ps||'/'||pc), 1, 3), ' | '),NFKD),'[^ -~]','') ex
FROM x GROUP BY 1
UNION ALL SELECT 'z_total_window_disagree', count(*), null, null FROM w
UNION ALL SELECT 'z_without_both_vendors', count(*), null, null FROM w WHERE ip_address NOT IN (SELECT ip_address FROM d JOIN p USING (ip_address))
ORDER BY 1
