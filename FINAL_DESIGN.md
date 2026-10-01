# IP Intelligence — Final Design

**Date:** 2026-09-11 · **Scope:** US traffic · **Purpose:** an analytical source of truth for IP
reputation, feeding bot detection and traffic quality decisions.

This is the reference document. Every design choice below is justified by a measurement in §1, not
by convention.

---

## 1. The analysis that drives the design

Measured across `unified.unified_session_summary` + `raw.raw_tune_clicks`, 4,956,391 distinct IPv4
addresses.

### 1.1 Most IPs are seen once and never again

| | Value |
|---|---:|
| Total distinct IPs | 4,956,391 |
| **Seen on exactly one day** | **3,369,752 — 68.0%** |
| Seen on 7+ days | 222,624 — 4.5% |
| Median hits per IP | **2** |
| Mean hits per IP | 5.6 |
| P99 hits per IP | 35 |
| Mean lifespan (first→last seen) | 84.5 days |

**Design consequence — the single most important one.** Enriching all 4.96M IPs equally is mostly
waste: 3.37M of them will never be seen again, and an IP's reputation only has value the next time
it appears. The pipeline must treat IPs as two classes:

- **Transient** — one sighting. Enrich once at first sight. Never refresh.
- **Recurring** — seen on multiple days. Enrich, then refresh on a cadence.

### 1.2 Traffic is concentrated in a few shared addresses

Last 90 days: 150,319 IPs, 396,174 sessions.

| | Share of sessions |
|---|---:|
| Top 100 IPs | **10.4%** |
| Top 1,000 IPs | **19.5%** |

**Design consequence.** A thousand addresses carry a fifth of all traffic, and they are
overwhelmingly shared infrastructure — iCloud Relay, CDN egress, CGNAT. They need per-IP scoring
that *suppresses* rather than amplifies risk, and they justify their own refresh tier: they change
often and a wrong verdict is expensive.

### 1.3 US filtering is a correctness measure, not a volume reduction

| | Value |
|---|---:|
| IPs with a country | 4,938,572 |
| **US** | **4,831,255 — 97.8%** |
| Non-US | 107,317 — 2.2% |
| No country resolved | 1,203 |

**Design consequence.** Filtering to US removes only 2.2% of rows, so it is not a cost saving. It
is still worth doing: non-US IPs have different vendor coverage and accuracy characteristics, and
mixing them silently distorts every per-vendor metric. **Apply the filter, and store
`country_code` so the decision stays visible and reversible.**

### 1.4 Only one vendor can cover the full population

| Tier | Vendors | Coverage |
|---|---|---|
| **File-based** | IP2Location DB11 · IP2Proxy PX12 · MaxMind GeoLite2 · DB-IP · authoritative lists | **all 4.96M**, no quota |
| **API** | proxycheck.io (80K/day paid) | 226,821 IPs in 90 days, plus ~1,900/day ongoing |
| **API, free tier** | ipinfo.io · ipwho.is | 1,000/day hard cap each — incremental only |

---

## 2. Final schema

Four tables. Two are consumed, two are the working.

```
                    ip_reputation          ← one row per IP · what the API serves
                          ▲
                          │ derived from
                          │
                    ip_vendor_claims       ← one row per IP × vendor · raw vendor answers
                          ▲
              ┌───────────┴───────────┐
              │                       │
        ip_labels              vendor_accuracy   ← one row per vendor · validated metrics
     (human / bot truth)
```

### 2.1 `unified.ip_reputation` — the source of truth

**Grain: one row per IP.** This is what an API serves and what analytics joins to.

| Column | Type | Notes |
|---|---|---|
| `ip_address` | varchar | **partition key candidate — see §3** |
| `reputation_score` | int | 0–100. 0 = certainly automated, 100 = certainly human |
| `confidence` | int | 0–100. How much evidence backs the score |
| `recommendation` | varchar | `allow` · `review` · `block` |
| `is_proxy` `is_vpn` `is_tor` `is_datacenter` `is_bot` `is_compromised` `is_scraper` `is_anonymous` | boolean | **nullable three-state.** NULL = no vendor had an opinion |
| `is_shared_infrastructure` | boolean | relay / CDN / CGNAT — changes how the score is read |
| `shared_infrastructure_type` | varchar | `icloud_relay` · `cdn` · `cloud` · `cgnat` · NULL |
| `vendors_answered` | int | denominator for everything |
| `vendors_agreeing` | int | how many matched the consensus |
| `country_code` `state` `city` `zip_code` `latitude` `longitude` | — | consensus location |
| `first_seen` `last_seen` `times_seen` | — | **from our own traffic**, not a vendor |
| `ip_class` | varchar | `transient` · `recurring` · `high_volume` — drives refresh (§1.1) |
| `created_at` `updated_at` | timestamp | |

### 2.2 `unified.ip_vendor_claims` — what each vendor said

**Grain: one row per IP × vendor.** Ahsan's column list, geo and risk in one table because both
answer "what did this vendor say about this IP".

