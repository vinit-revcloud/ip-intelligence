# Plan — 4.9M IPs, split tables, daily refresh

**Date:** 2026-09-11
**Goal:** every unique IP across `unified_session_summary` + `raw.raw_tune_clicks` available for bot
detection, with a daily job keeping it fresh.

Ahsan's schema is followed exactly. Three things are **measured facts**, not proposed changes, and
they shape the build — they are called out in §2 and §3 rather than buried.

---

## 1. Six tables, not four

The split he asked for. `ip_geo` and `ip_intelligence` carry **only** the listed columns; everything
else moves to an analytics twin, joinable on `ip_address` alone or `ip_address + vendor`.

| Table | Columns | Grain |
|---|---|---|
| **`unified.ip_geo`** | ip_address · vendor · state · city · zip_code · latitude · longitude · timezone · created_at · updated_at | IP × vendor |
| **`unified.ip_geo_analytics`** | ip_address · vendor · consensus_* · *_votes · *_matches_consensus · truth_* · *_matches_truth · fields_answered/judged/matched · row_agreement_pct · row_truth_agreement_pct · has_answer | IP × vendor |
| **`unified.ip_intelligence`** | ip_address · vendor · is_proxy · is_vpn · is_tor · is_datacenter · is_bot · **is_compromised · is_scraper · is_anonymous** · isp · asn · created_at · updated_at | IP × vendor |
| **`unified.ip_intelligence_analytics`** | ip_address · vendor · risk · confidence · first_seen · last_seen · times_seen · fraud_reason · is_masked_device · has_answer · flagged · known_infrastructure · infrastructure_list · verdict_class · bot_false_positive · row_agreement_pct | IP × vendor |
| **`unified.vendor_overview_geo`** | unchanged | vendor |
| **`unified.vendor_overview_proxy`** | unchanged | vendor |

Join in both directions:

```sql
-- by IP and vendor (the normal case)
FROM unified.ip_geo g
JOIN unified.ip_geo_analytics a
  ON a.ip_address = g.ip_address AND a.vendor = g.vendor

-- by IP alone (all vendors' analytics for one IP)
FROM unified.ip_intelligence i
JOIN unified.ip_intelligence_analytics a ON a.ip_address = i.ip_address
```

`last_seen` maps to `valid_from` / `updated_at`. **When the vendor returns no `last_seen`, we write
the current datetime**, exactly as specified.

---

## 2. The `detections` object — 9 of 12 fields are available

Measured against the live proxycheck response for `146.75.164.0` with `&vpn=3&asn=1&risk=1&seen=1`.
The full key set it returns is:

```
asn · city · continent · continentcode · country · currency · devices · isocode
last seen human · last seen unix · latitude · longitude · operator · organisation
postcode · provider · proxy · range · region · regioncode · risk · timezone · vpn
```

| `detections` field | Source | Status |
|---|---|---|
| `proxy` | `proxy == "yes"` | ✅ |
| `vpn` | `vpn == "yes"` | ✅ |
| `tor` | `type == "Tor"` | ✅ |
| `compromised` | `type == "Compromised Server"` | ✅ |
| `scraper` | `type == "Scraper"` | ✅ |
| `hosting` | `type == "Hosting"` | ✅ |
| `anonymous` | `operator.anonymity` present, or proxy/vpn true | ✅ |
| `risk` | `risk` (0–100) | ✅ |
| `last_seen` | `last seen unix` — **requires `&seen=1`** | ✅ |
| **`confidence`** | — | ❌ **proxycheck does not return this** |
| **`first_seen`** | — | ❌ **not returned** |
| **`times_seen`** | — | ❌ **not returned** |

**The three missing fields will be written as NULL**, not invented. `confidence: 100` in the sample
object cannot be sourced from proxycheck — emitting a hardcoded 100 would assert certainty the
vendor never expressed.

Two of them we can derive ourselves instead, if wanted:
- `first_seen` / `times_seen` — computable from **our own** data: first and count of appearances in
  `session_summary` + `tune_clicks`. That is more useful than a vendor's view anyway, because it is
  our traffic. Recommend deriving these internally and labelling them as ours.

**Note `&seen=1` is required** for `last_seen`; our current calls omit it, so it must be added.

Also worth knowing: with `&vpn=3`, proxycheck splits `proxy` and `vpn` into separate answers. The
same IP returns `proxy: "no", vpn: "yes"` — under `&vpn=1` it returned `proxy: "yes", type: "VPN"`.
**We must standardise on `&vpn=3`** or the two flags will disagree with each other.

---

## 3. 🛑 4.9M IPs cannot go through the API vendors — the numbers

| Source type | Can it cover 4.9M? | Why |
|---|---|---|
| **File-based** — IP2Location DB11, IP2Proxy PX12, MaxMind GeoLite2, DB-IP, authoritative lists | ✅ **Yes, today** | Local range lookups. No API, no quota. A full 4.9M pass is a few minutes of Athena |
| **proxycheck.io** | ❌ Not on free | 1,000/day → **13 years** for 4.9M |
| **ipinfo.io / ipwho.is** | ❌ | Measured hard caps at exactly 1,000/day each |

