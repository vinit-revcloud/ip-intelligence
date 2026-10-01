# Athena Queries — Review the Live IP Tables

All tables are in the **`ipintel_curated`** database. They are Iceberg tables partitioned by address, so
a query with `WHERE ip_address = '…'` reads only a few MB; aggregates over a whole table read 0.1–1.5 GB.

Every query here is read-only. Run them in the Athena console (Query editor, database
`ipintel_curated`).

| Table | One row per | What it answers |
|---|---|---|
| `ip_resolved` | address | **The answer to use**: location, proxy verdict, which vendors it rests on, where seen |
| `ip_geo` | address + vendor | Each location vendor's own answer |
| `ip_intelligence` | address + vendor | Each proxy/risk vendor's own answer |
| `ip_geo_analytics` | address + vendor | Consensus and agreement, where at least two vendors answered |
| `ip_intelligence_analytics` | address + vendor | Flagged, verdict class, risk score per vendor answer |
| `ip_occurrences` | address + base table | Where the address was seen: first/last date, days, rows |
| `vendor_overview_geo` | vendor | Location scorecard |
| `vendor_overview_proxy` | vendor | Proxy scorecard |
| `proxycheck_queue` | address | Base-table addresses that needed proxycheck.io, why, and when they were answered |

---

## 1. Look at each table

```sql
SELECT * FROM ipintel_curated.ip_resolved LIMIT 20;
SELECT * FROM ipintel_curated.ip_geo LIMIT 20;
SELECT * FROM ipintel_curated.ip_intelligence LIMIT 20;
SELECT * FROM ipintel_curated.ip_geo_analytics LIMIT 20;
SELECT * FROM ipintel_curated.ip_intelligence_analytics LIMIT 20;
SELECT * FROM ipintel_curated.ip_occurrences LIMIT 20;
SELECT * FROM ipintel_curated.vendor_overview_geo ORDER BY score DESC;
SELECT * FROM ipintel_curated.vendor_overview_proxy ORDER BY score DESC;
```

## 2. Everything about one IP address

Replace the address in each query.

```sql
-- The answer to use
SELECT * FROM ipintel_curated.ip_resolved WHERE ip_address = '152.232.101.74';

-- Every vendor's location answer
SELECT * FROM ipintel_curated.ip_geo WHERE ip_address = '152.232.101.74' ORDER BY vendor;

-- Every vendor's proxy answer, with its verdict
SELECT i.*, a.has_answer, a.flagged, a.verdict_class, a.risk_score, a.fraud_reason
FROM ipintel_curated.ip_intelligence i
LEFT JOIN ipintel_curated.ip_intelligence_analytics a
  ON a.ip_address = i.ip_address AND a.vendor = i.vendor
WHERE i.ip_address = '152.232.101.74'
ORDER BY i.vendor;

-- Where it was seen
SELECT * FROM ipintel_curated.ip_occurrences WHERE ip_address = '152.232.101.74';
```

## 3. Size and freshness

```sql
-- Rows per table and when each was last written
SELECT 'ip_resolved' AS table_name, count(*) AS rows_, count(DISTINCT ip_address) AS addresses, max(updated_at) AS last_written FROM ipintel_curated.ip_resolved
UNION ALL SELECT 'ip_geo', count(*), count(DISTINCT ip_address), max(updated_at) FROM ipintel_curated.ip_geo
UNION ALL SELECT 'ip_intelligence', count(*), count(DISTINCT ip_address), max(updated_at) FROM ipintel_curated.ip_intelligence
UNION ALL SELECT 'ip_geo_analytics', count(*), count(DISTINCT ip_address), NULL FROM ipintel_curated.ip_geo_analytics
UNION ALL SELECT 'ip_intelligence_analytics', count(*), count(DISTINCT ip_address), NULL FROM ipintel_curated.ip_intelligence_analytics
UNION ALL SELECT 'ip_occurrences', count(*), count(DISTINCT ip_address), max(updated_at) FROM ipintel_curated.ip_occurrences;

-- Rows per vendor, and when that vendor first and last wrote
SELECT 'ip_geo' AS table_name, vendor, count(*) AS rows_, min(created_at) AS first_written, max(updated_at) AS last_updated
FROM ipintel_curated.ip_geo GROUP BY vendor
UNION ALL
SELECT 'ip_intelligence', vendor, count(*), min(created_at), max(updated_at)
FROM ipintel_curated.ip_intelligence GROUP BY vendor
ORDER BY 1, 3 DESC;

-- Every version the daily jobs have written, newest first
SELECT committed_at, operation, summary['added-records'] AS added, summary['total-records'] AS total
FROM ipintel_curated."ip_resolved$snapshots" ORDER BY committed_at DESC LIMIT 20;
```

