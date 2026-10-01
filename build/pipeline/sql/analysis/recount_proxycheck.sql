WITH j AS (
  SELECT s.session_ip ip, l.expected_revenue rev FROM unified.unified_session_summary s
  JOIN sampledb.revenue_leads_plus l ON l.utm_content = s.session_id AND l.date_pst >= s.session_date AND l.date_pst >= date '2026-06-18'
  WHERE s.session_date BETWEEN date '2026-06-18' AND date '2026-09-09' AND nullif(s.session_ip,'') IS NOT NULL),
g AS (SELECT ip, sum(coalesce(rev,0)) > 0 human FROM j GROUP BY 1),
p AS (SELECT ip_address, (coalesce(is_proxy,false) OR coalesce(is_vpn,false) OR coalesce(is_tor,false) OR coalesce(is_datacenter,false) OR coalesce(is_bot,false) OR coalesce(is_compromised,false) OR coalesce(is_scraper,false)) f
      FROM ipintel_curated.ip_intelligence WHERE vendor = 'proxycheck_io')
SELECT count_if(f AND human) fp, count_if(NOT f AND human) tn, count_if(f AND NOT human) tp, count_if(NOT f AND NOT human) fn, count(*) n
FROM g JOIN p ON p.ip_address = g.ip
