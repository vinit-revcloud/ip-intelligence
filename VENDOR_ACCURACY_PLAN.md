# Vendor Accuracy Benchmark — Plan

**Status:** Planning. Nothing built for this yet.
**Date:** 2026-09-03
**Depends on:** `AWS_BUILD_LOG.md` (P0/P1 curated tables, already live)

The shift here is good and worth naming: instead of enriching 4.9M IPs with two sources, we
deeply enrich a *small, deliberately chosen* set of IPs with *many* sources. That is the right
move — accuracy is measured on IPs where we have truth, and truth is scarce.

Everything below follows from one measured fact, so it comes first.

---

## 1. The binding constraint: ground truth is 485 IPs

Geo accuracy needs a location that did **not** come from an IP lookup. The only such source in
the warehouse is a lead's self-reported address in `unified.uct_leads`, reachable to an IP via
`alyson_session_id → unified_session_summary.session_id → session_ip`.

Measured today:

| | Count |
|---|---:|
| `uct_leads` rows | 134,096 |
| …with a session id | 10,329 (only **632 distinct** sessions) |
| …joining to a session | 4,295 |
| **Distinct IPs with truth** | **552** |
| **…with full city + state + zip** | **485** ← the usable pool |
| …that FraudLogix flagged | 93 (19%) |
| Revenue on the pool | $346,515 |

Also measured, and it changes the design:

- **`uct_leads.county` is 100% NULL.** County accuracy is not measurable from this source.
- **`uct_leads.phone_number` is 100% NULL.** There is no phone-verified truth here.

### Recommendation: run all 485, not a sample of 200

Sampling exists to control cost. At this scale there is no cost to control — 485 lookups is under
ProxyCheck's 1,000/day free limit and trivial for every other source. Sampling 200 discards 60%
of the only ground truth you have, in exchange for nothing.

Statistically it matters. At n=485 a proportion carries roughly ±4.4% at 95% confidence; at n=200
it is ±6.9%. Neither will separate two vendors that are 89% vs 91% on city — that needs thousands.
Both will comfortably separate 60% from 85%. So:

> **Use all 485 for the benchmark. Keep the sample-size control in the UI**, because it will matter
> the moment the truth pool grows or a paid vendor with a real per-call cost is added.

### The thing worth fixing separately

552 IPs out of 4.9M is a **0.011% truth coverage rate**, and it is the ceiling on everything.
`uct_leads` is evidently one lead connector, not all leads. Widening this — another lead source
with addresses, or a session→lead key on `revenue_leads_plus` — is worth more to this project than
any additional vendor. Flagged as open decision D1.

---

## 2. Vendor roster — all tested live on 2026-09-03

### Tier 1 · Authoritative lists (free, unlimited, definitive)

These are not opinions. They are the operator's own published ranges, so they function as **truth**
for their specific class — which is what makes proxy accuracy measurable at all.

| Source | Endpoint | Gives |
|---|---|---|
| Tor Project | `check.torproject.org/torbulkexitlist` | definitive `is_tor` |
| Apple iCloud Private Relay | `mask-api.icloud.com/egress-ip-ranges.csv` | definitive relay **+ Apple's own city/region geo** |
| AWS | `ip-ranges.amazonaws.com/ip-ranges.json` | definitive `is_datacenter` |
| Google Cloud | `gstatic.com/ipranges/cloud.json` | definitive `is_datacenter` |
| Cloudflare | `cloudflare.com/ips-v4` | definitive CDN |
| Fastly | `api.fastly.com/public-ip-list` | definitive CDN |

The Apple list is the standout: 12 MB, and each range carries country/region/city. It resolves the
`104.28.97.18` case directly — we can identify a relay IP *and* recover the geography Apple intended
for it, instead of scoring every vendor as "wrong" about a city that was deliberately obscured.

### Tier 2 · Bulk databases (free download)

| Source | Status | Gives |
|---|---|---|
| IP2Location LITE DB11 | ✅ loaded | geo |
| IP2Proxy LITE PX12 | ✅ loaded | proxy (sparse: 0.34% hit rate) |
| MaxMind GeoLite2 City + ASN | needs free signup | geo, ASN |
| DB-IP Lite City | free monthly CSV | geo |

