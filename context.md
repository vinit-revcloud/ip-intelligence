# Context: IP data onboarding (RevCloud)

> Living brief for this workspace. Update when warehouse numbers change.  
> **Last warehouse pull:** 19 Aug 2026 (Athena, full `raw.raw_tune_clicks` — not 100K samples).  
> Companions: [`DATA_PROFILING.md`](./DATA_PROFILING.md) (Tune × Lite analytics + SQL), [`ATHENA_PROFILING_RUNBOOK.md`](./ATHENA_PROFILING_RUNBOOK.md), [`IP_Data_Source_Analysis.md`](./IP_Data_Source_Analysis.md), [`database.md`](./database.md).

---

## 0. How to answer future questions

Read this file first. Then:

1. If the question is about **our traffic / fill / sessions vs Tune** → use **§2 warehouse numbers** (Athena). Never use the 100K CSV.
2. If the question is **0.2%** → that is **not** session fill. See **§4 misconceptions**.
3. If the question is **225M IPs** → that is Segment **event rows**, not unique IPs. See **§4**.
4. If the question is **why Tune IPs > session IPs** → Tune click ≠ session. See **§4**.
5. If the question is **implement / join** → **§6 pipeline**. Do not use `session_click_ids`.
6. If the question is **DB11 accuracy / PX12 quality** → **§5** (local full dumps).

Athena: account `221490242148`, region `us-west-2`, workgroup `primary`, engine v3.  
CLI profile that can query: `source-creation-tool` (user `alyson-training-app` cannot). Unset HTTP(S)_PROXY if Athena CLI hangs.

---

## 1. What we are onboarding

Enrich **on-site sessions** with:

| Job | Source | Constraint |
|---|---|---|
| Grain | `unified.unified_session_summary` | One row = `session_id` |
| Geo | IP2Location Lite **DB11** | Country usable; city/ZIP Lite-approximate (~60% city) |
| Fraud primary | Tune `access_control_decision` + `access_control_reason_code` | Join on IP string |
| Fraud fallback | IP2Proxy Lite **PX12** | Positive hit only; miss ≠ clean; 100% `PUB` |

**Join key:** dotted IPv4 (`session_ip` / Tune `ip` / Segment `context_ip`) → uint32 → `BETWEEN ip_from AND ip_to`.  
**Do not join** Tune ↔ sessions on click IDs via `unified.session_click_ids`.

Partitions (confirmed DESCRIBE):

| Table | Partition |
|---|---|
| `raw.raw_tune_clicks` | `date_pst` |
| `unified.unified_session_summary` | `session_date` |
| `raw.segment_events` | `date` |
| `unified.session_click_ids` | `session_date` |

---

## 2. Warehouse truth (full tables, 18 Aug 2026)

### 2.1 Inventory

| src | rows | unique IPs | min date | max date |
|---|---:|---:|---|---|
| `raw.raw_tune_clicks` | **16,304,549** | **4,528,275** | 2023-01-11 | 2026-08-18 |
| `unified.unified_session_summary` | **11,331,530** | **1,990,844** | 2022-08-19 | 2026-08-16 |
| `raw.segment_events` | **297,910,970** | **~2,037,043** `context_ip` (approx_distinct) | 2022-08-19 | 2026-08-18 |

Tune unique IPs grew by ~121 vs an earlier scan the same day (4,528,154 → 4,528,275). Re-run before ship.

### 2.2 Bill’s fill rate (session IPs in Tune)

| session unique IPs | Tune unique IPs | overlap | **% of session IPs in Tune** |
|---:|---:|---:|---:|
| 1,990,844 | 4,528,275 | **1,582,733** | **79.5%** |

This is the number to quote for “can Tune enrich our visitors?”  
**~20.5%** of session IPs have no Tune row (organic / SMS-direct / unmatched).

Inverse: only **~35%** of Tune unique IPs ever appear on a session (~2.95M Tune-only IPs). Those are clicks that never became a session, not missing session storage.

### 2.3 Tune fraud fill

| clicks | `access_control` fill (rows) | unique IPs |
|---:|---:|---:|
| 16,304,549 | **98.69%** | 4,528,275 |

Decision and reason fill as a **pair**. Unique-IP fill **98.08%** (4,441,487 IPs). **86,788** unique IPs have no AC on any click.

Decisions (full table, 19 Aug 2026): `ACCEPTED` **76.71%** of clicks · `FLAGGED` **21.97%** · empty 1.31% · `IGNORED` ~0%.  
**Unique IPs ever FLAGGED: 661,316 (14.6%)** — not the 55% from the 100K sample. Mixed accepted+flagged: 288,678 IPs. IPs with no decision on any click: **86,788**.  
Top reasons: `NOT_APPLICABLE` 76.74%, `PROXY` 6.68%, `NON_HUMAN_SCRIPT` 3.82%, numeric `10` 3.46%, `BASIC_FRAUD` 2.01%, then `MASKED_DEVICES` / `ABNORMAL_TRAFFIC_PATTERNS` / `BOT_GENERATED`. Sample missed several warehouse reasons.  
`status` is `unknown_status` — ignore for fraud.