**Daily volume, measured over the last 30 days: ~1,900 distinct IPs/day** (range 921–2,943).

So even the *incremental* job exceeds proxycheck's free 1,000/day on most days.

### What this means for the build

**Two tiers, stated honestly in the data:**

1. **Full-coverage tier — all 4.9M IPs.** DB11, PX12, MaxMind, DB-IP, authoritative lists. This is
   what the bot-detection analytics cycle runs on. It can be backfilled now.
2. **Sampled tier — API vendors.** proxycheck, ipinfo, ipwho.is. They cover the daily new IPs
   only, and only if quota allows.

`ip_intelligence` will therefore have ~4.9M rows for file vendors and far fewer for API vendors.
**That is correct and must not be hidden** — `has_answer = false` in the analytics table marks the
difference between "asked, no answer" and "never asked".

### The decision needed

> **Does proxycheck get a paid plan?** At ~1,900 new IPs/day the free tier is short by roughly half.
> The $5.99/mo tier's daily limit needs confirming from the dashboard — if it covers 1,900/day,
> the incremental job works from day one for a rounding-error cost.

Without it, the honest options are: run proxycheck on a priority subset (qualified-lead IPs first),
or accept ~50% daily coverage and label it.

---

## 4. The daily job

**`ipintel-daily-refresh`** — Lambda on an EventBridge schedule, 03:00 UTC.

```
1. Extract   new IPs from the last 24h of unified_session_summary + raw.raw_tune_clicks
             that are not already in unified.ip_geo          (~1,900/day)
2. Enrich    file vendors  → all new IPs, no quota
             API vendors   → as many as quota allows, priority order
3. Load      append to ip_geo, ip_geo_analytics,
             ip_intelligence, ip_intelligence_analytics
4. SOT       refresh ipintel_curated.qualified_lead_ips (new qualified leads)
5. Overview  rebuild vendor_overview_geo + vendor_overview_proxy
6. Publish   refresh the serving JSON so the API and UI go current
```

**Execution shape.** Steps 1, 3, 4, 5 are Athena SQL — a Lambda that submits queries and polls, well
inside a 15-minute timeout. Step 2 is the only long pole: file vendors run as Athena range joins
(fast); API vendors are HTTP calls, ~1,900 at proxycheck's 100-per-batch = 19 requests, seconds.

**Idempotency.** Every write is partitioned by `ingest_date`. Re-running a day overwrites that
partition rather than duplicating. A failed run is safe to repeat.

**SCD2.** New observation for an existing (IP, vendor) closes the prior row by setting its
`valid_to`, then inserts the new row with `valid_to = NULL`. Athena cannot `UPDATE` Parquet, so this
is done as a rewrite of the affected partition, or by moving these two tables to **Iceberg**, which
supports `MERGE`. Recommend Iceberg for `ip_geo` and `ip_intelligence` — it is the difference
between a clean daily merge and a full-table rewrite at 4.9M rows.

---

## 5. Build order

| # | Step | Output | Time |
|---|---|---|---|
| 1 | Backfill file vendors across all 4.9M IPs | `ip_geo` + `ip_intelligence` at full scale | ~1 hr |
| 2 | Split existing tables into base + analytics twins | 4 tables, exact columns | 45 min |
| 3 | Add `is_compromised`, `is_scraper`, `is_anonymous`; switch proxycheck to `&vpn=3&seen=1` | detections mapping complete | 30 min |
| 4 | Derive `first_seen` / `times_seen` from our own traffic | fills 2 of the 3 gaps | 30 min |
| 5 | Rebuild both overview tables on the new base | fresh vendor scores | 20 min |
| 6 | Write the daily Lambda + EventBridge rule | `ipintel-daily-refresh` | 2 hrs |
| 7 | Convert `ip_geo` / `ip_intelligence` to Iceberg for MERGE | clean SCD2 at scale | 1 hr |

Steps 1–5 need no decisions and can start immediately. Step 6 depends on the proxycheck plan
question only for *how many* API rows it writes, not for whether it runs.

---

## 6. What I need confirmed

1. **proxycheck paid plan?** ~1,900 new IPs/day versus 1,000 free. Everything else is unaffected.
2. **`confidence`, `first_seen`, `times_seen`** — NULL from the vendor, or derive `first_seen` and
   `times_seen` from our own traffic and label them as ours? I recommend the latter.
3. **Iceberg for the two base tables?** Without it, daily SCD2 at 4.9M rows means rewriting
   partitions rather than merging.
4. **Vendor scope at 4.9M** — confirm the file vendors (DB11, PX12, MaxMind, DB-IP, authoritative)
   are the intended full-coverage set, with API vendors incremental-only. This is a physical limit,
   not a design choice.
