# Final Lovable Prompt — Benchmark Findings

Supersedes all earlier prompts. Add these two **server-side secrets** first (not public, not `VITE_`):

```
IPINTEL_API_URL   = https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/
IPINTEL_API_TOKEN = xEVWxcFa--qFzYdEqaVNOkDE5R4VG6VMu5se-2WddbA
```

Keep the trailing slash on the URL — paths are built as `${IPINTEL_API_URL}summary`.

Then paste everything below as one message.

---

> Add a `/findings` page to this TanStack Start app showing the results of a live IP-vendor
> benchmark. All data comes from an external API — **no mock data anywhere on this page.**
>
> ## Route and shell
>
> Create `src/routes/findings.tsx` exporting
> `Route = createFileRoute('/findings')({ component, head })`, with `head()` setting title,
> description, og:title, og:description, og:type and twitter:card, matching the other route files.
> Wrap the body in `<AppShell title="Benchmark Findings" subtitle="Seven location sources and four
> risk sources, measured on 485 real IPs.">`. Add a "Findings" nav item to
> `src/components/app-shell.tsx` using the Lucide `ClipboardCheck` icon with `strokeWidth={1.5}`
> and `className="h-4 w-4"`, placed directly after "Overview".
>
> ## Types — add to `src/lib/api/contract.ts`
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
>   run_complete: boolean; coverage_note: string | null
> }
> export type IndependencePair = {
>   vendor_a: string; vendor_b: string; ips: number
>   state_agree_pct: number; city_agree_pct: number; latlon_agree_pct: number; verdict: string
> }
> export type FindingsSummary = {
>   run_id: string; generated_at: string
>   sample: {
>     ips: number; leads: number; revenue: number
>     shared_infrastructure_ips: number; revenue_on_shared_infrastructure: number
>     geo_sources: number; risk_sources: number; selection: string
>   }
>   truth_caveat: string
>   geo_scorecard: GeoScore[]; risk_scorecard: RiskScore[]; source_independence: IndependencePair[]
> }
> export type GeoClaim  = { vendor: string; state: string | null; city: string | null
>                           zip: string | null; lat: number | null; lon: number | null }
> export type RiskClaim = { vendor: string; has_answer: boolean
>                           is_proxy: boolean | null; is_vpn: boolean | null; is_tor: boolean | null
>                           is_datacenter: boolean | null; is_bot: boolean | null
>                           reason: string | null; risk_score: number | null
>                           isp: string | null; asn: string | null }
> export type IpEvidence = {
>   ip: string
>   truth: { state: string | null; city: string | null; zip: string | null }
>   business: { leads: number; revenue: number; sessions: number; revenue_sessions: number }
>   shared_infrastructure: boolean
>   geo: GeoClaim[]; risk: RiskClaim[]
> }
> ```
>
> ## Data layer — `src/lib/api/findings.functions.ts`
>
> Two `createServerFn` functions from `@tanstack/react-start`:
>
> - `getFindingsSummary` — `GET ${process.env.IPINTEL_API_URL}summary`
> - `getIpEvidence` — `GET ${process.env.IPINTEL_API_URL}ip/${ip}`
>
> Both send `Authorization: Bearer ${process.env.IPINTEL_API_TOKEN}`. Read both env vars **inside**
> `.handler()`, never at module scope. Throw on non-OK responses, including the status code in the
> message. `getIpEvidence` treats 404 as a distinct "not in this run" result, not an error. Never
> fall back to mock data.
>
> Load via the route `loader` with `context.queryClient.ensureQueryData(...)` and read in the
> component with `useSuspenseQuery`. No `useEffect` fetching.
>
> ## Page sections, in this order
>
> **1. KPI row.** `<div className="grid gap-3.5 grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">` of
> `KpiCard`s: IPs Tested · Qualified Leads · Revenue in Sample · Location Sources · Risk Sources ·
> Revenue on Shared Infrastructure (`tone="warn"`). Money via
> `Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0})`.
>
> **2. `Callout`** rendering `summary.truth_caveat` verbatim from the API. Never hardcode this
> string. It must sit **above** the location table.
>
> **3. Card — "Vendor Disagreement — Location"** (do not call it "accuracy"). `DataTable`
> `minWidth={860}`, sorted by `state_match_pct` desc. Columns: Source · IPs · Answered % ·
> State Match % · ZIPs Supplied · ZIP Match % · Median Error · P90 Error.
>
> - `zip_match_pct === null` renders as an em-dash plus a neutral `Pill` reading "not supplied" —
>   **never 0%.** DB-IP and geojs return no postal code at all; 0% would call them wrong when they
>   simply did not answer.
> - Under each percentage: `<div className="text-[11px] text-muted-foreground">±4.5%</div>`.
> - Every source's confidence interval overlaps, so render all values in the default foreground
>   colour. Do not colour a winner.
> - Distances in miles, one decimal, `tabular-nums`.
> - Caption below the table: *"geojs.io and MaxMind GeoLite2 return identical coordinates on all 485
>   IPs — treat them as one source, not two."*
>
> **4. Card — "Are these sources actually independent?"** `DataTable` `minWidth={720}` over
> `source_independence`, sorted by `latlon_agree_pct` desc. Columns: Source A · Source B ·
> State Agree % · City Agree % · Lat/Lon Agree % · Verdict. Rows whose `verdict` is not
> "independent" get `Pill tone="bad"` with the verdict text; others a neutral "independent" pill.
> Above the table, a `Callout`: *"geojs.io returns byte-identical coordinates to MaxMind GeoLite2 on
> all 485 IPs. It is a wrapper, not a second opinion — counting both would overstate how many
> independent sources we have."*
>
> **5. Card — "Proxy, VPN and Bot Detection"** `DataTable` `minWidth={1040}`. Columns: Source ·
> Coverage · Answer Rate % · Proxy · VPN · Tor · Datacenter · Bot · Flagged IPs ·
> Revenue on Flagged (all) · Revenue on Flagged (excl. shared infra).
>
> - **Coverage** renders `answered / ips_sent` (e.g. `237 / 485`) in `tabular-nums`.
> - Rows where `run_complete === false` show a `Pill tone="warn"` reading "partial coverage" beside
>   the source name, with `coverage_note` as the pill's `title` attribute. **Do not infer this from
>   a percentage** — a low answer rate can mean the vendor had no opinion *or* that we failed to
>   query it fully, and only the API knows which.
> - The two revenue columns sit adjacent and right-aligned under a shared grouped header.
>
> **6. `Callout`** below that table: revenue attributed to a shared egress IP is summed across tens
> of thousands of different people, so it is not a per-customer figure — `146.75.164.0` alone has
> 53,967 sessions and 7 leads. FraudLogix appears to put **$305,758** at risk; excluding shared
> infrastructure the real figure is **$2,193**.
>
> **7. Card — "Proven vendor error."** `DataTable` `minWidth={640}` with this fixed content (a
> worked example, not API data):
>
> | Source | State | City | ZIP | Verdict |
> |---|---|---|---|---|
> | Apple (authoritative) | TX | Dallas | — | ground truth |
> | ipwho.is | Texas | Dallas | 75202 | correct |
> | ipinfo.io | Texas | Dallas | 75201 | correct |
> | MaxMind GeoLite2 | Texas | Dallas | 75201 | correct |
> | IP2Location DB11 | Ciudad de Mexico | Mexico City | 14629 | wrong country |
>
> Apple's row gets `bg-accent` and `Pill tone="info"` reading "ground truth". IP2Location's verdict
> is `Pill tone="bad"`. Caption in `text-[11px] text-muted-foreground`: *"IP 146.75.164.0. Apple
> publishes the city for every iCloud Private Relay egress range, so this is the operator's own
> statement, not an inference."*
>
> **8. Card — IP lookup.** A text input (prefilled `146.75.164.0`), a "Look up" `Button`, and on
> submit call `getIpEvidence`. Render:
> - the `geo` array as a `DataTable` (`minWidth={640}`): Source · State · City · ZIP · Lat · Lon
> - the `risk` array as a `DataTable` (`minWidth={760}`): Source · Proxy · VPN · Tor · Datacenter ·
>   Bot · Reason · Risk Score
> - `business` as four `MetricTile`s: Sessions · Leads · Revenue · Revenue Sessions
> - `Pill tone="warn"` reading "shared infrastructure" when that flag is true
>
> **In the risk table, a row with `has_answer === false` renders a neutral `Pill` reading "no
> answer" — visually distinct from a "clean" verdict.** These mean completely different things and
> conflating them is the single worst error this page could make. Likewise render `null` booleans as
> an em-dash, never as "false".
>
> A 404 renders an `EmptyState` saying the IP was not part of this benchmark run — not an error.
>
> ## States and constraints
>
> - Route-level `Skeleton` fallback matching the page shape; error state showing the thrown message
>   with a retry button.
> - Use only existing primitives from `src/components/ui/primitives.tsx` — `Card`, `CardTitle`,
>   `KpiCard`, `DataTable`, `Pill`, `Callout`, `Button`, `MetricTile`, `EmptyState`, `Skeleton`.
>   Do not introduce another component library.
> - **No hardcoded colours** — semantic tokens only. No `text-white`, no `bg-black`, no `bg-[#hex]`.
> - Do not install any router. Do not edit `src/routeTree.gen.ts`. Do not create
>   `tailwind.config.js`. Do not add Vite plugins.
> - Every table inside `DataTable` with an explicit `minWidth`; **no horizontal page scroll at
>   390px**.
> - Strict TypeScript: no `any`, no non-null assertions.
> - Do not hardcode the run id — read `run_id` from the API and show it, with `generated_at`, in
>   small muted text at the bottom of the page.
> - Verify: typecheck, build, then a Playwright pass at 1280px and 390px — page loads live API data,
>   IP lookup returns evidence for `146.75.164.0`, an unknown IP shows the `EmptyState`, no console
>   errors, no horizontal overflow.

---

## What the API returns (`run-2026-09-03-04`)

**Sample:** 485 IPs · 3,798 leads · $346,515 revenue · 28 shared-infrastructure IPs holding $346,245

### Location — 7 sources

| Source | IPs | Answered | State | ZIPs | ZIP match | Median | P90 |
|---|---:|---:|---:|---:|---:|---:|---:|
| MaxMind GeoLite2 | 485 | 99.2% | **59.5%** | 465 | **17.8%** | **49.3 mi** | 783.7 mi |
| geojs.io *(= MaxMind)* | 485 | 99.2% | 59.5% | 0 | — | 49.3 mi | 783.7 mi |
| ipinfo.io | 485 | 100% | 58.8% | 485 | 11.5% | 59.3 mi | 810.9 mi |
| ipwho.is | 485 | 100% | 58.4% | 485 | 9.3% | 59.5 mi | 834.5 mi |
| IP2Location DB11 | 485 | 100% | 54.8% | 485 | 7.0% | 74.4 mi | 972.2 mi |
| proxycheck.io | 485 | 100% | 54.2% | 441 | 7.9% | 84.1 mi | — |
| DB-IP City Lite | 485 | 100% | 52.8% | 0 | — | 88.1 mi | 981.3 mi |

### Risk — 4 sources

| Source | Coverage | Answer rate | Proxy | VPN | Bot | Complete |
|---|---:|---:|---:|---:|---:|:--|
| proxycheck.io | 485 / 485 | 100% | 31 | 30 | 0 | ✅ |
| Authoritative lists | 485 / 485 | 100% | 28 | 28 | 0 | ✅ |
| FraudLogix (TUNE) | 237 / 485 | 48.9% | 47 | 0 | 67 | ⚠️ partial |
| IP2Proxy PX12 | **1 / 485** | **0.2%** | 1 | 0 | 0 | ⚠️ partial |

### Headline conclusions the page will show

1. **MaxMind GeoLite2 is the strongest free geo source** — best ZIP match (2.5× IP2Location) and
   lowest median error.
2. **geojs.io is not an independent source** — byte-identical coordinates to MaxMind on all 485 IPs.
3. **IP2Proxy PX12 answered 1 of 485.** The free proxy database is effectively empty for this
   traffic — and absence is *not* a clean verdict.
4. **28 IPs (5.8%) are iCloud Private Relay**, holding 99.9% of the sample's attributed revenue —
   which is why per-IP revenue must be split with and without shared infrastructure.
5. **Location percentages are disagreement, not accuracy**, pending the property-vs-person address
   question. Median error and the independence finding are unaffected by that caveat.
