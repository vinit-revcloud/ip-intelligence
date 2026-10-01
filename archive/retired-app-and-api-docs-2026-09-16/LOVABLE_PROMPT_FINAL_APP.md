# Lovable Prompt — Final IP Intelligence App (one message)

Everything the app needs, in one paste, built against the live API (15 September 2026). It replaces
pasting LOVABLE_PROMPT_PIPELINE_CONTROL.md, LOVABLE_PROMPT_IP_LOOKUP.md and
LOVABLE_PROMPT_REMOVE_BENCHMARK.md separately. No env changes: same `IPINTEL_API_URL` and
`IPINTEL_API_TOKEN`.

What the app ends up with:

| Navigation | Page | What it shows |
|---|---|---|
| IP Lookup (home) | IP Lookup | One address, or up to 1,000 at once with a CSV download: the answer to use, every vendor's answer, where it was seen, proxycheck.io asked on the spot when needed |
| | Resolved IPs | One row per address with filters; tab **proxycheck.io queue** for addresses from new base-table rows |
| Tables | The six table pages | ip_geo, ip_geo_analytics, ip_intelligence, ip_intelligence_analytics, both vendor overviews (live tables) |
| Reports | Location Accuracy · Enrichment Coverage | Each vendor's state / city / ZIP accuracy against customer addresses, overall and by state; how much of the last 30 days is enriched and rows added per day |
| Pipeline | Safety · Base Tables · Daily Jobs · proxycheck Budget | Emergency stop, the tables addresses come from, the daily runs and the unified-table refresh, the 80,000/day budget (50,000 enrichment, 30,000 lookups) |
| Vendor Sources | unchanged | |

Every endpoint below was tested on the live API. Paste everything below the line as one message.

---

