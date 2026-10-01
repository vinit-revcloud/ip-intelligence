# One Lovable Prompt — Benchmark Findings Screen

Copy everything inside the box below and paste it into Lovable as a single message.

**First**, add these two to your Lovable project's environment variables (server-side / secrets,
not public):

```
IPINTEL_API_URL   = https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/
IPINTEL_API_TOKEN = (the token from chat — do not commit it)
```

---

> Add a new page to this TanStack Start app that displays the results of an IP vendor benchmark.
>
> ## Route and shell
>
> Create `src/routes/findings.tsx` exporting
> `Route = createFileRoute('/findings')({ component, head })` with a `head()` that sets title,
> description, og:title, og:description, og:type and twitter:card, matching the pattern used by the
> other route files. Wrap the body in `<AppShell title="Benchmark Findings" subtitle="Seven location
> sources and four risk sources, measured on 485 real IPs.">`. Add a "Findings" link to the sidebar
> nav in `src/components/app-shell.tsx` using a Lucide `ClipboardCheck` icon with
> `strokeWidth={1.5}` and `className="h-4 w-4"`, placed directly after "Overview".
>
> ## Data layer
>
> Create `src/lib/api/findings.functions.ts`. Define two server functions with `createServerFn`
> from `@tanstack/react-start`:
>
> - `getFindingsSummary` — GET `${process.env.IPINTEL_API_URL}summary`
> - `getIpEvidence` — GET `${process.env.IPINTEL_API_URL}ip/${ip}`
>
> Both send header `Authorization: Bearer ${process.env.IPINTEL_API_TOKEN}`. Read both env vars
> **inside** the `.handler()`, never at module scope. On a non-OK response, throw an Error including
> the status code. Never fall back to mock data.
>
> Add the response types to `src/lib/api/contract.ts`:
>
> ```ts
> export type GeoScore = {
>   vendor: string; ips_tested: number; answer_rate_pct: number | null
>   state_match_pct: number | null; zips_supplied: number
>   zip_match_pct: number | null; median_error_mi: number | null; p90_error_mi: number | null
> }
> export type RiskScore = {
>   vendor: string; ips_sent: number; answered: number; answer_rate_pct: number | null
>   flag_rate_pct: number | null; proxy: number; vpn: number; tor: number
>   datacenter: number; bot: number; flagged_ips: number; leads_on_flagged: number
>   revenue_on_flagged_all: number; revenue_on_flagged_excl_shared: number
> }
> export type IndependencePair = {
>   vendor_a: string; vendor_b: string; ips: number
>   state_agree_pct: number; city_agree_pct: number; latlon_agree_pct: number; verdict: string
> }
> export type FindingsSummary = {
>   run_id: string; generated_at: string
>   sample: { ips: number; leads: number; revenue: number; shared_infrastructure_ips: number
>             revenue_on_shared_infrastructure: number; geo_sources: number; risk_sources: number
>             selection: string }
>   truth_caveat: string
>   geo_scorecard: GeoScore[]; risk_scorecard: RiskScore[]; source_independence: IndependencePair[]
> }
> ```
>
> Load with the route `loader` calling `context.queryClient.ensureQueryData(...)` and read it in the
> component with `useSuspenseQuery`. Do not fetch in `useEffect`.
>
> ## Page content, in this order
>
> **1. KPI row** — `<div className="grid gap-3.5 grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">` of
> `KpiCard`s: IPs Tested · Qualified Leads · Revenue in Sample · Location Sources · Risk Sources ·
> Revenue on Shared Infrastructure. Give the last one `tone="warn"`. Format money with
> `Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0})`.
>
> **2. `Callout`** immediately below, rendering `summary.truth_caveat` verbatim from the API. Do not
> hardcode this string. It must sit above the location table.
>
> **3. Card "Vendor Disagreement — Location"** (do not title it "accuracy"). A `DataTable` with
> `minWidth={860}`, sorted by `state_match_pct` descending, columns: Source · IPs · Answered % ·
> State Match % · ZIPs Supplied · ZIP Match % · Median Error · P90 Error.
>
> - Render `null` for `zip_match_pct` as an em-dash plus a neutral `Pill` reading "not supplied" —
>   never 0%. DB-IP and geojs return no postal code at all; showing 0% would call them wrong when
>   they simply did not answer.
> - Under each percentage add `<div className="text-[11px] text-muted-foreground">±4.5%</div>`.
> - Because every source's interval overlaps, render all values in the default foreground colour.
>   Do not colour a winner.
> - Distances are miles, one decimal, `tabular-nums`.
>
> **4. Card "Are these sources actually independent?"** — a `DataTable` with `minWidth={720}` over
> `source_independence`, sorted by `latlon_agree_pct` descending, columns: Source A · Source B ·
> State Agree % · City Agree % · Lat/Lon Agree % · Verdict. Any row whose `verdict` is not
> "independent" gets a `Pill` with `tone="bad"` showing the verdict text; others get a neutral pill
> reading "independent". Above the table put a `Callout`:
> *"geojs.io returns byte-identical coordinates to MaxMind GeoLite2 on all 485 IPs. It is a wrapper,
> not a second opinion — counting both would overstate how many independent sources we have."*
>
> **5. Card "Proxy, VPN and Bot Detection"** — `DataTable` with `minWidth={1000}`, columns: Source ·
> Sent · Answered · Answer Rate % · Proxy · VPN · Tor · Datacenter · Bot · Flagged IPs · Revenue on
> Flagged (all) · Revenue on Flagged (excl. shared infra).
>
> - Any source with `answer_rate_pct < 10` gets a `Pill tone="bad"` reading "almost no coverage"
>   next to its name. IP2Proxy PX12 answered 1 of 485 and that must be impossible to miss.
> - The two revenue columns are adjacent and right-aligned.
>
> **6. `Callout` under that table**, explaining the two revenue columns: revenue attributed to a
> shared egress IP is summed across tens of thousands of different people, so it is not a
> per-customer figure — `146.75.164.0` alone has 53,967 sessions and 7 leads. FraudLogix appears to
> put $305,758 at risk; excluding shared infrastructure the real figure is $2,193.
>
> **7. Card "Proven vendor error"** — a `DataTable` with `minWidth={640}` holding this fixed
> content, since it is a worked example rather than API data:
>
> | Source | State | City | ZIP | Verdict |
> |---|---|---|---|---|
> | Apple (authoritative) | TX | Dallas | — | ground truth |
> | ipwho.is | Texas | Dallas | 75202 | correct |
> | ipinfo.io | Texas | Dallas | 75201 | correct |
> | MaxMind GeoLite2 | Texas | Dallas | 75201 | correct |
> | IP2Location DB11 | Ciudad de Mexico | Mexico City | 14629 | wrong country |
>
> Apple's row gets a tinted background (`bg-accent`) and a `Pill tone="info"` reading "ground
> truth". The IP2Location row's verdict is `Pill tone="bad"`. Caption underneath in
> `text-[11px] text-muted-foreground`: *"IP 146.75.164.0. Apple publishes the city for every iCloud
> Private Relay egress range, so this is the operator's own statement, not an inference."*
>
> **8. IP lookup card** at the bottom — a text `input`, a "Look up" `Button`, and on submit call
> `getIpEvidence`. Render the returned `geo` array and `risk` array as two `DataTable`s, plus the
> business outcome (sessions, leads, revenue) as `MetricTile`s. Show a `Pill tone="warn"` reading
> "shared infrastructure" when that flag is true. In the risk table, a row with
> `has_answer === false` renders a neutral `Pill` reading "no answer" — visually distinct from a
> "clean" verdict, because those mean completely different things. A 404 renders an `EmptyState`
> saying the IP was not part of this benchmark run, not an error. Prefill the input with
> `146.75.164.0`.
>
> ## Constraints
>
> - Use only the existing primitives from `src/components/ui/primitives.tsx` — `Card`, `CardTitle`,
>   `KpiCard`, `DataTable`, `Pill`, `Callout`, `Button`, `MetricTile`, `EmptyState`, `Skeleton`.
>   Do not introduce a new component library.
> - No hardcoded colours anywhere — semantic tokens only. No `text-white`, no `bg-black`, no
>   `bg-[#hex]`.
> - Do not install any router. Do not edit `src/routeTree.gen.ts`. Do not create
>   `tailwind.config.js`. Do not add Vite plugins.
> - Every table goes in `DataTable` with an explicit `minWidth`; the page must not scroll
>   horizontally at 390px width.
> - Add a `Skeleton` fallback matching the page's shape, and an error state that shows the thrown
>   message with a retry button.
> - Strict TypeScript: no `any`, no non-null assertions.
> - The build must pass.

