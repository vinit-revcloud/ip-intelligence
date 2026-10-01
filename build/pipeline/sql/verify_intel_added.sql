SELECT vendor,
  count(*) AS rows_now,
  count_if(is_proxy IS NULL AND is_bot IS NULL AND is_datacenter IS NULL) AS rows_with_no_answer
FROM ipintel_curated.ip_intelligence GROUP BY vendor ORDER BY vendor
