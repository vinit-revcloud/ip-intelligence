-- Read only. Is every IP in each source table mapped correctly into our tables?
-- Uses the same IP / date reading as the pipeline (_source_select), and only source rows dated before today,
-- so rows that arrived after today's 13:00 IST load are not counted as misses.
WITH src AS (
  SELECT 'tune_clicks' AS bt, CAST(ip AS varchar) AS ip, try_cast(datetime AS date) AS d FROM raw.raw_tune_clicks
  UNION ALL SELECT 'session_summary', CAST(session_ip AS varchar), try_cast(session_date AS date) FROM unified.unified_session_summary
  UNION ALL SELECT 'router_events', CAST(ip_address AS varchar), try_cast(server_timestamp_entry AS date) FROM experimentation_tools.experiment_router_events),
s AS (SELECT bt, ip, min(d) AS first_d, max(d) AS last_d FROM src
      WHERE regexp_like(ip, '^[0-9]{1,3}(\.[0-9]{1,3}){3}$') AND d < date '2026-09-21' GROUP BY 1, 2),
occ AS (SELECT base_table AS bt, ip_address AS ip, first_seen, last_seen FROM ipintel_curated.ip_occurrences),
pub AS (SELECT DISTINCT ip FROM s WHERE NOT (try_cast(split_part(ip, '.', 1) AS integer) IN (0, 10, 127) OR try_cast(split_part(ip, '.', 1) AS integer) >= 224 OR (try_cast(split_part(ip, '.', 1) AS integer) = 100 AND try_cast(split_part(ip, '.', 2) AS integer) BETWEEN 64 AND 127) OR (try_cast(split_part(ip, '.', 1) AS integer) = 169 AND try_cast(split_part(ip, '.', 2) AS integer) = 254) OR (try_cast(split_part(ip, '.', 1) AS integer) = 172 AND try_cast(split_part(ip, '.', 2) AS integer) BETWEEN 16 AND 31) OR (try_cast(split_part(ip, '.', 1) AS integer) = 192 AND try_cast(split_part(ip, '.', 2) AS integer) = 168) OR (try_cast(split_part(ip, '.', 1) AS integer) = 192 AND try_cast(split_part(ip, '.', 2) AS integer) = 0 AND try_cast(split_part(ip, '.', 3) AS integer) IN (0, 2)) OR (try_cast(split_part(ip, '.', 1) AS integer) = 198 AND try_cast(split_part(ip, '.', 2) AS integer) IN (18, 19)) OR (try_cast(split_part(ip, '.', 1) AS integer) = 198 AND try_cast(split_part(ip, '.', 2) AS integer) = 51 AND try_cast(split_part(ip, '.', 3) AS integer) = 100) OR (try_cast(split_part(ip, '.', 1) AS integer) = 203 AND try_cast(split_part(ip, '.', 2) AS integer) = 0 AND try_cast(split_part(ip, '.', 3) AS integer) = 113))),
ui AS (SELECT ip_address AS ip, count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND is_bot IS NOT NULL) AS reliable,
              count_if(vendor = 'proxycheck_io') AS pc FROM unified.ip_intelligence GROUP BY 1),
ug AS (SELECT DISTINCT ip_address AS ip FROM unified.ip_geo),
-- FraudLogix: the latest decided click per IP, as the pipeline defines it
fl_k AS (SELECT ip, access_control_decision AS dec, access_control_reason_code AS rsn,
                format_datetime(datetime, 'yyyy-MM-dd HH:mm:ss.SSSSSS') || '|' || CASE WHEN access_control_decision = 'FLAGGED' THEN '1' ELSE '0' END
                  || '|' || coalesce(access_control_reason_code, '') AS pick
         FROM raw.raw_tune_clicks WHERE coalesce(access_control_decision, '') <> '' AND try_cast(datetime AS date) < date '2026-09-21'),
fl_src AS (SELECT ip, max_by(dec, pick) AS dec, max_by(rsn, pick) AS rsn FROM fl_k GROUP BY ip),
fl_row AS (SELECT i.ip_address AS ip, i.is_bot, i.flagged_reason FROM unified.ip_intelligence i WHERE i.vendor = 'fraudlogix_tune')
SELECT 'A. ' || bt || ': IPv4 addresses in the source' AS check_, count(*) AS value FROM s GROUP BY bt
UNION ALL SELECT 'B. ' || s.bt || ': missing from ip_occurrences', count_if(o.ip IS NULL) FROM s LEFT JOIN occ o ON o.bt = s.bt AND o.ip = s.ip GROUP BY s.bt
UNION ALL SELECT 'C. ' || s.bt || ': last_seen older than the source', count_if(o.last_seen < s.last_d) FROM s JOIN occ o ON o.bt = s.bt AND o.ip = s.ip GROUP BY s.bt
UNION ALL SELECT 'D. ' || s.bt || ': first_seen later than the source', count_if(o.first_seen > s.first_d) FROM s JOIN occ o ON o.bt = s.bt AND o.ip = s.ip GROUP BY s.bt
UNION ALL SELECT 'E. ' || o.bt || ': occurrence rows with no such IP in the source', count(*) FROM occ o LEFT JOIN (SELECT DISTINCT bt, ip FROM src) x ON x.bt = o.bt AND x.ip = o.ip WHERE x.ip IS NULL GROUP BY o.bt
UNION ALL SELECT 'F. public IPs (all sources) missing from unified.ip_geo', count_if(g.ip IS NULL) FROM pub p LEFT JOIN ug g ON g.ip = p.ip
UNION ALL SELECT 'G. public IPs missing from unified.ip_intelligence', count_if(u.ip IS NULL) FROM pub p LEFT JOIN ui u ON u.ip = p.ip
UNION ALL SELECT 'H. public IPs without a reliable verdict (FraudLogix or proxycheck.io)', count_if(coalesce(u.reliable, 0) = 0) FROM pub p LEFT JOIN ui u ON u.ip = p.ip
UNION ALL SELECT 'I. public IPs without a proxycheck.io row', count_if(coalesce(u.pc, 0) = 0) FROM pub p LEFT JOIN ui u ON u.ip = p.ip
UNION ALL SELECT 'J. FraudLogix: decided IPs', count(*) FROM fl_src
UNION ALL SELECT 'K. FraudLogix: decided IPs with no FraudLogix row', count_if(r.ip IS NULL) FROM fl_src f LEFT JOIN fl_row r ON r.ip = f.ip
UNION ALL SELECT 'L. FraudLogix: row is_bot differs from latest decision', count_if(r.is_bot IS DISTINCT FROM (f.dec = 'FLAGGED')) FROM fl_src f JOIN fl_row r ON r.ip = f.ip
UNION ALL SELECT 'M. FraudLogix: row reason differs from latest decision', count_if(r.flagged_reason IS DISTINCT FROM CASE WHEN f.dec = 'FLAGGED' THEN f.rsn ELSE 'NOT_FLAGGED' END) FROM fl_src f JOIN fl_row r ON r.ip = f.ip
UNION ALL SELECT 'N. FraudLogix rows for IPs never clicked', count_if(t.ip IS NULL) FROM fl_row r LEFT JOIN (SELECT DISTINCT CAST(ip AS varchar) AS ip FROM raw.raw_tune_clicks) t ON t.ip = r.ip
UNION ALL SELECT 'O. source IPs with spaces around them (read as-is)', count(*) FROM (SELECT DISTINCT ip FROM src WHERE ip <> trim(ip) AND ip IS NOT NULL)
ORDER BY 1
