# IP Data Sources & Accuracy Constraints — Complete Analysis

**Date:** August 18, 2026  
**Prepared for:** IP data onboarding decision (pair-programming / blocker assessment follow-up)  
**Status:** Analysis complete on local 100K sample + full-table Athena scan of `raw.raw_tune_clicks` (18 Aug 2026)

---

## Executive summary

This document answers the onboarding questions on Tune / Fraudlogix `access_control` coverage, the “0.2% of US IPs” wording, default-flagged IPs, and a three-way cross-match of **IP2Location Lite DB11**, **raw Tune clicks**, and **IP2Proxy Lite PX12**.

**Headline findings**

1. Full `raw.raw_tune_clicks`: **16,304,374** click rows, **4,528,154 unique IPs** (4,460,300 US). The 100K sample had 71,718 unique IPs.
2. **`access_control` is not 100% on the full table.** Both decision and reason are filled on **98.69% of rows** and **98.08% of unique IPs**. The 100K sample (100% fill) overstated coverage. **86,788 unique IPs** (213,683 rows) have no Tune fraud status — that is the PX12 fallback population.
3. **100%** of sample IPs match an IP2Location DB11 range. Tune → DB11 is a complete lookup, not a 0.2% join.
4. The **~0.2% figure is reverse overlap** (random DB11 IPs found in Tune). It is **not** Tune field fill rate, and it is **not** “0.2% of US IPs.” Full-table distinct IPs are **0.303%** of DB11 US address space (US-labeled distinct IPs **0.298%**).
5. On the 100K sample, Tune flags **39,805 unique IPs (55.5%)**. Default pass is `ACCEPTED` / `NOT_APPLICABLE`. Full-table FLAG vs ACCEPTED mix still needs the decision-distribution query.
6. IP2Proxy PX12 matches only **1,082 sample Tune IPs (1.51%)**. It recovers **1.4%** of sample Tune-flagged IPs. PX12 Lite cannot replace Fraudlogix.
7. Geolocation should map directly to DB11. Country is usable; city/ZIP are filled but Lite-approximate (~60% city accuracy).

**Practical onboarding split**

| Purpose | Source of record | Constraint |
|---|---|---|
| Geolocation | IP2Location Lite DB11 | Country reliable; city/ZIP approximate |
| Fraud on historical clicks | Tune `access_control_*` | **98.08%** of unique IPs on full table (100% in 100K sample) |
| Fraud fallback (86,788 IPs with no Tune AC) | PX12 Lite is **not** sufficient | Sparse public-proxy list only |

---

## 1. Scope, datasets, and method

### 1.1 Datasets used

| Dataset | File | Grain | Rows / ranges used |
|---|---|---|---|
| Tune / Fraudlogix clicks | `raw_tune_clicks_100K_sample.csv` | One click event | 100,000 rows |
| IP2Location Lite DB11 | `IP2LOCATION-LITE-DB11.CSV` | Inclusive IPv4 range | 2,984,119 ranges (full dump) |
| IP2Proxy Lite PX12 | `IP2PROXY-LITE-PX12.CSV` | Inclusive IPv4 range | 2,690,046 ranges (full dump) |
| Session geo columns | `session_summary_geo_columns_100K_sample.csv` | Session / plugin geo | 100,000 rows — **no IP column, cannot join** |

Full-table Athena scan of `raw.raw_tune_clicks` (18 Aug 2026) plus prior reverse-overlap experiments:

| Metric | Value |
|---|---|
| Click rows | **16,304,374** |
| Distinct `ip` | **4,528,154** |
| Distinct US `ip` | **4,460,300** (98.50%) |
| US click rows | **16,041,061** (98.39%) |
| Both `access_control_*` filled (rows) | 16,090,691 (**98.69%**) |
| Both `access_control_*` filled (unique IPs) | 4,441,366 (**98.08%**) |
| Unique IPs missing AC (PX12 fallback set) | **86,788** |
| DB11 → Tune exact overlap (100K random DB11 IPs) | 214 (0.214%) |
| DB11 → Tune exact overlap (1M random DB11 IPs) | 2,327 (0.2327%) |

### 1.2 How IPs were matched

DB11 and PX12 store `ip_from` / `ip_to` as 32-bit integers, not dotted quads. Each Tune `ip` was converted to an integer and looked up with a binary search on sorted ranges (`ip_from <= ip_int <= ip_to`).