### Tier 3 · APIs (free tier)

| Source | Limit | Key | Tested |
|---|---|---|---|
| proxycheck.io | 1,000/day | have it | ✅ geo + proxy + risk + operator |
| ipwho.is | fair-use, no key | none | ✅ geo + ASN |
| ipinfo.io | 50k/mo w/ token | signup | ✅ geo + hostname + ASN |
| ipapi.co | 1,000/day | signup | ⚠️ rate-limited unauthenticated |
| AbuseIPDB | 1,000/day | free signup | not yet — reputation score |
| IPQualityScore | 5,000/mo | free signup | not yet — proxy + fraud score |

> **⚠️ ip-api.com is excluded.** It works and returns good data, but its free tier is licensed
> for **non-commercial use only**. This is a commercial product. Do not wire it in.

### Tier 4 · Internal

FraudLogix via TUNE `access_control_*` — already in `ipintel_curated.ip_flags`.

### What 485 IPs buys

Roughly **9 independent sources**, at effectively zero marginal cost, in one afternoon. That is the
whole argument for the narrow-and-deep approach: at 4.9M scale this roster is impossible; at 485 it
is free.

### The disagreement is already visible

One IP, `73.162.10.21` (Comcast, California), queried live:

| Source | City |
|---|---|
| ipwho.is | Fairfield-Suisun City |
| proxycheck.io | Fairfield |
| ip-api.com | Vallejo (zip 94591) |
| ipinfo.io | San Jose |

Four sources, three materially different answers, ~60 miles apart. This is the product in one row.

---

## 3. The three unified tables

Adopting the field specification as written. Three notes on implementation.

### 3.1 SCD2 without MERGE

Athena cannot `UPDATE` a Parquet table, so `valid_to` cannot be back-filled in place. Two options:
Iceberg tables (supports MERGE, and the lakehouse repo already standardises on it), or —
simpler and impossible to corrupt — **an append-only physical table plus a view that derives the
validity window**:

```sql
CREATE VIEW unified.ip_geo AS
SELECT *,
  observed_at AS valid_from,
  LEAD(observed_at) OVER (PARTITION BY ip_address, vendor ORDER BY observed_at) AS valid_to
FROM ipintel_curated.ip_geo_observations;

CREATE VIEW unified.ip_geo_current AS
SELECT * FROM unified.ip_geo WHERE valid_to IS NULL;
```

This gives the exact semantics specified — `valid_to IS NULL` means current, history retained —
with no mutation, no MERGE, and no way to corrupt the chain. Recommended.

### 3.2 The "no row ≠ not a proxy" rule needs a column

The semantic rule in the spec is correct and is the same trap PX12 sets. But a rule stated in
documentation gets violated; a rule in the schema does not. So every `ip_intelligence` row carries:

- `has_answer` — did this vendor return anything for this IP at all?
- `is_proxy` / `is_vpn` / `is_tor` / `is_datacenter` / `is_bot` — **nullable three-state**:
  `TRUE` = affirmed, `FALSE` = explicitly negated by the vendor, `NULL` = vendor did not say.

`FALSE` is written *only* when the vendor actively returns a negative. PX12 absence writes
`has_answer = false` and all flags `NULL` — never `FALSE`. ProxyCheck's `"proxy":"no"` is a real
negative and does write `FALSE`.

### 3.3 Namespace

`unified.*` is a shared production database owned by the data platform team. Recommend building in
`ipintel_curated` first, promoting to `unified` once the shape is stable and the owners have signed
off — rather than writing into a shared namespace on day one. Open decision D5.

### Table summary

| Table | Grain | Purpose |
|---|---|---|
| `lead_truth` | one lead | self-reported address + qualification + revenue. The ground truth. |
| `ip_geo` | (ip, vendor, observed_at) | every vendor's location claim, with history |
| `ip_intelligence` | (ip, vendor, observed_at) | every vendor's proxy/vpn/tor/datacenter/bot claim, with history |

---

## 4. Accuracy scoring

