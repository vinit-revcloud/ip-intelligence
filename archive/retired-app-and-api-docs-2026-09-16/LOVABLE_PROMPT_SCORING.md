# Lovable Prompt — Consensus Accuracy Scoring

API serves `run-2026-09-04-02`. No env changes. Paste everything below as one message.

---

> The benchmark API now returns consensus-based accuracy scoring, a brute-force pairwise agreement
> matrix, and explanation text. Add these to `/findings` and `/comparison`.
>
> ## Contract — `src/lib/api/contract.ts`
>
> ```ts
> export type GeoScoreRow = {
>   vendor: string; ips: number
>   fill_rate_pct: number; state_fill_pct: number; city_fill_pct: number; zip_fill_pct: number
>   state_judged: number; city_judged: number; zip_judged: number
>   state_agree_pct: number | null; city_agree_pct: number | null; zip_agree_pct: number | null
>   agreement_pct: number; score: number; excluded_from_voting: boolean
> }
> export type RiskScoreRow = {
>   vendor: string; pool_ips: number; answered: number; fill_rate_pct: number
>   flagged: number; detection_rate_pct: number | null
>   true_positive: number; infra_in_scope: number
>   precision_pct: number | null; recall_pct: number | null; f1: number | null
>   flagged_qualified: number; false_positive_pct: number | null; score: number | null
>   run_complete: boolean; coverage_note: string | null
> }
> export type PairwiseRow = {
>   vendor_a: string; vendor_b: string; ips: number
>   state_comparable: number; state_agree_pct: number | null
>   city_comparable: number;  city_agree_pct: number | null
>   zip_comparable: number;   zip_agree_pct: number | null
>   latlon_agree_pct: number | null; verdict: string
> }
> export type ScoringExplanation = {
>   location: string; location_caveat: string; risk: string; risk_caveat: string
> }
> // add to FindingsSummary:
> //   geo_score: GeoScoreRow[]; risk_score_v2: RiskScoreRow[]
> //   pairwise_agreement: PairwiseRow[]; scoring_explanation: ScoringExplanation
> //   method_notes: string[]; sample.voters: number
> ```
>
> ## 1. Explanation box — required above every scorecard
>
> Build a reusable `<ScoringBox variant="location" | "risk" />` component rendering a bordered
> `Card` with a muted background, titled **"How these scores are calculated"**. Body =
> `scoring_explanation.location` or `.risk`. Beneath it, a second paragraph in warning tone with
> `.location_caveat` or `.risk_caveat`, prefixed with a bold **"Important:"**.
>
> **All four strings come from the API — never hardcode them.** Place this box directly above the
> matching table on both `/findings` and `/comparison`.
>
> ## 2. Location scorecard — replace the old table
>
> Render `geo_score` sorted by `score` desc. Columns:
>
> Source · Fill Rate % · State Fill % · City Fill % · ZIP Fill % · State Agree % · City Agree % ·
> ZIP Agree % · **Agreement %** · **Score**
>
> - **Score** is the ranking column: bold, larger, right-aligned.
> - A `null` agreement renders as an em-dash plus a neutral `Pill` "not supplied" — never 0%.
> - Under each agreement percentage show its denominator in `text-[11px] text-muted-foreground`,
>   e.g. `of 271 judged` from `state_judged` / `city_judged` / `zip_judged`. A reader must be able
>   to see a percentage was computed on 271 rows, not 511.
> - A row with `excluded_from_voting === true` shows a `Pill tone="warn"` reading **"mirror — not a
>   voter"** beside the vendor name, and renders at 85% opacity.
> - Caption below: `Consensus over {sample.voters} independent voters.`
>
> ## 3. Risk scorecard — replace the old table
>
> Render `risk_score_v2` sorted by `score` desc. Columns:
>
> Source · Coverage (`answered / pool_ips`) · Fill Rate % · Flagged · Detection % · True Positives ·
> **Precision %** · **Recall %** · **F1** · False-Positive % · **Score**
>
> - **Detection %** must render in muted foreground with the header tooltip *"Descriptive only — not
>   ranked. A source flagging everything scores 100%."*
> - Precision, Recall, F1 and Score are the emphasised columns.
> - `null` F1/Score renders as an em-dash plus a neutral Pill "not computable" — this happens when a
>   source made no verifiable flags.
> - Rows with `run_complete === false` get a `Pill tone="warn"` "partial coverage" with
>   `coverage_note` as its `title`.
>
> ## 4. Pairwise matrix — the granular evidence, on `/comparison`
>
> Replace the empty-state card on `/comparison` with the full brute-force view.
>
> Add a `Tabs` control with four tabs: **State · City · ZIP · Lat/Lon**. For the active field render
> a `HeatMatrix` of every source against every other, cell value = the matching `*_agree_pct`.
> Cell tone: `a` when ≥90, `b` when 60–89, `c` below 60. Under the matrix, a `DataTable`
> (`minWidth={880}`) of all 21 `pairwise_agreement` rows: Source A · Source B · Comparable IPs ·
> Agree % · Verdict — with `verdict` as a `Pill tone="bad"` when it is not "independent".
>
> Above it, the location `ScoringBox`, and a `Callout` listing `method_notes` as bullet points.
>
> Page subtitle becomes: *"Every source compared against every other, field by field. This is the
> raw evidence behind each score."*
>
> ## 5. Remove
>
> Delete `authoritative_lists` from any scored table — it is no longer in `risk_score_v2` because it
> is not a vendor, it is the validator. If it appears anywhere as a ranked row, remove it. Keep the
> old `geo_scorecard` / `risk_scorecard` fields unused, or delete their rendering entirely.
>
> ## Constraints
>
> Existing primitives only. No hardcoded colours, vendor names, metric values or explanation text.
> Do not install a router, do not edit `src/routeTree.gen.ts`. Every table in `DataTable` with an
> explicit `minWidth`; no horizontal overflow at 390px. Strict TypeScript. Build must pass. After
> the change, grep for `authoritative_lists` — it must not appear in any scored table.