- **DB11 covers all IPv4** (`0`–`4,294,967,295`, zero gaps). Every valid IPv4 hits some row.
- **PX12 does not cover all IPv4.** It is a list of proxy/suspicious ranges only. A miss means “not in Lite PX12,” not “not a proxy.”
- String fields treat `-` as empty when computing fill rates.

### 1.3 Questions this document answers

1. How many unique IPs are in raw Tune clicks?
2. What is the `access_control` fill rate? Do 100% of those IPs have it populated?
3. How should “we only have 0.2% IPs of the US” be worded?
4. How many IPs are flagged by default?
5. Cross-match Tune × IP2Location × IP2Proxy — which IPs are marked fraud?
6. For the overlapping subset, what IP types are present?
7. Is 0.2% misleading once known IP types are removed? Is Tune → DB11 100%?
8. Fraud workflow: Tune first, fallback to the other DB, then map fraud.
9. Geolocation: map directly to IP2Location.

---

## 2. Direct answers

### Q1. From raw Tune clicks, how many unique IP addresses?

**Full table (`raw.raw_tune_clicks`): 4,528,154 unique IPs.**  
**100K sample: 71,718 unique IPs.**

| Metric | Full table (Athena) | 100K sample |
|---|---|---|
| Click rows | **16,304,374** | 100,000 |
| Unique IPs | **4,528,154** | 71,718 |
| Rows with an IP | 16,304,374 (100%) | 100,000 (100%) |
| Unique US IPs | **4,460,300 (98.50%)** | 68,883 (96.0%) |
| US click rows | **16,041,061 (98.39%)** | 95,220 (95.2%) |
| Distinct IPs / DB11 US space (1.495B) | **0.303%** | — |
| Distinct US IPs / DB11 US space | **0.298%** | — |

Every click row has an IP. Traffic is almost entirely US.

### Q2. Do 100% of those IPs have `access_control` values populated?

**No on the full table. Yes on the 100K sample.**

Decision and reason always fill together (identical counts). They are a pair, not independent columns.

| Grain | Full table (Athena) | 100K sample |
|---|---|---|
| Rows with both AC columns | 16,090,691 / 16,304,374 (**98.69%**) | 100,000 / 100,000 (100%) |
| Unique IPs with both AC columns | 4,441,366 / 4,528,154 (**98.08%**) | 71,718 / 71,718 (100%) |
| Rows missing AC | **213,683 (1.31%)** | 0 |
| Unique IPs missing AC | **86,788 (1.92%)** | 0 |

The 100K sample overstated fill. On historical warehouse data, about **1 in 52 unique IPs** has no Tune fraud status. That **86,788-IP set is the real fallback universe** for PX12 (or commercial proxy data). Do not treat historical Tune as 100% complete.

---

## 3. Historical Tune `access_control` — values, not just fill

Fill rate being 100% does not mean every IP is clean. Decision split:

### 3.1 Decision

| `access_control_decision` | Click rows | % of rows | Unique IPs (always this value) |
|---|---|---|---|
| `FLAGGED` | 52,675 | 52.68% | 39,601 always FLAGGED |
| `ACCEPTED` | 47,325 | 47.32% | 31,913 always ACCEPTED |
| Mixed (both across clicks) | — | — | 204 |

**Unique IPs with at least one FLAGGED click: 39,805 (55.5%).**

### 3.2 Reason codes

| `access_control_reason_code` | Click rows | % of rows | Unique IPs (primary reason) |
|---|---|---|---|
| `NOT_APPLICABLE` (pass) | 47,325 | 47.33% | 32,014 |
| `PROXY` | 42,169 | 42.17% | 34,346 |
| `MASKED_DEVICES` | 6,734 | 6.73% | 3,084 |
| `ABNORMAL_TRAFFIC_PATTERNS` | 1,625 | 1.63% | 1,406 |
| `BOT_GENERATED` | 885 | 0.89% | 29 |
| `DATA_CENTER` | 607 | 0.61% | 373 |
| `MOBILE_PROXY_SIGNALS` | 560 | 0.56% | 422 |
| `VPN` | 94 | 0.09% | 43 |
| `TOR` | 1 | <0.01% | 1 |

Primary reason = the most frequent reason code on that IP. PROXY dominates the flagged population.

