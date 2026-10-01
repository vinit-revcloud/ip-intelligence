SELECT count(*) AS intelligence_rows_missing_an_analytics_row
FROM ipintel_curated.ip_intelligence i
WHERE NOT EXISTS (SELECT 1 FROM ipintel_curated.ip_intelligence_analytics a
                  WHERE a.ip_address = i.ip_address AND a.vendor = i.vendor)
