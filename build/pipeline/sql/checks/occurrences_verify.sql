SELECT base_table, count(*) AS rows_, count(DISTINCT ip_address) AS ips, max(last_seen) AS latest,
       (SELECT count(*) FROM (SELECT ip_address, base_table FROM ipintel_curated.ip_occurrences GROUP BY 1, 2 HAVING count(*) > 1)) AS duplicate_pairs
FROM ipintel_curated.ip_occurrences GROUP BY base_table