These are the Fraudlogix-style security fields (proxy, bot, datacenter, VPN, Tor). They are **fully populated** on historical clicks. The original blocker that described them as “populated for only ~0.2% of IP2Location coverage” was mixing **field fill on click rows** with **reverse IPv4-space overlap**. Those are different metrics (see Section 4).

---

## 4. Coverage framing: the 0.2% figure

### 4.1 What the 0.2% actually measured

Previous analysis sampled random IPs **from IP2Location DB11**, then exact-matched them to the **full** `raw.raw_tune_clicks` table in Athena.

| Experiment | Sample IPs | Present in Tune | Rate |
|---|---|---|---|
| 100K random DB11 IPs (global) | 100,000 | 214 | **0.214%** |
| 1M random DB11 IPs (global) | 1,000,000 | 2,327 | **0.233%** |

Of the 214 hits in the 100K run, **210 were US**, 2 CA, 1 ZA, 1 GP.

This is **reverse overlap**: “if I pick a random IPv4 from the geo DB, how often have we ever seen it in Tune?” It is expected to be small because DB11 spans all 4.29 billion IPv4 addresses and Tune only has ~4.5 million distinct IPs.

### 4.2 Proposed wording vs correct wording

**Do not say:** “We only have 0.2% IPs of the US.”

That sentence uses the global reverse-overlap rate as if it were US inventory coverage. It is neither.

| Coverage question | Result | Correct reading |
|---|---|---|
| Tune IPs → DB11 (enrichment direction) | **100%** | Every historical click IP looks up. This is the join to use. |
| Random **global** DB11 IPs → full Tune table | 0.21–0.23% | Original 0.2%. Includes unused, reserved, and non-US space. |
| Random **US-labeled** DB11 IPs → full Tune table | **0.69–0.74%** | Same experiment, US only (210/30,578; 2,264/305,383). |
| Full Tune distinct IPs / DB11 US address mass | **0.303%** | 4,528,154 / 1,494,722,560. |
| Full Tune distinct US IPs / DB11 US address mass | **0.298%** | 4,460,300 / 1,494,722,560. |
| PX12 US addresses / DB11 US address mass | **0.072%** | 1,071,370 / 1,494,722,560. PX12 is not a US inventory. |

**Recommended wording for management**

> Historical Tune / Fraudlogix contains on the order of **0.30% of US IPv4 addresses labeled in IP2Location** (4,528,154 distinct click IPs, of which 4,460,300 are US, vs ~1.50B US addresses in DB11). A random sample of all IPv4 from DB11 hits Tune only ~0.2% of the time; restricting that sample to US-labeled ranges raises the hit rate to ~0.7%. This is a **universe-size** limit (we only see click traffic). Separately, `access_control` is filled for **98.08% of unique IPs** on the full table (100% in the 100K sample), so there is a small real fill gap of **86,788 IPs**.

### 4.3 Why 0.2% is misleading — remove known types

The reverse 0.2% is pulled down by sampling:

- Unallocated / unknown DB11 ranges (`country_code = '-'`): 7,658 ranges, **616M addresses (~14.4% of IPv4)**
- Non-US space (~65% of IPv4 by DB11 labels)
- Datacenter and other well-known types that are not our click mix

Restricting to US-labeled ranges (the relevant commercial universe) moves 0.2% → **~0.7%**.

**That still does not change enrichment.** Direction of the join:

- **Clicks ⊂ DB11 ≈ 100%** (confirmed on this sample: 71,718 / 71,718)
- **Random DB11 ⊂ clicks ≈ 0.2%** (wrong join shape for onboarding)

After dropping the 17 Tune IPs that land in unknown-geo DB11 ranges (`148.178.x.x`), remaining IPs still match DB11 at **100%** (71,701 / 71,701). Known-type filtering does **not** reduce the Tune → DB11 match rate below 100%.

---

## 5. How many IPs are flagged by default?

There are two “default flag” concepts — one in Tune, one in PX12. They are not the same.

### 5.1 Tune / Fraudlogix (source of record on historical clicks)

On Tune, **default is a pass, not a fraud flag.**

| Class | Definition | Unique IPs | Click rows |
|---|---|---|---|
| Default pass | Always `ACCEPTED` + `NOT_APPLICABLE` | **31,913** | 47,325 |
| Actively flagged | Any `FLAGGED` click | **39,805 (55.5%)** | 52,675 |
| Mixed | Same IP accepted on some clicks, flagged on others | 204 | — |