---

## The results this renders

### Location — consensus over 6 independent voters (n=511)

| Source | Fill | State Agr | City Agr | ZIP Agr | Agreement | **Score** |
|---|---:|---:|---:|---:|---:|---:|
| **ipinfo.io** | 100% | 95.7% | 76.8% | 81.3% | 84.8% | **84.8** |
| ipwho.is | 100% | 95.9% | 76.4% | 63.5% | 79.7% | **79.7** |
| IP2Location DB11 | 100% | 88.8% | 70.9% | 53.3% | 72.2% | **72.2** |
| proxycheck.io | 97.0% | 84.5% | 69.9% | 51.8% | 70.3% | **68.2** |
| MaxMind GeoLite2 | 96.9% | 89.2% | 53.5% | 37.4% | 61.8% | **59.9** |
| DB-IP combined | 66.7% | 82.8% | 66.7% | — | 74.8% | **49.9** |
| geojs.io *(mirror)* | 65.0% | 89.2% | 53.5% | — | 71.7% | **46.6** |

### ⚠️ The finding that matters most

**MaxMind ranks 1st against Apple's real ground truth, but 5th on consensus.**

Consensus rewards conformity. MaxMind disagrees with the crowd more often — and on the 30 IPs where
we have operator-published truth, MaxMind is the one that is right while IP2Location puts a Dallas
address in Mexico City. **This is the clearest possible demonstration that agreement is not
accuracy**, and it is why the caveat box is mandatory above the table.

### Risk — precision against operator-published ranges (n=511)

| Source | Coverage | Flagged | Detection | Precision | Recall | F1 | **Score** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **proxycheck.io** | 511/511 | 33 | 6.5% | **90.9%** | **100%** | **95.2** | **95.2** |
| FraudLogix (TUNE) | 249/511 | 84 | 33.7% | 9.5% | 27.6% | 14.2 | **6.9** |
| IP2Proxy PX12 | 1/511 | 1 | 100% | 0% | 0% | — | — |

proxycheck caught **all 30** known-infrastructure IPs with only 3 extra flags.

FraudLogix flags 33.7% of traffic but only 8 of 84 land on a published range — **however**, it
largely detects behavioural fraud (bots, abnormal patterns) which by definition never appears on an
infrastructure list. Its low precision here means *unverifiable by this method*, not *wrong*. That
caveat is in `scoring_explanation.risk_caveat` and must be shown.

### Method notes (rendered from `method_notes`)

- geojs.io agrees with MaxMind on **100.0%** of state, city and lat/lon — one database, two names.
- DB-IP and proxycheck agree on **88.6%** of lat/lon, suggesting shared upstream data.
- DB-IP Lite publishes no postal code, so its ZIP is "not supplied", never 0%.
- `authoritative_lists` is no longer scored — it is the validator.

### Still outstanding

**vpnapi.io needs a free API key** (unauthenticated hits a Cloudflare challenge). It would add a
third real proxy voter — right now risk scoring rests on proxycheck and FraudLogix alone.
**ipinfo.io's privacy module is paid only** and stays excluded.
