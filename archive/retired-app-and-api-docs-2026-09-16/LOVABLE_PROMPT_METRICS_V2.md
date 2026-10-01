# Lovable Prompt — Agreement Rename, New Metrics, Raw Data

API serves the 2,071-IP qualified-lead pool with new metric columns. No env changes.
Paste everything below as one message.

---

> The benchmark moved to a new population and the scorecards gained columns. Update the console.
>
> ## 1. Rename Accuracy → Agreement, everywhere
>
> Every UI label, column header, tooltip and type name that says *accuracy* becomes **Agreement**,
> except in two places where the word is earned and must stay: **precision/recall against
> operator-published ranges**, and the **Apple-verified ground truth** card. Those measure against
> fact; everything else measures conformity with a majority.
>
> Field renames in the payload: `state_agree_pct` → `state_agreement_pct`, `city_agree_pct` →
> `city_agreement_pct`, `zip_agree_pct` → `zip_agreement_pct`, `row_accuracy_pct` →
> `row_agreement_pct`. Update `contract.ts` and let TypeScript find every usage.
>
> ## 2. Location scorecard — new columns
>
> `geo_score` rows now carry `cost_per_1k` and a renamed agreement set:
>
> ```ts
> export type GeoScoreRow = {
>   vendor: string; ips: number
>   fill_rate_pct: number; state_fill_pct: number; city_fill_pct: number; zip_fill_pct: number
>   state_judged: number; city_judged: number; zip_judged: number
>   state_agreement_pct: number | null; city_agreement_pct: number | null
>   zip_agreement_pct: number | null
>   agreement_pct: number; cost_per_1k: string; score: number
>   excluded_from_voting: boolean
> }
> ```
>
> Columns: Source · Fill Rate % · State Fill % · City Fill % · ZIP Fill % · State Agreement % ·
> City Agreement % · ZIP Agreement % · **Agreement %** · **Cost / 1k** · **Score**.
>
> Cost renders as `$0.00` for every enabled source. Do not hide the column because the values are
> zero — showing it makes "free" explicit rather than assumed, and it is where a paid tier appears.
>
> ## 3. Risk scorecard — new columns and two deliberate nulls
>
> ```ts
> export type RiskScoreRow = {
>   vendor: string; pool_ips: number; answered: number; fill_rate_pct: number
>   flagged: number; detection_rate_pct: number | null
>   bot_flagged: number; bot_identification_pct: number | null
>   false_positive_rate_pct: number | null
>   true_positive: number; infra_in_scope: number
>   precision_infra_pct: number | null; recall_infra_pct: number | null; f1_infra: number | null
>   precision_bot_pct: number | null      // always null - see below
>   recall_bot_pct: number | null         // always null - see below
>   bot_metric_status: string             // "needs a bot-labelled pool"
>   cost_per_1k: string; score: number | null
> }
> ```
>
> Columns: Source · Coverage (`answered / pool_ips`) · Fill Rate % · Flagged · Detection % ·
> **Bot Identification %** · **False-Positive Rate %** · Precision (infra) % · Recall (infra) % ·
> F1 · **Cost / 1k** · **Score**.
>
> **`precision_bot_pct` and `recall_bot_pct` are always null and must NOT render as 0%.** Render an
> em-dash plus a `Pill tone="neutral"` showing `bot_metric_status`. Add a header tooltip:
>
> > *Every IP in this pool produced a qualified lead, so it is a confirmed human. That makes the
> > false-positive rate exact — any bot flag here is definitely wrong. It also means the pool
> > contains no true bots, so bot precision and recall have no denominator. They need a
> > bot-labelled pool.*
>
> **False-Positive Rate is the headline column on this table.** Give it the same visual weight as
> Score: bold, right-aligned, and `tone="bad"` when above 10%.
>
> ## 4. New page — `/raw`, the unfiltered data
>
> Add **"Raw Data"** to the sidebar after "IP Detail", Lucide `Database` icon. Two endpoints:
> `GET /unified/geo` and `GET /unified/intelligence`, each `{ count, rows: [...] }`.
>
> A `Tabs` control — **Geolocation** and **Proxy & Bot** — and for each:
>
> - A filter row: free-text IP search, a vendor `Select` ("All vendors" default), and for the geo
>   tab a "disagreements only" checkbox that keeps rows where `row_agreement_pct < 100`.
> - A `DataTable` showing **every column of the table, unfiltered and untruncated**. This screen
>   exists so nobody has to trust an aggregate — it is the evidence.
> - Row count above the table: `Showing {filtered} of {count} rows`.
> - A **Download CSV** button exporting the currently filtered rows.
> - Client-side pagination at 100 rows per page; do not virtualise, keep it simple.
>
> **Tri-state booleans render three ways on both tabs:** `true` → "yes", `false` → "no",
> `null` → em-dash with a neutral "no opinion" pill. A null is not a "no", and on the proxy tab that
> distinction is the whole point — IP2Proxy PX12 is null on almost every row.
>
> ## 5. Scope note
>
> `scope_note` is served on `/summary`, `/console` and `/recommendations`. Render it as a neutral
> `Callout` at the top of `/findings`, `/recommendations` and `/raw`. It states that this console
> compares vendors on a fixed test pool and does not model revenue or business outcomes.
>
> ## Constraints
>
> Existing primitives only; semantic tokens only; no hardcoded colours, vendor names, metric values
> or explanation strings — everything from the API. No router changes, no `src/routeTree.gen.ts`
> edits. Explicit `minWidth` on every table; no horizontal page overflow at 390px. Strict
> TypeScript, no `any`. Build must pass, no console errors.
>
> **Verify:** typecheck, build, then grep for `accuracy` and `Accuracy` — the only matches allowed
> are the infra precision/recall tooltip and the Apple ground-truth card. Confirm
> `precision_bot_pct` never renders as `0%`.