So: **31,913 unique IPs are “flagged by default” only in the sense that they take the default pass path.** The fraud-positive set is the 39,805 FLAGGED IPs, led by `PROXY`.

### 5.2 IP2Proxy Lite PX12 (entire database)

Every PX12 row is already a proxy listing. `proxy_type` is **PUB (public proxy) on 100% of 2,690,046 ranges**. There is no residential / enterprise class in this Lite dump.

Numeric default on PX12 is `fraud_score = 80`:

| PX12 class | Ranges | % of PX12 ranges | Addresses |
|---|---|---|---|
| `proxy_type = PUB` (every row) | 2,690,046 | 100% | 3,030,536 |
| `fraud_score = 80` (default) | **2,309,652** | **85.86%** | 2,528,464 (83.4% of PX12 address mass) |
| `fraud_score` 91–99 (high band) | 351,950 | 13.08% | 471,758 |
| `fraud_score` 27–36 (low band) | ~28,444 | ~1.06% | — |
| `usage_type = DCH` | 2,639,857 | 98.13% | — |
| `threat` filled (not `-`) | 51,002 | 1.90% | — |
| `provider` filled (not `-`) | 26,278 | 0.98% | — |

**PX12 default-flagged IPs (score 80): 2,309,652 ranges / 2,528,464 addresses.** Being in PX12 at all is already a public-proxy flag; 80 is the generic score, not a calibrated high-risk score.

### 5.3 Default score on the overlapping Tune IPs

Of the 1,082 Tune IPs that hit PX12:

| `fraud_score` | Unique Tune IPs | % of PX12 hits |
|---|---|---|
| 80 (default) | 639 | 59.1% |
| 91–99 (high) | 439 | 40.6% |
| 36 (low) | 4 | 0.4% |

Even when PX12 matches click traffic, most hits carry the default 80.

---

## 6. Three-way cross-match (DB11 × Tune × PX12)

Lookup was performed on the **71,718 unique Tune IPs** against the full DB11 and PX12 range files.

| Set | Unique IPs | % of Tune unique IPs |
|---|---|---|
| Tune IPv4 | 71,718 | 100% |
| Tune ∩ DB11 | **71,718** | **100%** |
| Tune ∩ PX12 | **1,082** | **1.51%** |
| Tune ∩ DB11 ∩ PX12 | 1,082 | 1.51% |
| Tune ∩ DB11 only (no PX12) | 70,636 | 98.49% |
| In PX12 but not DB11 | 0 | 0% |
| In neither | 0 | 0% |

US-only among Tune unique IPs: 68,883 match DB11 (100%); **989 (1.44%)** match PX12.

**Interpretation:** every click IP can be geolocated in DB11. PX12 is a thin overlay, not a second copy of Fraudlogix coverage.

### 6.1 Which IPs are marked fraud — Tune vs PX12 disagreement

Tune `FLAGGED` is the fraud label on historical clicks. PX12 membership is an independent public-proxy list. They barely overlap.

Using **primary** Tune decision per IP (most frequent `access_control_decision`):

| Tune primary decision | Unique IPs | In PX12 | Not in PX12 |
|---|---|---|---|
| `FLAGGED` | 39,704 | **567 (1.43%)** | **39,137 (98.57%)** |
| `ACCEPTED` | 32,014 | **515 (1.61%)** | 31,499 |

PX12 Lite recovers **567 of 39,704** Tune-flagged IPs. It also lists **515 IPs Tune accepted**. The two systems do not agree on the same fraud set.

### 6.2 Tune reason code vs PX12 hit

| Tune primary reason | Unique IPs | In PX12 | PX12 hit rate | Missed by PX12 |
|---|---|---|---|---|
| `PROXY` | 34,346 | 286 | **0.83%** | 34,060 |
| `MASKED_DEVICES` | 3,084 | 215 | 6.97% | 2,869 |
| `ABNORMAL_TRAFFIC_PATTERNS` | 1,406 | 13 | 0.92% | 1,393 |
| `MOBILE_PROXY_SIGNALS` | 422 | **0** | **0%** | 422 |
| `DATA_CENTER` | 373 | 44 | 11.8% | 329 |
| `VPN` | 43 | 9 | 20.9% | 34 |
| `BOT_GENERATED` | 29 | **0** | **0%** | 29 |
| `TOR` | 1 | **0** | **0%** | 1 |
| `NOT_APPLICABLE` (accepted) | 32,014 | 515 | 1.61% | 31,499 |

