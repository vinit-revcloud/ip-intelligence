# Tune × IP2Location Lite — data profiling

**Grain of this trial:** unique IPs on `raw.raw_tune_clicks`, then Lite DB11 (geo) and Lite PX12 (proxy).  
**Not in this document:** `unified.unified_session_summary`, routers, Segment, `session_click_ids`.

**Athena:** account `221490242148` · region `us-west-2` · workgroup `primary` · engine v3  
**CLI profile:** `source-creation-tool` (unset `HTTP_PROXY` / `HTTPS_PROXY` if Athena hangs)

**Last warehouse pull:** 19 Aug 2026 (full `raw.raw_tune_clicks`, not the 100K CSV).

---

## How to show this

| Slide / question | Number to quote | Do not quote |
|---|---|---|
| How many click IPs do we have? | **4,528,275** unique IPv4 | 225M, 0.2% |
| Is Fraudlogix filled? | **98.69%** of clicks · **98.08%** of unique IPs | 100% (that was the 100K sample) |
| How many IPs have no Tune fraud status? | **86,788** (PX12 fallback set) | — |
| What share of IPs did Fraudlogix flag? | **14.6%** ever `FLAGGED` | 55% (100K sample was biased) |
| Can Lite geo every Tune IP? | **Yes — ~100%** (DB11 covers all IPv4) | 0.2% |
| Can Lite PX12 replace Fraudlogix? | **No.** Sample hit **1.51%**; recovers **~1.4%** of Tune-flagged IPs | PX12 miss = clean |
| What was 0.2%? | Random **DB11 → Tune** reverse overlap | Session fill / US inventory |

---

## 0. Tables in scope

| Source | Where it lives | Role |
|---|---|---|
| Tune / Fraudlogix | Athena `raw.raw_tune_clicks` | Click IPs + `access_control_*` labels |
| IP2Location Lite DB11 | Local `IP2LOCATION-LITE-DB11.CSV` (no header) | Geo lookup |
| IP2Proxy Lite PX12 | Local `IP2PROXY-LITE-PX12.CSV` (no header) | Thin public-proxy overlay |

Lite dumps are **not** Glue tables today. Tune-only metrics are Athena. Tune → DB11 / PX12 metrics are from the local range lookup (100K click sample vs **full** Lite CSVs) until the CSVs are loaded (SQL in §6).

**Do not use** `raw_tune_clicks_100K_sample.csv` for warehouse KPIs. That sample overstated `FLAGGED` (55% of IPs vs **14.6%** on the full table).

---

## 1. Tune inventory

```sql
SELECT
  COUNT(*) AS click_rows,
  COUNT(NULLIF(TRIM(ip), '')) AS ip_filled_rows,
  COUNT(DISTINCT NULLIF(TRIM(ip), '')) AS unique_ips,
  COUNT(DISTINCT CASE WHEN ip LIKE '%.%.%.%' THEN TRIM(ip) END) AS unique_ipv4,
  COUNT(DISTINCT CASE WHEN ip LIKE '%:%' THEN TRIM(ip) END) AS unique_ipv6,
  COUNT(DISTINCT CASE WHEN UPPER(TRIM(country_code)) = 'US' THEN TRIM(ip) END) AS unique_us_ips,
  COUNT(CASE WHEN UPPER(TRIM(country_code)) = 'US' THEN 1 END) AS us_click_rows,
  MIN(date_pst) AS min_date_pst,
  MAX(date_pst) AS max_date_pst
FROM raw.raw_tune_clicks;
```

**Result (19 Aug 2026)**

| Metric | Value |
|---|---:|
| Click rows | **16,304,549** |
| IP filled | 16,304,549 (**100%**) |
| Unique IPs | **4,528,275** |
| Unique IPv4 | 4,528,275 |
| Unique IPv6 | **0** |
| Unique US IPs (`country_code = US`) | **4,460,420 (98.50%)** |
| US click rows | **16,041,234 (98.39%)** |
| Dates (`date_pst`) | 2023-01-11 → 2026-08-18 |

