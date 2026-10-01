# Lovable Prompt — Corrected Truth Source

The API now serves `run-2026-09-04-01`, rebuilt from `sampledb.revenue_leads_plus`.
No env changes. Paste everything below as one message.

---

> The benchmark API has been rebuilt on a corrected truth source. The payload has new fields, a
> renamed metric, and the location scorecard now has two segments. Update the `/findings` page.
>
> ## Contract changes — `src/lib/api/contract.ts`
>
> ```ts
> export type GeoScore = {
>   segment: 'all' | 'phone_verified'          // NEW
>   vendor: string; ips_tested: number; answer_rate_pct: number | null
>   state_match_pct: number | null
>   cities_comparable: number                   // NEW
>   city_match_pct: number | null               // NEW
>   zips_supplied: number; zip_match_pct: number | null
>   median_error_mi: number | null; p90_error_mi: number | null
> }
>
> export type FindingsSummary = {
>   run_id: string; generated_at: string
>   truth_source: string                        // NEW e.g. "sampledb.revenue_leads_plus"
>   metric_name: string                         // NEW e.g. "IP-to-property distance"
>   sample: {
>     ips: number; leads: number; revenue: number
>     phone_verified_ips: number                // NEW
>     qualified_ips: number; deal_ips: number   // NEW
>     cities_with_truth: number                 // NEW
>     metros_with_truth: number                 // NEW
>     shared_infrastructure_ips: number; revenue_on_shared_infrastructure: number
>     geo_sources: number; risk_sources: number; truth_sources: number
>     selection: string
>   }
>   truth_caveat: string
>   geo_scorecard: GeoScore[]; risk_scorecard: RiskScore[]
>   source_independence: IndependencePair[]
>   truth_sources: { vendor: string; ips: number; role: string; note: string }[]
> }
> ```
>
> `IpEvidence` also changes — `truth` gains `metro`, and there is a new `lead` object:
>
> ```ts
> truth: { state: string | null; city: string | null; zip: string | null; metro: string | null }
> lead: { leads: number; phone_verified: boolean; intro_qualified: boolean
>         talked_to_client: boolean; is_deal: boolean }
> business: { revenue: number; sessions: number; revenue_sessions: number }
> ```
>
> ## 1. Rename the location table
>
> Its heading becomes `{metric_name}` from the API — currently **"IP-to-property distance"**. Do not
> hardcode the string, and do not call it accuracy or disagreement.
>
> Add a subheading beneath it in `text-[11px] text-muted-foreground`:
> `Truth: {truth_source}`.
>
> **Why this matters.** The lead address is the property being enquired about, not where the person
> was sitting. This table measures how far the visitor's IP is from the property — a lead-quality
> and fraud signal. It is not a vendor accuracy score, and labelling it as one would be wrong.
>
> ## 2. Add the segment toggle
>
> `geo_scorecard` now contains each vendor twice, once per `segment`. Add a `Tabs` control above the
> table with two tabs: **All leads** (`all`) and **Phone-verified** (`phone_verified`), defaulting
> to All. Filter rows by the active segment. Show the row count for each tab in its label, e.g.
> `Phone-verified (140)` — take the count from `sample.phone_verified_ips`.
>
> Beneath the tabs add a `Callout`: *"Phone-verified leads are records a human confirmed by phone.
> They score the same as the full set, which is how we know the low match rate is not a data-quality
> problem."*
>
> ## 3. Add the city column
>
> The table columns become: Source · IPs · Answered % · State Match % · Cities Comparable ·
> City Match % · ZIPs Supplied · ZIP Match % · Median Error · P90 Error.
>
> `city_match_pct` and `zip_match_pct` render as an em-dash plus a neutral `Pill` reading
> "not supplied" when null — never 0%. `cities_comparable` and `zips_supplied` are the denominators
> and must be visible, so a reader can see a percentage is computed on 271 rows, not 511.
>
> ## 4. Update the KPI row
>
> Replace the six cards with: **IPs Tested** (`sample.ips`) · **Phone-Verified**
> (`sample.phone_verified_ips`) · **Qualified Leads** (`sample.qualified_ips`) · **Deals**
> (`sample.deal_ips`) · **Location Sources** (`sample.geo_sources`) · **Revenue on Shared
> Infrastructure** (`sample.revenue_on_shared_infrastructure`, `tone="warn"`, subtitle
> `{sample.shared_infrastructure_ips} shared IPs`).
>
> ## 5. Escalate the truth caveat
>
> The `truth_caveat` string is now a confirmed finding rather than a suspicion. Render it in a
> `Callout` with the **destructive** tone (it is currently warning), still verbatim from the API,
> still above the location table. Prefix it with a bold label reading **Confirmed:**.
>
> ## 6. IP lookup card
>
> Add the new fields to the evidence view. Show `truth.metro` alongside state/city/zip. Render the
> `lead` object as a row of pills: "phone verified", "intro qualified", "talked to client", "deal" —
> each shown only when true, using `tone="good"`. If none are true, show a neutral pill reading
> "no qualification recorded".
>
> ## Constraints
>
> Existing primitives only. No hardcoded colours, metric names, source counts or truth-source
> strings — everything from the API. Do not install a router, do not edit `src/routeTree.gen.ts`.
> Every table in `DataTable` with an explicit `minWidth`; no horizontal overflow at 390px. Strict
> TypeScript. Build must pass. After the change, grep for `485` and `uct_leads` — neither should
> appear in any component.

