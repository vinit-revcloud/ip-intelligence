# IP onboarding — full-warehouse profiling runbook

Use this to implement from scratch on **real Athena tables**, not the 100K CSVs.

**Workgroup:** `primary` · **Region:** `us-west-2` · **Engine:** Athena v3  
**Do not** use `raw_tune_clicks_100K_sample.csv` or `session_summary_geo_columns_100K_sample.csv` for these numbers.

---

## What you are building

One enriched row per **on-site session**:

| Need | Source | Join |
|---|---|---|
| Who visited | `unified.unified_session_summary` | grain = `session_id` |
| Geo | IP2Location Lite DB11 | `session_ip` as uint32 BETWEEN `ip_from` AND `ip_to` |
| Fraud (primary) | `raw.raw_tune_clicks.access_control_*` | same IP string |
| Fraud (fallback) | IP2Proxy Lite PX12 | same uint32 range lookup; **miss ≠ clean** |

**Do not join** through `unified.session_click_ids` (incomplete).

---

## Step 0 — Confirm tables exist

```sql
SHOW TABLES IN raw;
SHOW TABLES IN unified;

DESCRIBE raw.raw_tune_clicks;
DESCRIBE unified.unified_session_summary;
DESCRIBE raw.segment_events;
DESCRIBE unified.session_click_ids;
```

Required columns:

- Tune: `ip`, `transaction_id`, `affiliate_click_id`, `date_pst`, `access_control_decision`, `access_control_reason_code`, `country_code`
- Sessions: `session_id`, `session_ip`, `session_date`, `is_bot_click`, `session_id_source`, `last_utm_source`
- Segment: `context_ip`, `properties_ip`, `event_date`, `tune_transaction_id`, `canonical_session_id`, `type`

If DB11 / PX12 are **not** in Glue yet, keep using the local CSVs for range lookup, or load them as:

- `ip_from bigint`, `ip_to bigint`, plus geo / proxy columns  
- Full DB11/PX12 CSVs have **no header**

---

## Step 1 — Size, grain, dates

```sql
SELECT
  'tune' AS src,
  COUNT(*) AS rows,
  COUNT(DISTINCT transaction_id) AS distinct_txn,
  COUNT(DISTINCT ip) AS unique_ips,
  MIN(date_pst) AS min_d,
  MAX(date_pst) AS max_d
FROM raw.raw_tune_clicks

UNION ALL

SELECT
  'sessions',
  COUNT(*),
  COUNT(DISTINCT session_id),
  COUNT(DISTINCT NULLIF(TRIM(session_ip), '')),
  MIN(session_date),
  MAX(session_date)
FROM unified.unified_session_summary

UNION ALL

SELECT
  'segment_events',
  COUNT(*),
  approx_distinct(canonical_session_id),
  approx_distinct(NULLIF(TRIM(context_ip), '')),
  MIN(event_date),
  MAX(event_date)
FROM raw.segment_events;
```

**Sanity (last run 18 Aug 2026):** Tune ~16.3M rows / **4.53M IPs**; sessions ~11.3M / **1.99M IPs**; Segment ~298M events / **~2.0M** `context_ip`.

If Segment unique IPs ≈ session unique IPs, unified is **not** missing an IP universe. Event count is not unique IPs.

---

## Step 2 — IP quality (fill, IPv4 vs IPv6)

### Tune

```sql
SELECT
  COUNT(*) AS rows,
  COUNT(NULLIF(TRIM(ip), '')) AS ip_filled,
  COUNT(DISTINCT NULLIF(TRIM(ip), '')) AS unique_ips,
  COUNT(DISTINCT CASE WHEN ip LIKE '%.%.%.%' THEN ip END) AS unique_ipv4,
  COUNT(DISTINCT CASE WHEN ip LIKE '%:%' THEN ip END) AS unique_ipv6
FROM raw.raw_tune_clicks;
```

Expect: **100% fill, all IPv4, 0 IPv6**.

### Sessions