`ip_address` · `vendor` · `state` · `city` · `zip_code` · `latitude` · `longitude` · `timezone` ·
`is_proxy` · `is_vpn` · `is_tor` · `is_datacenter` · `is_bot` · `is_compromised` · `is_scraper` ·
`is_anonymous` · `isp` · `asn` · `created_at` · `updated_at`

Plus two operational columns that must not be dropped:

| Column | Why it is non-negotiable |
|---|---|
| `has_answer` | distinguishes *"asked, no answer"* from *"never asked"*. Without it, PX12's silence on 4.9M IPs reads as 4.9M clean verdicts |
| `raw_payload` | the vendor's original JSON. When a mapping turns out to be wrong, it is re-derivable without re-querying |

### 2.3 `unified.ip_labels` — ground truth

**Grain: one row per IP.** The table that makes accuracy measurable at all.

| Column | Notes |
|---|---|
| `ip_address` | |
| `label` | `human` · `bot` |
| `label_source` | `qualified_lead` · `self_declared_crawler` · `verified_crawler_range` · `incumbent_bot_click` |
| `label_strength` | `confirmed` · `suspected` |
| `evidence` | e.g. the furthest stage reached, or the user-agent string |
| `labelled_at` | |

Current contents: **2,105 confirmed humans** (qualified leads) · **484 confirmed bots**
(self-declared crawler UA) · 9,954 suspected bots (`is_bot_click`, an incumbent's opinion — kept
separate and never mixed into the confirmed set).

### 2.4 `unified.vendor_accuracy` — per-vendor, validated

**Grain: one row per vendor per capability.**

| Column | Meaning |
|---|---|
| `vendor` · `capability` (`geo` / `risk`) | |
| `fill_rate_pct` | how often it answers |
| `precision_pct` · `recall_pct` · `f1` | **against `ip_labels`** — real accuracy, not agreement |
| `false_positive_rate_pct` | of confirmed humans, how many it flagged |
| `geo_state_pct` · `geo_city_pct` · `geo_zip_pct` | against the lead's own address |
| `agreement_pct` | consensus with other vendors — kept, but clearly separate from accuracy |
| `cost_per_1k` · `score` | |
| `labelled_humans` · `labelled_bots` | **the denominators always ship with the metrics** |

---

## 3. Physical design

| Decision | Choice | Why |
|---|---|---|
| **Format** | **Iceberg** for `ip_reputation` and `ip_vendor_claims`; Parquet for the rest | Daily refresh updates existing rows. Athena cannot `UPDATE` Parquet, so plain tables mean rewriting partitions; Iceberg `MERGE` touches only what changed. At 4.96M rows that is the difference between minutes and hours |
| **Partitioning — claims** | `bucket(ip_address, 64)` | Lookups are by IP. Date partitioning would force every point lookup to scan every day |
| **Partitioning — reputation** | `bucket(ip_address, 32)` | Same reason. ~150K rows per bucket, comfortable file sizes |
| **Partitioning — labels, accuracy** | none | Small tables |
| **Sort order** | `ip_address` within each bucket | Makes range scans and joins cheap |
| **History** | **`valid_from` / `valid_to` on `ip_vendor_claims` only** | A vendor changing its mind is worth recording. `ip_reputation` is a current-state table — history there would double the row count for little gain |
| **Retention** | claims: 2 years · reputation: current only · labels: forever | IP reassignment makes a 3-year-old verdict misleading |

### Why `ip_address` bucketing rather than date

The access pattern is *"tell me about this IP"*, not *"tell me about yesterday"*. Bucketing on the
lookup key means a single-IP query reads one file. Date partitioning would be right for an
append-only event log; this is a dimension table that happens to be refreshed daily.

---

## 4. Data flow

```
┌─────────────────────────────────────────────────────────────────┐
│ SOURCES                                                          │
│  unified.unified_session_summary   raw.raw_tune_clicks          │
│  sampledb.revenue_leads_plus (qualified leads → human labels)   │
└───────────────────────────┬─────────────────────────────────────┘
                            │  filter: valid IPv4 · country_code = 'US'
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1 · IP DISCOVERY                                                 │
│    new IPs in the last 24h not already in ip_vendor_claims      │
│    ~1,900/day measured                                           │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2 · ENRICHMENT                                                   │
│    file vendors  → every new IP        (Athena range joins)     │
│    proxycheck    → every new IP        (2.4% of 80K quota)      │
│    authoritative → every new IP        (published ranges)       │
│    crawler lists → every new IP        (Googlebot etc.)         │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3 · MERGE into ip_vendor_claims  (Iceberg MERGE, SCD2)          │
│    changed verdict → close old row, insert new                   │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌──────────────────────┬──────────────────────┬───────────────────┐
│ 4a · LABELS          │ 4b · REPUTATION      │ 4c · ACCURACY     │
│ new qualified leads  │ recompute score for  │ recompute per     │
│ new crawler UAs      │ touched IPs only     │ vendor vs labels  │
└──────────────────────┴──────────┬───────────┴───────────────────┘
                                  ▼
                    ┌─────────────────────────────┐
                    │ 5 · PUBLISH                 │
                    │   serving JSON → API → UI   │
                    └─────────────────────────────┘
```

---