### 4.1 Geo — 5 columns per vendor

County is unavailable (§1), so the five reported levels are:

| Column | Definition |
|---|---|
| **State match %** | vendor state = lead state |
| **Metro match %** | CBSA of vendor zip = CBSA of lead zip (needs a ZIP→CBSA crosswalk — free from Census/HUD, loaded once as reference) |
| **City match %** | normalised city string match (see below) |
| **ZIP match %** | exact zip5 |
| **Median distance error** | miles between vendor lat/lon and the centroid of the lead's zip |

Median distance is the most informative of the five, because it degrades gracefully — "Vallejo vs
Fairfield" is a 12-mile error, not simply "wrong".

**City matching must be normalised or every vendor looks bad.** `Fairfield-Suisun City` vs
`Fairfield` is a match, not a miss. Rules: casefold, strip punctuation, drop `Township/City/Town`
suffixes, split on `-` and `/` and match any part, and treat a known-alias pair as equal.
The alias list is a reference table, not code.

**Report country separately, not as one of the five.** Traffic is 98.5% US, so country accuracy is
~100% for everyone and carries no signal.

### 4.2 Proxy — there is no ground truth, and pretending otherwise is the main risk

Nothing tells us whether an arbitrary IP "really is" a proxy. Scoring vendors against each other
just measures conformity. So proxy performance is measured two ways, both defensible:

**(a) Against authoritative lists — real precision and recall.**
For Tor, datacenter and relay we have operator-published truth. Every vendor can be scored properly:

| Metric | Meaning |
|---|---|
| Tor recall | of IPs on the Tor exit list, what share did the vendor flag as Tor |
| Datacenter precision | of IPs the vendor called datacenter, what share are in AWS/GCP/Azure/CF/Fastly ranges |
| Datacenter recall | the converse |

**(b) Against business outcome — the commercially meaningful measure.**
This is why sampling on qualified leads is the right instinct: a flagged IP that produced a
**qualified lead with a verified address** is a false positive with dollars attached.

The five reported columns per vendor:

| Column | Definition |
|---|---|
| **Answer rate %** | share of the 485 the vendor returned anything for (`has_answer`) |
| **Flag rate %** | share it classified as proxy/vpn/tor/datacenter/bot |
| **False-positive rate %** | share of *flagged* IPs that produced a qualified lead |
| **Revenue at risk $** | revenue on flagged IPs with qualified leads |
| **Authoritative agreement %** | precision against Tor + cloud + relay lists, where applicable |

Report revenue at risk **twice — including and excluding shared infrastructure** (relay, CDN,
CGNAT). One number cannot answer both "what would we lose" and "what should we block", and
iCloud Private Relay at $154K on a single IP will otherwise dominate every ranking.

### 4.3 Honest limits, stated up front

- n=485 → ±4.4% at 95%. Vendors within ~8 points of each other are **not** separable. Publish the
  confidence interval next to every percentage, or the console will manufacture false precision.
- The pool is qualified-lead traffic, which is **not** representative of all traffic — it is
  cleaner. Proxy rates here will be lower than population rates, by construction. That is fine for
  ranking vendors; it is wrong for estimating population proxy prevalence. Label it.

---

## 5. UI control

The requirement is that this is driven from the UI, not the backend. The way to honour that is the
same principle already used for vendors: **a sample definition is a row, not code.**

### New screen: Sample Builder

**Define the population** — every control writes to a `sample_definition` row:

- Truth requirement: has qualified lead · has full address · has verified phone
- Qualification filter: lead stage, `qualification_talked_to_client`, lead score
- Revenue: minimum revenue, revenue-positive only
- FraudLogix verdict: flagged only · accepted only · any · disagreements only
- Date range on session or lead
- Sample size + selection method: all · random(seed) · top-N by revenue · stratified by verdict

**Choose the vendors** — checkboxes rendered from the `vendor_product` registry, never hardcoded.
Adding a vendor makes a new checkbox appear with no UI change.

**Preview before running** — matching IPs, per-vendor call count, quota consumed vs remaining
(ProxyCheck: *"485 of 1,000 today"*), estimated cost, estimated duration. Nothing runs until this
is reviewed.

