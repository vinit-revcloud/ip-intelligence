# Lovable Prompt — Recommendations Screen

New endpoint `GET /recommendations` is live on the same base URL and token. No env changes.
Paste everything below as one message.

---

> Add a `/recommendations` page — **"Source Recommendations"** — that tells a reader which IP source
> to use for which job, why, and exactly how the conclusion was reached. It is the report view of
> the benchmark. Add it to the sidebar directly after "Findings", with the Lucide `Award` icon,
> `strokeWidth={1.5}`, `className="h-4 w-4"`.
>
> ## Contract — `src/lib/api/contract.ts`
>
> ```ts
> export type RecEvidence = { label: string; value: string; note?: string }
> export type RecPick = {
>   rank: number; need: string; source_id: string; source_label: string
>   verdict: 'primary' | 'specialist'; headline: string; why: string
>   evidence: RecEvidence[]; weakness: string
> }
> export type RecAvoid = {
>   source_id: string; source_label: string
>   severity: 'critical' | 'warning'; headline: string; why: string
> }
> export type RecWarning = { source_id: string; source_label: string; headline: string; why: string }
> export type RecMethod = { step: string; formula?: string; detail: string }
> export type RecNext = { priority: 'highest' | 'high' | 'medium'; action: string; why: string }
> export type Recommendations = {
>   generated_at: string; run_id: string
>   population: { ips: number; sources: number; confidence_interval_pct: number }
>   picks: RecPick[]; avoid: RecAvoid[]; fair_warnings: RecWarning[]
>   method: RecMethod[]; caveats: string[]; next_steps: RecNext[]
> }
> ```
>
> Add `getRecommendations` to `src/lib/api/findings.functions.ts` — a `createServerFn` calling
> `${process.env.IPINTEL_API_URL}recommendations` with the bearer token, both env vars read inside
> `.handler()`. Load via the route `loader` with `ensureQueryData`, read with `useSuspenseQuery`.
>
> ## Page layout
>
> **1. Header strip.** Under the page subtitle, one muted line:
> `Run {run_id} · {population.ips} IPs · {population.sources} sources · ±{population.confidence_interval_pct}% at 95% confidence`
>
> **2. "Use these" — one Card per pick**, ordered by `rank`, in a single column (not a grid — these
> are meant to be read).
>
> Each card:
> - **Header row:** `need` as a small uppercase eyebrow in `text-[10px] tracking-wide text-muted-foreground`;
>   `source_label` as the card title; a `Pill` on the right — `tone="good"` for `verdict === 'primary'`,
>   `tone="info"` for `'specialist'`, showing the verdict text.
> - **`headline`** directly beneath the title, in 15px medium weight — this is the one-line answer.
> - **`why`** as body text, max ~70 characters per line.
> - **Evidence strip:** the `evidence` array as a row of `MetricTile`s — `label` above, `value` as
>   the metric, `note` beneath in `text-[11px] text-muted-foreground` when present. Wrap on narrow
>   screens.
> - **`weakness`** in a `Callout` with warning tone, prefixed with a bold **"Where it falls short:"**.
>   Every pick has one and it must always render — a recommendation without its limitation is a
>   sales pitch.
>
> **3. "Do not rely on these" — one Card per `avoid` entry.** Title = `source_label`, a `StatusPill`
> from `severity` (`critical`→bad, `warning`→warn), `headline` in medium weight, `why` as body text.
> Render this section immediately after the picks, not at the bottom — what to avoid is as
> actionable as what to choose.
>
> **4. "Read this before judging" — `fair_warnings`.** Same card shape but neutral tone, no severity
> pill. This section exists so FraudLogix's low precision is not misread as a failure.
>
> **5. "How these scores are calculated" — the method.** A `DataTable` (`minWidth={720}`) over
> `method`: Step · Formula · What it does. Render `formula` in a `code` element with
> `font-mono text-[12px]`, or an em-dash when absent. This table is what makes the page
> report-ready — a reader must be able to reproduce every number without asking anyone.
>
> **6. "Caveats" — a numbered list** from `caveats`, inside a `Callout` with warning tone, titled
> **"These must travel with any report"**. Render as an ordered list, one caveat per item, full text
> — do not truncate. The first caveat (agreement is not accuracy) is the single most important
> sentence on the page.
>
> **7. "What would change these conclusions" — `next_steps`.** A `DataTable` (`minWidth={640}`):
> Priority · Action · Why. Priority as a `Pill`: `highest`→bad, `high`→warn, `medium`→neutral.
>
> ## Rules
>
> - **Every string comes from the API.** No hardcoded source names, scores, formulas, caveats or
>   recommendations anywhere in the component. When the benchmark is re-run the page must update
>   from the payload alone.
> - Each pick's `source_label` links to `/sources` filtered to that `source_id`, so a reader can see
>   its live registry entry and last diagnosis.
> - `weakness`, `avoid` and `caveats` are **not optional rendering**. A page that shows only the
>   recommendations and hides the limitations would misrepresent the evidence.
> - Semantic tokens only, no hardcoded colours. Existing primitives only (`Card`, `CardTitle`,
>   `Pill`, `StatusPill`, `Callout`, `MetricTile`, `DataTable`, `Skeleton`, `EmptyState`).
> - Route `head()` with title, description, og:title, og:description, og:type, twitter:card.
> - Skeleton fallback matching the page shape; error state showing the thrown message with retry.
> - Strict TypeScript, no `any`. Explicit `minWidth` on both tables. No horizontal overflow at 390px.
> - Build must pass with no console errors.
>
> ## Add a print stylesheet
>
> This page will be exported as a report. Add `@media print` rules: hide the sidebar and any
> nav/header chrome, force single-column layout, remove card shadows, keep borders, and set
> `break-inside: avoid` on every Card and table row so nothing splits across pages.

---

## What the endpoint returns

**4 picks** · **3 to avoid** · **1 fair warning** · **7 method steps** · **5 caveats** ·
**3 next steps**

| # | Need | Source | Verdict |
|---|---|---|---|
| 1 | Geolocation — bulk, millions of IPs | **IP2Location LITE DB11** | primary |
| 2 | Geolocation — per-lookup accuracy | **ipinfo.io** | primary |
| 3 | Geolocation — hardest cases | **MaxMind GeoLite2** | specialist |
| 4 | Proxy, VPN and bot detection | **proxycheck.io** | primary |

**Avoid:** IP2Proxy PX12 (answered 1 of 511) · geojs.io (MaxMind mirror) · ip-api.com
(non-commercial licence).

**Fair warning:** FraudLogix — 9.5% precision means *unverifiable by this method*, not wrong.

Every pick carries its own `weakness`, and the caveat list leads with the one that matters most:
**agreement is not accuracy**. MaxMind ranks 5th on consensus while being the only source correct
against Apple's real ground truth — which is why the method table and the caveats are mandatory
rendering, not decoration.

## To refresh after a re-run

```bash
aws s3 cp recommendations.json s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/recommendations.json
```

The page updates on next load. No redeploy.
