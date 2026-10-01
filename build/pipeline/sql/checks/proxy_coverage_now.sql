WITH ans AS (SELECT ip_address, count_if(is_proxy IS NOT NULL) n_ans, count_if(vendor='proxycheck_io') pc
             FROM ipintel_curated.ip_intelligence GROUP BY 1),
s AS (SELECT session_ip ip, max(session_date) last_date, bool_or(nullif(experiment_id,'') IS NOT NULL) in_exp
      FROM unified.unified_session_summary WHERE nullif(session_ip,'') IS NOT NULL GROUP BY 1)
SELECT 'all addresses in our tables' k, count(*) ips, count_if(a.n_ans > 0) with_proxy_answer, count_if(a.pc > 0) with_proxycheck FROM ans a
UNION ALL SELECT 'session IPs, all time', count(*), count_if(a.n_ans > 0), count_if(a.pc > 0) FROM s LEFT JOIN ans a ON a.ip_address = s.ip
UNION ALL SELECT 'session IPs, last 90 days', count(*), count_if(a.n_ans > 0), count_if(a.pc > 0) FROM s LEFT JOIN ans a ON a.ip_address = s.ip WHERE s.last_date >= date '2026-06-18'
UNION ALL SELECT 'experiment session IPs, all time', count(*), count_if(a.n_ans > 0), count_if(a.pc > 0) FROM s LEFT JOIN ans a ON a.ip_address = s.ip WHERE s.in_exp
UNION ALL SELECT 'experiment session IPs, last 90 days', count(*), count_if(a.n_ans > 0), count_if(a.pc > 0) FROM s LEFT JOIN ans a ON a.ip_address = s.ip WHERE s.in_exp AND s.last_date >= date '2026-06-18'