Every click has a dotted IPv4. Traffic is almost entirely US.

### Country mix (Tune `country_code`, not DB11)

```sql
SELECT
  COALESCE(NULLIF(TRIM(country_code), ''), '<empty>') AS country_code,
  COUNT(*) AS clicks,
  COUNT(DISTINCT TRIM(ip)) AS unique_ips,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS pct_clicks
FROM raw.raw_tune_clicks
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
```

| country_code | Clicks | Unique IPs | % clicks |
|---|---:|---:|---:|
| US | 16,041,234 | 4,460,420 | **98.39%** |
| UK | 50,312 | 3,800 | 0.31% |
| CA | 29,329 | 10,721 | 0.18% |
| IN | 15,119 | 6,489 | 0.09% |
| ES | 12,594 | 671 | 0.08% |
| DE | 11,869 | 1,676 | 0.07% |

---

## 2. Fraudlogix fill (`access_control_*`)

Decision and reason fill as a **pair**. Empty decision ⇔ empty reason.

```sql
SELECT
  COUNT(*) AS click_rows,
  COUNT(NULLIF(TRIM(access_control_decision), '')) AS decision_filled_rows,
  COUNT(NULLIF(TRIM(access_control_reason_code), '')) AS reason_filled_rows,
  COUNT(CASE
    WHEN NULLIF(TRIM(access_control_decision), '') IS NOT NULL
     AND NULLIF(TRIM(access_control_reason_code), '') IS NOT NULL
    THEN 1 END) AS both_ac_filled_rows,
  ROUND(100.0 * COUNT(CASE
    WHEN NULLIF(TRIM(access_control_decision), '') IS NOT NULL
     AND NULLIF(TRIM(access_control_reason_code), '') IS NOT NULL
    THEN 1 END) / COUNT(*), 4) AS both_ac_fill_pct_rows,
  COUNT(DISTINCT NULLIF(TRIM(ip), '')) AS unique_ips,
  COUNT(DISTINCT CASE
    WHEN NULLIF(TRIM(access_control_decision), '') IS NOT NULL
     AND NULLIF(TRIM(access_control_reason_code), '') IS NOT NULL
    THEN TRIM(ip) END) AS unique_ips_with_ac
FROM raw.raw_tune_clicks;
```

**Result**

| Grain | Filled | Missing |
|---|---:|---:|
| Click rows | **16,090,866 (98.69%)** | 213,683 (1.31%) |
| Unique IPs with ≥1 filled AC row | **4,441,487 (98.08%)** | — |
| Unique IPs with **no** decision on any click | **86,788 (1.92%)** | ← PX12 fallback universe |

`COUNT(DISTINCT ip)` on empty-AC **rows** is 131,875 — that includes IPs that also have filled clicks. The implementation number is **86,788 IPs with zero Fraudlogix status**.

The 100K CSV had 100% fill. Do not use it for this KPI.

---

## 3. Fraudlogix decisions and reasons (full table)

### 3.1 Decision mix

```sql
SELECT
  COALESCE(NULLIF(TRIM(access_control_decision), ''), '<empty>') AS decision,
  COUNT(*) AS clicks,
  COUNT(DISTINCT TRIM(ip)) AS unique_ips,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS pct_clicks
FROM raw.raw_tune_clicks
GROUP BY 1
ORDER BY 2 DESC;
```

| Decision | Clicks | Unique IPs on those rows | % clicks |
|---|---:|---:|---:|
| `ACCEPTED` | 12,507,553 | 4,068,780 | **76.71%** |
| `FLAGGED` | 3,582,791 | 661,316 | **21.97%** |
| `<empty>` | 213,683 | 131,875 | 1.31% |
| `IGNORED` | 522 | 413 | 0.003% |

Default path is **pass** (`ACCEPTED`), not flag.

