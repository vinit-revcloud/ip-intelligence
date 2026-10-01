-- Read only. What exactly is empty for the incomplete IPs?
WITH base AS (SELECT ip_address, max(last_seen) AS last_seen FROM ipintel_curated.ip_occurrences GROUP BY ip_address),
risk AS (SELECT ip_address,
           count_if(vendor IN ('fraudlogix_tune','proxycheck_io') AND is_proxy IS NOT NULL) AS acceptable,
           count_if(vendor='fraudlogix_tune') AS fl_rows,
           count_if(vendor='proxycheck_io') AS pc_rows,
           count_if(vendor='ip2proxy_px12' AND is_proxy IS NOT NULL) AS px
         FROM ipintel_curated.ip_intelligence GROUP BY ip_address),
geo AS (SELECT ip_address,
          count_if(nullif(state,'') IS NOT NULL OR nullif(city,'') IS NOT NULL) AS filled,
          count(*) AS rows_any,
          count_if(vendor='ip2location_db11') AS db11_rows
        FROM ipintel_curated.ip_geo GROUP BY ip_address)
SELECT 'no acceptable risk answer' AS gap, count(*) AS ips,
       count_if(b.last_seen >= date_add('day',-90,current_date)) AS seen_90d,
       count_if(r.pc_rows > 0) AS has_proxycheck_row, count_if(r.fl_rows > 0) AS has_fraudlogix_row
FROM base b JOIN risk r ON r.ip_address=b.ip_address
WHERE r.acceptable = 0
UNION ALL
SELECT 'no usable location', count(*),
       count_if(b.last_seen >= date_add('day',-90,current_date)),
       count_if(r.pc_rows > 0), count_if(g.db11_rows > 0)
FROM base b JOIN geo g ON g.ip_address=b.ip_address JOIN risk r ON r.ip_address=b.ip_address
WHERE g.filled = 0 AND r.acceptable > 0
