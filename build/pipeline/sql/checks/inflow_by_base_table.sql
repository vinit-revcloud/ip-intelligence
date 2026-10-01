SELECT base_table, cast(first_seen AS varchar) d, count(DISTINCT ip_address) new_ips
FROM ipintel_curated.ip_occurrences WHERE first_seen >= date '2026-09-01' GROUP BY 1,2
UNION ALL SELECT base_table, 'max_last_seen:' || cast(max(last_seen) AS varchar), count(DISTINCT ip_address) FROM ipintel_curated.ip_occurrences GROUP BY 1
ORDER BY 1,2