> This is one change in four parts. Do them in order, and keep the app building after each part.
>
> # Part 1 — Remove the benchmark pages
>
> The API no longer serves benchmark sample data. Remove every page and component that depends on it,
> so the app shows only live pipeline data.
>
> ## Remove
>
> 1. Delete the routes and their files: `/findings`, `/recommendations`, and the Overview, Vendor
>    Comparison, Jobs & Sampling, Operations and Sources & Plans pages that read `getConsoleData`.
>    Delete their navigation entries.
> 2. Delete the server functions `getFindings`, `getSummary`, `lookupIp` **only if it calls `/ip/{ip}`**
>    (keep the new one that calls `/lookup/{ip}`), `getConsoleData`, `getRecommendations`, and any
>    function calling `/unified/geo`, `/unified/intelligence`, `/tables/ip-proxy` or
>    `/tables/ip-geo-legacy`. Delete `src/lib/api/findings.functions.ts` if nothing is left in it.
> 3. Delete from `src/lib/api/contract.ts` every type used only by the deleted pages (the findings,
>    summary, console and recommendations types). Keep every type the remaining pages use; let the
>    TypeScript compiler confirm nothing still references a deleted type.
> 4. Remove the print stylesheet added for the Recommendations page if no other page uses it.
>
> ## Keep and adjust
>
> - Make **IP Lookup** the home route (`/`), so the app opens on it.
> - Navigation, in this order: IP Lookup, Resolved IPs, Tables (the six table pages), Reports (Location
>   Accuracy, Enrichment Coverage — built in Part 4), Pipeline (Safety, Base Tables, Daily Jobs, proxycheck
>   Budget), Vendor Sources.
> - **Vendor overview – proxy** can legitimately be empty for a day or two: it is recalculated once
>   1,000 addresses have been asked of every running risk vendor. When `rows` is empty, show a calm
>   panel: "The proxy scorecard is being recalculated from the daily proxycheck.io backfill. It appears
>   after the next daily run." Never show it as an error.
> - **Vendor overview – location** now lists only the vendors the system runs: IP2Location DB11,
>   ipinfo.io, ipwho.is and proxycheck.io. Do not hardcode vendor rows; render whatever the API returns.
> - Any remaining text that mentions "benchmark", "sample", "485 IPs", "2,105 IPs", MaxMind, DB-IP,
>   GeoJS or "published ranges" as live sources: remove it.
>
> ## Check before finishing
>
> - The app builds with no TypeScript errors and no unused imports of deleted modules.
> - No request goes to `/findings`, `/summary`, `/console`, `/recommendations`, `/ip/`, `/unified/`,
>   `/tables/ip-proxy` or `/tables/ip-geo-legacy` (search the codebase for each string).
> - Every remaining page loads without an error panel.
>
> # Part 2 — IP Lookup and Resolved IPs
>
> Add a page **IP Lookup** as the first item of the navigation, and make the existing IP lookup card
> on other pages link to it instead of calling `/ip/{ip}`. Follow the conventions already used by
> Vendor Sources exactly: server functions, one contract file, API error strings shown to the user
> word for word.
>
> ## Endpoint
>
> ```
> GET /lookup/{ip}                 → Lookup
> GET /lookup/{ip}?refresh=true    → Lookup, and asks proxycheck.io again even if it answered before
> ```
>
> A lookup takes 2 to 3 seconds, and up to 8 seconds when proxycheck.io is asked. Show a skeleton of
> the result cards while it runs, never a blank page.
>
> ## Contract — add to `src/lib/api/contract.ts`
>
> ```ts
> export type GeoStatus = 'agreed' | 'nearby' | 'same_state' | 'single_source' | 'vendors_disagree' | 'no_answer'
> export type ProxyStatus =
>   | 'confirmed'                     // proxycheck.io answered and at least one other vendor agrees
>   | 'proxycheck_only'               // proxycheck.io is the only vendor that answered
>   | 'proxycheck_overrides'          // proxycheck.io answered and every other vendor said the opposite
>   | 'confirmed_by_published_range'  // flagged, and the address is in a published infrastructure range
>   | 'clean_by_vendors'              // no proxycheck.io answer, every vendor that answered says clean
>   | 'vendors_disagree'              // no proxycheck.io answer, vendors disagree
>   | 'flagged_unconfirmed'           // no proxycheck.io answer, flagged with nothing confirming it
>   | 'no_answer'
>
> export type ResolvedGeo = {
>   status: GeoStatus
>   state: string | null; city: string | null; zip_code: string | null
>   latitude: number | null; longitude: number | null; timezone: string | null
>   decided_by: string | null          // vendor id whose fields are shown
>   agreeing_vendors: string[]
>   vendors_answered: number
> }
>
> export type ResolvedProxy = {
>   status: ProxyStatus
>   flagged: boolean | null            // null means no conclusion
>   is_proxy: boolean | null; is_vpn: boolean | null; is_tor: boolean | null
>   is_datacenter: boolean | null; is_bot: boolean | null; is_compromised: boolean | null
>   is_scraper: boolean | null; is_anonymous: boolean | null
>   decided_by: string | null
>   agreeing_vendors: string[]
>   vendors_answered: number
>   isp: string | null; asn: string | null
> }
>
> export type VendorGeoRow = {
>   vendor: string; state: string | null; city: string | null; zip_code: string | null
>   latitude: number | null; longitude: number | null; timezone: string | null
>   created_at: string | null; updated_at: string | null
>   table: string                      // where the row came from, e.g. "ipintel_curated.ip_geo"
> }
>
> export type VendorProxyRow = {
>   vendor: string
>   is_proxy: boolean | null; is_vpn: boolean | null; is_tor: boolean | null
>   is_datacenter: boolean | null; is_bot: boolean | null; is_compromised: boolean | null
>   is_scraper: boolean | null; is_anonymous: boolean | null
>   isp: string | null; asn: string | null
>   created_at: string | null; updated_at: string | null
>   table: string
> }
>
> export type Occurrence = {
>   base_table: string                 // base table id, e.g. "tune_clicks"
>   source_table: string               // e.g. "raw.raw_tune_clicks"
>   first_seen: string | null          // YYYY-MM-DD
>   last_seen: string | null
>   days_seen: number
>   rows_seen: number
> }
>
> export type Lookup = {
>   ip: string
>   mode: 'shadow' | 'live'
>   public_address: boolean           // false for private, loopback and reserved ranges
>   found: boolean                     // any vendor row exists, from the tables or from proxycheck.io
>   seen_in_base_tables: boolean
>   occurrences: Occurrence[]
>   resolved: { geo: ResolvedGeo; proxy: ResolvedProxy }
>   vendors: { geo: VendorGeoRow[]; proxy: VendorProxyRow[] }
>   proxycheck: {
>     called: boolean
>     reason: string | null            // why it was or would have been asked, in plain English
>     reason_code: 'refresh' | 'new_address' | 'no_location' | 'no_answer' | 'vendors_disagree'
>                | 'flagged_unconfirmed' | 'location_disagree' | null
>     error?: string                   // e.g. paused, daily limit reached
>     risk_score?: number | null
>     type?: string | null
>     vendor_warning?: string
>     saved?: boolean
>   }
>   elapsed_ms: number
> }
> ```
>
> ## Server function
>
> `src/lib/api/lookup.functions.ts`: `lookupIp({ ip, refresh })`, a `createServerFn` that reads
> `IPINTEL_API_URL` and `IPINTEL_API_TOKEN` inside `.handler()`. Validate the input as a dotted-quad
> IPv4 address before calling; the API returns 400 for anything else, show its `error` exactly.
> Non-OK responses throw with the status code and the API's `error` string.
>
> ## Page
>
> **Header:** "IP Lookup". Subtitle: "Location and proxy answers for one address, from our IP tables,
> and from proxycheck.io when the tables have no conclusion."
>
> **Search bar** across the top: an input with placeholder "e.g. 152.232.101.74", a **Look up**
> button, and Enter submits. Keep the address in the URL as `?ip=` so a lookup can be shared as a
> link, and run it on page load when present. Keep the last 10 addresses looked up as clickable chips
> under the input (browser storage only).
>
> **1. Answer cards**, two side by side on wide screens, stacked on narrow ones.
>
> *Location card.* The resolved `state`, `city`, `zip_code` large; `timezone` and the coordinates
> underneath in muted text. A status pill:
> `agreed` → success "Vendors agree", `nearby` → success "Same area" (tooltip: "Vendors name the same state and
> places within 25 km"), `same_state` → neutral "Same state" (tooltip: "Vendors agree on the state; the cities are
> more than 25 km apart"), `single_source` → neutral "One source", `vendors_disagree` → warning "States differ",
> `no_answer` → neutral "No location". Render any other value as a neutral pill with the raw text.
> Then "Based on `decided_by`" and, when more than one, "Agreeing: `agreeing_vendors`" as small chips.
>
> *Proxy card.* One big verdict line: `flagged` true → danger "Flagged", false → success "Clean",
> null → neutral "No conclusion". Under it the flags that are true as danger chips (Proxy, VPN, Tor,
> Datacenter, Bot, Compromised, Scraper, Anonymous). ISP and ASN in muted text. A status pill:
> `confirmed` and `confirmed_by_published_range` → success "Confirmed",
> `proxycheck_only` → info "proxycheck.io only",
> `proxycheck_overrides` → warning "proxycheck.io disagrees with the other vendors",
> `clean_by_vendors` → success "Clean by every vendor",
> `vendors_disagree` → warning "Vendors disagree",
> `flagged_unconfirmed` → warning "Flagged, not confirmed",
> `no_answer` → neutral "No answer".
> Then "Decided by `decided_by`" and the agreeing vendors as chips. When `proxycheck.risk_score` is
> present show "Risk score N / 100".
>
> **2. proxycheck.io strip** directly under the cards, one line:
> - `called` true: info "Asked proxycheck.io just now: `reason`." If `saved` is false, add in warning
>   colour "The answer could not be saved and will not reach the tables."
> - `called` false and `error` present: warning with `error` exactly.
> - `called` false and no error: muted "Answered from our IP tables. proxycheck.io was not needed."
> - `vendor_warning` present: warning with its text.
> A small **Ask proxycheck.io again** text button at the end of the strip calls the lookup with
> `refresh=true`, after a confirmation: "This uses one proxycheck.io query from today's budget."
>
> **3. Where this address was seen.** A compact table from `occurrences`: base table (`source_table`
> in monospace), first seen, last seen, days seen, rows. If `seen_in_base_tables` is false: muted
> "Not seen in any base table. It was looked up directly."
>
> **4. Every vendor's answer**, two collapsible tables (open by default on wide screens):
> *Location* — vendor, state, city, zip, timezone, updated, and `table` as a muted monospace tooltip
> on the vendor name. *Proxy* — vendor, the eight flags, ISP, ASN, updated, same tooltip. Highlight the
> row of `decided_by` with a subtle accent border. Rows whose `table` starts with "proxycheck.io"
> get a small "fetched live" badge.
>
> **5. Footer line:** "Answered in `elapsed_ms` ms." When `public_address` is false, show above the
> cards a neutral panel: "This is a private or reserved address. No vendor has a location or proxy record
> for it, and proxycheck.io is not asked."
>
> **When proxycheck.io is asked.** Show this rule once, as a muted collapsible "When is proxycheck.io
> asked?" under the strip. It is the same rule the daily pipeline applies to new rows in the base tables:
> never for private or reserved addresses or when proxycheck.io has already answered; otherwise when the
> address is not in the IP tables, has no location, has no proxy answer, the proxy vendors disagree, a
> flag has nothing confirming it, or the location vendors disagree.
>
> ## Bulk lookup (a tab on the IP Lookup page)
>
> Add two tabs at the top of IP Lookup: **One address** (everything above) and **Many addresses**.
>
> ```
> POST /lookup   body { ips: string[], proxycheck?: boolean, refresh?: boolean, detail?: 'summary' | 'full' }
>                → BulkLookup
> ```
>
> ```ts
> export type BulkResult = {
>   ip: string
>   public_address: boolean
>   found: boolean
>   in_tables: boolean                 // was already in the IP tables before this request
>   seen_in_base_tables: boolean
>   first_seen: string | null; last_seen: string | null
>   resolved: { geo: ResolvedGeo; proxy: ResolvedProxy }
>   proxycheck: { called: boolean; reason_code: string | null; reason: string | null;
>                 risk_score?: number | null; type?: string | null; error?: string }
>   vendors?: { geo: VendorGeoRow[]; proxy: VendorProxyRow[] }   // only with detail: 'full'
>   occurrences?: Occurrence[]                                  // only with detail: 'full'
> }
> export type BulkLookup = {
>   count: number                      // distinct addresses answered
>   requested: number                  // addresses sent, duplicates included
>   proxycheck: { needed: number; asked: number; answered: number; queries_reserved: number;
>                 saved?: boolean; error: string | null; vendor_warning?: string }
>   results: BulkResult[]
>   elapsed_ms: number
> }
> ```
>
> Server function `lookupIps({ ips, proxycheck, refresh })` in `src/lib/api/lookup.functions.ts`, same
> conventions as `lookupIp`.
>
> **Input.** A large textarea: "Paste up to 1,000 IPv4 addresses, one per line or separated by commas or
> spaces." Parse on the client, drop blanks, merge duplicates, and show live counts under it: "N addresses
> · M duplicates removed · K not valid" with the invalid ones listed in danger colour (they are not sent).
> Also accept a `.csv` or `.txt` upload whose first column is the address. Disable the button above 1,000
> with "At most 1,000 per request. Split the list."
>
> **Options.** A switch **Ask proxycheck.io when needed** (default on). When off, helper text: "Answers come
> from the IP tables only. No proxycheck.io queries are used." A second switch **Ask proxycheck.io again
> for every address** (default off), which sends `refresh: true`; turning it on shows a warning "This
> uses about one query per address from today's budget."
>
> **Button.** "Look up N addresses". While it runs show a progress state "Looking up N addresses… up to
> a minute" (the API answers in one response; there is no partial progress to show).
>
> **Result summary strip.** Four figures: Addresses (`count`), Found in tables (`in_tables` true), Asked
> proxycheck.io (`proxycheck.asked`), Flagged (`resolved.proxy.flagged` true). Under it, when
> `proxycheck.error` is set, a warning panel with the text exactly. When `needed` > `asked` and there is
> no error, nothing else is needed.
>
> **Results table** (client-side sort and filter, 50 rows per page): IP (link to the One address tab with
> it), Location (city, state, zip), Location status pill, Proxy verdict (Flagged / Clean / No conclusion),
> Proxy status pill, true flags as chips, ISP, Risk, Asked proxycheck.io (Yes with the reason as a
> tooltip, or No), Last seen. Reuse the pill tones from the One address tab. Private addresses show a
> neutral "Private" pill in the Location column.
>
> **Download.** A **Download CSV** button that builds the CSV in the browser from `results` with columns
> ip, state, city, zip_code, latitude, longitude, timezone, geo_status, flagged, is_proxy, is_vpn, is_tor,
> is_datacenter, is_bot, proxy_status, isp, asn, risk_score, asked_proxycheck, reason_code, last_seen.
> Write `null` as an empty cell, never as false.
>
> ## Second page — Resolved IPs
>
> Add **Resolved IPs** directly under IP Lookup in the navigation. It lists
> `ipintel_curated.ip_resolved`: one row per address with the answer to use, the same answer the lookup
> shows. Use the same pagination contract as the existing table pages (`limit`, `next_cursor`,
> `total`, `truncated`).
>
> ```
> GET /tables/ip-resolved?limit=&cursor=&ip=&geo_status=&proxy_status=&flagged=&state=&city=&zip=
>                        &is_proxy=&is_vpn=&is_tor=&is_datacenter=&is_bot=&is_compromised=&is_scraper=&is_anonymous=
> GET /tables/ip-occurrences?ip=&base_table=
> GET /tables/proxycheck-queue?ip=&reason=&outcome=&limit=&cursor=
> ```
>
> Add a third tab **proxycheck.io queue** on this page: addresses from new base-table rows that needed
> proxycheck.io, with columns IP, reason (same wording as `reason_code` above), queued at, answered at,
> outcome (`answered`, `no_record_from_proxycheck`, or empty while waiting shown as an info pill
> "Waiting"). Filter by reason and outcome.
>
> ```ts
> export type ResolvedRow = {
>   ip_address: string
>   geo_status: GeoStatus
>   state: string | null; city: string | null; zip_code: string | null
>   latitude: number | null; longitude: number | null; timezone: string | null
>   geo_decided_by: string | null
>   geo_agreeing_vendors: string       // comma-separated vendor ids, '' when none
>   geo_vendors_answered: number
>   proxy_status: ProxyStatus
>   flagged: boolean | null
>   is_proxy: boolean | null; is_vpn: boolean | null; is_tor: boolean | null
>   is_datacenter: boolean | null; is_bot: boolean | null; is_compromised: boolean | null
>   is_scraper: boolean | null; is_anonymous: boolean | null
>   proxy_decided_by: string | null
>   proxy_agreeing_vendors: string     // comma-separated
>   proxy_vendors_answered: number
>   isp: string | null; asn: string | null
>   proxycheck_risk_score: number | null
>   seen_in_base_tables: string        // comma-separated source tables, '' when never seen
>   first_seen: string | null; last_seen: string | null
>   updated_at: string
> }
> ```
>
> Filter bar: IP (exact), Location status select, Proxy status select, Flagged (Yes / No / No
> conclusion → `true` / `false` / `null`), State, City. Changing a filter resets paging. Columns: IP (a
> link to IP Lookup `?ip=`), Location (city, state, zip), Location status pill, Proxy verdict (the same
> Flagged / Clean / No conclusion wording as the lookup), Proxy status pill, true flags as small chips,
> ISP, Last seen. Reuse the status pill tones defined for the lookup page.
>
> Above the table, a strip of counts for the current filter using `total`, and three quick filters as
> buttons: **No conclusion** (`proxy_status=flagged_unconfirmed`, then `vendors_disagree`, then
> `no_answer`, as a segmented control), **Confirmed flagged** (`proxy_status=confirmed&flagged=true`),
> **proxycheck.io disagrees** (`proxy_status=proxycheck_overrides`). Show the helper text "The daily
> proxycheck.io backfill resolves addresses with no conclusion first, 50,000 a day."
>
> ## Copy and behaviour rules
>
> - Every yes/no value has three states: `true` Yes, `false` No, `null` a muted em-dash meaning "no
>   answer". Never display `null` as No, and never show a flag chip for `null`.
> - Show vendor ids as names: ip2location_db11 "IP2Location DB11", ip2proxy_px12 "IP2Proxy PX12",
>   fraudlogix_tune "FraudLogix", proxycheck_io "proxycheck.io", ipinfo_io "ipinfo.io",
>   ipwho_is "ipwho.is", maxmind_geolite2 "MaxMind GeoLite2", dbip_combined "DB-IP",
>   geojs_io "GeoJS", authoritative_lists "Published ranges". Unknown ids are shown as they are.
> - **Agreement** means vendors compared with each other (vendor overview). **Accuracy** is used only on the Location
>   Accuracy page, where a vendor is compared with the customer's own postal address. Never swap the two. No revenue anywhere.
> - Never add an input for an API key.
> - Keep the existing visual style.
>
> # Part 3 — Pipeline pages
>
> Add four pages under a new **Pipeline** section in the navigation, in this order: **Safety**,
> **Base Tables**, **Daily Jobs** and **proxycheck Budget**. Keep the existing Vendor Sources page
> unchanged. Follow the
> conventions already used by Vendor Sources exactly: server functions, one contract file, API
> error strings shown to the user word for word, and `router.invalidate()` after every change.
>
> Nothing about a table, job or budget may be hardcoded in a component. Everything comes from the
> API.
>
> ## Two ideas the UI must keep separate
>
> - **Base tables** are where IP addresses *come from*. For example the website session table and
>   the ad-click table. The pipeline only ever **reads** them.
> - **Vendor sources** are who *answers questions* about an address. For example IP2Location or
>   proxycheck.io. They already have their own page.
>
> Never mix the two on one page and never call a base table a "source" in the copy. Call them
> "base tables" everywhere.
>
> ## Endpoints
>
> ```
> GET    /safety                           → Safety
> POST   /safety/pause                     → body { reason }  → Safety
> POST   /safety/resume                    → body { reason }  → Safety | 409 if a safety check is failing
>
> GET    /input-tables                     → { count, input_tables: InputTable[] }
> POST   /input-tables                     → create (201) | 400 invalid | 409 id exists
> GET    /input-tables/{id}                → InputTable
> PATCH  /input-tables/{id}                → partial update
> DELETE /input-tables/{id}                → remove from the list
> POST   /input-tables/{id}/validate       → run checks, returns Validation
>
> GET    /catalog/databases                → { databases: string[] }
> GET    /catalog/tables?database=X        → { tables: CatalogTable[] }
> GET    /catalog/columns?database=X&table=Y → { columns: CatalogColumn[] }
>
> GET    /jobs                             → { jobs: Job[] }
> PATCH  /jobs/{id}                        → partial update
> POST   /jobs/{id}/run                    → 202 { run_id, status } | 409 already running
> GET    /jobs/{id}/runs?limit=30          → { runs: Run[] }
>
> GET    /quota                            → Quota
> ```
>
> ## Contract — add to `src/lib/api/contract.ts`
>
> ```ts
> export type SafetyCheck = {
>   name: string                       // e.g. "Pipeline cannot write to any production table"
>   passed: boolean
>   checked_at: string
>   detail: string | null              // plain-English explanation, always present when failed
> }
>
> export type Safety = {
>   paused: boolean                    // true stops every job and live proxycheck call at once
>   paused_at: string | null
>   paused_reason: string | null
>   mode: 'shadow' | 'live'            // shadow: results written only to the project's own tables
>   production_write_access: 'none' | 'detected'
>   checks: SafetyCheck[]
>   last_audit_at: string | null       // when the pipeline last reviewed its own AWS activity
>   last_audit_findings: string[]      // empty means nothing outside the project was touched
> }
>
> export type ValidationStatus = 'valid' | 'invalid' | 'stale' | 'unchecked'
>
> export type Validation = {
>   status: ValidationStatus
>   checked_at: string | null
>   table_format: 'iceberg' | 'hive' | 'unknown'
>   write_pattern: 'append' | 'overwrite' | 'unknown'   // read from the table's own write log
>   last_write_at: string | null
>   rows_estimate: number | null
>   valid_ipv4_pct: number | null      // share of sampled values that are real IPv4 addresses
>   scan_gb_per_run: number | null     // what one daily run will read from this table
>   problems: string[]                 // plain-English reasons it is not valid, empty when valid
> }
>
> export type InputTable = {
>   id: string
>   database: string
>   table: string
>   ip_column: string
>   seen_at_column: string             // a date or timestamp column saying when the address was seen
>   enabled: boolean
>   note: string | null
>   validation: Validation
>   created_at: string
>   updated_at: string
> }
>
> export type CatalogTable  = { name: string; format: 'iceberg' | 'hive' | 'unknown' }
> export type CatalogColumn = { name: string; type: string }
>
> export type RunStatus = 'running' | 'succeeded' | 'failed' | 'skipped'
>
> export type Check = { name: string; passed: boolean; detail: string | null }
>
> export type Run = {
>   run_id: string
>   status: RunStatus
>   started_at: string
>   finished_at: string | null
>   message: string | null             // why it failed or was skipped, in plain English
>   new_ips: number | null
>   rows_inserted: number | null       // brand-new address and vendor pairs
>   rows_added: number | null          // a vendor's first answer for an address we already had
>   rows_updated: number | null        // an existing answer that changed
>   checks: Check[]
>   // free-sources job only: base-table addresses it queued for proxycheck.io, by reason
>   queued_for_proxycheck?: number
>   queued_by_reason?: Record<string, number>
>   // proxycheck job only
>   queue_waiting?: number             // queued addresses still waiting after this run
>   batches_done?: number
>   batches_total?: number
>   queries_spent?: number
> }
>
> export type Job = {
>   id: 'free-daily' | 'proxycheck-daily'
>   name: string
>   description: string
>   enabled: boolean
>   schedule_utc: string               // "HH:MM"
>   next_run_at: string | null
>   daily_budget?: number              // proxycheck job only
>   budget_cap?: number                // proxycheck job only: the most the server will accept
>   daily_limit?: number               // proxycheck job only: queries the plan allows per day (80,000)
>   topup_utc?: string | null          // proxycheck job only: when the late top-up run starts, "HH:MM" UTC
>   topup_keep?: number | null         // proxycheck job only: queries the top-up leaves for live lookups
>   live_reserve?: number              // proxycheck job only: queries kept free every day for API lookups (30,000)
>   publish_unified?: boolean          // proxycheck job only: refresh unified.ip_geo / unified.ip_intelligence after each run
>   last_run: Run | null
> }
>
> export type PublishedTable = {
>   table: string                      // "unified.ip_geo" or "unified.ip_intelligence"
>   rows: number | null
>   files: number | null
>   samples_checked: number | null
>   dry_run: boolean
> }
>
> export type PublishRun = Run & {
>   source_run: string | null          // the proxycheck run that triggered it; null when started by hand
>   published: PublishedTable[]
> }
>
> export type PublishStatus = {
>   tables: string[]                   // ["unified.ip_geo", "unified.ip_intelligence"]
>   last_published_at: string | null
>   last_run_id: string | null
>   last_tables: { table: string; rows: number | null }[]
>   runs: PublishRun[]                 // newest first; GET /publish?limit=10 (max 50)
> }
>
> export type Quota = {
>   plan_tier: string                  // e.g. "Free", "Pro"
>   daily_limit: number
>   reserved_today: number             // our own counter, updated the moment a query is reserved
>   provider_reported_today: number    // proxycheck's own counter, runs a few minutes behind
>   live_lookup_reserve: number        // held back so live lookups never run dry
>   batch_budget: number
>   key_status: 'valid' | 'invalid' | 'missing'
>   as_of: string
> }
> ```
>
> ## Server functions
>
> `src/lib/api/safety.functions.ts`: `getSafety`, `pausePipeline`, `resumePipeline`.
>
> `src/lib/api/inputTables.functions.ts`: `listInputTables`, `createInputTable`,
> `updateInputTable`, `deleteInputTable`, `validateInputTable`, `listDatabases`, `listTables`,
> `listColumns`.
>
> `src/lib/api/jobs.functions.ts`: `listJobs`, `updateJob`, `runJob`, `listRuns`, `getQuota`, `getPublish`
(`GET /publish?limit=10`, read only).
>
> Each is a `createServerFn` that reads `IPINTEL_API_URL` and `IPINTEL_API_TOKEN` **inside**
> `.handler()`. Non-OK responses throw with the status code and the API's `error` string, and the
> user sees that string exactly.
>
> **A 404 from any of these endpoints means that part of the backend has not shipped yet.** Do not
> show it as an error. Show a calm panel on that page reading "This part of the pipeline is not
> available yet." with the endpoint name underneath in small monospace text. Every other part of the
> page that does work must keep working.
>
> ## Page 1 — Safety
>
> **Header:** "Safety". Subtitle: "The pipeline only reads production data. This page proves it, and
> stops everything in one click."
>
> **A status banner across the top**, the first thing on the page:
>
> - When `production_write_access` is `none` and every check passed: a success banner reading
>   "Production is read-only for this pipeline. All safety checks passed."
> - When any check failed, or `production_write_access` is `detected`: a danger banner reading
>   "A safety check failed. Jobs are paused until it passes." followed by each failed check's
>   `detail`.
> - When `paused` is true: a warning banner reading "Paused by request", with `paused_reason` and
>   `paused_at` as relative time.
>
> **Emergency stop.** Beside the banner, a large button. When running it reads **Pause everything**
> in the danger style. Clicking it opens a dialog asking for a short reason, required, with the text
> "This stops both daily jobs and all live proxycheck calls immediately. Nothing is deleted. Data
> already written stays as it is." The confirm button reads **Pause everything now**. Call
> `POST /safety/pause`.
>
> When paused, the button reads **Resume** in the normal style, also with a required reason. If the
> API returns 409, show its message exactly and keep the pipeline paused: resuming is refused while a
> safety check is failing.
>
> **Mode.** A pill: `shadow` → info "Shadow mode", with the helper text "The daily jobs are updating
> the new tables, but this app still shows the earlier data while the results are checked." `live` →
> success "Live", with the helper text "This app shows the tables the daily jobs keep up to date."
>
> **Safety checks** as a list, one row each: a tick or cross, the check `name`, and `checked_at` as
> relative time. A failed check shows its `detail` underneath in danger colour.
>
> **Last activity review.** "The pipeline last reviewed its own AWS activity `last_audit_at`." If
> `last_audit_findings` is empty, show "Nothing outside the project was touched." in success colour.
> Otherwise list every finding in danger colour.
>
> Refresh this page every 30 seconds. Also show a small safety pill in the app header on every page:
> green "Read-only" when all checks pass, red "Check failed" otherwise, amber "Paused" when paused.
> Clicking it opens the Safety page.
>
> ## Page 2 — Base Tables
>
> **Header:** "Base Tables". Subtitle: "Tables IP addresses are collected from. The pipeline only
> reads these tables. It never writes to them."
>
> **Table of base tables**, one row each:
>
> | Column | Content |
> |---|---|
> | Name | `id`, with `note` underneath in muted text |
> | Table | `database.table` in monospace |
> | IP column | `ip_column` in monospace |
> | Seen-at column | `seen_at_column` in monospace |
> | Status | a pill from `validation.status` |
> | Last write | `validation.last_write_at` as relative time, e.g. "3 hours ago", with the exact UTC time on hover |
> | Enabled | a switch |
> | Actions | Validate, Edit, Remove |
>
> Status pill tones: `valid` → success "Valid", `invalid` → danger "Invalid", `stale` → warning
> "Needs re-check", `unchecked` → neutral "Not checked".
>
> Above the table, a summary strip with three numbers: **Enabled tables**, **Needs attention**
> (count of `invalid` plus `stale`), and **Scanned per daily run** (sum of `scan_gb_per_run` for
> enabled tables, shown as GB with one decimal).
>
> **Expanding a row** shows the full validation: table format, write pattern ("Adds rows only" for
> `append`, "Rewrites rows" for `overwrite`), rows estimate, valid IPv4 share, scan size, checked
> time, and every entry in `problems` as a bulleted list in danger colour.
>
> **Add base table** opens a form. Build it as three linked pickers, never free-text boxes, so a
> typo cannot reach the backend:
>
> 1. **Database**, a select filled from `GET /catalog/databases`.
> 2. **Table**, a select filled from `GET /catalog/tables?database=…` once a database is chosen.
>    Show the format as a small badge beside each option.
> 3. **IP column** and **Seen-at column**, two selects filled from `GET /catalog/columns`. Show each
>    column's type beside its name. In the IP column select, list `string` and `varchar` columns
>    first. In the seen-at select, list `date` and `timestamp` columns first.
>
> Plus **Name** (becomes `id`, lowercase letters, digits and underscores only, validated as the user
> types), **Note** (optional), and **Enabled** (default on).
>
> On save: `POST /input-tables`, then immediately `POST /input-tables/{id}/validate`, then show the
> validation result in the drawer before closing it. If validation comes back `invalid`, keep the
> drawer open and show `problems`, so the user can fix the column choice straight away.
>
> **Edit** uses the same form. After `PATCH`, if the response says the validation is stale, show a
> warning toast "Settings changed. Re-check this table before the next run." with a **Validate now**
> button in the toast.
>
> **Remove** opens a confirmation dialog: "Stop collecting addresses from `database.table`? Addresses
> already collected from it stay in the IP tables." Buttons: Cancel, Remove. If the API refuses
> because it is the last enabled table, show its error message exactly.
>
> **The enabled switch** calls `PATCH` with `{ enabled }`. Turning a table off shows a toast "Paused.
> The next daily run will skip this table."
>
> ## Page 3 — Daily Jobs
>
> **Header:** "Daily Jobs". Subtitle: "Two scheduled jobs keep the IP tables current, and every
> successful proxycheck run refreshes the two unified tables other APIs read. Times are UTC."
>
> One **card per job**, side by side on wide screens and stacked on narrow ones, both the same
> height. Each card shows:
>
> - `name` as the title and `description` beneath it
> - An enabled switch in the top right
> - Schedule: "Runs daily at `schedule_utc` UTC" and the next run as relative time
> - **Last run** block: a status pill, started time, duration, then the counts
> - **Checks** list: each check with a tick or a cross and its name. Any failed check shows its
>   `detail` underneath in danger colour
> - A **Run now** button and a **History** link
>
> Status pill tones: `succeeded` → success, `failed` → danger, `running` → info with a spinner,
> `skipped` → neutral. When `status` is `skipped` or `failed`, show `message` directly under the pill.
>
> **Counts on the free-sources card:** New addresses, Inserted, Added, Updated, and "Sent to
> proxycheck.io" (`queued_for_proxycheck`, with `queued_by_reason` in a tooltip). Put a small info icon
> beside "Added" with the tooltip "A vendor's first answer for an address we already had."
>
> **Counts on the proxycheck card:** Batches `batches_done` of `batches_total` as a progress bar,
> then Queries spent, Inserted, Added, Updated. When `queue_waiting` is above 0 show a warning line
> "`queue_waiting` addresses from the base tables are still waiting for proxycheck.io". Under the budget
> line add: "`daily_budget` queries a day enrich the tables (backfill plus new base-table addresses).
> `live_reserve` queries a day always stay free for API lookups. Plan limit: `daily_limit`." Under it, in muted
> text: "The `topup_utc` UTC top-up only finishes the enrichment budget if the morning run stopped early; it
> never uses the lookup queries."  Also show "Daily budget: `daily_budget` queries" with an **Edit** button.
>
> **Edit budget** opens a small dialog with a number input. The input's maximum is `budget_cap`, and
> the helper text reads "At most `budget_cap` a day, so live lookups always have queries left." The
> server enforces the same cap. If it refuses, show its message exactly.
>
> **Run now** on the free-sources job runs immediately after a one-line confirmation.
>
> **When the pipeline is paused** (from `GET /safety`), disable every Run now button and every
> enabled switch on this page, and show above the cards: "The pipeline is paused. Resume it on the
> Safety page." with a link.
>
> **Run now on the proxycheck job spends money**, so it needs a stronger confirmation. Before opening
> the dialog, call `GET /quota`. The dialog reads: "This can spend up to `min(daily_budget,
> daily_limit − reserved_today − live_lookup_reserve)` proxycheck queries today. Already reserved
> today: `reserved_today` of `daily_limit`." The confirm button says **Spend up to N queries** with
> the real number, never a generic "Confirm".
>
> A `409` from Run now means a run is already in progress. Show "Already running" as an info toast,
> not an error.
>
> While any job's last run is `running`, poll `GET /jobs` every 10 seconds and stop polling once no
> run is in progress.
>
> **History** opens a drawer with `GET /jobs/{id}/runs` as a table: started, duration, status, new
> addresses, inserted, added, updated, and queries spent for the proxycheck job. Clicking a row
> expands it to show that run's checks and message.
>
> **A third card, full width under the two job cards: "Unified tables".** Data from `GET /publish`
> (use `getPublish`; refresh every 60 seconds, and every 10 seconds while the newest run is `running`).
> This card is read only: no switch, no Run now, no edit.
>
> - Description: "After every successful proxycheck run, `unified.ip_geo` and `unified.ip_intelligence`
>   are refreshed from the enriched tables, so other teams' APIs read the same answers. The new copy is
>   checked before it replaces the old one, and the previous copy is kept for rollback. If any check
>   fails, the tables keep yesterday's data."
> - "Last refreshed `last_published_at`" as relative time (exact UTC on hover). `null` → "Not refreshed yet".
> - One row per entry in `last_tables`: the table name in monospace and `rows` with thousands separators.
> - **Newest run** (`runs[0]`): status pill with the same tones as the job cards, started time, duration,
>   "Started after proxycheck run `source_run`" (or "Started by hand" when null), and its checks list
>   with ticks and crosses; failed checks show `detail` in danger colour, and `failed` shows `message`.
> - Runs where every entry in `published` has `dry_run: true` get a neutral "Test run — tables not changed"
>   pill and never count as the last refresh.
> - If `runs[0].status` is `failed`, show a warning line: "The unified tables still hold the previous
>   copy. The next proxycheck run will try again."
> - If `last_published_at` is more than 36 hours old while the pipeline is not paused, show a warning:
>   "The unified tables have not been refreshed for over a day."
> - A **History** link opens a drawer listing `runs`: started, duration, status, rows per table.
>
> ## Page 4 — proxycheck Budget
>
> **Header:** "proxycheck Budget". Subtitle: "Queries are reserved before they are sent, so the key
> cannot be used up by accident."
>
> **Key status** at the top as a pill: `valid` → success "Key working", `invalid` → danger "Key
> rejected", `missing` → danger "No key set". Beside it, the plan tier.
>
> When the key is `invalid` or `missing`, show a danger panel: "The proxycheck key is stored in AWS
> Secrets Manager under ipintel/proxycheck-paid. Update it there. For security this page never accepts
> or displays the key." **Never add an input for the API key anywhere in the app.**
>
> **Today's usage** as one horizontal stacked bar drawn to scale against `daily_limit`:
>
> - Reserved today, `reserved_today`, in the accent colour
> - Held back for API lookups, `live_lookup_reserve`, in a warning tint
> - Still available, the remainder, as the empty track
>
> Label the scale with 0 and `daily_limit`. Under the bar, three figures: Reserved today, Held back
> for API lookups, Still available. Under them, a muted line: "Split: `batch_budget` a day for enrichment,
> `live_lookup_reserve` a day for API lookups."
>
> Below that, a muted line: "proxycheck's own counter reads `provider_reported_today`. It runs a few
> minutes behind, so our counter is the one the jobs trust." If `provider_reported_today` is more than
> 5% above `reserved_today`, turn that line into a warning: "proxycheck reports more use than we
> reserved. Something outside this pipeline may be using the key."
>
> Show "As of `as_of`" at the bottom and refresh the page data every 60 seconds.
>
> ## Copy and behaviour rules
>
> - Every yes/no value from the API has three states. `true` is Yes, `false` is No, and `null` is a
>   muted em-dash meaning "no answer". Never display `null` as No.
> - **Agreement** means vendors compared with each other (vendor overview). **Accuracy** is used only on the Location
>   Accuracy page, where a vendor is compared with the customer's own postal address. Never swap the two.
> - There is no revenue anywhere in this product. Do not add any.
> - Show times as relative with the exact UTC time on hover, and label every schedule as UTC.
> - Every destructive or money-spending action names exactly what will happen in its button text.
> - Keep the existing visual style. Do not restyle pages that are not listed here.
>
> # Part 4 — Location Accuracy and Enrichment Coverage
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
>   geo_nearby: number                  // same state, two vendors within 25 km
>   geo_same_state: number              // same state, cities more than 25 km apart
>   geo_disagree_or_missing: number     // no two vendors name the same state, or no location
>   proxycheck_pct: number | null
>   proxy_concluded_pct: number | null
>   geo_agreed_pct: number | null
>   geo_state_agreed_pct: number | null // agreed + nearby + same_state
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
> 4. **Location agreed by two or more vendors** — `geo_agreed_pct`%, with "State agreed: `geo_state_agreed_pct`%"
>    and "`geo_disagree_or_missing` where states differ" underneath.
>
> Under the tiles, a thin 100% stacked bar for the last 30 days' location status: agreed (success), nearby (success,
> lighter), same_state (neutral), states differ or missing (warning), one source (muted), with a legend and counts.
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