---

## What changed in the data

**Truth source:** `unified.uct_leads` → **`sampledb.revenue_leads_plus`** (14,966,619 leads).
`uct_leads` remains only as the bridge to an IP via `alyson_session_id`.

| | Before | After |
|---|---:|---:|
| Benchmark pool | 485 | **511** |
| City truth | 54 | **284** |
| Metro truth | 0 | **313** |
| Phone-verified | 0 | **140** |
| Qualified / deals | — | 137 / 137 |

### Location scorecard — all leads (n=511)

| Source | State | Cities comp. | City | ZIP | Median err |
|---|---:|---:|---:|---:|---:|
| **MaxMind GeoLite2** | **64.3%** | 271 | **30.6%** | **19.4%** | **36.8 mi** |
| geojs.io *(= MaxMind)* | 64.3% | 271 | 30.6% | — | 37.0 mi |
| ipinfo.io | 63.8% | 284 | 23.2% | 12.9% | 46.2 mi |
| ipwho.is | 63.2% | 284 | 17.3% | 9.8% | 47.4 mi |
| IP2Location DB11 | 59.9% | 284 | 16.5% | 8.0% | 59.6 mi |
| proxycheck.io | 58.3% | 284 | 14.8% | 7.7% | 67.3 mi |
| DB-IP City Lite | 56.8% | 284 | 13.4% | — | 73.1 mi |

Every metric improved with better truth, and the ranking is unchanged — **MaxMind still wins on all
four dimensions.**

### The decisive result

| Segment | n | MaxMind state match |
|---|---:|---:|
| All leads | 511 | 64.3% |
| **Phone-verified** | **140** | **64.0%** |

Records a human confirmed by phone score **the same**. Cleaner data does not close the gap, which
proves the ~64% is not a data-quality artefact — the address was never measuring the person's
location. That settles the open question, and it is why the metric is renamed rather than fixed.

### Risk scorecard (n=511)

| Source | Coverage | Proxy | VPN | Bot |
|---|---:|---:|---:|---:|
| proxycheck.io | 511 / 511 | 33 | 32 | 0 |
| Authoritative lists | 511 / 511 | 30 | 30 | 0 |
| FraudLogix (TUNE) | 249 / 511 | 49 | 0 | 69 |
| IP2Proxy PX12 | **1 / 511** | 1 | 0 | 0 |

Vendor accuracy remains anchored only to Apple's published relay city, on 30 IPs.
