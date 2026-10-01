-- Read only. sampledb.revenue_leads_plus as ground truth: size, span, the fake / phone_verified fields, and how many link to a session.
WITH l AS (SELECT id, utm_content, date_pst, expected_revenue, CAST(fake AS varchar) AS fake, CAST(phone_verified AS varchar) AS pv,
                  CAST(is_deal AS varchar) AS deal FROM sampledb.revenue_leads_plus),
s AS (SELECT DISTINCT session_id FROM unified.unified_session_summary)
SELECT count(*) AS leads, min(date_pst) AS first_day, max(date_pst) AS last_day,
       histogram(fake) AS fake_values, histogram(pv) AS phone_verified_values, histogram(deal) AS is_deal_values,
       count_if(expected_revenue > 0) AS with_expected_revenue,
       count_if(s.session_id IS NOT NULL) AS linked_to_session,
       count_if(s.session_id IS NOT NULL AND expected_revenue > 0) AS linked_with_revenue,
       count_if(s.session_id IS NOT NULL AND date_pst >= date '2025-01-01') AS linked_since_2025
FROM l LEFT JOIN s ON s.session_id = l.utm_content