### 3.2 Unique-IP flag classes (use this for “how many IPs are bots?”)

```sql
WITH ip_ac AS (
  SELECT
    TRIM(ip) AS ip,
    MAX(CASE WHEN TRIM(access_control_decision) = 'FLAGGED' THEN 1 ELSE 0 END) AS ever_flagged,
    MAX(CASE WHEN TRIM(access_control_decision) = 'ACCEPTED' THEN 1 ELSE 0 END) AS ever_accepted,
    MAX(CASE WHEN NULLIF(TRIM(access_control_decision), '') IS NOT NULL THEN 1 ELSE 0 END) AS has_decision
  FROM raw.raw_tune_clicks
  WHERE NULLIF(TRIM(ip), '') IS NOT NULL
  GROUP BY 1
)
SELECT
  COUNT(*) AS unique_ips,
  SUM(ever_flagged) AS ips_ever_flagged,
  SUM(CASE WHEN ever_flagged = 0 AND ever_accepted = 1 THEN 1 ELSE 0 END) AS ips_accepted_only,
  SUM(CASE WHEN ever_flagged = 1 AND ever_accepted = 1 THEN 1 ELSE 0 END) AS ips_mixed,
  SUM(CASE WHEN has_decision = 0 THEN 1 ELSE 0 END) AS ips_no_decision,
  ROUND(100.0 * SUM(ever_flagged) / COUNT(*), 2) AS pct_ips_ever_flagged
FROM ip_ac;
```

| Class | Unique IPs | % of Tune IPs |
|---|---:|---:|
| Ever `FLAGGED` (any click) | **661,316** | **14.6%** |
| `ACCEPTED` only | 3,780,102 | 83.5% |
| Mixed (accepted **and** flagged) | 288,678 | 6.4% |
| No decision on any click | 86,788 | 1.9% |
| All unique IPs | 4,528,275 | 100% |

**Rule for serving:** if any click on the IP is `FLAGGED`, keep that IP flagged; else `ACCEPTED`; else no Tune status → PX12 overlay only.

The 100K sample said 55.5% of IPs were flagged. **Warehouse is 14.6%.** Sample was FLAG-heavy — never present FLAG mix from it.

### 3.3 Reason codes

```sql
SELECT
  COALESCE(NULLIF(TRIM(access_control_reason_code), ''), '<empty>') AS reason,
  COUNT(*) AS clicks,
  COUNT(DISTINCT TRIM(ip)) AS unique_ips,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS pct_clicks
FROM raw.raw_tune_clicks
GROUP BY 1
ORDER BY 2 DESC;
```

| Reason | Clicks | Unique IPs | % clicks |
|---|---:|---:|---:|
| `NOT_APPLICABLE` (pass) | 12,512,362 | 4,069,291 | **76.74%** |
| `PROXY` | 1,089,334 | 336,011 | 6.68% |
| `NON_HUMAN_SCRIPT` | 623,639 | 179,013 | 3.82% |
| `10` (numeric, undocumented) | 563,411 | 82,092 | 3.46% |
| `BASIC_FRAUD` | 327,099 | 77,599 | 2.01% |
| `MASKED_DEVICES` | 270,931 | 89,409 | 1.66% |
| `ABNORMAL_TRAFFIC_PATTERNS` | 268,743 | 105,199 | 1.65% |
| `<empty>` | 213,683 | 131,875 | 1.31% |
| `BOT_GENERATED` | 205,306 | 22,432 | 1.26% |
| `9` (numeric) | 146,977 | 27,165 | 0.90% |
| `OTHER_REASON` | 45,620 | 15,072 | 0.28% |
| `SPOOFED` | 12,269 | 2,685 | 0.08% |
| `DATA_CENTER` | 9,766 | 2,666 | 0.06% |
| `VPN` | 8,302 | 4,004 | 0.05% |
| `MOBILE_PROXY_SIGNALS` | 6,342 | 3,908 | 0.04% |
| `NON_UNIQUE` | 522 | 413 | 0.003% |
| `8` (numeric) | 204 | 110 | <0.01% |
| `TOR` | 38 | 29 | <0.01% |
| `TOR_EXIT_NODE` | 1 | 1 | <0.01% |

