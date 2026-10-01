SELECT vendor, count(*) rows_, sum(CASE WHEN has_answer THEN 1 ELSE 0 END) answered,
 sum(CASE WHEN truth_state IS NOT NULL THEN 1 ELSE 0 END) with_truth,
 sum(CASE WHEN truth_state IS NOT NULL AND has_answer THEN 1 ELSE 0 END) truth_answered,
 count(DISTINCT truth_state) states,
 round(100.0*avg(CASE WHEN truth_state IS NOT NULL AND has_answer THEN CASE WHEN state_matches_truth THEN 1 ELSE 0 END END),1) st,
 round(100.0*avg(CASE WHEN truth_city IS NOT NULL AND has_answer THEN CASE WHEN city_matches_truth THEN 1 ELSE 0 END END),1) ci,
 round(100.0*avg(CASE WHEN truth_zip IS NOT NULL AND has_answer THEN CASE WHEN zip_matches_truth THEN 1 ELSE 0 END END),1) zi
FROM ipintel_curated.ip_geo_analytics GROUP BY 1
UNION ALL SELECT 'overview:'||vendor, ips_tested, null, null, null, null, state_truth_pct, city_truth_pct, zip_truth_pct FROM ipintel_curated.vendor_overview_geo