## 4. How conclusive the answers are

```sql
-- Proxy verdicts, overall and for addresses seen in the last 90 days
SELECT proxy_status, flagged, count(*) AS addresses,
       count_if(last_seen >= current_date - interval '90' day) AS seen_last_90_days
FROM ipintel_curated.ip_resolved
GROUP BY 1, 2 ORDER BY 3 DESC;

-- Location verdicts
SELECT geo_status, count(*) AS addresses,
       count_if(last_seen >= current_date - interval '90' day) AS seen_last_90_days
FROM ipintel_curated.ip_resolved
GROUP BY 1 ORDER BY 2 DESC;

-- Which vendor the answer rests on
SELECT 'location' AS side, geo_decided_by AS decided_by, count(*) AS addresses FROM ipintel_curated.ip_resolved GROUP BY 2
UNION ALL
SELECT 'proxy', proxy_decided_by, count(*) FROM ipintel_curated.ip_resolved GROUP BY 2
ORDER BY 1, 3 DESC;

-- What the flagged addresses are
SELECT count(*) AS flagged_addresses,
       count_if(is_proxy) AS proxy, count_if(is_vpn) AS vpn, count_if(is_tor) AS tor,
       count_if(is_datacenter) AS datacenter, count_if(is_compromised) AS compromised,
       count_if(is_scraper) AS scraper, count_if(is_anonymous) AS anonymous
FROM ipintel_curated.ip_resolved
WHERE flagged;
```

## 5. What the proxycheck.io backfill is doing

```sql
-- Addresses answered by proxycheck.io, per day
SELECT substr(created_at, 1, 10) AS day, count(*) AS answered
FROM ipintel_curated.ip_intelligence
WHERE vendor = 'proxycheck_io'
GROUP BY 1 ORDER BY 1 DESC;

-- How many addresses still have no conclusion, and how many of those were seen recently
SELECT count(*) AS no_conclusion,
       count_if(last_seen >= current_date - interval '90' day) AS seen_last_90_days,
       round(count(*) / 50000.0, 1) AS days_left_at_50k
FROM ipintel_curated.ip_resolved
WHERE proxy_status IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed');

-- Where proxycheck.io disagrees with FraudLogix
SELECT pc.flagged AS proxycheck_flagged, fl.flagged AS fraudlogix_flagged, count(*) AS addresses
FROM ipintel_curated.ip_intelligence_analytics pc
JOIN ipintel_curated.ip_intelligence_analytics fl
  ON fl.ip_address = pc.ip_address AND fl.vendor = 'fraudlogix_tune'
WHERE pc.vendor = 'proxycheck_io' AND pc.has_answer AND fl.has_answer
GROUP BY 1, 2 ORDER BY 3 DESC;

-- proxycheck.io risk scores
SELECT CASE WHEN risk_score >= 67 THEN 'high 67-100' WHEN risk_score >= 34 THEN 'medium 34-66'
            WHEN risk_score >= 1 THEN 'low 1-33' WHEN risk_score = 0 THEN 'none 0' ELSE 'no score' END AS risk,
       count(*) AS addresses
FROM ipintel_curated.ip_intelligence_analytics
WHERE vendor = 'proxycheck_io'
GROUP BY 1 ORDER BY 2 DESC;
```

