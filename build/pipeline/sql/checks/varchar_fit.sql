SELECT 'geo_analytics.vendor<=16' k, max(length(vendor)) mx, count_if(length(vendor) > 16) over_n FROM ipintel_curated.ip_geo_analytics
UNION ALL SELECT 'intel_analytics.verdict_class<=28', max(length(verdict_class)), count_if(length(verdict_class) > 28) FROM ipintel_curated.ip_intelligence_analytics
UNION ALL SELECT 'overview_geo.vendor<=16', max(length(vendor)), count_if(length(vendor) > 16) FROM ipintel_curated.vendor_overview_geo
UNION ALL SELECT 'overview_proxy.bot_metric_status<=25', max(length(bot_metric_status)), count_if(length(bot_metric_status) > 25) FROM ipintel_curated.vendor_overview_proxy