PX12 is slightly better at `DATA_CENTER` and `VPN` than generic `PROXY`, and still misses **88% of Tune DATA_CENTER IPs** and **79% of Tune VPN IPs**. It contributes **nothing** on bot, mobile-proxy, and Tor in this sample.

**PX12 Lite cannot stand in for Tune / Fraudlogix.** A PX12 miss does not mean the IP is clean.

---

## 7. IP types in the overlapping subset (the 1,082 Tune ∩ PX12 IPs)

This is the only place PX12 can attach a type onto click IPs. Every one of these IPs is also in DB11.

### 7.1 Columns that are present

| PX12 field | On the 1,082 hits | Share of hits |
|---|---|---|
| `proxy_type` | `PUB` only | **1,082 (100%)** |
| `usage_type = DCH` | Datacenter / hosting / transit | **899 (83.1%)** |
| `usage_type = EDU` | University / school | 178 (16.5%) |
| `usage_type = ISP` | Fixed-line ISP | 4 (0.4%) |
| `usage_type = ORG` | Organization | 1 (<0.1%) |
| `fraud_score = 80` | Default numeric flag | 639 (59.1%) |
| `fraud_score` 91–99 | High-risk band | 439 (40.6%) |
| `threat` filled | BOTNET / SPAM / SCANNER (and combos) | 73 (6.7%) |
| `provider` filled | Named VPN/proxy vendor | 9 (0.8%) |
| PX12 `country_code = US` | — | 949 (87.7%) |

`proxy_type` being 100% `PUB` confirms the Lite limitation: **no residential or enterprise proxy class.** Enterprise/residential proxies will go unflagged if we rely on PX12 Lite.

### 7.2 Threat values when filled (73 IPs)

| `threat` | Unique Tune IPs in PX12 |
|---|---|
| (empty / `-`) | 1,009 |
| `BOTNET` | 40 |
| `SPAM` | 14 |
| `SCANNER` | 13 |
| `SPAM/SCANNER` | 5 |
| `SPAM/BOTNET` | 1 |

### 7.3 After removing known types (DCH)

The 0.2% / overlay figures are distorted by datacenter ranges (98% of PX12, 83% of Tune∩PX12).

| After dropping `usage_type = DCH` | Unique Tune IPs |
|---|---|
| Remaining PX12 hits (EDU + ISP + ORG) | **183** |
| Share of all Tune unique IPs | **0.26%** |
| DCH removed | 899 |

**183 non-datacenter PX12 hits do not replace Tune PROXY coverage (34,346 unique IPs).** Filtering known types makes the PX12 overlay smaller, not more complete.

### 7.4 Example overlapping IPs

| IP | Tune FLAGGED? | `usage_type` | `fraud_score` | `threat` | ISP |
|---|---|---|---|---|---|
| 156.230.228.131 | No | DCH | 99 | — | DynaNode LLC |
| 71.14.218.2 | No | ORG | 99 | BOTNET | Better Family Life |
| 154.6.87.103 | Yes | DCH | 99 | SPAM | LogicWeb Inc |
| 156.241.248.165 | No | DCH | 99 | — | DynaNode LLC |
| 63.232.208.101 | No | EDU | 95 | — | University of St Francis |
| 149.88.103.79 | Yes | DCH | 99 | SPAM | DataCamp Limited |
| 3.12.120.35 | No | DCH | 80 | — | Amazon Technologies Inc. |
| 38.154.190.153 | No | DCH | 80 | — | ServerMania / 24Shells |

Several high PX12 scores are **ACCEPTED in Tune**. The two fraud systems contradict each other on individual IPs.

---

## 8. Fraud detection workflow

Proposed pipeline (from the onboarding discussion): *check Tune for complete status; if missing, search the other DB; then map fraud. Geo maps directly to IP2Location.*

### 8.1 Step 1 — Tune status (primary)

For each IP, require both `access_control_decision` and `access_control_reason_code`.

| Check | This sample |
|---|---|
| Unique IPs with both AC fields | Full table **4,441,366 / 4,528,154 (98.08%)**; sample 71,718 / 71,718 (100%) |
| Unique IPs missing Tune status | Full table **86,788 (1.92%)**; sample 0 |
| Fallback required on historical clicks | **Yes, for 86,788 IPs** — PX12 Lite is a weak fallback |

