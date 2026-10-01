CREATE TABLE ipintel_curated.ip_resolved
WITH (table_type='ICEBERG', is_external=false, format='PARQUET', write_compression='SNAPPY', location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/ip_resolved/', partitioning=ARRAY['bucket(ip_address, 64)']) AS
SELECT r.*, CAST('2026-09-14T21:30:00Z' AS varchar) AS updated_at FROM (
WITH scores AS (SELECT vendor, coalesce(max(score), 0) AS score FROM ipintel_curated.vendor_overview_geo GROUP BY vendor),
ga AS (
  SELECT g.ip_address, g.vendor, g.state, g.city, g.zip_code, g.latitude, g.longitude, g.timezone,
         coalesce(s.score, 0) AS score, g.vendor <> 'geojs_io' AS votes,
         nullif(lower(trim(g.state)), '') AS nstate,
         regexp_extract(regexp_replace(lower(coalesce(g.city, '')), '[^a-z ]', ''), '[a-z]+') AS ncity
  FROM ipintel_curated.ip_geo g LEFT JOIN scores s ON s.vendor = g.vendor
  WHERE nullif(trim(g.state), '') IS NOT NULL OR nullif(trim(g.city), '') IS NOT NULL OR g.latitude IS NOT NULL),
voters AS (SELECT ip_address, count_if(votes) AS nvoters, count(*) AS nanswered FROM ga GROUP BY ip_address),
pool AS (SELECT ga.* FROM ga JOIN voters v ON v.ip_address = ga.ip_address WHERE ga.votes OR v.nvoters = 0),
grp AS (
  SELECT ip_address, nstate, ncity, count(*) AS n, max(score) AS best, min(vendor) AS first_vendor,
         array_sort(array_agg(vendor)) AS vendors
  FROM pool GROUP BY ip_address, nstate, ncity),
bestgrp AS (
  SELECT * FROM (SELECT grp.*, row_number() OVER (PARTITION BY ip_address ORDER BY n DESC, best DESC, first_vendor) AS rn
                 FROM grp) WHERE rn = 1),
pick AS (
  SELECT * FROM (
    SELECT p.*, b.n, b.vendors,
           row_number() OVER (PARTITION BY p.ip_address ORDER BY p.score DESC, p.vendor) AS rn
    FROM pool p JOIN bestgrp b ON b.ip_address = p.ip_address
     AND p.nstate IS NOT DISTINCT FROM b.nstate AND p.ncity IS NOT DISTINCT FROM b.ncity) WHERE rn = 1),
geo_res AS (
  SELECT k.ip_address, k.state, k.city, k.zip_code, k.latitude, k.longitude, k.timezone,
         k.vendor AS geo_decided_by, array_join(k.vendors, ',') AS geo_agreeing_vendors,
         v.nanswered AS geo_vendors_answered,
         CASE WHEN k.n >= 2 THEN 'agreed' WHEN v.nvoters <= 1 THEN 'single_source' ELSE 'vendors_disagree' END AS geo_status
  FROM pick k JOIN voters v ON v.ip_address = k.ip_address),
ia AS (SELECT i.*, (coalesce(i.is_proxy, false) OR coalesce(i.is_vpn, false) OR coalesce(i.is_tor, false) OR coalesce(i.is_datacenter, false) OR coalesce(i.is_bot, false) OR coalesce(i.is_compromised, false) OR coalesce(i.is_scraper, false)) AS flagged FROM ipintel_curated.ip_intelligence i WHERE i.is_proxy IS NOT NULL),
pc AS (SELECT * FROM ia WHERE vendor = 'proxycheck_io'),
o AS (
  SELECT ip_address, count(*) AS n, count_if(flagged) AS nf,
         array_join(array_sort(array_agg(vendor)), ',') AS all_v,
         array_join(array_sort(filter(array_agg(CASE WHEN flagged THEN vendor END), x -> x IS NOT NULL)), ',') AS flagged_v,
         array_join(array_sort(filter(array_agg(CASE WHEN NOT flagged THEN vendor END), x -> x IS NOT NULL)), ',') AS clean_v
  FROM ia WHERE vendor <> 'proxycheck_io' GROUP BY ip_address),
l AS (SELECT * FROM ia WHERE vendor = 'authoritative_lists' AND flagged),
isp AS (
  SELECT ip_address,
         min_by(isp, CASE WHEN vendor = 'proxycheck_io' THEN '' ELSE vendor END) AS isp,
         min_by(asn, CASE WHEN vendor = 'proxycheck_io' THEN '' ELSE vendor END) AS asn
  FROM ia WHERE nullif(isp, '') IS NOT NULL GROUP BY ip_address),
risk AS (SELECT ip_address, max(risk_score) AS risk_score FROM ipintel_curated.ip_intelligence_analytics
         WHERE vendor = 'proxycheck_io' GROUP BY ip_address),
occ AS (
  SELECT ip_address, min(first_seen) AS first_seen, max(last_seen) AS last_seen,
         array_join(array_sort(array_agg(DISTINCT source_table)), ',') AS seen_in
  FROM ipintel_curated.ip_occurrences GROUP BY ip_address),
ips AS (SELECT ip_address FROM ipintel_curated.ip_geo UNION SELECT ip_address FROM ipintel_curated.ip_intelligence)
SELECT ips.ip_address,
  coalesce(gr.geo_status, 'no_answer') AS geo_status,
  gr.state, gr.city, gr.zip_code, gr.latitude, gr.longitude, gr.timezone,
  gr.geo_decided_by, coalesce(gr.geo_agreeing_vendors, '') AS geo_agreeing_vendors,
  coalesce(gr.geo_vendors_answered, 0) AS geo_vendors_answered,
  CASE WHEN pc.ip_address IS NOT NULL THEN
         CASE WHEN o.n IS NULL THEN 'proxycheck_only'
              WHEN (pc.flagged AND o.nf > 0) OR (NOT pc.flagged AND o.nf < o.n) THEN 'confirmed'
              ELSE 'proxycheck_overrides' END
       WHEN o.n IS NULL THEN 'no_answer'
       WHEN o.nf = 0 THEN 'clean_by_vendors'
       WHEN o.nf < o.n THEN 'vendors_disagree'
       WHEN l.ip_address IS NOT NULL THEN 'confirmed_by_published_range'
       ELSE 'flagged_unconfirmed' END AS proxy_status,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.flagged WHEN o.n IS NOT NULL AND o.nf = 0 THEN false
       WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN true END AS flagged,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_proxy WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_proxy END AS is_proxy,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_vpn WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_vpn END AS is_vpn,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_tor WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_tor END AS is_tor,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_datacenter WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_datacenter END AS is_datacenter,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_bot WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_bot END AS is_bot,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_compromised WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_compromised END AS is_compromised,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_scraper WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_scraper END AS is_scraper,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.is_anonymous WHEN o.n IS NOT NULL AND o.nf = 0 THEN false WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.is_anonymous END AS is_anonymous,
  CASE WHEN pc.ip_address IS NOT NULL THEN 'proxycheck_io' WHEN o.n IS NOT NULL AND o.nf = 0 THEN 'all answering vendors'
       WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN 'authoritative_lists' END AS proxy_decided_by,
  coalesce(CASE WHEN pc.ip_address IS NOT NULL THEN (CASE WHEN pc.flagged THEN o.flagged_v ELSE o.clean_v END)
                WHEN o.n IS NOT NULL AND o.nf = 0 THEN o.all_v
                WHEN o.n IS NOT NULL AND o.nf = o.n THEN o.flagged_v END, '') AS proxy_agreeing_vendors,
  coalesce(o.n, 0) + CASE WHEN pc.ip_address IS NOT NULL THEN 1 ELSE 0 END AS proxy_vendors_answered,
  isp.isp, isp.asn, risk.risk_score AS proxycheck_risk_score,
  coalesce(occ.seen_in, '') AS seen_in_base_tables, occ.first_seen, occ.last_seen
FROM ips
LEFT JOIN geo_res gr ON gr.ip_address = ips.ip_address
LEFT JOIN pc ON pc.ip_address = ips.ip_address
LEFT JOIN o ON o.ip_address = ips.ip_address
LEFT JOIN l ON l.ip_address = ips.ip_address
LEFT JOIN isp ON isp.ip_address = ips.ip_address
LEFT JOIN risk ON risk.ip_address = ips.ip_address
LEFT JOIN occ ON occ.ip_address = ips.ip_address
) r