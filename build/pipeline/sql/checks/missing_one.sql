WITH seen AS (SELECT ip_address, max(last_seen) AS last_seen, max(base_table) AS bt FROM ipintel_curated.ip_occurrences
              WHERE last_seen >= date_add('day', -90, current_date) GROUP BY ip_address),
ans AS (SELECT ip_address, count_if(vendor IN ('fraudlogix_tune','proxycheck_io') AND has_answer) AS n,
               count_if(has_answer) AS any_n
        FROM ipintel_curated.ip_intelligence_analytics GROUP BY ip_address)
SELECT s.ip_address, s.last_seen, s.bt, coalesce(a.any_n, 0) AS any_vendor_answers,
       (SELECT count(*) FROM ipintel_curated.proxycheck_queue q WHERE q.ip_address = s.ip_address AND q.answered_at IS NULL) AS queued
FROM seen s LEFT JOIN ans a ON a.ip_address = s.ip_address
WHERE coalesce(a.n, 0) = 0