## 6. Where addresses come from

```sql
-- Addresses per base table, and how recently they were seen
SELECT source_table, count(*) AS addresses,
       count_if(last_seen >= current_date - interval '1' day) AS seen_last_day,
       count_if(last_seen >= current_date - interval '7' day) AS seen_last_7_days,
       count_if(last_seen >= current_date - interval '90' day) AS seen_last_90_days,
       min(first_seen) AS earliest, max(last_seen) AS latest
FROM ipintel_curated.ip_occurrences
GROUP BY 1;

-- Addresses in both base tables versus only one
SELECT seen_in_base_tables, count(*) AS addresses
FROM ipintel_curated.ip_resolved
GROUP BY 1 ORDER BY 2 DESC;

-- New addresses per day (first time IP2Location answered them)
SELECT substr(created_at, 1, 10) AS day, count(*) AS new_addresses
FROM ipintel_curated.ip_geo
WHERE vendor = 'ip2location_db11' AND created_at >= '2026-09-11T00:00:01Z'
GROUP BY 1 ORDER BY 1 DESC;
```

## 7. Location quality

```sql
-- Location scorecard
SELECT vendor, ips_tested, fill_rate_pct, agreement_pct, state_truth_pct, city_truth_pct, zip_truth_pct, score, as_of_date
FROM ipintel_curated.vendor_overview_geo ORDER BY score DESC;

-- Top states and cities of the resolved answer (addresses seen in the last 90 days)
SELECT state, city, count(*) AS addresses
FROM ipintel_curated.ip_resolved
WHERE last_seen >= current_date - interval '90' day AND state IS NOT NULL
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 25;

-- Addresses where the location vendors disagree, with every vendor's answer side by side
SELECT r.ip_address, r.state AS resolved_state, r.city AS resolved_city, r.geo_decided_by,
       array_join(array_agg(g.vendor || ': ' || coalesce(g.state, '-') || ' / ' || coalesce(g.city, '-')), ' | ') AS vendor_answers
FROM ipintel_curated.ip_resolved r
JOIN ipintel_curated.ip_geo g ON g.ip_address = r.ip_address
WHERE r.geo_status = 'vendors_disagree'
GROUP BY 1, 2, 3, 4
LIMIT 25;
```

## 8. Proxy and bot detection quality

```sql
-- Proxy scorecard
SELECT vendor, ips_tested, answered, fill_rate_pct, flagged, bot_flagged, compromised_flagged,
       scraper_flagged, anonymous_flagged, false_positive_rate_pct, score, as_of_date
FROM ipintel_curated.vendor_overview_proxy ORDER BY score DESC;

-- Verdict classes per vendor
SELECT vendor, verdict_class, count(*) AS rows_
FROM ipintel_curated.ip_intelligence_analytics
GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- Bots: only FraudLogix classifies bots (proxycheck.io does not)
SELECT vendor, count_if(is_bot) AS bot, count_if(NOT is_bot) AS not_bot, count_if(is_bot IS NULL) AS no_answer
FROM ipintel_curated.ip_intelligence
GROUP BY 1 ORDER BY 1;

-- The most-seen flagged addresses in the last 90 days
SELECT r.ip_address, r.proxy_status, r.is_proxy, r.is_vpn, r.is_tor, r.is_datacenter, r.isp,
       r.proxycheck_risk_score, sum(o.rows_seen) AS rows_seen, max(o.last_seen) AS last_seen
FROM ipintel_curated.ip_resolved r
JOIN ipintel_curated.ip_occurrences o ON o.ip_address = r.ip_address
WHERE r.flagged AND r.last_seen >= current_date - interval '90' day
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
ORDER BY rows_seen DESC LIMIT 25;

-- ISPs with the most flagged addresses
SELECT isp, count(*) AS flagged_addresses, count_if(is_datacenter) AS datacenter, count_if(is_vpn) AS vpn
FROM ipintel_curated.ip_resolved
WHERE flagged AND isp IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC LIMIT 25;
```

