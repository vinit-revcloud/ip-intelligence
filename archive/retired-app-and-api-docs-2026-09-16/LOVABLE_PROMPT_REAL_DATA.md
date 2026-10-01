# Lovable Prompt — Replace the Remaining Mock Pages with Real Data

`/findings` is already live. These five still show invented numbers:

| Page | Currently shows | Reality |
|---|---|---|
| Overview | 28,442 comparable IPs · 93.7% coverage · "MaxMind Anonymous failed" | 485 benchmarked · 4.94M universe · MaxMind GeoLite2 is healthy and the best source |
| Vendor Comparison | Fraudlogix vs ProxyCheck vs "MaxMind Anonymous" · $918K | 7 geo + 4 risk sources · $346,515 |
| Jobs & Sampling | ProxyCheck 80K/day · 18,922 rows | proxycheck free tier is **1,000/day** · 485 rows |
| Operations | OPS-1048 "MaxMind credential 401" | Six real issues, two critical |
| Sources & Plans | $2,510 annual committed · 2 paid plans | **$0** — every source in use is free tier |

There is no "MaxMind Anonymous" product in this project and no expired credential. Paste the
prompt below as one message.

---

> Replace the mock data on five pages with live API data. A new endpoint `GET /console` is
> available on the same base URL and token already configured as `IPINTEL_API_URL` /
> `IPINTEL_API_TOKEN`.
>
> ## Data layer
>
> Add `getConsoleData` to `src/lib/api/findings.functions.ts` — a `createServerFn` calling
> `${process.env.IPINTEL_API_URL}console` with `Authorization: Bearer ${process.env.IPINTEL_API_TOKEN}`,
> reading both env vars inside `.handler()`. Add these types to `src/lib/api/contract.ts`:
>
> ```ts
> export type ConsoleSource = {
>   id: string; company: string; product: string; delivery: string; purpose: string
>   plan: string; cost_per_month: number; limit: string | null
>   health: 'healthy' | 'degraded' | 'failed' | 'not_configured'
>   owner: string; capabilities: string[]; coverage_pct: number | null; note: string | null
> }
> export type ConsoleIssue = {
>   id: string; severity: 'critical' | 'warning' | 'info'; status: string
>   owner: string; title: string; detail: string; action: string
> }
> export type ConsoleRun = {
>   id: string; started: string; status: string; ips: number; sources: number
>   rows_written: number; cost_usd: number; population: string; note: string
> }
> export type ConsoleData = {
>   generated_at: string; run_id: string
>   overview: {
>     universe_ips: number; session_ips: number; total_revenue: number
>     db11_covered_pct: number; px12_covered_pct: number; fraudlogix_flagged_pct: number
>     geo_gap_filled: number; revenue_on_geo_gap: number
>     benchmark_ips: number; geo_sources: number; risk_sources: number
>     open_issues: number; critical_issues: number
>   }
>   sources: ConsoleSource[]; issues: ConsoleIssue[]; runs: ConsoleRun[]
>   plans: { paid_plans: number; annual_committed: number; weighted_actual_cpm: number; note: string }
> }
> ```
>
> Every page below loads through the route `loader` with
> `context.queryClient.ensureQueryData(...)` and reads with `useSuspenseQuery`. **Delete the
> corresponding constants from `src/lib/console-data.ts` as each page is converted** — no page may
> fall back to mock data.
>
> ## 1. Overview (`src/routes/index.tsx`)
>
> Replace all six KPI cards with, in order: **IP Universe** (`universe_ips`, formatted `4.94M`) ·
> **Session IPs** (`session_ips`) · **Attributed Revenue** (`total_revenue`, USD no decimals) ·
> **Geo Gap DB11 Fills** (`geo_gap_filled`, subtitle `$7.07M of revenue affected` from
> `revenue_on_geo_gap`) · **Benchmarked IPs** (`benchmark_ips`, subtitle
> `{geo_sources} geo · {risk_sources} risk sources`) · **Open Issues** (`open_issues`, `tone="bad"`
> when `critical_issues > 0`, subtitle `{critical_issues} critical`).
>
> Replace the red "MaxMind Anonymous enrichment has failed" `AlertBanner` with the highest-severity
> item from `issues` — render `title`, and a "View issue" action linking to `/operations`. Do not
> hardcode any issue text.
>
> **Delete the "Data Flow" area chart entirely.** It plots invented weekly volumes for a product
> that does not exist. Replace that card with **"Source Coverage"**: a `BarRow` per source from
> `sources` where `coverage_pct !== null`, sorted descending, labelled with `product`, using
> `tone="success"` above 90, `tone="warning"` 10–90, and `tone="destructive"` below 10. PX12 at 0.34%
> must be visibly alarming.
>
> Replace "Vendor Quality Snapshot" with a compact `DataTable` (`minWidth={520}`) of the top five
> sources by `coverage_pct`: Product · Purpose · Coverage · Health `StatusPill`.
>
> ## 2. Vendor Comparison (`src/routes/compare.tsx`)
>
> This page duplicates `/findings`. Strip it to a thin wrapper: delete the Comparison Builder,
> the four comparable-population metrics, the Product Scorecard and the Business Outcomes table —
> all of it is invented. Render instead an `EmptyState` with the title "Vendor comparison lives in
> Benchmark Findings", body text explaining that comparison runs on the 485-IP benchmark
> population, and a primary `Button` linking to `/findings`.
>
> Do not attempt to rebuild scorecards here; there is exactly one comparison and `/findings` owns it.
>
> ## 3. Jobs & Sampling (`src/routes/jobs.tsx`)
>
> Replace the mock form defaults and the plan-impact preview with real values.
>
> - The source checkboxes come from `sources` where `capabilities` includes `risk` or `geo`, showing
>   `product` and `limit`. **proxycheck.io must read "1,000/day", never 80K/day.** A source whose
>   `health` is `not_configured` renders disabled with a muted "not configured" pill.
> - Replace "Plan impact preview" with **"Recent runs"**: a `DataTable` (`minWidth={880}`) over
>   `runs` — Run ID · Started · Population · IPs · Sources · Rows Written · Cost · Status
>   `StatusPill`. Format `cost_usd` as USD with two decimals (`$0.02`).
> - Under it, a `Callout`: the whole benchmark costs about $0.02 per run in Athena scans and nothing
>   in vendor fees, because every source in use is free tier.
> - Keep the "Run job" button visually present but `disabled`, with a muted caption reading
>   "Runs are triggered from the data pipeline; UI-triggered runs are not wired yet." Do not
>   pretend it works.
>
> ## 4. Operations (`src/routes/data-health.tsx`)
>
> Replace the entire mock task queue with the real `issues` array.
>
> - Four KPI cards: Open Issues (`open_issues`) · Critical (`critical_issues`, `tone="bad"`) ·
>   Sources Degraded (count of `sources` with `health === 'degraded'`) · Sources Healthy.
> - Each issue renders as a `Card`: `id` and `title` on the first line, a severity `StatusPill` and
>   `owner` pill beside them, `detail` as body text, and `action` inside a `Callout` prefixed
>   **"Next step:"**. Sort critical first, then warning, then info.
> - Delete the mock `Retry / Assign / Ignore / Resolve` buttons — none of them do anything. Replace
>   with a single "Copy issue" button that copies `id + title + action` to the clipboard.
> - Delete the "Classification Drift" and "Recent Incidents" cards entirely; both are invented.
>
> ## 5. Sources & Plans (`src/routes/sources.tsx` and `costs.tsx`)
>
> - KPI cards become: **Total Sources** (`sources.length`) · **Paid Plans** (`plans.paid_plans`,
>   which is 0) · **Annual Committed** (`plans.annual_committed`, which is $0) · **Sources Degraded**.
> - The inventory table renders every row of `sources` (`minWidth={1100}`): Company · Product ·
>   Delivery · Purpose · Capabilities (small pills from the array) · Plan · Limit · Coverage % ·
>   Health `StatusPill` · Owner.
> - Where `note` is non-null, render it beneath the product name in
>   `text-[11px] text-muted-foreground`. Three of these notes are the most important text on the
>   page — geojs.io not being independent, PX12 answering 1 of 485, and ip-api.com being excluded on
>   licence grounds — so they must not be truncated or hidden behind a tooltip.
> - A row whose `health` is `not_configured` renders the whole row at reduced opacity.
> - Add a `Callout` above the table rendering `plans.note`.
>
> ## Constraints
>
> - Use only existing primitives from `src/components/ui/primitives.tsx`. No new component library.
> - No hardcoded colours — semantic tokens only. No hardcoded vendor names, issue text, or metric
>   values anywhere; everything renders from the API response.
> - Do not install a router, do not edit `src/routeTree.gen.ts`, do not create `tailwind.config.js`.
> - Every table in `DataTable` with an explicit `minWidth`; no horizontal page scroll at 390px.
> - Strict TypeScript: no `any`, no non-null assertions.
> - Each page keeps a `Skeleton` fallback and an error state with a retry button.
> - Verify with typecheck, build, and a Playwright pass at 1280px and 390px: no console errors, no
>   horizontal overflow, and **grep the repo for `28,442`, `918K`, `80K/day`, `2,510` and
>   `MaxMind Anonymous` — all must be gone.**

