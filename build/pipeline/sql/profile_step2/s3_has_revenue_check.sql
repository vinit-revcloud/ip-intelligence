-- Read only. Is the session has_revenue flag real revenue? Compare with linked leads' expected_revenue.
WITH l AS (SELECT utm_content, max(expected_revenue) AS rev FROM sampledb.revenue_leads_plus GROUP BY 1)
SELECT s.has_revenue, s.has_lead, count(*) AS sessions,
       count_if(l.utm_content IS NOT NULL) AS with_linked_lead, count_if(l.rev > 0) AS linked_lead_with_revenue,
       count_if(s.expected_revenue > 0) AS session_expected_revenue_gt0,
       min(s.session_date) AS first_day, max(s.session_date) AS last_day
FROM unified.unified_session_summary s LEFT JOIN l ON l.utm_content = s.session_id
GROUP BY 1, 2 ORDER BY sessions DESC
