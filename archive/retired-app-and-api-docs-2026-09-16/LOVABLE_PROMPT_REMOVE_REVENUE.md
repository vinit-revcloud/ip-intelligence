# Lovable Prompt — Remove Revenue, Vendor Comparison Only

API now serves `run-2026-09-07-01` with every revenue figure removed. No env changes.
Paste everything below as one message.

---

> Strip all revenue and business-outcome analysis from this console. It compares IP intelligence
> vendors on a fixed set of 511 test IPs — nothing else. Per-IP revenue attribution was unsound
> (a shared egress IP sums thousands of different people) and it distracted from the vendor question.
>
> ## 1. Fields removed from the API
>
> These no longer exist in any response. Delete them from `src/lib/api/contract.ts` and every
> component that reads them — TypeScript will point at each one:
>
> ```
> sample.revenue                          sample.revenue_on_shared_infrastructure
> sample.deal_ips
> risk_scorecard[].revenue_on_flagged_all risk_scorecard[].revenue_on_flagged_excl_shared
> risk_scorecard[].leads_on_flagged
> risk_score_v2[].flagged_qualified       risk_score_v2[].false_positive_pct
> per_ip[].business                       per_ip[].lead.is_deal
> console.overview.total_revenue          console.overview.revenue_on_geo_gap
> console.plans                           (the whole object)
> ```
>
> ## 2. New field — render it
>
> `scope_note` is on `/summary`, `/console` and `/recommendations`. Render it as a neutral `Callout`
> at the top of `/findings` and `/recommendations`, above everything else:
>
> > *"This console compares IP intelligence vendors on a fixed set of 511 test IPs. It does not model
> > revenue, fraud loss or business outcomes…"*
>
> From the API, never hardcoded.
>
> ## 3. Screen-by-screen removals
>
> **`/findings`** — delete the "Revenue in Sample" and "Revenue on Shared Infrastructure" KPI cards.
> The KPI row becomes: IPs Tested · Qualified Leads · Phone-Verified · Location Sources ·
> Risk Sources · Shared-Infrastructure IPs (`sample.shared_infrastructure_ips`, `tone="warn"`).
>
> Delete the two revenue columns from the risk table and the callout beneath it explaining them.
> The risk table columns become: Source · Coverage · Fill Rate % · Flagged · Detection % ·
> True Positives · Precision % · Recall % · F1 · Score.
>
> **`/overview`** — remove any revenue KPI. Replace with: IP Universe · Session IPs ·
> Benchmark IPs · Location Sources · Risk Sources · Open Issues.
>
> **`/sources`** — delete the "Annual Committed", "Paid Plans" and CPM KPI cards, and the
> `plans.note` callout. Keep the per-source `cost_model`, `plan` and `limit` columns — vendor
> pricing is part of comparing vendors; modelled business revenue is not.
>
> **`/ip-explorer`** and the IP lookup card — delete the business-outcome MetricTiles (sessions,
> revenue, revenue sessions). Keep the `lead` pills: phone verified, intro qualified, talked to
> client. Keep the shared-infrastructure badge.
>
> **`/operations`** — the API now returns 4 issues instead of 6; the revenue-framed ones are gone.
> No code change needed, but confirm nothing assumes a fixed count.
>
> ## 4. New page — `/ip-detail`, the full evidence grid
>
> Two unified tables now exist with one row per IP per vendor and per-row accuracy. Add a route
> **"IP Detail"** to the sidebar after "Findings", Lucide `Table2` icon.
>
> Two endpoints return them (add server functions for both):
> `GET /unified/geo` and `GET /unified/intelligence`, each `{ count, rows: [...] }`.
>
> ```ts
> export type UnifiedGeoRow = {
>   ip_address: string; vendor: string
>   country_code: string | null; country_name: string | null
>   state: string | null; city: string | null; zip_code: string | null
>   latitude: number | null; longitude: number | null; timezone: string | null
>   has_answer: boolean
>   consensus_state: string | null; consensus_city: string | null; consensus_zip: string | null
>   state_votes: number | null; city_votes: number | null; zip_votes: number | null
>   state_matches_consensus: boolean | null
>   city_matches_consensus: boolean | null
>   zip_matches_consensus: boolean | null
>   fields_answered: number; fields_judged: number; fields_matched: number
>   row_agreement_pct: number | null
>   property_state: string | null; property_city: string | null; property_zip: string | null
>   state_matches_property: boolean | null
>   observed_at: string; valid_from: string; valid_to: string | null
> }
> export type UnifiedIntelRow = {
>   ip_address: string; vendor: string
>   is_proxy: boolean | null; is_vpn: boolean | null; is_tor: boolean | null
>   is_datacenter: boolean | null; is_bot: boolean | null
>   fraud_reason: string | null; risk_score: number | null
>   isp: string | null; asn: string | null
>   has_answer: boolean; flagged: boolean
>   known_infrastructure: boolean; infrastructure_list: string | null
>   verdict_class: 'confirmed_by_published_range' | 'unconfirmed_flag'
>              | 'missed_known_infrastructure' | 'agreed_not_flagged' | 'no_answer'
>   verdict_correct: boolean | null; row_accuracy_pct: number | null
>   observed_at: string; valid_from: string; valid_to: string | null
> }
> ```
>
> **Layout.** A `Tabs` control: **Geolocation** and **Proxy & Bot**. Each tab shows an IP selector
> (a `Select` of distinct `ip_address`, defaulting to the first) and a `DataTable` of that IP's rows
> — one row per vendor, so a reader sees all 7 geo sources or all 4 risk sources side by side for a
> single IP.
>
> Geolocation columns: Vendor · State · City · ZIP · Lat · Lon · Timezone · Consensus State ·
> Consensus City · Consensus ZIP · Matches (3 pills) · Row Agreement %.
> The three "matches" pills: `true`→good "match", `false`→bad "differs", `null`→neutral "not judged".
>
> Proxy & Bot columns: Vendor · Proxy · VPN · Tor · Datacenter · Bot · Reason · Risk Score · ISP ·
> ASN · Known Infrastructure · Verdict · Row Accuracy %.
> **Every tri-state boolean renders three ways: `true`→"yes" (bad tone, it is a flag), `false`→"no"
> (good tone), `null`→em-dash with a neutral "no opinion" pill.** A null is not a "no" — that
> distinction is the most important rule on this screen.
>
> `verdict_class` renders as a `Pill`: `confirmed_by_published_range`→good,
> `unconfirmed_flag`→warn, `missed_known_infrastructure`→bad, `agreed_not_flagged`→neutral,
> `no_answer`→neutral outline.
>
> Above each table, a `Callout` explaining the accuracy column:
> - Geolocation: *"Row agreement is how many of this vendor's answered fields match the majority of
>   independent sources. geojs.io mirrors MaxMind and does not vote."*
> - Proxy: *"Row accuracy checks each flag against operator-published ranges — Tor, AWS, GCP,
>   Cloudflare, Fastly, Apple relay. A source with no opinion is scored as neither right nor wrong."*
>
> Add a **"Download CSV"** button per tab that exports the currently loaded rows.
>
> ## Constraints
>
> Existing primitives only; semantic tokens only; no hardcoded colours, vendor names or figures.
> No router changes, no `src/routeTree.gen.ts` edits. Explicit `minWidth` on every table; no
> horizontal page overflow at 390px. Strict TypeScript, no `any`. Build must pass.
>
> **Verify:** typecheck, build, then grep the repo for `revenue`, `Revenue`, `business.revenue`,
> `annual_committed`, `CPM` and `false_positive` — none may remain in any component.

