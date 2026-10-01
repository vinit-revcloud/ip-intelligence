WITH l AS (SELECT * FROM sampledb.revenue_leads_plus),
s AS (SELECT session_id, session_ip, session_date FROM unified.unified_session_summary WHERE session_date >= date '2026-07-01')
SELECT 'rows' k, cast(count(*) AS varchar) v FROM l
UNION ALL SELECT 'date_pst range', cast(min(date_pst) AS varchar) || ' .. ' || cast(max(date_pst) AS varchar) FROM l
UNION ALL SELECT 'rows last 60d', cast(count(*) AS varchar) FROM l WHERE date_pst >= date '2026-07-18'
UNION ALL SELECT 'utm_content filled last 60d', cast(count_if(nullif(utm_content,'') IS NOT NULL) AS varchar) FROM l WHERE date_pst >= date '2026-07-18'
UNION ALL SELECT 'utm_content matches a session_id (sessions since Jul)', cast(count(DISTINCT l.id) AS varchar) FROM l JOIN s ON s.session_id = l.utm_content WHERE l.date_pst >= date '2026-07-18'
UNION ALL SELECT 'expected_revenue >0 last 60d', cast(count_if(expected_revenue > 0) AS varchar) FROM l WHERE date_pst >= date '2026-07-18'
UNION ALL SELECT 'calculated_value_g6_5 >0 last 60d', cast(count_if(calculated_value_g6_5 > 0) AS varchar) FROM l WHERE date_pst >= date '2026-07-18'
UNION ALL SELECT 'is_deal true last 60d', cast(count_if(is_deal) AS varchar) FROM l WHERE date_pst >= date '2026-07-18'
UNION ALL SELECT 'fake true last 60d', cast(count_if(fake) AS varchar) FROM l WHERE date_pst >= date '2026-07-18'
UNION ALL SELECT 'stage:' || coalesce(stage,'null'), cast(count(*) AS varchar) FROM l WHERE date_pst >= date '2026-07-18' GROUP BY stage
UNION ALL SELECT 'furthest:' || coalesce(furthest_stage,'null'), cast(count(*) AS varchar) FROM l WHERE date_pst >= date '2026-07-18' GROUP BY furthest_stage
UNION ALL SELECT 'status_cat:' || coalesce(lead_status_category,'null'), cast(count(*) AS varchar) FROM l WHERE date_pst >= date '2026-07-18' GROUP BY lead_status_category
UNION ALL SELECT 'flags meeting/listing/closed/intro', cast(sum(is_meeting) AS varchar)||'/'||cast(sum(is_listing) AS varchar)||'/'||cast(sum(is_closed) AS varchar)||'/'||cast(sum(is_intro_qualified) AS varchar) FROM l WHERE date_pst >= date '2026-07-18'
UNION ALL SELECT 'sessions per day recent', array_join(array_agg(cast(session_date AS varchar)||'='||cast(n AS varchar) ORDER BY session_date DESC), ' ') FROM (SELECT session_date, count(*) n FROM s WHERE session_date >= date '2026-08-15' GROUP BY 1)