The 100K sample only showed PROXY / MASKED_DEVICES / … and missed **`NON_HUMAN_SCRIPT`, `BASIC_FRAUD`, `SPOOFED`, and numeric codes `8`/`9`/`10`**. Warehouse reasons are the contract.

`status` is `unknown_status` on the sample — ignore it for fraud.

---

## 4. The 0.2% figure (wrong direction)

That number was **not** Tune fill and **not** “we have 0.2% of US IPs.”

Method: sample random IPs **from DB11**, exact-match to full Tune.

| Experiment | Sample | Present in Tune | Rate |
|---|---:|---:|---:|
| Random global DB11 IPs | 100,000 | 214 | **0.214%** |
| Random global DB11 IPs | 1,000,000 | 2,327 | **0.233%** |
| Same, US-labeled DB11 only | ~305k of the 1M | 2,264 | **~0.74%** |

Tune is 4.53M IPs. DB11 is all 4.29B IPv4. Reverse overlap **must** be tiny.

| Correct coverage question | Result |
|---|---|
| Tune IPs → DB11 (enrichment) | **~100%** of valid IPv4 |
| Tune unique IPs / DB11 US address mass (1.495B) | 4,528,275 / 1,494,722,560 = **0.303%** |
| Tune unique **US** IPs / DB11 US mass | 4,460,420 / 1,494,722,560 = **0.298%** |

**Talking line:** we see ~0.30% of US IPv4 as click traffic. Every one of those IPs can be geolocated in Lite DB11. 0.2% was sampling the internet, not our clicks.

Athena for reverse overlap (only if the scratch sample table still exists):

```sql
SELECT
  (SELECT COUNT(*) FROM scratch_ahsan.ip2location_db11_1m_ip_sample) AS sample_ips,
  COUNT(DISTINCT s.ip) AS present_in_tune
FROM scratch_ahsan.ip2location_db11_1m_ip_sample s
JOIN raw.raw_tune_clicks c ON s.ip = c.ip;
```

Do not use this as an onboarding KPI.

---

## 5. Lite DB11 / PX12 (full local dumps)

Queried from the CSVs in this repo (not Athena). Headers: **none**.

IPv4 int (same in Athena and Python):

```sql
TRY(
  CAST(split_part(ip, '.', 1) AS bigint) * 16777216
+ CAST(split_part(ip, '.', 2) AS bigint) * 65536
+ CAST(split_part(ip, '.', 3) AS bigint) * 256
+ CAST(split_part(ip, '.', 4) AS bigint)
) AS ip_int
```

Lookup: `ip_from <= ip_int AND ip_int <= ip_to`.

### 5.1 DB11 geo

| Property | Value |
|---|---|
| Ranges | 2,984,119 |
| Coverage | **Full IPv4**, `0` … `4,294,967,295`, **0 gaps** |
| US ranges / addresses | 911,913 · ~1.495B (~34.8% of IPv4) |
| Country `-` (no geo) | ~616M addresses (~14.4%) |
| Vendor Lite accuracy | ~**98% country / ~60% city** |

**Every valid Tune IPv4 hits a DB11 range.** Country is usable. City/ZIP are filled but Lite-approximate.

### 5.2 PX12 proxy

| Property | Value |
|---|---|
| Ranges | 2,690,046 |
| Addresses | **3,030,536** (0.07% of IPv4) |
| `proxy_type` | **PUB 100%** (no residential / enterprise) |
| `usage_type` | **DCH ~98%**, then ISP, EDU, … |
| `fraud_score` | Always filled; mode **80 (~86%)**; high 91–99 ~13% |
| `threat` filled | **1.90%** |
| `provider` filled | **0.98%** |