---

## What was built in AWS

Two tables, created in `unified` (both names were free — nothing existing was touched), with data
stored under our own `ip-intelligence/unified/` prefix rather than another team's space.

### `unified.ip_geo` — 3,577 rows (511 IPs × 7 sources)

Your schema, plus accuracy. Every field you specified is present; `country_name` and `timezone` are
null for sources that do not publish them.

| Vendor | Rows | Answered | Fields judged | Matched | Avg row agreement |
|---|---:|---:|---:|---:|---:|
| ipinfo.io | 511 | 511 | 1,430 | 1,209 | **83.3%** |
| ipwho.is | 511 | 511 | 1,430 | 1,150 | 80.1% |
| DB-IP combined | 511 | 511 | 1,019 | 756 | 74.3% |
| IP2Location DB11 | 511 | 511 | 1,430 | 1,049 | 72.6% |
| geojs.io | 511 | 507 | 995 | 707 | 70.4% |
| proxycheck.io | 511 | 511 | 1,401 | 973 | 68.6% |
| MaxMind GeoLite2 | 511 | 507 | 1,396 | 858 | 60.6% |

### `unified.ip_intelligence` — 2,044 rows (511 IPs × 4 sources)

| Vendor | Answered | Flagged | Confirmed | Unconfirmed | Missed | No answer | Avg accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Authoritative lists | 511 | 30 | 30 | 0 | 0 | 0 | 100.0% |
| **proxycheck.io** | 511 | 33 | 30 | 3 | 0 | 0 | **99.4%** |
| FraudLogix (TUNE) | 249 | 84 | 8 | 76 | **21** | 262 | 61.0% |
| IP2Proxy PX12 | 1 | 1 | 0 | 1 | 0 | **510** | 0.0% |

`verdict_class` makes the failure mode explicit: FraudLogix **missed 21 IPs that are on published
infrastructure ranges**, which no aggregate score showed before.

### A worked row — one IP, all seven geo sources

| Vendor | State | City | ZIP | Agreement |
|---|---|---|---|---:|
| geojs.io | Maryland | Waldorf | — | 100% |
| ipwho.is | Maryland | Waldorf | 20602 | 100% |
| MaxMind | Maryland | Waldorf | 20602 | 100% |
| ipinfo.io | Maryland | Waldorf | 20603 | 66.7% |
| IP2Location DB11 | Maryland | Waldorf | 20603 | 66.7% |
| DB-IP combined | District of Columbia | Washington D.C. | — | 0% |
| proxycheck.io | District of Columbia | Washington D.C. | 20068 | 0% |

Five sources say Maryland, two say DC — roughly 30 miles apart, on one IP.

## CSVs

`unified_ip_geo_511.csv` (3,577 rows) and `unified_ip_intelligence_511.csv` (2,044 rows), both in
the project folder and both including every accuracy column.

## SCD2 note

`valid_from` = `observed_at`, `valid_to` = NULL on every row, because this is the first observation
of each (IP, vendor). On the next run, close the prior row by setting its `valid_to` to the new
`observed_at` and insert the new row with `valid_to` NULL. The columns exist now so that history
works without a schema change.