## 8b. The base-table path to proxycheck.io

```sql
-- Addresses queued from new base-table rows, by reason and outcome
SELECT reason, coalesce(outcome, 'waiting') AS outcome, count(*) AS addresses,
       min(queued_at) AS first_queued, max(answered_at) AS last_answered
FROM ipintel_curated.proxycheck_queue
GROUP BY 1, 2 ORDER BY 3 DESC;

-- Every queued address with its current answer
SELECT q.ip_address, q.reason, q.queued_at, q.answered_at, q.outcome,
       r.proxy_status, r.flagged, r.proxycheck_risk_score, r.geo_status, r.state, r.city
FROM ipintel_curated.proxycheck_queue q
LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = q.ip_address
ORDER BY q.queued_at DESC LIMIT 50;

-- Should be 0 after the proxycheck job has run: queued, but no proxycheck.io answer and not closed
SELECT count(*) AS still_waiting
FROM ipintel_curated.proxycheck_queue q
WHERE q.answered_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM ipintel_curated.ip_intelligence i
                  WHERE i.ip_address = q.ip_address AND i.vendor = 'proxycheck_io');
```

## 9. Health checks (every result should be 0)

```sql
-- Duplicate address + vendor rows
SELECT 'ip_geo' AS table_name, count(*) AS duplicate_pairs FROM (SELECT ip_address, vendor FROM ipintel_curated.ip_geo GROUP BY 1, 2 HAVING count(*) > 1)
UNION ALL SELECT 'ip_intelligence', count(*) FROM (SELECT ip_address, vendor FROM ipintel_curated.ip_intelligence GROUP BY 1, 2 HAVING count(*) > 1)
UNION ALL SELECT 'ip_geo_analytics', count(*) FROM (SELECT ip_address, vendor FROM ipintel_curated.ip_geo_analytics GROUP BY 1, 2 HAVING count(*) > 1)
UNION ALL SELECT 'ip_intelligence_analytics', count(*) FROM (SELECT ip_address, vendor FROM ipintel_curated.ip_intelligence_analytics GROUP BY 1, 2 HAVING count(*) > 1)
UNION ALL SELECT 'ip_occurrences', count(*) FROM (SELECT ip_address, base_table FROM ipintel_curated.ip_occurrences GROUP BY 1, 2 HAVING count(*) > 1)
UNION ALL SELECT 'ip_resolved', count(*) FROM (SELECT ip_address FROM ipintel_curated.ip_resolved GROUP BY 1 HAVING count(*) > 1);

-- Addresses in ip_geo or ip_intelligence without a resolved answer
SELECT count(*) AS missing_resolved
FROM (SELECT ip_address FROM ipintel_curated.ip_geo UNION SELECT ip_address FROM ipintel_curated.ip_intelligence) a
LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = a.ip_address
WHERE r.ip_address IS NULL;

-- Intelligence rows without their analytics row
SELECT count(*) AS missing_analytics
FROM ipintel_curated.ip_intelligence i
LEFT JOIN ipintel_curated.ip_intelligence_analytics a ON a.ip_address = i.ip_address AND a.vendor = i.vendor
WHERE a.ip_address IS NULL;

-- Rows from vendors the system no longer runs (removed 14 Sep)
SELECT count(*) AS removed_vendor_rows
FROM ipintel_curated.ip_geo WHERE vendor IN ('maxmind_geolite2', 'dbip_combined', 'geojs_io');
```

### Full reconciliation against the two production tables (reads about 1.6 GB)

Every column should be 0 except `source_ips`.