PX12 is a sparse public-proxy list. **Miss ≠ clean.** Do not treat `fraud_score = 80` as high risk.

---

## 6. Tune IPs → Lite DBs (the join that matters)

Athena cannot run this until DB11/PX12 are loaded. Until then, numbers are from **71,718 unique IPs in the 100K click sample** vs **full** Lite CSVs (`analyze_ip_sources.py`).

### 6.1 Fill / match (sample unique IPs — directional)

| Set | Unique IPs | % of sample Tune IPs |
|---|---:|---:|
| Tune IPv4 | 71,718 | 100% |
| Tune ∩ DB11 (any range) | **71,718** | **100%** |
| Usable geo (country ≠ `-`) | 71,701 | 99.98% |
| Tune `country_code` agrees with DB11 | — | **98.12%** of sample rows |
| Tune ∩ PX12 | **1,082** | **1.51%** |
| Tune ∩ DB11 ∩ PX12 | 1,082 | 1.51% |

Re-run on all **4.53M** unique Tune IPs after loading Lite tables (expect DB11 still ~100%; PX12 still ~1–2%).

### 6.2 Load Lite CSVs to Athena (one-time)

Upload `IP2LOCATION-LITE-DB11.CSV` and `IP2PROXY-LITE-PX12.CSV` to S3, then:

```sql
CREATE EXTERNAL TABLE scratch_<you>.ip2location_lite_db11 (
  ip_from bigint,
  ip_to bigint,
  country_code string,
  country_name string,
  region_name string,
  city_name string,
  latitude double,
  longitude double,
  zip_code string,
  time_zone string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES ('separatorChar' = ',')
LOCATION 's3://<bucket>/ip2location-lite-db11/'
TBLPROPERTIES ('skip.header.line.count'='0');

CREATE EXTERNAL TABLE scratch_<you>.ip2proxy_lite_px12 (
  ip_from bigint,
  ip_to bigint,
  proxy_type string,
  country_code string,
  country_name string,
  region_name string,
  city_name string,
  isp string,
  domain string,
  usage_type string,
  asn string,
  as_name string,
  last_seen string,
  threat string,
  provider string,
  fraud_score string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES ('separatorChar' = ',')
LOCATION 's3://<bucket>/ip2proxy-lite-px12/'
TBLPROPERTIES ('skip.header.line.count'='0');
```

Sanity:

```sql
SELECT COUNT(*) AS ranges, MIN(ip_from) AS min_from, MAX(ip_to) AS max_to
FROM scratch_<you>.ip2location_lite_db11;
-- expect 2984119, 0, 4294967295

SELECT COUNT(*) AS ranges, COUNT(DISTINCT proxy_type) AS proxy_types
FROM scratch_<you>.ip2proxy_lite_px12;
-- expect ~2690046 ranges, 1 type (PUB)
```

### 6.3 Unique Tune IPs → geo / proxy fill (warehouse)

Enrich **distinct IPs first** (~4.5M), not 16M click rows.

```sql
CREATE TABLE scratch_<you>.tune_unique_ips AS
SELECT
  TRIM(ip) AS ip,
  TRY(
    CAST(split_part(TRIM(ip), '.', 1) AS bigint) * 16777216
  + CAST(split_part(TRIM(ip), '.', 2) AS bigint) * 65536
  + CAST(split_part(TRIM(ip), '.', 3) AS bigint) * 256
  + CAST(split_part(TRIM(ip), '.', 4) AS bigint)
  ) AS ip_int,
  COUNT(*) AS clicks,
  MAX(CASE WHEN TRIM(access_control_decision) = 'FLAGGED' THEN 1 ELSE 0 END) AS ever_flagged,
  MAX(CASE WHEN NULLIF(TRIM(access_control_decision), '') IS NOT NULL THEN 1 ELSE 0 END) AS has_tune_ac,
  MAX(CASE WHEN TRIM(access_control_decision) = 'FLAGGED' THEN access_control_reason_code END) AS any_flag_reason,
  MAX(country_code) AS tune_country
FROM raw.raw_tune_clicks
WHERE NULLIF(TRIM(ip), '') IS NOT NULL
GROUP BY 1, 2;
```

