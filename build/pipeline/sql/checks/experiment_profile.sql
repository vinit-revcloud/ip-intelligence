SELECT min(session_date) first_day, max(session_date) last_day, count(*) sessions, count(DISTINCT session_ip) ips, count(DISTINCT experiment_id) experiments,
  array_join(slice(array_agg(DISTINCT experiment_id), 1, 8), ', ') sample_ids
FROM unified.unified_session_summary WHERE nullif(experiment_id,'') IS NOT NULL