## 5. Workflows

### 5.1 Daily — `ipintel-daily-refresh`, 03:00 UTC

| Step | Detail |
|---|---|
| Discover | new IPs from last 24h, US only, not already known — ~1,900 |
| Enrich | all vendors; proxycheck uses 2.4% of daily quota |
| Merge | Iceberg `MERGE` into `ip_vendor_claims` |
| Label | new qualified leads → human; new crawler UAs → bot |
| Score | recompute `ip_reputation` **for touched IPs only**, not the whole table |
| Accuracy | rebuild `vendor_accuracy` (small, full rebuild is fine) |
| Publish | refresh serving JSON |

Runtime ~10 minutes. Idempotent: re-running a day replaces that day's work.

### 5.2 Weekly — refresh recurring IPs

The 222,624 IPs seen on 7+ days get re-enriched weekly. Reputation decays: an IP clean six months
ago may be compromised now. **Transient IPs are deliberately excluded** — refreshing 3.37M
one-sighting IPs would consume the entire quota to update records nobody will ever query again.

### 5.3 Monthly — refresh the file vendors

DB11, PX12, MaxMind and DB-IP publish new files monthly. Download, reload, re-resolve all 4.96M.
Pure Athena, roughly $0.50.

### 5.4 On demand — backfill

Last 90 days = 226,821 IPs = 3 days at 80K/day. Run once at launch.

---

## 6. The reputation score

Transparent and auditable — every input traceable.

| Signal | Direction | Weight |
|---|---|---:|
| Verified crawler range (Googlebot etc.) | → bot | **decisive** |
| Crawler UA **not** verified by reverse DNS | → bot + spoofing | **decisive** |
| Self-declared crawler UA, verified | → bot | high |
| Tor exit | → bot | high |
| proxycheck `scraper` or `compromised` | → bot | high |
| On cloud/hosting ranges | → bot | medium |
| proxycheck `risk` | proportional | medium |
| Multiple vendors agree proxy | → bot | medium |
| **Produced a qualified lead** | **→ human** | **overrides all flags** |
| Shared infrastructure | **caps confidence** | — |

Two rules that keep it defensible:

1. **A qualified lead outranks every vendor flag.** Someone who was introduced, met an agent and
   listed a property is not a bot, whatever an IP database says.
2. **Shared infrastructure lowers confidence, never raises the score.** 25% of qualified traffic is
   behind iCloud Relay. Treating those as risky would block a quarter of real customers.

**Validation gate:** the score must separate the 2,105 confirmed humans from the 484 confirmed bots.
If it does not, it does not ship.

---

## 7. Implementation order

| # | Step | Output | Time | Blocked by |
|---|---|---|---|---|
| 1 | `ip_labels` from qualified leads + crawler UAs | 2,105 + 484 labelled IPs | 1 hr | — |
| 2 | Published crawler ranges + reverse-DNS verification | more bot positives, spoof detection | 2 hrs | — |
| 3 | `ip_vendor_claims` as Iceberg, US filter, file vendors across 4.96M | full geo coverage | 2 hrs | — |
| 4 | proxycheck 90-day backfill | risk on 226,821 IPs | 3 days unattended | paid key |
| 5 | `vendor_accuracy` against labels | **real precision and recall** | 1 hr | 1–4 |
| 6 | `ip_reputation` with the weighted score | the source of truth | 3 hrs | 5 |
| 7 | Validate against labels | proof it separates | 1 hr | 6 |
| 8 | Daily + weekly + monthly jobs | stays current | 3 hrs | 7 |

**Steps 1, 2 and 3 need nothing and can start now.** Step 4 needs the paid key. Realistically four
to five days to fully live.

---

## 8. What this delivers, and what it does not

**Delivers**
- One row per IP: score, confidence, recommendation, evidence — directly consumable
- Genuine per-vendor precision and recall, because labels finally exist
- Auditable scoring: every number traces to the signals behind it
- A pipeline that stays fresh without anyone touching it

**Does not**
- Decide whether a *session* is a bot. IP reputation is one input; session behaviour is the other,
  and it belongs in your analytics cycle
- Work reliably on shared infrastructure. A quarter of qualified traffic sits behind iCloud Relay,
  and no IP-level system separates the people behind one address
- Say anything useful about the 3.37M one-sighting IPs. They are enriched because they are cheap to
  enrich, not because the answer will ever be read

**The framing for consumers:** *"this IP's reputation, with its evidence and confidence"* — not
*"this visitor is a bot"*.

---

## 9. Open decisions

1. **Iceberg for the two large tables?** Recommended. Without it the daily merge rewrites partitions
   at 4.96M rows.
2. **Transient IPs — enrich at all?** They are 68% of the population and almost none will be queried
   again. Enriching them costs little; *refreshing* them would cost everything. The plan enriches
   once and never refreshes.
3. **Is there a labelled fraud or invalid-traffic set in the business?** Still the highest-value
   missing input — worth more than any vendor, and the only thing here I cannot derive.
4. **`confidence` from proxycheck stays NULL** — it does not return the field, and writing 100 would
   assert a certainty the vendor never gave.
