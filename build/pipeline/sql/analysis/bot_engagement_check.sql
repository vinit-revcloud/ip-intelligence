-- Read only. Is has_consent a visitor action or a page property? Compare it with quiz start / partial lead,
-- session length and events, in the MoM window.
WITH s AS (
  SELECT * FROM unified.unified_session_summary
  WHERE session_date BETWEEN date '2026-06-18' AND date '2026-09-09' AND nullif(session_ip, '') IS NOT NULL)
SELECT has_consent, has_quiz_start, has_partial_lead, (nullif(device_type, '') IS NOT NULL) AS has_device,
  count(*) AS sessions,
  approx_percentile(CAST(duration_seconds AS double), 0.5) AS median_dur,
  approx_percentile(CAST(event_count AS double), 0.5) AS median_events,
  count_if(nullif(consent_trustedform_url, '') IS NOT NULL) AS trustedform,
  count(DISTINCT page_template) AS templates
FROM s GROUP BY 1, 2, 3, 4 ORDER BY sessions DESC
