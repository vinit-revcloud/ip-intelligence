CREATE TABLE unified.vendor_overview_proxy
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/unified/vendor_overview_proxy/d=2026-09-11/') AS
-- Scored against a FIXED reference pool, not against whatever each vendor
-- happens to cover. The pool is the 2,105 benchmark addresses, and a vendor
-- with no row for one of them scores that as unanswered. Scoring each vendor
-- on its own footprint would make fill rate read 100% for everyone, which
-- measures nothing.
WITH pool AS (
  SELECT DISTINCT ip_address FROM ipintel_curated.qualified_lead_ips WHERE has_full_address
),
vendors AS (
  SELECT DISTINCT vendor FROM ipintel_curated.intel_src WHERE vendor <> 'proxycheck_io'
),
spine AS (SELECT p.ip_address, v.vendor FROM pool p CROSS JOIN vendors v)
SELECT s.vendor, count(*) ips_tested,
  sum(CASE WHEN coalesce(a.has_answer,false) THEN 1 ELSE 0 END) answered,
  round(100.0*sum(CASE WHEN coalesce(a.has_answer,false) THEN 1 ELSE 0 END)/count(*),1) fill_rate_pct,
  sum(CASE WHEN a.flagged THEN 1 ELSE 0 END) flagged,
  sum(CASE WHEN i.is_bot THEN 1 ELSE 0 END) bot_flagged,
  round(100.0*sum(CASE WHEN i.is_bot THEN 1 ELSE 0 END)
        /nullif(sum(CASE WHEN coalesce(a.has_answer,false) THEN 1 ELSE 0 END),0),1) bot_identification_pct,
  round(100.0*sum(CASE WHEN coalesce(i.is_bot,false) THEN 1 ELSE 0 END)
        /nullif(sum(CASE WHEN coalesce(a.has_answer,false) THEN 1 ELSE 0 END),0),1) false_positive_rate_pct,
  sum(CASE WHEN i.is_compromised THEN 1 ELSE 0 END) compromised_flagged,
  sum(CASE WHEN i.is_scraper THEN 1 ELSE 0 END) scraper_flagged,
  sum(CASE WHEN i.is_anonymous THEN 1 ELSE 0 END) anonymous_flagged,
  round(100.0*sum(CASE WHEN a.flagged AND a.known_infrastructure THEN 1 ELSE 0 END)
        /nullif(sum(CASE WHEN a.flagged THEN 1 ELSE 0 END),0),1) precision_infra_pct,
  round(100.0*sum(CASE WHEN a.flagged AND a.known_infrastructure THEN 1 ELSE 0 END)
        /nullif(sum(CASE WHEN a.known_infrastructure THEN 1 ELSE 0 END),0),1) recall_infra_pct,
  CAST(NULL AS double) precision_bot_pct, CAST(NULL AS double) recall_bot_pct,
  'needs a bot-labelled pool' bot_metric_status,
  CAST('0.00' AS varchar) cost_per_1k,
  -- Agreement only, with unanswered rows excluded from the average. This is the
  -- formula the proxy board has always used. The geo board multiplies by fill
  -- rate and this one does not; that inconsistency predates this change and is
  -- left alone rather than altered silently.
  round(avg(CASE WHEN NOT coalesce(a.has_answer,false) THEN NULL
                 WHEN a.verdict_class IN ('confirmed_by_published_range','agreed_not_flagged')
                      THEN 100.0 ELSE 0.0 END), 1) score,
  CAST(current_date AS varchar) as_of_date
FROM spine s
LEFT JOIN unified.ip_intelligence i ON i.ip_address=s.ip_address AND i.vendor=s.vendor
LEFT JOIN unified.ip_intelligence_analytics a ON a.ip_address=s.ip_address AND a.vendor=s.vendor
GROUP BY s.vendor