Range join (Athena v3; may need a scratch IP table + sorted ranges):

```sql
-- Geo fill
SELECT
  COUNT(*) AS unique_ips,
  COUNT(d.ip_from) AS db11_hits,
  COUNT(CASE WHEN d.country_code NOT IN ('', '-') THEN 1 END) AS usable_country,
  COUNT(CASE WHEN d.city_name NOT IN ('', '-') THEN 1 END) AS city_filled,
  COUNT(CASE WHEN d.zip_code NOT IN ('', '-') THEN 1 END) AS zip_filled,
  ROUND(100.0 * COUNT(CASE WHEN t.tune_country = d.country_code THEN 1 END) / COUNT(*), 2) AS country_agree_pct
FROM scratch_<you>.tune_unique_ips t
LEFT JOIN scratch_<you>.ip2location_lite_db11 d
  ON t.ip_int BETWEEN d.ip_from AND d.ip_to;

-- PX12 hit rate
SELECT
  COUNT(*) AS unique_ips,
  COUNT(p.ip_from) AS px12_hits,
  ROUND(100.0 * COUNT(p.ip_from) / COUNT(*), 4) AS px12_hit_pct,
  COUNT(CASE WHEN t.ever_flagged = 1 AND p.ip_from IS NOT NULL THEN 1 END) AS flagged_and_in_px12,
  COUNT(CASE WHEN t.ever_flagged = 1 AND p.ip_from IS NULL THEN 1 END) AS flagged_missed_by_px12
FROM scratch_<you>.tune_unique_ips t
LEFT JOIN scratch_<you>.ip2proxy_lite_px12 p
  ON t.ip_int BETWEEN p.ip_from AND p.ip_to;
```

If the BETWEEN join is too expensive, run the same lookup in Python against the local CSVs (binary search on sorted ranges — see `analyze_ip_sources.py`).

---

## 7. Can Lite reconstruct Fraudlogix for a **new** IP?

Question: if an IP has never been in Tune, can DB11 + PX12 tag it as bot/proxy the way Fraudlogix does?

**Holdout idea:** IPs Tune already labeled, pretend they are new, score from Lite only, compare to `access_control`.

### 7.1 Sample evidence (71,718 IPs — do not treat as warehouse FLAG mix)

Using **primary** Tune decision per IP vs PX12 membership:

| Tune primary | Unique IPs | In PX12 | Not in PX12 |
|---|---:|---:|---:|
| `FLAGGED` | 39,704 | **567 (1.43%)** | **39,137 (98.57%)** |
| `ACCEPTED` | 32,014 | 515 (1.61%) | 31,499 |

PX12 also flags IPs Tune **accepted**. The lists are not the same fraud set.

| Tune primary reason | Unique IPs | PX12 hit rate |
|---|---:|---:|
| `PROXY` | 34,346 | **0.83%** |
| `MASKED_DEVICES` | 3,084 | 6.97% |
| `DATA_CENTER` | 373 | 11.8% |
| `VPN` | 43 | 20.9% |
| `BOT_GENERATED` | 29 | **0%** |
| `MOBILE_PROXY_SIGNALS` | 422 | **0%** |
| `TOR` | 1 | **0%** |

PX12 is slightly less bad on datacenter/VPN and contributes **nothing** on bot / mobile-proxy / Tor in this sample.

On the 1,082 PX12 hits: `proxy_type` = **PUB 100%**, `usage_type` DCH 83%, `fraud_score` 80 on 59%.

### 7.2 Warehouse holdout (after Lite tables are loaded)