### 2.4 Session IP / geo / proxy fields already on the table

| field | fill % |
|---|---:|
| `session_ip` | **100.0%** |
| `ip_country_code` | **76.59%** |
| `ip_city_name` | **76.59%** |
| `ip_zip_code` | **76.59%** |
| `ip_is_proxy` | **76.59%** |
| `ip_is_vpn` | **0.0%** |

Sessions already have **some** IP intel on 76.59% of rows (country/city/zip/proxy together). **VPN is unused.**  
DB11 is a **replace/compare** for geo, not filling a blank table. Tune/PX12 are still needed for real fraud (proxy flag at 76.59% is not Tune `access_control`).

Other session facts (prior scan, still valid unless re-run):

- Distinct `session_id` = row count (11,331,530).
- Almost all `session_ip` are IPv4 (~30 IPv6).
- `is_bot_click`: ~2.23M bot sessions / 1.87M unique IPs on non-bot.
- `last_channel` = 100% `client` — **useless** for SMS vs Tune. Use `last_utm_source` / `session_id_source`.
- `session_id_source` top: `tune_synthetic_child` ~4.92M, `provisional` ~3.79M, `native` ~1.40M.
- Top UTMs: `aff-cc`, `aff-bsm`, empty, `aff-maven`, `facebook`, `aff-ora`.

### 2.5 Segment (confirms unique-IP cardinality)

| field | fill | approx distinct |
|---|---:|---:|
| `context_ip` | ~99.97% | **~2.04M** |
| `properties_ip` | ~65.2% | **~2.69M** |
| `ip_hash` | ~99.97% | ~2.08M |
| `canonical_session_id` | 100% | **~33.0M** |
| `tune_transaction_id` | ~60.6% | ~5.78M |

Event types: track ~154M, page ~144M, identify ~83k.  
`is_organic_session` is tiny (~9k events). `is_direct_session` ~21M events (7%).  
**~33M canonical session IDs vs 11.3M unified sessions** → unified is a collapsed/quality set, not every Segment session.

### 2.6 `unified.session_click_ids` — do not use

| rows | `clickid_tune_click_id` filled | `clickid_txn_id` | dates |
|---:|---:|---:|---|
| **49,746** | 35,730 | **0** | 2026-01-17 → 2026-08-16 |

0.44% of sessions. Tune `affiliate_click_id` match was ~783. **Not a production join.**

---

## 3. Local Lite DBs (full CSVs in this repo)

Headers: **none** on `IP2LOCATION-LITE-DB11.CSV` and `IP2PROXY-LITE-PX12.CSV`.  
`*-us-1000.csv` files are **not** full US extracts.

### 3.1 IP2Location Lite DB11 (geo)

- 2,984,119 ranges; **full IPv4**, no gaps (`0` … `4294967295`).
- US: 911,913 ranges, ~1.495B addresses (~34.8% of IPv4).
- Country `-`: ~616M addresses (~14.4%).
- Lite = Class C (/24) majority location. Vendor ~**98% country / ~60% city**.
- On the 100K **click sample** (lookup only): 100% range hit, 99.98% usable geo, 98.8% country agree with Tune. **Do not cite 100K for warehouse fill rates.**

IPv4 int: `ip_int = a*16777216 + b*65536 + c*256 + d`. Lookup: `ip_from <= ip_int <= ip_to`.

### 3.2 IP2Proxy Lite PX12 (proxy)

- 2,690,046 ranges, **3,030,536 addresses** (0.07% of IPv4). Sparse list.
- `proxy_type` = **PUB 100%**. No residential/enterprise class.
- `usage_type`: **DCH ~98%**, then ISP, EDU, …
- `fraud_score` always filled, mode **80 (~86%)**; high band 91–99 ~13%.
- `threat` fill **1.90%**; `provider` **0.98%**.
- On 100K Tune unique IPs: PX12 hit **1.51%**. Recovers ~1.4% of Tune-FLAGGED IPs. **Cannot replace Tune/Fraudlogix.**

---

## 4. Misconceptions (repeat these)

| Claim | Truth |
|---|---|
| Tune fills 0.2% of sessions | **False.** Session-IP overlap is **79.5%**. 0.2% was random IPs drawn from **all IPv4 in DB11** that happened to appear in Tune (214/100k = 0.214%). Wrong denominator. |
| We have 0.2% of US IPs | **False.** Tune 4.53M / DB11 US mass 1.495B ≈ **0.30%** of US IPv4 space. US-only reverse sample was **~0.7%**. |
| Session unique IPs = 225M | **False.** Sessions = **1.99M** unique IPs. Segment = **~298M event rows**, **~2.04M** unique `context_ip`. 225M was almost certainly event volume. |
| Every Tune click is a session, so session IPs ≥ Tune IPs | **False.** Tune is the ad network; a session needs Segment on the page. **65% of Tune unique IPs never appear on a session.** SMS-direct/organic add **sessions**, not millions of new IPs (same ~2M pool). |
| Unified is missing most IP data | **False vs Segment.** Segment unique `context_ip` ≈ session unique IPs (~2M). Unified is smaller than ~33M canonical Segment session IDs (collapsed), not missing a 225M-IP list. |
| 100K sample `access_control` = 100% | Sample only. Warehouse = **98.69%** of Tune **rows**. |
| PX12 miss = clean IP | **False.** Lite is a thin public-proxy list. |
| Use `session_click_ids` to stitch Tune | **False.** ~50k rows, no txn_id. Join on **IP**. |