---

## What `/console` returns

**11 sources** — every one free tier. IP2Location DB11 · IP2Proxy PX12 · MaxMind GeoLite2 ·
DB-IP City Lite · proxycheck.io · ipwho.is · ipinfo.io · geojs.io · Authoritative lists ·
FraudLogix via TUNE · ip-api.com (excluded, non-commercial licence).

**6 issues** — two critical:

| ID | Severity | Title |
|---|---|---|
| IPI-001 | critical | Location truth may be the property, not the person |
| IPI-002 | critical | IP2Proxy PX12 answered 1 of 485 |
| IPI-003 | warning | geojs.io is not an independent source |
| IPI-004 | warning | An unnamed vendor sits inside the business-truth table |
| IPI-005 | warning | 127,354 FraudLogix verdicts are unmapped |
| IPI-006 | info | The truth pool is 0.011% of the IP universe |

**4 runs**, run-01 through run-04, showing how the benchmark evolved — 6 sources to 11, proxycheck
200 to 485 once the key was replaced.

**Overview:** 4,939,775 universe IPs · 1,990,813 session IPs · $15,939,329 attributed revenue ·
644,539 geo gaps DB11 fills · $7,074,034 of revenue on those gaps · 485 benchmarked.

### The single most important correction

Annual committed spend is **$0**, not $2,510. Every source in production use is free tier. The only
paid option evaluated is proxycheck.io at $5.99/mo. Any page showing committed spend or CPM is
showing fiction.
