SELECT CAST(snapshot_id AS varchar) s, committed_at FROM "ipintel_curated"."ip_intelligence$snapshots" ORDER BY committed_at DESC LIMIT 1
