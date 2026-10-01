SELECT count(*) AS n FROM experimentation_tools.experiment_router_events WHERE server_timestamp_entry >= current_timestamp - interval '1' hour
