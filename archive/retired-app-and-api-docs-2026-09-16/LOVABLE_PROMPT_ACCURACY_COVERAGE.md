# Lovable Prompt — Location Accuracy and Enrichment Coverage (update message)

Paste this **only if the app already has `LOVABLE_PROMPT_FINAL_APP.md` applied** (and
`LOVABLE_PROMPT_UNIFIED_PUBLISH.md` if you pasted that). If not, paste `LOVABLE_PROMPT_FINAL_APP.md`
instead: it already contains everything below. Both endpoints are live and tested (16 September 2026).

---

> Add two read-only report pages. Do not change any other page. Also change the copy rule "The word is
> Agreement, never Accuracy" to: "Agreement means vendors compared with each other (vendor overview). Accuracy
> is used only on the Location Accuracy page, where a vendor is compared with the customer's own postal address."
>
> Add a new **Reports** section to the navigation, between Tables and Pipeline, with two pages in this
> order: **Location Accuracy** and **Enrichment Coverage**. Both are read only. Both read a JSON report that
> the daily jobs rebuild after every run, so they load instantly. Use the same server-function conventions as
> the other pages (`IPINTEL_API_URL` and `IPINTEL_API_TOKEN` read inside `.handler()`, API error strings shown
> word for word). A 404 or 503 shows the calm panel "This report appears after the next daily run." — never an
> error.
>
> ## Endpoints
>
> | Method | Path | Returns |
> |---|---|---|
> | GET | `/accuracy/geo` | `GeoAccuracy` |
> | GET | `/coverage` | `Coverage` |
>
> Server functions in `src/lib/api/reports.functions.ts`: `getGeoAccuracy`, `getCoverage`. Refresh each page's
> data every 5 minutes; the files change at most a few times a day.
>
> ## Contract — add to `src/lib/api/contract.ts`
>
> ```ts
> export type AccuracyRow = {
>   vendor: string          // "ip2location_db11" | "proxycheck_io" | "ipinfo_io" | "ipwho_is" | "resolved" (render whatever arrives)
>   tested: number          // truth addresses this vendor was checked on
>   answered: number
>   answered_pct: number | null
>   state_judged: number; state_match: number; state_pct: number | null
>   city_judged: number;  city_match: number;  city_pct: number | null
>   zip_judged: number;   zip_match: number;   zip_pct: number | null
>   state_city_judged: number; state_city_match: number; state_city_pct: number | null
> }
> export type GeoAccuracy = {
>   as_of: string
>   truth: { source: string; addresses: number; note: string }
>   rules: { state: string; city: string; zip: string; state_city: string }
>   min_state_sample: number
>   vendors: (AccuracyRow & { pool: 'all' })[]
>   common_pool: { description: string; addresses: number; vendors: (AccuracyRow & { pool: 'common' })[] }
>   by_state: (AccuracyRow & { state: string; small_sample: boolean })[]
> }
>
> export type CoverageCounts = {
>   addresses: number
>   proxycheck_answered: number
>   proxy_concluded: number
>   proxy_no_conclusion: number
>   geo_agreed: number
>   geo_single_source: number
>   geo_disagree_or_missing: number
>   proxycheck_pct: number | null
>   proxy_concluded_pct: number | null
>   geo_agreed_pct: number | null
> }
> export type Coverage = {
>   as_of: string
>   window_days: number                 // 30
>   window_start: string                // "YYYY-MM-DD"
>   totals: { last_30_days: CoverageCounts; all_addresses: CoverageCounts }
>   inserted_by_day: { d: string; geo_rows: number; intel_rows: number; new_addresses: number }[]
>   window_by_last_seen_day: ({ d: string } & Omit<CoverageCounts, 'proxycheck_pct' | 'proxy_concluded_pct' | 'geo_agreed_pct'>)[]
>   definitions: Record<string, string>
> }
> ```
>
> Vendor display names everywhere on these pages: `ip2location_db11` → "IP2Location DB11", `proxycheck_io` →
> "proxycheck.io", `ipinfo_io` → "ipinfo.io", `ipwho_is` → "ipwho.is", `resolved` → "Our answer (resolved)".
> Any other id is shown as it arrives. "Our answer (resolved)" is always the last row and visually set apart
> (a subtle accent background and a small "combined" badge), because it is not a vendor.
>
> ## Page — Location Accuracy
>
> **Header:** "Location Accuracy". Subtitle: "How often each vendor's location matches the customer's own
> postal address, for `truth.addresses` customers who gave a full address."
>
> **An info callout directly under the header** with `truth.note`, and a second line: "Accuracy compares a
> vendor with the customer's address. Agreement, on the vendor overview, compares vendors with each other."
>
> **Pool switch** (segmented control, default **Same addresses**):
> - **Same addresses** → rows from `common_pool.vendors`, helper text `common_pool.description` and
>   "`common_pool.addresses` addresses". Use this for comparing vendors fairly.
> - **Every address each vendor answered** → rows from `vendors`, helper text "Each vendor on every truth address it
>   has an answer for; vendors with more answers are judged on more addresses."
>
> **Four stat tiles**, one per level: State, City, ZIP, State + city. Each tile shows the best vendor for that level
> (excluding "Our answer") with its percentage large, the vendor name under it, and "Our answer: N%" in muted text.
>
> **Grouped bar chart** (Recharts): one group per vendor, four bars per group for `state_pct`, `city_pct`,
> `zip_pct`, `state_city_pct`, y-axis 0–100%. Bar colours: one consistent colour per level across the app, with a
> legend. Tooltip: "`state_match` of `state_judged` addresses (N%)" for the hovered bar. `null` percentages draw no bar
> and show "no answers" in the tooltip.
>
> **Vendor table** under the chart, sortable, default sort by State + city descending with "Our answer" pinned last:
>
> | Column | Content |
> |---|---|
> | Vendor | display name |
> | Tested | `tested` |
> | Answered | `answered_pct`% |
> | State | `state_pct`% with "`state_match` / `state_judged`" in muted text underneath |
> | City | `city_pct`% with "`city_match` / `city_judged`" underneath |
> | ZIP | `zip_pct`% with "`zip_match` / `zip_judged`" underneath |
> | State + city | `state_city_pct`% with the counts underneath |
>
> Percentages get a small inline bar behind the number. The highest value in each column (excluding "Our answer")
> is bold.
>
> **By state** section below: header "By customer state". Controls: a **Vendor** select (all vendors plus "Our
> answer", default "Our answer"), a **Level** select (State, City, ZIP, State + city; default State), and a
> checkbox **Hide small samples** (default on) that hides rows where `small_sample` is true. Content:
> - A table with one row per state from `by_state` filtered to the chosen vendor: State, Tested, and the four
>   percentages with counts, sortable, default sort by Tested descending. Rows with `small_sample` show a muted
>   "small sample (< `min_state_sample`)" badge.
> - A **comparison table** beside it on wide screens (stacked on narrow): for the chosen Level, one row per state
>   and one column per vendor, each cell the percentage with a colour scale from low (neutral) to high (success tint);
>   empty cells show an em-dash. This answers "which vendor is best in which state".
>
> **Rules footnote** at the bottom in small muted text: the four `rules` strings, and "As of `as_of`".
>
> ## Page — Enrichment Coverage
>
> **Header:** "Enrichment Coverage". Subtitle: "How much of the last `window_days` days of IP addresses is enriched,
> and how many rows the tables gained each day."
>
> **Headline tiles** from `totals.last_30_days`:
> 1. **Addresses seen in the last `window_days` days** — `addresses`, with "since `window_start`" underneath.
> 2. **Answered by proxycheck.io** — `proxycheck_pct`% (`proxycheck_answered` of `addresses`).
> 3. **Proxy answer decided** — `proxy_concluded_pct`%, with "`proxy_no_conclusion` still undecided" underneath in warning
>    colour when above 0, success "all decided" when 0.
> 4. **Location agreed by two or more vendors** — `geo_agreed_pct`%, with "`geo_single_source` from one vendor only"
>    underneath.
>
> A muted line under the tiles with the same three percentages from `totals.all_addresses`: "All `addresses` addresses in
> the tables: N% answered by proxycheck.io, N% proxy decided, N% location agreed."
>
> **Chart 1 — "Last 30 days, by the day each address was last seen"**: stacked bars from `window_by_last_seen_day`, x-axis
> `d`, stacks `proxy_concluded` (success colour) and `proxy_no_conclusion` (warning colour), and a line on a second axis
> for the share answered by proxycheck.io (`proxycheck_answered / addresses`). Tooltip lists every field for that day
> with its `definitions` text.
>
> **Chart 2 — "Rows added per day"**: bars from `inserted_by_day` for `new_addresses`, plus a table under it with
> columns Day, New addresses, Location rows added (`geo_rows`), Risk rows added (`intel_rows`). In the table, days where
> `geo_rows` or `intel_rows` is above 100,000 get a muted "bulk load" badge (11 September was the first full load;
> 15 September was the first 77k proxycheck.io backfill).
>
> **Table "Last 30 days, day by day"** from `window_by_last_seen_day`: Day, Addresses, Answered by proxycheck.io,
> Proxy decided, Proxy undecided, Location agreed, Location one vendor, Location disagree or missing. Undecided above 0 in
> warning colour.
>
> **Definitions** at the bottom in a collapsible panel: every entry in `definitions`. "As of `as_of`".
