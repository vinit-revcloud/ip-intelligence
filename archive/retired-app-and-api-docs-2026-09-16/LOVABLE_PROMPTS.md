# Lovable Prompts — IP Intelligence Console

Paste these into Lovable **in order**. Each is self-contained and builds on the last.
Prompts 1–3 need no backend — they run on fixtures, so you can do them today while AWS finishes.

**Before prompt 1**, put `PROJECT_CONTEXT.md` §10 in the repo root as `.cursorrules` (and
`CLAUDE.md`). Without it an agent will install `react-router-dom`, edit `routeTree.gen.ts`, or add
`tailwind.config.js`, and the build breaks.

The through-line: **sources, sample definitions and metrics are all data, never code.** Adding
proxycheck.io's $5.99 plan later must be a form submission, not a deploy.

---

## Prompt 1 — Put a data seam under the whole app

> Refactor how the app gets its data, with **no visual change at all**. Every screen must look
> pixel-identical when you're done.
>
> 1. Create `src/lib/api/contract.ts` exporting a TypeScript type for each screen's response
>    payload. Derive the shapes from the existing exports in `src/lib/console-data.ts` and the
>    canonical types in `src/lib/types.ts`. These types are the contract with the backend — they
>    are the single source of truth for response shape.
> 2. Create one `createServerFn` per screen in `src/lib/api/*.functions.ts`
>    (`overview.functions.ts`, `sources.functions.ts`, `compare.functions.ts`, and so on). For now
>    every handler returns the matching constant from `console-data.ts`, typed with the contract.
> 3. Add `src/lib/api/client.ts` with a single `fetchFromBackend(path, init)` helper. It reads
>    `process.env.IPINTEL_API_URL` **inside** the handler, never at module scope. If the variable
>    is unset it throws a clearly-named error. Nothing calls it yet.
> 4. Convert every route to load data through its server function using the route `loader` with
>    `context.queryClient.ensureQueryData(...)` plus `useSuspenseQuery` in the component. Do not
>    use `useEffect` fetching.
> 5. Add proper loading and error states: a `Skeleton` layout per screen matching its real shape,
>    and an error boundary showing a retry action. Use the existing primitives.
>
> Constraints: don't install any router, don't touch `src/routeTree.gen.ts`, don't add
> `tailwind.config.js`, no hardcoded colors — semantic tokens only. Build must pass.

---

## Prompt 2 — Sources become editable data

> Build a **Source Registry** so vendor products are managed entirely from the UI. Nothing about a
> vendor may be hardcoded in a component ever again.
>
> Add to `src/lib/api/contract.ts`:
>
> ```ts
> export type VendorSourceRecord = {
>   id: string
>   company: string
>   product: string
>   kind: 'database' | 'api' | 'authoritative_list' | 'internal_feed'
>   capabilities: { geo: boolean; risk: boolean; asn: boolean }
>   plan: { name: string; dailyLimit: number | null; monthlyLimit: number | null; costPerMonth: number; costPerLookup: number }
>   credentialRef: string | null   // Secrets Manager key name. NEVER the secret itself.
>   status: 'healthy' | 'degraded' | 'failed' | 'not_configured'
>   enabled: boolean
>   owner: string
>   notes: string
> }
> ```
>
> Rewrite `/sources` to render this list from the server function, and add:
>
> - **"+ Add Source"** opening a `Drawer` form covering every field above. `credentialRef` is a
>   **name only**, with helper text: *"Name of the secret in AWS Secrets Manager. Never paste the
>   key itself."* Validate with Zod.
> - **Edit** and **Enable/Disable** per row. Disabled sources stay visible, greyed, and are excluded
>   from runs.
> - A **capabilities** column rendered as small pills (Geo / Risk / ASN).
> - A **plan** column showing limit and cost, with an inline editor — so changing proxycheck.io from
>   the free tier to the $5.99 plan is editing two numbers, not a code change.
>
> Seed the registry with: IP2Location LITE DB11 (database, geo, free), IP2Proxy LITE PX12 (database,
> risk, free), FraudLogix via TUNE (internal feed, risk, bundled), proxycheck.io (api, geo+risk,
> free tier 1000/day), ipwho.is (api, geo, free), ipinfo.io (api, geo+asn, free),
> Authoritative Lists (authoritative_list, risk, free), MaxMind GeoLite2 (database, geo,
> not_configured), Spur (api, risk, not_configured).
>
> Every other screen that lists vendors must now iterate this registry. Adding a tenth source must
> require zero component changes — verify that before you finish.

---

## Prompt 3 — Sample Builder

> Add a new route `/sample-builder` — "Build an Accuracy Test" — and add it to the sidebar. This is
> where the user chooses **which IPs get tested**. All selection logic lives here, in the UI; the
> backend only executes what this screen defines.
>
> A `sample_definition` is a plain object the user composes:
>
> ```ts
> export type SampleDefinition = {
>   name: string
>   truthRequirement: 'qualified_lead' | 'lead_with_address' | 'revenue_positive' | 'any'
>   minRevenue: number | null
>   minLeads: number | null
>   fraudlogixVerdict: 'any' | 'flagged_only' | 'accepted_only' | 'disagreements_only'
>   dateRange: { from: string; to: string } | null
>   excludeSharedInfrastructure: boolean
>   sampleSize: number | null          // null = use every matching IP
>   selection: 'all' | 'random' | 'top_by_revenue' | 'stratified_by_verdict'
>   randomSeed: number | null
>   vendorIds: string[]                // from the Source Registry
> }
> ```
>
> Layout, using existing primitives:
>
> 1. **Define population** — a `KeyValue` grid of `Select`s and inputs for every field above.
> 2. **Choose sources** — checkboxes generated from the Source Registry. Disabled sources render
>    greyed with a "not configured" pill. Never hardcode this list.
> 3. **Preview impact** — a prominent card, refreshed whenever any control changes, calling
>    `POST /samples/preview`. It must show: matching IPs, IPs with usable truth, and a per-source
>    table of lookups needed, daily quota remaining, whether the run fits in quota, and estimated
>    cost. Show a `Callout` in a warning tone when a source would exceed its limit, naming the
>    source and by how much. Preview has **no side effects**.
> 4. **Run** — primary button, disabled until the preview succeeds. Posts to `POST /samples` and
>    routes to the run detail page.
>
> Also add `/sample-builder/runs/:runId` showing status, per-source progress bars, rows written,
> errors, and a link to the accuracy report when complete.
>
> Until the backend exists, the preview and run server functions return realistic fixtures. Wire the
> real endpoints behind `IPINTEL_API_URL` exactly as prompt 1 set up.

