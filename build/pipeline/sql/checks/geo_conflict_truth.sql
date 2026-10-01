WITH lead AS (SELECT ip_address, max(lead_state) st, max(lead_city) ct FROM ipintel_curated.qualified_lead_ips WHERE has_full_address GROUP BY 1),
g AS (SELECT ip_address, vendor, lower(trim(state)) s, regexp_replace(lower(normalize(city,NFKD)),'[^a-z]','') c, latitude lat, longitude lon FROM ipintel_curated.ip_geo WHERE state IS NOT NULL),
pairs AS (
  SELECT l.ip_address, a.vendor va, b.vendor vb, a.s = b.s same_state, a.c = b.c same_city,
    2*6371*asin(sqrt(power(sin(radians(b.lat-a.lat)/2),2)+cos(radians(a.lat))*cos(radians(b.lat))*power(sin(radians(b.lon-a.lon)/2),2))) km,
    a.s = lower(l.st) a_state_ok, b.s = lower(l.st) b_state_ok,
    a.c = regexp_replace(lower(l.ct),'[^a-z]','') a_city_ok, b.c = regexp_replace(lower(l.ct),'[^a-z]','') b_city_ok
  FROM lead l JOIN g a ON a.ip_address = l.ip_address JOIN g b ON b.ip_address = l.ip_address AND a.vendor < b.vendor)
SELECT va || ' vs ' || vb pair,
  CASE WHEN same_state AND same_city THEN '1 agree' WHEN same_state AND km <= 25 THEN '2 same state <=25km'
       WHEN same_state THEN '3 same state >25km' ELSE '4 different state' END kind,
  count(*) n, count_if(a_state_ok) a_state_right, count_if(b_state_ok) b_state_right,
  count_if(a_city_ok) a_city_right, count_if(b_city_ok) b_city_right
FROM pairs GROUP BY 1, 2 ORDER BY 1, 2
