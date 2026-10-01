-- Read only. Distinct values of the yes/no style session columns in the MoM window.
WITH s AS (
  SELECT * FROM unified.unified_session_summary
  WHERE session_date BETWEEN date '2026-06-18' AND date '2026-09-09' AND nullif(session_ip, '') IS NOT NULL),
v AS (
  SELECT 'has_visit' c, CAST(has_visit AS varchar) v FROM s UNION ALL
  SELECT 'has_quiz_start', CAST(has_quiz_start AS varchar) FROM s UNION ALL
  SELECT 'has_partial_lead', CAST(has_partial_lead AS varchar) FROM s UNION ALL
  SELECT 'has_lead', CAST(has_lead AS varchar) FROM s UNION ALL
  SELECT 'has_otp_verified', CAST(has_otp_verified AS varchar) FROM s UNION ALL
  SELECT 'has_qualified_connected', CAST(has_qualified_connected AS varchar) FROM s UNION ALL
  SELECT 'has_meeting', CAST(has_meeting AS varchar) FROM s UNION ALL
  SELECT 'has_consent', CAST(has_consent AS varchar) FROM s UNION ALL
  SELECT 'consent_status', CAST(consent_status AS varchar) FROM s UNION ALL
  SELECT 'device_type', CAST(device_type AS varchar) FROM s UNION ALL
  SELECT 'journey_stage', CAST(journey_stage AS varchar) FROM s UNION ALL
  SELECT 'ip_is_proxy', CAST(ip_is_proxy AS varchar) FROM s UNION ALL
  SELECT 'tz_matches_ip', CAST(nullif(timezone, '') IS NOT NULL AND nullif(ip_time_zone, '') IS NOT NULL AS varchar) FROM s)
SELECT c, v, count(*) n FROM v GROUP BY 1, 2 HAVING count(*) >= 20 ORDER BY 1, 3 DESC