Use Tune as source of record when present:

- `ACCEPTED` + `NOT_APPLICABLE` → pass
- `FLAGGED` + reason (`PROXY`, `BOT_GENERATED`, `VPN`, `TOR`, `DATA_CENTER`, `MASKED_DEVICES`, `MOBILE_PROXY_SIGNALS`, `ABNORMAL_TRAFFIC_PATTERNS`) → fraud / risk label

### 8.2 Step 2 — Fallback to IP2Proxy PX12

Only if Tune has **no** status for that IP (new IPs never seen in historical clicks).

| PX12 fallback rule | Implication |
|---|---|
| Positive hit | Public proxy (`PUB`). Optionally use `usage_type`, `fraud_score`, `threat`, `provider` when filled. |
| Miss | **Not clean.** Lite PX12 is a sparse list (3.03M addresses = 0.071% of IPv4; 1.07M US = 0.072% of DB11 US space). |
| Do not use as primary | Recovers 1.4% of Tune-flagged IPs; 0% of bot / mobile-proxy / Tor in this sample. |

If Tune were empty on this sample, PX12 would still only annotate **1,082 / 71,718 IPs (1.51%)**.

### 8.3 Step 3 — Map fraud

| Signal | Source | Use |
|---|---|---|
| Decision + reason | Tune `access_control_*` | Primary fraud label on known click IPs |
| Public proxy listing | PX12 `proxy_type = PUB` | Overlay / fallback only |
| Network class | PX12 `usage_type` (`DCH`, `ISP`, `EDU`, …) | Datacenter vs other; DCH dominates |
| Numeric risk | PX12 `fraud_score` | Weak: mode 80 (~86% of PX12). Treat 91–99 as a high band if used at all |
| Threat tags | PX12 `threat` | Sparse (1.9% of PX12; 6.7% of Tune∩PX12 hits) |
| Vendor | PX12 `provider` | Sparse (1.0% of PX12; 0.8% of hits) |

**Do not require “all status received in Tune and PX12.”** Tune is complete on historical clicks; PX12 will usually be absent. Requiring both would drop fraud coverage from 55.5% of unique IPs (Tune FLAGGED) to 0.79% (567 IPs).

### 8.4 What PX12 *cannot* do on live IPs outside Tune

For the ~99.7% of US IPv4 never seen in historical Tune:

- PX12 Lite covers **0.072%** of US space
- Almost all of that is public datacenter proxy (`PUB` + `DCH`)
- Residential / enterprise proxies and bots will largely go unflagged

Fallback for unseen IPs needs commercial proxy data or keeping Fraudlogix on the live path. Lite PX12 is not that fallback.

---

## 9. Geolocation mapping

**Rule: map location directly to IP2Location DB11.** Do not use Tune `country_code` as the geo source of record (it is useful only as an audit field).

### 9.1 Lookup coverage on Tune IPs

| Metric | Unique IPs | % |
|---|---|---|
| Matched a DB11 range | 71,718 | **100%** |
| Usable geo (country + city + non-zero coords) | 71,701 | **99.976%** |
| City filled | 71,701 | 99.976% |
| ZIP filled | 71,211 | **99.29%** |
| In a range but geo = `-` | 17 | 0.024% |

The 17 no-geo IPs sit in `148.178.x.x` (unknown/reserved DB fields). Range membership is trivially 100% because DB11 spans all IPv4. The useful KPI is **usable geo**, not “found in DB.”

### 9.2 Country agreement vs Tune

On 71,701 comparable unique IPs, Tune `country_code` and DB11 country agree on **70,859 (98.83%)**.

Top mismatches (Tune → DB11): US→HN 59, US→JM 53, UK→US 44, US→MX 42, US→SE 40.

### 9.3 Accuracy constraint (Lite product)

DB11 Lite resolves at **Class C (/24) majority location**. Vendor ballpark:

- Country ~**98%** (consistent with 98.83% agreement here)
- City ~**60%**

**A filled city or ZIP is not a deterministic rooftop or ZIP marker.** Treat those fields as approximate estimates. Country is the reliable grain.

### 9.4 Session geo sample

`session_summary_geo_columns_100K_sample.csv` contains plugin lat/lon/address (`geo_latitude` fill 100%, `geo_address` fill 99.84%) but **no IP address**. It cannot be cross-matched to Tune, DB11, or PX12 without a separate join key.

---

