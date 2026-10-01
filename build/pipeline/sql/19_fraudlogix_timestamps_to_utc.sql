UPDATE ipintel_curated.ip_intelligence
SET created_at = CASE WHEN regexp_like(created_at, '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
                      THEN date_format(with_timezone(date_parse(substr(created_at, 1, 19), '%Y-%m-%d %H:%i:%s'), 'America/Los_Angeles') AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%i:%sZ')
                      ELSE created_at END,
    updated_at = CASE WHEN regexp_like(updated_at, '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
                      THEN date_format(with_timezone(date_parse(substr(updated_at, 1, 19), '%Y-%m-%d %H:%i:%s'), 'America/Los_Angeles') AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%i:%sZ')
                      ELSE updated_at END
WHERE vendor = 'fraudlogix_tune'
  AND (regexp_like(created_at, '^\d{4}-\d{2}-\d{2} \d') OR regexp_like(updated_at, '^\d{4}-\d{2}-\d{2} \d'))
