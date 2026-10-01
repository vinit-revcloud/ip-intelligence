WITH w AS (
  SELECT session_id, session_ip, session_date, is_bot_click, has_lead, has_partial_lead, furthest_stage AS sess_stage
  FROM unified.unified_session_summary
  WHERE session_date BETWEEN date '2026-09-04' AND date '2026-09-09' AND nullif(session_ip, '') IS NOT NULL),
l AS (SELECT id, utm_content, expected_revenue, lead_status_category, fake, stage
      FROM sampledb.revenue_leads_plus WHERE date_pst >= date '2026-09-04'),
ip AS (
  SELECT w.session_ip,
    count(DISTINCT w.session_id) sessions,
    count(DISTINCT l.id) leads,
    coalesce(sum(l.expected_revenue), 0) revenue,
    count_if(l.expected_revenue IS NULL AND l.id IS NOT NULL) null_rev_leads,
    bool_or(w.is_bot_click) any_bot_click,
    bool_or(w.has_lead = 'true') session_says_lead,
    bool_or(w.has_partial_lead = 'true') session_says_partial,
    max(CASE l.lead_status_category WHEN 'closed' THEN 5 WHEN 'listing' THEN 4 WHEN 'meeting' THEN 3 WHEN 'intro_qualified' THEN 2 WHEN 'below_intro' THEN 1 END) best_stage,
    bool_or(l.fake OR l.stage IN ('fake','spam')) fake_spam
  FROM w LEFT JOIN l ON l.utm_content = w.session_id GROUP BY 1)
SELECT
  CASE WHEN revenue > 0 THEN 'HUMAN: lead with revenue > 0'
       WHEN leads > 0 THEN 'BOT: lead(s), revenue = 0'
       ELSE 'BOT: no matching lead' END AS label,
  count(*) ips,
  count_if(any_bot_click) with_bot_click_session,
  count_if(session_says_lead) session_table_says_lead,
  count_if(session_says_partial) session_says_partial_lead,
  count_if(best_stage >= 2) stage_intro_qualified_plus,
  count_if(best_stage >= 3) stage_meeting_plus,
  count_if(null_rev_leads > 0) with_null_revenue_lead,
  count_if(fake_spam) fake_or_spam,
  count_if(sessions > 1) multi_session
FROM ip GROUP BY 1 ORDER BY 1 DESC
