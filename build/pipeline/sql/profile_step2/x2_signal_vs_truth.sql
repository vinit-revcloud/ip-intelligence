-- Read only. Every candidate bot signal, per IP, against truth from the leads table (all time).
-- human = an IP with a linked lead that has expected_revenue > 0. fake = an IP with a linked lead marked fake.
WITH l AS (SELECT utm_content, expected_revenue, CAST(fake AS varchar) AS fake FROM sampledb.revenue_leads_plus),
sess AS (SELECT trim(session_ip) AS ip, session_id, is_bot_click FROM unified.unified_session_summary
         WHERE regexp_like(trim(session_ip), '^\d{1,3}(\.\d{1,3}){3}$')),
truth AS (SELECT s.ip, bool_or(l.expected_revenue > 0) AS paid, bool_or(l.fake IN ('true', '1', 't')) AS fake
          FROM sess s JOIN l ON l.utm_content = s.session_id GROUP BY 1 HAVING bool_or(l.expected_revenue > 0) OR bool_or(l.fake IN ('true', '1', 't'))),
sb AS (SELECT ip, bool_or(is_bot_click) AS session_bot FROM sess WHERE ip IN (SELECT ip FROM truth) GROUP BY 1),
rb AS (SELECT trim(ip_address) AS ip, bool_or(is_bot = 1) AS router_bot FROM experimentation_tools.experiment_router_events WHERE trim(ip_address) IN (SELECT ip FROM truth) GROUP BY 1),
fl AS (SELECT ip, max_by(access_control_decision, datetime) AS dec, max_by(access_control_reason_code, datetime) AS rsn,
              array_agg(DISTINCT access_control_reason_code) AS ever
       FROM raw.raw_tune_clicks WHERE coalesce(access_control_decision, '') <> '' AND ip IN (SELECT ip FROM truth) GROUP BY 1),
pc AS (SELECT ip_address AS ip, is_bot AS pc_bot, is_datacenter AS pc_dc, is_proxy OR is_vpn AS pc_pv
       FROM unified.ip_intelligence WHERE vendor = 'proxycheck_io' AND ip_address IN (SELECT ip FROM truth)),
j AS (SELECT t.*, sb.session_bot, rb.router_bot, fl.dec, fl.rsn, fl.ever, pc.pc_bot, pc.pc_dc, pc.pc_pv
      FROM truth t LEFT JOIN sb ON sb.ip = t.ip LEFT JOIN rb ON rb.ip = t.ip LEFT JOIN fl ON fl.ip = t.ip LEFT JOIN pc ON pc.ip = t.ip),
sig AS (
  SELECT ip, paid, fake, 'session is_bot_click' AS signal, session_bot AS hit FROM j
  UNION ALL SELECT ip, paid, fake, 'router is_bot', router_bot FROM j
  UNION ALL SELECT ip, paid, fake, 'FL latest = current bot rule', rsn IN ('BOT_GENERATED','NON_HUMAN_SCRIPT','DATA_CENTER','SPOOFED','TOR','TOR_EXIT_NODE') AND dec = 'FLAGGED' FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever BOT_GENERATED', contains(ever, 'BOT_GENERATED') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever NON_HUMAN_SCRIPT', contains(ever, 'NON_HUMAN_SCRIPT') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever ABNORMAL_TRAFFIC_PATTERNS', contains(ever, 'ABNORMAL_TRAFFIC_PATTERNS') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever BASIC_FRAUD', contains(ever, 'BASIC_FRAUD') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever MASKED_DEVICES', contains(ever, 'MASKED_DEVICES') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever code 10', contains(ever, '10') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever code 9', contains(ever, '9') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever DATA_CENTER', contains(ever, 'DATA_CENTER') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever SPOOFED', contains(ever, 'SPOOFED') FROM j
  UNION ALL SELECT ip, paid, fake, 'FL ever PROXY', contains(ever, 'PROXY') FROM j
  UNION ALL SELECT ip, paid, fake, 'proxycheck is_bot (current rule)', pc_bot FROM j
  UNION ALL SELECT ip, paid, fake, 'proxycheck proxy or vpn', pc_pv FROM j)
SELECT signal,
       count_if(paid) AS paying_ips, count_if(paid AND hit) AS paying_hit,
       round(100.0 * count_if(paid AND hit) / nullif(count_if(paid), 0), 2) AS pct_paying_hit,
       count_if(fake) AS fake_ips, count_if(fake AND hit) AS fake_hit,
       round(100.0 * count_if(fake AND hit) / nullif(count_if(fake), 0), 2) AS pct_fake_hit,
       count_if(hit IS NOT NULL) AS ips_with_signal_data
FROM sig GROUP BY 1 ORDER BY 1