```sql
WITH src AS (
  SELECT DISTINCT ip FROM (
    SELECT CAST(session_ip AS varchar) AS ip FROM unified.unified_session_summary
    UNION ALL SELECT CAST(ip AS varchar) FROM raw.raw_tune_clicks)
  WHERE regexp_like(ip, '^(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])(\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])){3}$')
),
tune AS (SELECT DISTINCT CAST(ip AS varchar) AS ip FROM raw.raw_tune_clicks),
geo AS (SELECT ip_address, count_if(vendor = 'ip2location_db11') AS db11 FROM ipintel_curated.ip_geo GROUP BY 1),
intel AS (SELECT ip_address, count_if(vendor = 'ip2proxy_px12') AS px12, count_if(vendor = 'fraudlogix_tune') AS fl
          FROM ipintel_curated.ip_intelligence GROUP BY 1),
occ AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_occurrences)
SELECT
  (SELECT count(*) FROM src) AS source_ips,
  (SELECT count(*) FROM src s LEFT JOIN geo g ON g.ip_address = s.ip WHERE coalesce(g.db11, 0) = 0) AS missing_ip2location,
  (SELECT count(*) FROM src s LEFT JOIN intel i ON i.ip_address = s.ip WHERE coalesce(i.px12, 0) = 0) AS missing_ip2proxy,
  (SELECT count(*) FROM tune t JOIN src s ON s.ip = t.ip LEFT JOIN intel i ON i.ip_address = t.ip WHERE coalesce(i.fl, 0) = 0) AS tune_ips_missing_fraudlogix,
  (SELECT count(*) FROM src s LEFT JOIN occ o ON o.ip_address = s.ip WHERE o.ip_address IS NULL) AS missing_occurrences;
```

Addresses first seen after the last daily run (07:30 UTC) show as missing until the next run.

---

## Column meanings — `ip_resolved`

| Column | Meaning |
|---|---|
| `geo_status` | `agreed` (2+ vendors agree on state and city), `single_source` (one vendor answered), `vendors_disagree`, `no_answer` |
| `state`, `city`, `zip_code`, `latitude`, `longitude`, `timezone` | The location to use, taken from `geo_decided_by` |
| `geo_decided_by` / `geo_agreeing_vendors` | The vendor whose fields are shown / every vendor in the agreeing group |
| `proxy_status` | `confirmed` (proxycheck.io and another vendor agree), `proxycheck_only`, `proxycheck_overrides` (proxycheck.io disagrees with every other vendor, and its answer is used), `clean_by_vendors`, `vendors_disagree`, `flagged_unconfirmed`, `no_answer` |
| `flagged` | `true` flagged, `false` clean, **NULL = no conclusion** (never read NULL as clean) |
| `is_proxy` … `is_anonymous` | The flags behind the verdict; NULL when there is no conclusion |
| `proxy_decided_by` / `proxy_agreeing_vendors` | Which vendor decided / which vendors agree with the verdict |
| `proxycheck_risk_score` | proxycheck.io risk 0–100, when it has answered |
| `seen_in_base_tables`, `first_seen`, `last_seen` | Which production tables the address appears in, and when |
| `updated_at` | When this row last changed |

All `created_at` / `updated_at` values in every table are UTC, written as `YYYY-MM-DDTHH:MM:SSZ`.
FraudLogix times were converted from Pacific time on 15 Sep 2026.

## Column meanings — `vendor_overview_proxy` (changed 15 Sep 2026)

| Column | Meaning |
|---|---|
| `false_positive_rate_pct` | Of the confirmed humans (`qualified_lead_ips.confirmed_human`) in the pool that the vendor gave a bot answer for, the share it flagged as bot. Blank for vendors that never classify bots. The sample size is in `bot_metric_status` |
| `bot_identification_pct` | Share of all answered addresses the vendor flagged as bot |
| `precision_infra_pct`, `recall_infra_pct` | Blank while no published-range address is in the pool |