## 10. IP2Location and IP2Proxy database-level facts (context for the blockers)

### 10.1 IP2Location Lite DB11

| Property | Value |
|---|---|
| Ranges | 2,984,119 |
| IPv4 coverage | 100% (no gaps) |
| US ranges | 911,913 |
| US addresses | 1,494,722,560 (~34.8% of IPv4) |
| Unknown country `-` addresses | 616,359,168 (~14.4% of IPv4) |

Lite city/ZIP must be classified as **approximate**, matching the original blocker.

### 10.2 IP2Proxy Lite PX12

| Property | Value |
|---|---|
| Ranges | 2,690,046 |
| Addresses listed | 3,030,536 (0.071% of IPv4) |
| `proxy_type` | **PUB 100%** |
| `usage_type` | DCH 98.13%; then ISP, EDU, ISP/MOB, COM, MOB, GOV, CDN, MIL, ORG, LIB |
| `fraud_score` | Always filled; range 27–99; mode **80 (85.86%)** |
| `threat` fill | 1.90% |
| `provider` fill | 0.98% |

This matches the original blocker: public-proxy-only classification, weak residential/enterprise detection, sparse threat/provider.

---

## 11. Mapping original blockers to evidence

| Blocker as written | What this analysis shows | Direction |
|---|---|---|
| IP2Location Lite DB11 ~60% city accuracy; ZIP not deterministic | Confirmed. 100% range lookup; city/ZIP filled but Lite-approximate. Country ~98.8% vs Tune. | **Proceed for geo**, document city/ZIP as estimates. |
| Tune / Fraudlogix security fields only ~0.2% of IP2Location coverage | **Wrong as fill rate** (full table **98.08%** of unique IPs; 100% in 100K sample). **Right as reverse IPv4 sampling** (~0.23% global). **Wrong as “0.2% of US IPs”** (US reverse overlap ~0.7%; inventory share **0.30%**). | **Reframe.** Tune covers ~0.30% of US IPv4, and **98.08%** of observed unique IPs have `access_control`. Gap = 86,788 IPs. |
| PX12 Lite mostly public proxies; enterprise/residential limited | Confirmed. 100% `PUB`, 98% `DCH`. Recovers 0.83% of Tune `PROXY` IPs; 0% of bot / mobile-proxy / Tor. | **Do not use PX12 Lite as primary fraud.** Optional sparse overlay / last-resort fallback only. |

---

## 12. Recommended onboarding strategy

1. **Geolocation:** Load IP2Location Lite DB11. Serve with integer range lookup (`ip_int BETWEEN ip_from AND ip_to`). Expose country as the reliable field. Label `city_name` and `zip_code` as approximate. Handle the rare `-` geo rows.

2. **Fraud on historical Tune clicks:** Use `access_control_decision` + `access_control_reason_code` as source of record. Fill rate is 100% here. Do not wait on PX12 to “complete” status.

3. **Fraud on IPs not in Tune:** Check PX12 only as a **positive public-proxy signal**. Do not treat a miss as clean. Do not treat `fraud_score = 80` as high risk. If unseen-IP fraud is in scope, Lite PX12 is not enough — keep Fraudlogix on the live path or license a commercial proxy DB.

4. **Do not design a pipeline that requires all three sources to agree.** Intersection of Tune-flagged ∩ PX12 is 567 IPs (0.79% of unique Tune IPs). Union of Tune-flagged is the fraud set that matters (39,805 IPs).

5. **Correct the 0.2% talking point** before it lands in a steering deck: it measures unused IPv4 space vs click inventory, not missing columns on our traffic.

---

## 13. Reproducibility

| Item | Detail |
|---|---|
| Local runner | `analyze_ip_sources.py` |
| Machine-readable output | `analysis_results.json` |
| Interactive view | Canvas `ip-source-blocker-assessment.canvas.tsx` |
| Tune sample | `raw_tune_clicks_100K_sample.csv` (100,000 rows) |
| DB11 / PX12 | Full Lite dumps, no headers |
| Reverse-overlap 0.2% | Prior Athena join, random seed 42, full `raw.raw_tune_clicks` |
| Lookup | Python `numpy.searchsorted` on sorted `ip_from` |

---

## Appendix A — Unique-IP reason codes (any occurrence)

An IP can carry more than one reason across clicks. Counts below are unique IPs that ever had the code (not mutually exclusive):