```sql
SELECT
  COUNT(*) AS rows,
  COUNT(NULLIF(TRIM(session_ip), '')) AS ip_filled,
  COUNT(DISTINCT session_ip) AS unique_ips,
  COUNT(DISTINCT CASE WHEN session_ip LIKE '%.%.%.%' THEN session_ip END) AS unique_ipv4,
  COUNT(DISTINCT CASE WHEN session_ip LIKE '%:%' THEN session_ip END) AS unique_ipv6,
  COUNT(CASE WHEN is_bot_click THEN 1 END) AS bot_sessions,
  COUNT(CASE WHEN NOT is_bot_click THEN 1 END) AS human_sessions
FROM unified.unified_session_summary;
```

Expect: IP filled on almost every row; **~2M unique IPv4**.

Cast helper (reuse everywhere):

```sql
TRY(
  CAST(split_part(ip, '.', 1) AS bigint) * 16777216
+ CAST(split_part(ip, '.', 2) AS bigint) * 65536
+ CAST(split_part(ip, '.', 3) AS bigint) * 256
+ CAST(split_part(ip, '.', 4) AS bigint)
) AS ip_int
```

---

## Step 3 — Tune fraud fields (source of record)

```sql
SELECT
  COUNT(*) AS rows,
  COUNT(NULLIF(TRIM(access_control_decision), '')) AS decision_filled,
  COUNT(NULLIF(TRIM(access_control_reason_code), '')) AS reason_filled,
  ROUND(100.0 * COUNT(NULLIF(TRIM(access_control_decision), '')) / COUNT(*), 4) AS decision_fill_pct_rows,
  COUNT(DISTINCT ip) AS unique_ips,
  COUNT(DISTINCT CASE WHEN NULLIF(TRIM(access_control_decision), '') IS NOT NULL THEN ip END) AS unique_ips_with_decision
FROM raw.raw_tune_clicks;
```

```sql
SELECT
  COALESCE(NULLIF(TRIM(access_control_decision), ''), '<empty>') AS decision,
  COUNT(*) AS clicks,
  COUNT(DISTINCT ip) AS unique_ips
FROM raw.raw_tune_clicks
GROUP BY 1
ORDER BY 2 DESC;
```

```sql
SELECT
  COALESCE(NULLIF(TRIM(access_control_reason_code), ''), '<empty>') AS reason,
  COUNT(*) AS clicks,
  COUNT(DISTINCT ip) AS unique_ips
FROM raw.raw_tune_clicks
GROUP BY 1
ORDER BY 2 DESC;
```

Expect: decision and reason **always fill together** (~98.7% of rows, ~98.1% of unique IPs). Values: `ACCEPTED` / `FLAGGED` / rarely empty / `IGNORED`. Reasons include `NOT_APPLICABLE`, `PROXY`, `MASKED_DEVICES`, `BOT_GENERATED`, `DATA_CENTER`, `VPN`, `TOR`, …

**Implement:** for each IP, if any Tune click is `FLAGGED`, keep that reason; else if any is `ACCEPTED`, pass; else fallback to PX12.

---

## Step 4 — Session mix (SMS / direct vs Tune)

`last_channel` is **not** usable (was 100% `client`). Use `last_utm_source` and `session_id_source`.

```sql
SELECT
  COALESCE(NULLIF(TRIM(session_id_source), ''), '<empty>') AS session_id_source,
  COUNT(*) AS sessions,
  COUNT(DISTINCT session_ip) AS unique_ips
FROM unified.unified_session_summary
GROUP BY 1
ORDER BY 2 DESC;
```

```sql
SELECT
  COALESCE(NULLIF(TRIM(last_utm_source), ''), '<empty>') AS utm_source,
  COUNT(*) AS sessions,
  COUNT(DISTINCT session_ip) AS unique_ips
FROM unified.unified_session_summary
GROUP BY 1
ORDER BY 2 DESC
LIMIT 30;
```

Last run: `tune_synthetic_child` ~43% of sessions; `aff-*` UTMs dominate; empty UTM ~648k sessions (direct/SMS-like, still on the same ~2M IP pool).

---

## Step 5 — Bill’s fill rate (session IPs in Tune)

