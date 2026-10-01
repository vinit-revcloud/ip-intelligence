# Lovable Prompt — IP Lookup (live)

Adds one page where anyone on the team types an IP address and gets, in one place: the answer to use
for location and for proxy, which vendors that answer rests on, every vendor's own row, and where the
address appears in our base tables. When our tables have no answer, or the vendors reach no
conclusion, the API asks proxycheck.io on the spot and the answer is added to the tables by the next
daily run.

No env changes. Same `IPINTEL_API_URL` and `IPINTEL_API_TOKEN`.

**Backend status (15 September 2026): live and tested** with a clean address, a disputed one, one
already answered by the proxycheck backfill, a repeat lookup (served from the saved answer, no second
charge) and an address never seen before. Paste everything below the line as one message.

---

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
> export type GeoStatus = 'agreed' | 'single_source' | 'vendors_disagree' | 'no_answer'
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
> `agreed` → success "Vendors agree", `single_source` → neutral "One source",
> `vendors_disagree` → warning "Vendors disagree", `no_answer` → neutral "No location".
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
> - The word is **Agreement**, never Accuracy. No revenue anywhere.
> - Never add an input for an API key.
> - Keep the existing visual style.
