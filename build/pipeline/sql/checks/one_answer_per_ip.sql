-- One answer per IP.
-- Bot: true if FraudLogix OR proxycheck.io says bot (either vendor's bot sign is strong: under 1% of paying customers).
-- Proxy/VPN: FraudLogix when it decided (lowest wrong-flag rate), otherwise proxycheck.io.
SELECT ip_address,
       CASE WHEN count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND is_bot IS NOT NULL) = 0 THEN NULL
            ELSE bool_or(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND coalesce(is_bot, false)) END AS is_bot,
       coalesce(max(CASE WHEN vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL THEN vendor END),
                max(CASE WHEN vendor = 'proxycheck_io' THEN vendor END)) AS proxy_source,
       coalesce(max(CASE WHEN vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL THEN CAST(is_proxy OR is_vpn AS integer) END),
                max(CASE WHEN vendor = 'proxycheck_io' THEN CAST(is_proxy OR is_vpn AS integer) END)) = 1 AS is_proxy_or_vpn
FROM unified.ip_intelligence
GROUP BY ip_address;