This is the metric for “can Tune enrich our visitors?” — **not** 0.2%.

```sql
WITH tune AS (
  SELECT DISTINCT NULLIF(TRIM(ip), '') AS ip
  FROM raw.raw_tune_clicks
  WHERE NULLIF(TRIM(ip), '') IS NOT NULL
),
sess AS (
  SELECT DISTINCT NULLIF(TRIM(session_ip), '') AS ip
  FROM unified.unified_session_summary
  WHERE NULLIF(TRIM(session_ip), '') IS NOT NULL
)
SELECT
  (SELECT COUNT(*) FROM sess) AS session_unique_ips,
  (SELECT COUNT(*) FROM tune) AS tune_unique_ips,
  COUNT(*) AS overlap,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM sess), 2) AS pct_session_ips_in_tune,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM tune), 2) AS pct_tune_ips_in_sessions
FROM sess s
INNER JOIN tune t ON s.ip = t.ip;
```

Expect ~**79.5%** of session IPs in Tune, ~**35%** of Tune IPs ever seen on a session.

Why Tune unique IPs > session unique IPs:

```sql
WITH sess AS (
  SELECT DISTINCT NULLIF(TRIM(session_ip), '') AS ip
  FROM unified.unified_session_summary
  WHERE NULLIF(TRIM(session_ip), '') IS NOT NULL
)
SELECT
  COUNT(DISTINCT c.ip) AS tune_ips,
  COUNT(DISTINCT CASE WHEN s.ip IS NOT NULL THEN c.ip END) AS also_in_sessions,
  COUNT(DISTINCT CASE WHEN s.ip IS NULL THEN c.ip END) AS tune_only
FROM raw.raw_tune_clicks c
LEFT JOIN sess s ON NULLIF(TRIM(c.ip), '') = s.ip
WHERE NULLIF(TRIM(c.ip), '') IS NOT NULL;
```

Expect ~**2.95M Tune-only IPs** (clicks that never became a session). That is click leakage / bots / prefetch, not missing session rows.

---

## Step 6 — Prove Segment agrees with ~2M IPs

```sql
SELECT
  COUNT(*) AS events,
  COUNT(NULLIF(TRIM(context_ip), '')) AS context_ip_filled,
  approx_distinct(NULLIF(TRIM(context_ip), '')) AS approx_context_ip,
  COUNT(NULLIF(TRIM(properties_ip), '')) AS properties_ip_filled,
  approx_distinct(NULLIF(TRIM(properties_ip), '')) AS approx_properties_ip,
  COUNT(NULLIF(TRIM(tune_transaction_id), '')) AS tune_txn_filled,
  approx_distinct(canonical_session_id) AS approx_canonical_sessions
FROM raw.segment_events;
```

Expect: ~298M events, **~2.0M** `context_ip`, **~2.7M** `properties_ip`.  
~225–300M is **event rows**, not unique IPs.

```sql
SELECT type, COUNT(*) AS events
FROM raw.segment_events
GROUP BY 1
ORDER BY 2 DESC;
```

---

## Step 7 — Kill the bad join path

```sql
SELECT
  COUNT(*) AS rows,
  COUNT(DISTINCT session_id) AS sessions,
  COUNT(NULLIF(TRIM(clickid_tune_click_id), '')) AS tune_click_id_filled,
  COUNT(NULLIF(TRIM(clickid_txn_id), '')) AS txn_id_filled,
  MIN(session_date) AS min_d,
  MAX(session_date) AS max_d
FROM unified.session_click_ids;
```

Expect ~**50k rows**, 2026-only, **txn_id = 0**. Do not use this table in the pipeline.

---

## Step 8 — IP2Location / IP2Proxy (if loaded to Athena)

If not loaded, run the same checks in Python on the full CSVs (no 100K sample).