---

## Prompt 4 — Accuracy Report

> Add `/accuracy` — "Accuracy Report" — reading a completed run.
>
> **Two separate tables, and the distinction between them matters.**
>
> **Table A — Location.** One row per source: IPs tested · answer rate % · state match % ·
> ZIP match % · median error (mi) · P90 error (mi).
>
> **Table B — Proxy & Bot.** One row per source: IPs tested · answer rate % · flag rate % ·
> false-positive rate % · revenue at risk $ · authoritative agreement %.
>
> Rules the UI must enforce:
>
> - Every percentage shows its **95% confidence interval** as smaller muted text beneath
>   (`±4.4%` at n=485). Sort by the metric but never imply an ordering the interval doesn't support:
>   when two sources' intervals overlap, render both with a neutral tone rather than
>   winner-coloured.
> - Column headers carry an info tooltip with the exact definition of the metric.
> - **Revenue at risk appears twice** — "including shared infrastructure" and "excluding" — as two
>   adjacent columns, because iCloud Private Relay alone can dominate the ranking.
> - A `Callout` at the top of Table A states which truth source was used and its known limitations.
>   Make this text come from the API response, not hardcoded — the caveat changes with the source.
> - A source with no data for a metric shows an em-dash and a "not measured" pill. Never 0%.
>
> Clicking any cell drills through to the per-IP evidence for that source and metric.

---

## Prompt 5 — Per-IP evidence

> Rebuild `/ip-explorer` around a real comparison, and make it reachable from every drill-through.
>
> - Header: the IP, its ISP and ASN, sessions, leads, revenue, and pills for shared-infrastructure
>   classification (CDN / relay / datacenter / CGNAT) when it applies.
> - **Location comparison table**: one row per source plus a highlighted first row for the truth
>   value. Columns: source, state, city, ZIP, distance from truth (mi), and a match/miss pill per
>   field. The truth row is visually distinct — a tinted background, not a different colour system.
> - **Classification table**: one row per source — verdict pill, raw vendor verdict string,
>   confidence/risk score, and the reason.
> - **A "no answer" row is not a clean verdict.** A source that returned nothing renders a neutral
>   "no answer" pill, visibly different from a "clean" verdict. This is the single most important
>   rule on this screen.
> - "View raw responses" opens a `Drawer` with the stored raw JSON per source in a `CodeBlock`.
> - If the IP is iCloud Private Relay, show a `Callout`: the sources calling it a proxy are
>   technically correct, and Apple's own published city for that range is X.
>
> Use `73.162.10.21` and `172.59.171.92` as fixture examples — both have genuine four-way vendor
> disagreement.

---

## Prompt 6 — Go live, one screen at a time

> Wire the frontend to the real backend, screen by screen, so each can be reverted independently.
>
> - Add `IPINTEL_API_URL` and `IPINTEL_API_KEY` to server-side env. They are read **inside**
>   handlers only and must never appear in a client bundle — verify by searching the built output.
> - Add `src/lib/api/flags.ts` exporting `isLive(screen)`, driven by a comma-separated
>   `IPINTEL_LIVE_SCREENS` env var. Each server function checks its own flag: live → call the API,
>   otherwise → return the fixture. One env var change puts a screen live or rolls it back.
> - Go live in this order: **sources → accuracy → sample-builder → ip-explorer → overview.**
> - Add a small "Data: live / fixture" indicator in the header, driven by the same flag, so nobody
>   mistakes fixtures for measurements in a demo.
>
> Do not change any component's visual output in this prompt. It is wiring only.

---

## Backend endpoints these prompts assume

```
GET  /sources                    list registry          POST /sources         create
PATCH /sources/{id}              update / enable        
POST /samples/preview            counts + quota, no side effects
POST /samples                    create definition, enqueue run
GET  /samples/{runId}            status + progress
GET  /accuracy/{runId}           both scorecards + truth caveat text
GET  /accuracy/{runId}/ips/{ip}  per-IP evidence + raw payloads
```

---

## Two things to keep straight while building

**Read `BENCHMARK_RESULTS.md` §2 before you trust any accuracy number.** The first run produced
~55% state accuracy, but two independent vendors agree with *each other* 93.2% of the time — which
means the lead address is very likely the property being sold, not where the person was sitting.
Until that is confirmed with the business, the Accuracy Report should present **agreement**, not
accuracy. Prompt 4's API-supplied caveat text exists precisely so that this can be stated honestly
without a redeploy.

**The ProxyCheck key currently isn't working** — the API is treating requests as anonymous and
capping at 100/day. Check it in the dashboard before buying the $5.99 plan; when it is upgraded,
the only change is two numbers in the Source Registry form.