```sql
SELECT
  CASE
    WHEN t.ever_flagged = 1 THEN 'FLAGGED'
    WHEN t.has_tune_ac = 1 THEN 'ACCEPTED_OR_OTHER'
    ELSE 'NO_TUNE_AC'
  END AS tune_class,
  CASE WHEN p.ip_from IS NOT NULL THEN 'px12_hit' ELSE 'px12_miss' END AS px12,
  COALESCE(p.usage_type, '<none>') AS usage_type,
  COUNT(*) AS unique_ips
FROM scratch_<you>.tune_unique_ips t
LEFT JOIN scratch_<you>.ip2proxy_lite_px12 p
  ON t.ip_int BETWEEN p.ip_from AND p.ip_to
GROUP BY 1, 2, 3
ORDER BY 1, 4 DESC;
```

By Fraudlogix reason vs PX12 (warehouse):

```sql
SELECT
  COALESCE(NULLIF(TRIM(t.any_flag_reason), ''), '<none>') AS flag_reason,
  COUNT(*) AS unique_ips,
  COUNT(p.ip_from) AS px12_hits,
  ROUND(100.0 * COUNT(p.ip_from) / COUNT(*), 2) AS px12_hit_pct
FROM scratch_<you>.tune_unique_ips t
LEFT JOIN scratch_<you>.ip2proxy_lite_px12 p
  ON t.ip_int BETWEEN p.ip_from AND p.ip_to
WHERE t.ever_flagged = 1
GROUP BY 1
ORDER BY 2 DESC;
```

**Expected conclusion (already supported by the sample):** Lite **cannot** reconstruct Fraudlogix for unseen IPs. Known IPs: use Tune. Unknown IPs: PX12 is a thin DCH/PUB overlay only; a miss is “not in Lite,” not “human.”

DB11 country/city/ZIP are **geo**, not bot rules. They will not replace `BOT_GENERATED` / `NON_HUMAN_SCRIPT` / `MASKED_DEVICES`.

---

## 8. Implementation split (from these analytics)

| Job | Source | What the data says |
|---|---|---|
| Geo on Tune IPs | Lite DB11 | ~100% range hit; country usable; city/ZIP Lite-approx |
| Fraud on **known** Tune IPs | `access_control_*` | 98.08% of unique IPs; 14.6% ever flagged |
| Fraud on **unknown** IPs / 86,788 with no AC | Lite PX12 | Overlay only; ~1.5% hit on sample; miss ≠ clean |
| Do not require | Tune ∩ PX12 ∩ DB11 | Intersection is tiny; DB11 is universal, PX12 is not |

---

## 9. Re-run checklist

| # | Query | Pass if |
|---|---|---|
| 1 | §1 inventory | ~16.3M rows, ~4.53M unique IPv4, ~98.4% US |
| 2 | §2 AC fill | ~98.7% rows, ~98.1% unique IPs; ~87k IPs with no AC |
| 3 | §3.2 IP flags | Ever-flagged **≪** 55% (warehouse ~15%) |
| 4 | §3.3 reasons | `NOT_APPLICABLE` majority; PROXY + NON_HUMAN_SCRIPT + numeric codes present |
| 5 | §6 DB11 | ~100% of unique Tune IPv4 |
| 6 | §6–7 PX12 | Low hit rate; does not recover most `FLAGGED` |

Re-run §1–3 on ship day; Tune grew slightly even on 18–19 Aug 2026.

---

## 10. Query IDs (this pull)

| Query | Athena execution id |
|---|---|
| Inventory | `3740685e-bc10-41e6-9974-3a10a1e91eee` |
| AC fill | `9a423da3-760f-4d95-84db-09d4499df096` |
| Decision mix | `47bba3aa-ed2e-4a59-a0d2-bde5bfbb7fbc` |
| Reason mix | `7e38d3b3-7fe4-4535-8bf2-645bd2a98f9b` |
| IP-level flags | `7bfa377a-b1b0-48fc-9b61-dd7ac22f1e44` |
| Country mix | `2453c573-38ee-46eb-a365-a5adc16484de` |
