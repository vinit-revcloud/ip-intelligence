SELECT CAST(timestamp '2026-09-14 21:40:05.000' AS varchar) AS pacific_wall_clock,
       date_format(with_timezone(timestamp '2026-09-14 21:40:05.000', 'America/Los_Angeles') AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%i:%sZ') AS as_utc_summer,
       date_format(with_timezone(timestamp '2026-01-11 15:00:35.000', 'America/Los_Angeles') AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%i:%sZ') AS as_utc_winter,
       date_format(with_timezone(date_parse('2023-01-11 15:00:35.000000', '%Y-%m-%d %H:%i:%s.%f'), 'America/Los_Angeles') AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%i:%sZ') AS stored_text_converted
