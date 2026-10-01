WITH s AS (
  SELECT session_id, session_ip, session_date, is_bot_click,
         sum(1) OVER (ORDER BY session_date DESC, session_id ROWS UNBOUNDED PRECEDING) AS cum
  FROM unified.unified_session_summary
  WHERE session_date <= date '2026-09-16' - interval '7' day AND session_date > date '2026-09-16' - interval '30' day
    AND nullif(session_ip, '') IS NOT NULL),
w AS (SELECT * FROM s WHERE cum <= 20000),
l AS (SELECT id, utm_content, expected_revenue, lead_status_category, furthest_stage, stage, fake, date_pst
      FROM sampledb.revenue_leads_plus WHERE date_pst >= date '2026-08-01')
SELECT min(w.session_date) first_day, max(w.session_date) last_day, count(*) sessions, count(DISTINCT w.session_ip) ips,
  count_if(w.is_bot_click) bot_click_sessions,
  count(DISTINCT l.id) leads, count(DISTINCT CASE WHEN l.id IS NOT NULL THEN w.session_ip END) ips_with_lead,
  count(DISTINCT CASE WHEN l.expected_revenue > 0 THEN w.session_ip END) ips_nonzero_rev,
  count(DISTINCT CASE WHEN l.lead_status_category IN ('intro_qualified','meeting','listing','closed') THEN w.session_ip END) ips_intro_plus,
  count(DISTINCT CASE WHEN l.fake OR l.stage IN ('fake','spam') THEN w.session_ip END) ips_fake_spam
FROM w LEFT JOIN l ON l.utm_content = w.session_id