```sql
-- DB11: must span all IPv4 with no gaps
SELECT
  COUNT(*) AS ranges,
  MIN(ip_from) AS min_from,
  MAX(ip_to) AS max_to
FROM <db11_table>;
-- expect min_from = 0, max_to = 4294967295

-- PX12: sparse proxy list
SELECT
  COUNT(*) AS ranges,
  COUNT(DISTINCT proxy_type) AS proxy_types,
  COUNT(CASE WHEN threat NOT IN ('', '-') THEN 1 END) AS threat_filled,
  COUNT(CASE WHEN provider NOT IN ('', '-') THEN 1 END) AS provider_filled
FROM <px12_table>;
```

Lite PX12: `proxy_type` is **PUB** on every row; `threat` ~2% filled. Absence from PX12 does not mean the IP is clean.

Session → DB11 hit rate should be ~100% for valid IPv4 (binary search / BETWEEN on ranges).

---

## Step 9 — Build the serving table

After the checks above pass, implement:

```sql
-- Sketch only: requires DB11 / PX12 as tables with ip_from, ip_to
CREATE TABLE scratch_<you>.session_ip_enrichment AS
WITH sess AS (
  SELECT
    session_id,
    session_date,
    is_bot_click,
    NULLIF(TRIM(session_ip), '') AS ip,
    TRY(
      CAST(split_part(session_ip, '.', 1) AS bigint) * 16777216
    + CAST(split_part(session_ip, '.', 2) AS bigint) * 65536
    + CAST(split_part(session_ip, '.', 3) AS bigint) * 256
    + CAST(split_part(session_ip, '.', 4) AS bigint)
    ) AS ip_int
  FROM unified.unified_session_summary
  WHERE NULLIF(TRIM(session_ip), '') IS NOT NULL
),
tune_ip AS (
  SELECT
    ip,
    MAX(CASE WHEN TRIM(access_control_decision) = 'FLAGGED' THEN 1 ELSE 0 END) AS ever_flagged,
    MAX(access_control_decision) AS any_decision,  -- replace with a proper FLAG>empty>ACCEPTED pick
    COUNT(*) AS tune_clicks
  FROM raw.raw_tune_clicks
  WHERE NULLIF(TRIM(ip), '') IS NOT NULL
  GROUP BY ip
)
SELECT
  s.session_id,
  s.session_date,
  s.ip,
  s.ip_int,
  s.is_bot_click,
  t.ever_flagged,
  t.tune_clicks,
  CASE WHEN t.ip IS NOT NULL THEN TRUE ELSE FALSE END AS tune_ip_matched
FROM sess s
LEFT JOIN tune_ip t ON s.ip = t.ip;
```

Then left-range-join `ip_int` to DB11 (always) and PX12 (only where `tune_ip_matched = FALSE`, or as an extra overlay).

Athena range joins on 3M DB11 rows × 11M sessions can be expensive. Common pattern: pre-sort DB11, or enrich **distinct session IPs first** (~2M) then join back to sessions.

```sql
-- Distinct IPs first (cheaper)
SELECT DISTINCT session_ip
FROM unified.unified_session_summary
WHERE NULLIF(TRIM(session_ip), '') IS NOT NULL;
```

Enrich those ~2M IPs, then join to 11.3M sessions on `session_ip`.

---

## Step 10 — Sign-off checks before shipping

| Check | Pass if |
|---|---|
| Session IP fill | ~100% |
| Session unique IPs ≈ Segment `context_ip` | both ~2M, not 225M |
| Tune → session IP fill (Bill) | ~80% of session IPs |
| Tune `access_control` fill | ~99% of clicks; pair fields |
| DB11 lookup | ~100% of valid IPv4 |
| PX12 | overlay only; not primary fraud |
| `session_click_ids` | unused |

---

## Numbers from the 18 Aug 2026 warehouse run (reference, not samples)

| Metric | Value |
|---|---|
| Tune unique IPs | 4,528,154 |
| Session unique IPs | 1,990,844 |
| Overlap | 1,582,730 (**79.5%** of session IPs) |
| Tune IPs never in sessions | 2,945,424 (65%) |
| Tune `access_control` fill (rows) | 98.69% |
| Segment events | 297,910,970 |
| Segment approx unique `context_ip` | 2,037,043 |
| `session_click_ids` rows | 49,746 |

Re-run Steps 1–7 on ship day; tables grow.