---

## What the API returns right now

| | |
|---|---|
| Run | `run-2026-09-03-02` |
| Sample | 485 IPs · 3,798 leads · $346,515 revenue |
| Location sources | 7 (+ Apple relay as truth) |
| Risk sources | 4 |
| Shared infrastructure | 28 IPs holding $346,245 |

### Location table as it will render

| Source | IPs | Answered | State | ZIPs supplied | ZIP match | Median err | P90 err |
|---|---:|---:|---:|---:|---:|---:|---:|
| MaxMind GeoLite2 | 485 | 99.2% | 59.5% | 465 | **17.8%** | **49.3 mi** | 783.7 mi |
| geojs.io | 485 | 99.2% | 59.5% | 0 | — | 49.3 mi | 783.7 mi |
| ipinfo.io | 485 | 100% | 58.8% | 485 | 11.5% | 59.3 mi | 810.9 mi |
| ipwho.is | 485 | 100% | 58.4% | 485 | 9.3% | 59.5 mi | 834.5 mi |
| IP2Location DB11 | 485 | 100% | 54.8% | 485 | 7.0% | 74.4 mi | 972.2 mi |
| proxycheck.io | 200 | 100% | 53.5% | 183 | 7.1% | 78.5 mi | 821.2 mi |
| DB-IP City Lite | 485 | 100% | 52.8% | 0 | — | 88.1 mi | 981.3 mi |

**MaxMind wins on every measurable dimension** — best ZIP match at 17.8% (more than double
IP2Location's 7.0%) and the lowest median error at 49 miles. On this sample it is the strongest
free geolocation source.

Read state/ZIP percentages as *disagreement*, not accuracy, until the truth question is settled.
Median error and the independence finding are unaffected by that caveat.