**Run** — writes a `sample_run` row and enqueues. The backend only executes what the row says; it
holds no policy of its own.

### New screen: Accuracy Report

Per-vendor rows, the five geo columns and five proxy columns from §4, confidence intervals shown,
drill-through from any cell to the per-IP evidence, and a per-IP comparison view — every vendor's
claim beside the lead's actual address.

### Backend contract

```
POST /samples/preview   → counts, quota impact, cost   (no side effects)
POST /samples           → create definition + run, enqueue
GET  /samples/{id}      → status, progress, per-vendor results
GET  /accuracy/{run_id} → the scorecard
GET  /accuracy/{run_id}/ips/{ip} → per-IP evidence trail
```

The only backend-held policy is the vendor rate limit, which is a safety interlock rather than a
product decision — the UI previews it, the worker enforces it.

---

## 6. Build sequence

| Step | Work | Gate |
|---|---|---|
| 1 | `lead_truth` from `uct_leads` × sessions | 485 IPs with full address reproduce |
| 2 | Load Tier 1 authoritative lists → `ipintel_reference`, refreshed daily | Tor + cloud + relay ranges queryable; `104.28.97.18` resolves as iCloud relay |
| 3 | ZIP→CBSA crosswalk + city alias table | `Fairfield-Suisun City` = `Fairfield` |
| 4 | `ip_geo` / `ip_intelligence` append-only tables + validity views | DB11, PX12, FraudLogix loaded for the 485 |
| 5 | Vendor adapters behind one interface; ProxyCheck, ipwho.is, ipinfo, MaxMind, DB-IP | one run populates all sources for 485 IPs |
| 6 | Accuracy scoring queries → `ipintel_analytics` | the two 5-column scorecards, with CIs |
| 7 | API endpoints per §5 | preview is side-effect free and quota-accurate |
| 8 | Lovable: Sample Builder + Accuracy Report | a run is defined, previewed and launched entirely from the UI |

Steps 1–4 are a day or two and need no vendor signups. Step 5 needs MaxMind/DB-IP/IPQS/AbuseIPDB
accounts — worth starting those signups now, in parallel, since they gate nothing else.

---

## 7. Open decisions

| # | Decision | Why it matters |
|---|---|---|
| **D1** | Can the truth pool be widened beyond `uct_leads`? Another lead source with addresses, or a session key on `revenue_leads_plus`? | 552 IPs is 0.011% of the universe and caps everything. Higher value than any new vendor. |
| **D2** | Run all 485 or sample 200? | Recommend 485 — same cost, ±4.4% instead of ±6.9%. |
| **D3** | Which free-tier accounts to create: MaxMind, DB-IP, IPQualityScore, AbuseIPDB, ipinfo? | Each adds an independent source; all free; only signup friction. |
| **D4** | Is a proxy verdict on iCloud Private Relay a false positive, or correct-but-unblockable? | Decides whether $154K counts against a vendor. Product decision, not a data one. |
| **D5** | Write to `unified.*` or stay in `ipintel_*` until stable? | `unified` is shared and platform-owned. |
| **D6** | Mapping for the 127,354 unmapped FraudLogix reason codes (`MASKED_DEVICES`, `BASIC_FRAUD`, numeric `"10"`/`"9"`/`"8"`) | Carried over from the build log; affects FraudLogix's flag rate in every comparison. |
| **D7** | Refresh cadence for the authoritative lists | Tor exits rotate hourly; cloud ranges change weekly. Daily is probably right; stale lists silently degrade recall. |

---

## 8. What I would change about the original framing

Three things, all small:

1. **200 → 485.** Use everything you have. (D2)
2. **"Vendor accuracy" splits in two.** Geo accuracy is genuinely measurable against lead addresses.
   Proxy accuracy is *not* measurable in general — only against authoritative lists and against
   business outcomes. Reporting a single "proxy accuracy %" would be inventing a number.
3. **Widening the truth pool beats adding vendors.** Nine sources scored on 485 IPs is a decent
   study. Nine sources on 5,000 IPs would settle the question. (D1)