| Reason | Unique IPs ever having this code |
|---|---|
| `PROXY` | 34,399 |
| `NOT_APPLICABLE` | 32,117 |
| `MASKED_DEVICES` | 3,147 |
| `ABNORMAL_TRAFFIC_PATTERNS` | 1,414 |
| `MOBILE_PROXY_SIGNALS` | 430 |
| `DATA_CENTER` | 385 |
| `VPN` | 46 |
| `BOT_GENERATED` | 34 |
| `TOR` | 1 |

## Appendix B — PX12 `usage_type` enum (full dump)

| `usage_type` | Meaning | Ranges | % of PX12 |
|---|---|---|---|
| `DCH` | Data Center / Web Hosting / Transit | 2,639,857 | 98.13% |
| `ISP` | Fixed Line ISP | 20,131 | 0.75% |
| `EDU` | University / College / School | 19,355 | 0.72% |
| `ISP/MOB` | Fixed + Mobile ISP | 7,435 | 0.28% |
| `COM` | Commercial | 1,712 | 0.06% |
| `MOB` | Mobile ISP | 878 | 0.03% |
| `GOV` | Government | 342 | 0.01% |
| `CDN` | Content Delivery Network | 294 | 0.01% |
| `MIL` | Military | 20 | <0.01% |
| `ORG` | Organization | 20 | <0.01% |
| `LIB` | Library | 2 | <0.01% |

## Appendix C — PX12 `fraud_score` histogram (full dump)

| Score | Ranges | % |
|---|---|---|
| 27–35 | 81 | ~0.003% |
| 36 | 28,363 | 1.05% |
| **80** | **2,309,652** | **85.86%** |
| 91 | 47,311 | 1.76% |
| 92 | 39,070 | 1.45% |
| 93 | 34,135 | 1.27% |
| 94 | 32,835 | 1.22% |
| 95 | 33,955 | 1.26% |
| 96 | 20,484 | 0.76% |
| 97 | 17,890 | 0.67% |
| 98 | 17,632 | 0.66% |
| 99 | 108,638 | 4.04% |

Range observed: **27–99**. High band 91–99 ≈ 12.8–13.1% of ranges.

---

## 14. Full-table profiles (implementation contract)

Athena, 18 Aug 2026. Interactive view: `ip-table-profiling.canvas.tsx`.

### 14.1 Inventory

| Table | Grain | Rows | Unique IPs | Dates |
|---|---|---|---|---|
| `raw.raw_tune_clicks` | Affiliate click | 16,304,374 | 4,528,154 (all IPv4) | 2023-01-11 → 2026-08-18 |
| `unified.unified_session_summary` | On-site session | 11,331,530 | 1,990,844 | 2022-08-19 → 2026-08-16 |
| `raw.segment_events` | Page/track event | 297,910,970 | ~2.04M `context_ip` | 2022-08-19 → 2026-08-18 |
| `unified.session_click_ids` | Partial session | **49,746** | — | 2026-01-17 → 2026-08-16 |
| IP2Location Lite DB11 | IPv4 range | 2,984,119 ranges | All IPv4 | Lite dump |
| IP2Proxy Lite PX12 | Proxy range | 2,690,046 ranges | 3.03M addresses | Lite dump |

### 14.2 Join keys that work vs that do not

**Use:** `session_ip` / Tune `ip` / Segment `context_ip` as dotted IPv4 → `ip_int`, then `ip_int BETWEEN ip_from AND ip_to` on DB11 and PX12. Tune `access_control_*` grouped by `ip`.

**Do not use:** `unified.session_click_ids` (0.44% of sessions, `clickid_txn_id` fill = 0, Tune click-id match ≈ 783). Do not treat Segment event rows (~298M) as unique IPs.

### 14.3 Pipeline

1. Grain = `unified.unified_session_summary` (`session_id`, `session_ip`).
2. Geo = DB11 range lookup on `session_ip` (city/ZIP approximate).
3. Fraud primary = Tune `access_control_decision` / `reason` on that IP (~80% of session IPs hit).
4. Fraud fallback = PX12 only if Tune has no row; miss ≠ clean.

---

*End of analysis. Warehouse figures: Athena `raw.raw_tune_clicks`, `unified.unified_session_summary`, `raw.segment_events` on 18 Aug 2026. Lite DB11/PX12 from local dumps. Reverse-overlap 0.2% is the older IP2Location-sampling experiment, not session fill.*