---

## What changed in the data

### The population — your `utm_content` join

| | Old (email via `uct_leads`) | New (`utm_content` + `furthest_stage`) |
|---|---:|---:|
| IPs | 511 | **2,071** |
| with state + ZIP | 511 | 2,055 |
| with city | 284 | **1,812** |
| **phone-verified** | 140 (27%) | **1,660 (80%)** |

Qualified leads are defined by your 11 `furthest_stage` values. **Only 49 IPs overlap with the old
pool** — this is different traffic, not an extension, so every published figure moves.

### Free API tiers do not scale — a real procurement finding

Enriching 2,055 IPs exposed hard daily caps:

| Source | Returned | Note |
|---|---:|---|
| proxycheck.io | **2,055** | batch POST of 100/request — barely touched the 1,000/day cap |
| ipwho.is | **1,000** | undocumented daily cap; "fair use" is literally 1,000 |
| ipinfo.io | **1,000** | free-tier cap |
| geojs.io | timed out | rate-limited; excluded anyway as a MaxMind mirror |
| DB11 · PX12 · MaxMind · DB-IP | **2,055** | local files, no cap |

**At 2,055 IPs the free API tiers cover half the pool; the file-based sources cover all of it.**
That is the clearest argument yet for IP2Location DB11 as the bulk primary — and it is why
proxycheck's batch endpoint matters so much, since it is the one API that keeps up.

Their fill rates will show ~49%. That is the vendor's cap, not a failure of ours, and the coverage
note in the registry says so.

### Bot metrics

`false_positive_rate_pct` is exact: the pool is 100% confirmed humans, so every bot flag is wrong.
`precision_bot_pct` and `recall_bot_pct` are null with `bot_metric_status` explaining why. To fill
them, a bot-labelled pool is needed — `is_bot_click` sessions would be the cheapest option, though
it measures agreement with an incumbent rather than truth.
