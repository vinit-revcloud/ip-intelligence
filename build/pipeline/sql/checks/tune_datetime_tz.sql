SELECT count(*) AS rows_,
       count_if(date_pst = CAST(datetime - interval '8' hour AS date) OR date_pst = CAST(datetime - interval '7' hour AS date)) AS pst_is_utc_minus_7_or_8,
       count_if(date_pst = CAST(datetime AS date)) AS pst_equals_datetime_date,
       min(datetime) AS earliest, max(datetime) AS latest
FROM raw.raw_tune_clicks WHERE datetime >= timestamp '2026-09-01 00:00:00'