**One-liner for Bill:** Tune covers **~80% of session IPs**; 0.2% is internet-wide sampling; 225M is Segment events; Tune can have more unique IPs than sessions because most extra Tune IPs never landed.

---

## 5. Implementation contract

### 5.1 Serving grain

`unified.unified_session_summary`  
Keys: `session_id`, `session_date`, `session_ip`, `is_bot_click`.  
Enrich **distinct `session_ip` first (~2M)**, then join back to 11.3M sessions (cheaper than ranging 11M × 3M DB11).

### 5.2 Pipeline

1. `session_ip` → `ip_int`.
2. **Geo:** DB11 `ip_int BETWEEN ip_from AND ip_to`. Compare/replace existing `ip_country_*` / city / zip (already 76.59% filled). Label city/ZIP approximate.
3. **Fraud primary:** Tune clicks grouped by `ip`. If any `FLAGGED`, use that reason; else `ACCEPTED`; else no Tune status.
4. **Fraud fallback:** PX12 only if no Tune row (or overlay). Miss ≠ clean. Do not treat `fraud_score = 80` as high risk. `ip_is_vpn` is currently **0%** — PX12/Tune will not magically fill VPN unless the source has it (Tune reasons include `VPN` rarely; PX12 `provider` ~1%).
5. Do not require Tune ∩ PX12 ∩ session (intersection is tiny).

### 5.3 Athena IP int

```sql
TRY(
  CAST(split_part(ip, '.', 1) AS bigint) * 16777216
+ CAST(split_part(ip, '.', 2) AS bigint) * 65536
+ CAST(split_part(ip, '.', 3) AS bigint) * 256
+ CAST(split_part(ip, '.', 4) AS bigint)
) AS ip_int
```

### 5.4 Existing session IP columns vs new sources

| Session column | Today | After onboarding |
|---|---|---|
| `session_ip` | 100% | keep as join key |
| `ip_country_*` / city / zip | 76.59% | DB11 can raise toward ~100% of IPv4; city/ZIP still Lite-approx |
| `ip_is_proxy` | 76.59% | Tune FLAGED/`PROXY` + PX12 PUB are stronger fraud labels |
| `ip_is_vpn` | 0% | Tune `VPN` reason is rare; PX12 Lite will not fill this densely |

---

## 6. Key column map

**Tune** (`raw.raw_tune_clicks`): `ip`, `transaction_id`, `affiliate_click_id`, `date_pst`, `access_control_decision`, `access_control_reason_code`, `country_code` (audit only).

**Sessions:** `session_id`, `session_ip`, `session_date`, `session_id_source`, `last_utm_source`, `is_bot_click`, `page_brand`, existing `ip_*` geo/proxy.

**Segment:** `context_ip` (near-full), `properties_ip` (sparser, slightly higher distinct), `canonical_session_id`, `tune_transaction_id`, `event_date` / partition `date`.

**DB11 (no header):** `ip_from, ip_to, country_code, country_name, region_name, city_name, latitude, longitude, zip_code, time_zone`.

**PX12 (no header):** `ip_from, ip_to, proxy_type, country_code, country_name, region_name, city_name, isp, domain, usage_type, asn, as, last_seen, threat, provider, fraud_score`.

---

## 7. Local files (this repo)

| File | Use |
|---|---|
| `IP2LOCATION-LITE-DB11.CSV` | Full geo DB (no header) |
| `IP2PROXY-LITE-PX12.CSV` | Full proxy DB (no header) |
| `raw_tune_clicks_100K_sample.csv` | **Dev only** — not warehouse KPIs |
| `session_summary_geo_columns_100K_sample.csv` | Geo plugin sample — **no IP**, cannot join |
| `DATA_PROFILING.md` | Tune × Lite profiling (Athena SQL + filled results) |
| `ATHENA_PROFILING_RUNBOOK.md` | SQL to re-run on full tables |
| `IP_Data_Source_Analysis.md` | Long-form analysis |
| `analyze_ip_sources.py` | Local sample × DB11 × PX12 |

---

## 8. Sign-off checks

| Check | Pass |
|---|---|
| Session IP fill | 100% |
| Session unique IPs ≈ Segment `context_ip` | both ~2M |
| Session IPs in Tune | **~79.5%** |
| Tune AC fill | **~98.7%** of clicks |
| DB11 | ~100% of valid IPv4 |
| PX12 | overlay only |
| `session_click_ids` | unused |

Re-run inventory + overlap on ship day; Tune already moved slightly on 18 Aug 2026.
