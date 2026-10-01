# Lovable Prompt — IP Intelligence App v2 (one message)

Replaces `archive/retired-app-and-api-docs-2026-09-16/LOVABLE_PROMPT_FINAL_APP.md`. Written 17 Sep 2026.

**What changed since the last version**
- Our own API (`IPINTEL_API_URL`, `ipintel-findings-api`) is retired and refuses every call, so every page that called it has to go.
- Live IP lookup now goes through the teammate's **IP Lookup API** (`GET /v1/ip/{ip}`).
- Everything else is a **read-only snapshot**: JSON files in `public/data/`, rebuilt by `build/pipeline/analysis/export_app_data.py`.

## Before you paste

1. From `build/pipeline`, run `python analysis/export_app_data.py`. It writes `app-data/*.json` in the project folder.
2. Copy every file in `app-data/` into the Lovable project as `public/data/` (GitHub sync, or upload in Lovable).
3. In Lovable → Project settings → Secrets:
   - add `IP_LOOKUP_API_URL` = `https://9w07dr3qq2.execute-api.us-west-2.amazonaws.com`;
   - add `IP_LOOKUP_API_TOKEN` = the Bearer token from your teammate. Never paste the token into the chat or the code.
   - After the app works, delete `IPINTEL_API_URL` and `IPINTEL_API_TOKEN`.
4. To refresh the snapshot later: run steps 1 and 2 again. No prompt is needed.

**What the app ends up with**

| Navigation | Page | Data |
|---|---|---|
| IP Lookup (home) | IP Lookup: one address, or up to 200 at once | Teammate API, live |
| Analysis | Bot / Not bot (every session IP) | `session_ip_labels.json` |
| | Lead-IP Vendor Evaluation | `lead_ip_analysis.json`, `lead_ips.json` |
| Reports | Location Accuracy | `geo_accuracy.json` |
| | Enrichment Coverage | `coverage.json`, `proxy_coverage.json` |
| | Vendor Scorecards | `vendor_overview_geo.json`, `vendor_overview_proxy.json` |

Paste everything below the line as one message.

---

> This is one change in three parts. Do them in order, and keep the app building after each part.
>
> # Part 1 — Remove everything that uses the retired API
>
> The API behind `IPINTEL_API_URL` is permanently switched off. Every request to it fails.
>
> 1. Delete every page, route, component and server function that reads `IPINTEL_API_URL` or `IPINTEL_API_TOKEN`. That includes:
>    - IP Lookup (old) and Resolved IPs;
>    - the six table pages;
>    - Location Accuracy and Enrichment Coverage (old versions; rebuilt in Part 3);
>    - Safety, Base Tables, Daily Jobs and proxycheck Budget;
>    - Vendor Sources.
>
>    Remove their navigation entries.
> 2. Delete every type in `src/lib/api/contract.ts` that only those pages used. Let the TypeScript compiler confirm nothing still references a deleted type.
> 3. Search the codebase for `IPINTEL_API`, `/lookup/`, `/pipeline`, `/jobs`, `/budget`, `/tables/`, `/accuracy/`, `/coverage` and `/sources`. Nothing may remain.
> 4. Remove any text that describes pipeline controls, an emergency stop, a lookup budget or "30,000 lookups". The app no longer controls anything.
>
> # Part 2 — IP Lookup (teammate API)
>
> ## Server function
>
> Create `src/lib/api/iplookup.functions.ts` with `lookupIp(ip: string)`.
> - Read `IP_LOOKUP_API_URL` and `IP_LOOKUP_API_TOKEN` inside the handler (server side only).
> - Call `GET {IP_LOOKUP_API_URL}/v1/ip/{ip}` with the header `Authorization: Bearer {IP_LOOKUP_API_TOKEN}`, with a 20-second timeout.
> - Return the parsed JSON body and the HTTP status.
> - Never send the token to the browser. Never log it.
>
> Validate the address in the browser before calling: dotted IPv4, four numbers 0–255. Otherwise show "Enter a valid IPv4 address" and send nothing.
>
> ## Contract — add to `src/lib/api/contract.ts`
>
> ```ts
> export type LookupGeo = {
>   source: string            // e.g. "ip2location_db11"
>   lookup: string            // e.g. "unified.ip_geo" or the range database
>   state: string | null; city: string | null; zip: string | null
>   lat: number | null; lng: number | null; timezone: string | null
> }
> export type LookupRisk = {
>   source: string            // "fraudlogix_tune" | "authoritative_lists" | "ip2proxy_px12" | "proxycheck_io"
>   lookup: string            // "unified.ip_intelligence" or "proxycheck.api"
>   is_proxy: boolean | null; is_vpn: boolean | null; is_tor: boolean | null
>   is_datacenter: boolean | null; is_compromised: boolean | null
>   is_scraper: boolean | null; is_anonymous: boolean | null
>   isp: string | null; asn: string | null
>   risk: number | null; confidence: number | null
> }
> export type LookupResult = { 'ip-address': string; 'ip-geolocation': LookupGeo; 'ip-risk': LookupRisk }
> export type LookupError = { error: 'unauthorized' | 'invalid_ipv4' | 'not_found' | 'lookup_failed' | string; message?: string; ip?: string }
> ```
>
> ## Page (route `/`, first navigation item)
>
> - **Header:** "IP Lookup". **Subtitle:** "Location and proxy / VPN / bot signals for one IPv4 address, from the company IP tables."
> - **Input and button.** A lookup takes a few seconds (longer when proxycheck.io is asked live). Show skeleton cards while it runs, never a blank page.
> - **Two cards side by side** (stacked on narrow screens):
>   - **Location:** state, city, ZIP, a small static map pin if `lat`/`lng` are present (otherwise just the coordinates), timezone. Footer: "Source: {source} · {lookup}".
>   - **Risk:**
>     - a verdict chip at the top:
>       - "Flagged" (warning) when any of is_proxy, is_vpn, is_tor, is_datacenter, is_compromised, is_scraper or is_anonymous is `true`;
>       - "Clean" (success) when all non-null ones are `false`;
>       - "Unknown" (muted) when all are `null`.
>     - A row per signal: true = warning badge, false = "No", null = em-dash with the tooltip "The source did not supply this field".
>     - ISP, ASN, risk score (0–100 bar) and confidence.
>     - Footer: "Source: {source} · {lookup}", with a "live" badge when `lookup` is `proxycheck.api`.
> - **Errors:** show the API's `error` value in the message.
>   - 401: "The lookup token is missing or wrong. Check IP_LOOKUP_API_TOKEN."
>   - 400: "Not a valid IPv4 address."
>   - 502: "Lookup failed" plus `message`, with a Retry button.
>   - Timeout: "The lookup service did not answer in 20 seconds." with Retry.
> - **"In our analysis" panel** under the cards, only when the address appears in `public/data/lead_ips.json`: its MoM label, revenue, lead stage, experiment ids, and a link to the Lead-IP Vendor Evaluation page filtered to that IP.
> - **Bulk tab:**
>   - A textarea for up to 200 addresses, one per line; deduplicate and validate.
>   - Call `lookupIp` 4 at a time and show progress "n of N".
>   - Results table: IP, State, City, ZIP, Geo source, Verdict, Proxy, VPN, Tor, Datacenter, ISP, Risk, Risk source, Error.
>   - A "Download CSV" button, and a Cancel button that stops sending further requests.
>
> # Part 3 — Snapshot pages (read `public/data/*.json`)
>
> ## Shared rules
>
> - Load each file with `fetch('/data/<file>')` and cache it for the session.
> - A 404 shows the calm panel "This report has not been exported yet. Run export_app_data.py and copy app-data/ into public/data/." Never show it as an error.
> - Every page shows "Snapshot as of {as_of}" in the header, in muted text.
> - `public/data/manifest.json` lists the files and the export time. Show "Data snapshot: {as_of}" in the app footer.
> - Vendor display names:
>
>   | Id | Display name |
>   |---|---|
>   | `fraudlogix_tune` | FraudLogix |
>   | `ip2proxy_px12` | IP2Proxy PX12 |
>   | `proxycheck_io` | proxycheck.io |
>   | `ip2location_db11` | IP2Location DB11 |
>   | `ipinfo_io` | ipinfo.io |
>   | `ipwho_is` | ipwho.is |
>   | `authoritative_lists` | Published lists |
>   | `session_summary` | Session table flag |
>   | `session_summary_bot_click` | Session bot-click |
>   | `resolved_answer` / `resolved` | Our combined answer |
>
>   Any other id is shown as it arrives.
> - Percent fields end in `_pct` and are already 0–100, or `null` → show an em-dash.
> - Use Recharts. Keep the existing theme and components.
>
> ## Page — Bot / Not bot (`/analysis/bot-labels`, file `session_ip_labels.json`)
>
> ```ts
> type Scorecard = { source: string; session_ips: number; answered: number; coverage_pct: number | null; flagged: number
>   TP: number; FP: number; TN: number; FN: number; no_answer: number
>   FPR_pct: number | null; accuracy_pct: number | null; precision_pct: number | null; recall_pct: number | null }
> type Evidence = { label_detail: 'real_person' | 'lead_no_revenue' | 'no_lead'; ips: number
>   with_proxy_answer: number; with_proxy_answer_pct: number
>   bot_click_session_ips: number; bot_click_session_pct: number
>   resolved_flagged_ips: number; resolved_flagged_pct: number
>   fraudlogix_bot_ips: number; fraudlogix_bot_pct: number
>   proxycheck_high_risk_ips: number; proxycheck_high_risk_pct: number
>   in_experiment_ips: number; in_experiment_pct: number }
> type Experiment = { experiment_id: string; ips: number; real_person: number; lead_no_revenue: number; no_lead: number
>   bot_click_ips: number; resolved_flagged_ips: number; with_proxy_answer: number
>   bot_pct_mom: number; flagged_pct: number; proxy_answer_pct: number }
> type SessionIpLabels = { as_of: string; window: [string, string]; session_ips: number; sessions: number
>   labels: { real_person: number; lead_no_revenue: number; no_lead: number }; bot_mom: number
>   with_proxy_answer: number; with_proxycheck: number
>   evidence: Evidence[]; scorecard: Scorecard[]; per_experiment: Experiment[] }
> ```
>
> - **Header:** "Bot / Not bot". **Subtitle:** "Every public IP with a website session between {window[0]} and {window[1]}, labelled by what its sessions produced."
> - **Rule callout (always visible):**
>   - "**Real person** = at least one lead with expected revenue above 0.
>   - **Bot** = everything else. Blank revenue counts as 0.
>   - Leads are joined on `utm_content = session_id`, with the lead on or after the session."
> - **Tiles:**
>   - Session IPs (`session_ips`), with `sessions` sessions underneath.
>   - Real person (`labels.real_person`).
>   - Bot (`bot_mom`), split underneath into "lead, no revenue: {lead_no_revenue} · no lead: {no_lead}".
>   - With a proxy answer: `with_proxy_answer` / `session_ips` %, with "proxycheck.io: {with_proxycheck}" underneath.
> - **Evidence table** from `evidence`: one row per group, columns ending in `_pct` as percentages with counts underneath. Group names: Real person, Lead without revenue, No lead.
>   - Add a note under the table: "Vendor flags are **higher** for real people than for no-lead IPs. A proxy / VPN flag alone does not mean bot; many real customers use mobile carriers, VPNs and corporate networks."
> - **Vendor scorecard** from `scorecard`. Bot is the positive class.
>   - Columns: Source, Coverage %, Flagged, TP, FP, TN, FN, FPR %, Precision %, Recall %, Accuracy %.
>   - Highlight FPR (lower is better) with a colour scale.
>   - Help tooltip on FPR: "Share of real people the source flagged."
> - **Per experiment** from `per_experiment`:
>   - Sortable table: Experiment, IPs, Real person, Lead no revenue, No lead, Bot % (MoM), Bot-click IPs, Flagged %, Proxy answer %.
>   - A bar chart of the top 15 experiments by IPs, stacked by real_person / lead_no_revenue / no_lead.
> - **Footer:** "Per-IP labels: analysis/session-ip-bot-labels-2026-09/session_ip_labels.csv (not in the app, too large)."
>
> ## Page — Lead-IP Vendor Evaluation (`/analysis/lead-ips`, files `lead_ip_analysis.json`, `lead_ips.json`)
>
> ```ts
> type LeadIpAnalysis = { as_of: string; window: [string, string]; lead_ips: number; leads: number
>   real_person_ips: number; bot_ips: number; blank_revenue_ips: number
>   scorecard_any_flag: VendorCard[]; scorecard_bot_flag_only: VendorCard[]
>   lead_category_signal: Record<string, string | number | null>[]   // lead_category, ips, revenue_ips, revenue_pct, <vendor>_flag_pct...
>   lead_stage_signal: Record<string, string | number | null>[]      // lead_category, furthest_stage, ips, revenue_ips, revenue_pct, <vendor>_flag_pct, <vendor>_answered...
>   fraudlogix_wrong_flags: { ip: string; revenue: number; lead_category: string | null; furthest_stage: string | null
>     fraud_reason: string | null; is_proxy: boolean | null; is_vpn: boolean | null; is_bot: boolean | null }[]
>   fraudlogix_wrong_by_reason: Record<string, number> }
> type VendorCard = { vendor: string; lead_ips: number; answered: number; coverage_pct: number | null; flagged: number
>   TP: number; FP: number; TN: number; FN: number; no_answer: number
>   FPR_pct: number | null; accuracy_pct: number | null; precision_pct: number | null; recall_pct: number | null }
> type LeadIpRow = { ip: string; label: 'real_person' | 'bot'; revenue: number; leads: number; blank_revenue_leads: number
>   lead_category: string | null; furthest_stage: string | null; sessions: number; bot_click_sessions: number
>   experiment_ids: string | null
>   risk: Record<string, Record<string, string | number | boolean | null>>   // vendor -> its fields
>   geo: Record<string, { state: string | null; city: string | null; zip_code: string | null; latitude: number | null
>                         longitude: number | null; timezone: string | null; updated_at: string | null }>
>   resolved: { geo_status: string; state: string | null; city: string | null; zip_code: string | null
>               geo_decided_by: string | null; proxy_status: string; flagged: boolean | null
>               proxy_decided_by: string | null; isp: string | null; proxycheck_risk_score: number | null } | null
>   outcome?: Record<string, 'TP' | 'FP' | 'TN' | 'FN' | 'no_answer'> }
> type LeadIps = { as_of: string; window: [string, string]; rows: LeadIpRow[] }
> ```
>
> - **Header:** "Lead-IP Vendor Evaluation". **Subtitle:** "{lead_ips} IPs that produced {leads} leads between {window[0]} and {window[1]}. Real person = revenue above 0."
> - **Tiles:**
>   - Lead IPs;
>   - Real person;
>   - Bot (MoM), with "{blank_revenue_ips} of them have blank revenue" underneath in warning colour.
>   - Add a note: "Open question: is blank revenue 0 or unknown?"
> - **Scorecard** with a switch between "Any risk flag" (`scorecard_any_flag`, default) and "Bot flag only" (`scorecard_bot_flag_only`). Same columns as on the Bot / Not bot page.
>   - A bar chart of FPR by vendor.
>   - When `coverage_pct` < 5, add the muted badge "too few answers to judge".
> - **By lead category** (`lead_category_signal`) and **By lead stage** (`lead_stage_signal`): tables.
>   - Render every column that arrives, with `_pct` as percentages.
>   - Order categories as closed, listing, meeting, intro_qualified, below_intro, then anything else.
> - **FraudLogix wrong flags:**
>   - A small bar chart of `fraudlogix_wrong_by_reason`.
>   - A searchable table of `fraudlogix_wrong_flags`: real customers FraudLogix flagged.
> - **Per-IP explorer** from `lead_ips.json`:
>   - Filters: label, lead category, vendor outcome, "any vendor flagged", experiment id, IP search. Supports `?ip=` in the URL.
>   - Paged table: IP, Label, Revenue, Category, Stage, Sessions, Bot-click sessions, FraudLogix / IP2Proxy / proxycheck.io / Session outcome (TP/FP/TN/FN chips; FP in warning colour), Our proxy status, Our state/city.
>   - Clicking a row opens a side panel with:
>     - every vendor's risk fields (one column per vendor);
>     - every vendor's location (one row per vendor, with "our answer" last and `geo_decided_by`);
>     - a "Look up live" button that opens IP Lookup with that IP.
>   - A "Download CSV" button for the filtered rows.
>
> ## Page — Location Accuracy (`/reports/location-accuracy`, file `geo_accuracy.json`)
>
> Rebuild the earlier Location Accuracy page exactly as before (pool switch, four tiles, grouped bar chart, vendor table, by-state tables, rules footnote). The only change: it now reads this file instead of `/accuracy/geo`. The shape is unchanged:
>
> ```ts
> type AccuracyRow = { vendor: string; tested: number; answered: number; answered_pct: number | null
>   state_judged: number; state_match: number; state_pct: number | null
>   city_judged: number; city_match: number; city_pct: number | null
>   zip_judged: number; zip_match: number; zip_pct: number | null
>   state_city_judged: number; state_city_match: number; state_city_pct: number | null }
> type GeoAccuracy = { as_of: string; truth: { source: string; addresses: number; note: string }
>   rules: { state: string; city: string; zip: string; state_city: string }; min_state_sample: number
>   vendors: (AccuracyRow & { pool: 'all' })[]
>   common_pool: { description: string; addresses: number; vendors: (AccuracyRow & { pool: 'common' })[] }
>   by_state: (AccuracyRow & { state: string; small_sample: boolean })[] }
> ```
>
> - "resolved" is "Our combined answer", always the last row, visually set apart.
> - Default pool: "Same addresses" (`common_pool`).
>
> ## Page — Enrichment Coverage (`/reports/coverage`, files `coverage.json`, `proxy_coverage.json`)
>
> Rebuild the earlier Enrichment Coverage page exactly as before. The shape is unchanged:
>
> ```ts
> type CoverageCounts = { addresses: number; proxycheck_answered: number; proxy_concluded: number; proxy_no_conclusion: number
>   geo_agreed: number; geo_single_source: number; geo_nearby: number; geo_same_state: number; geo_disagree_or_missing: number
>   proxycheck_pct: number | null; proxy_concluded_pct: number | null; geo_agreed_pct: number | null; geo_state_agreed_pct: number | null }
> type Coverage = { as_of: string; window_days: number; window_start: string
>   totals: { last_30_days: CoverageCounts; all_addresses: CoverageCounts }
>   inserted_by_day: { d: string; geo_rows: number; intel_rows: number; new_addresses: number }[]
>   window_by_last_seen_day: ({ d: string } & Omit<CoverageCounts, 'proxycheck_pct' | 'proxy_concluded_pct' | 'geo_agreed_pct'>)[]
>   definitions: Record<string, string> }
> type ProxyCoverage = { as_of: string; addresses: number; with_proxy_answer: number; with_proxycheck: number }
> ```
>
> The page contains:
> - **Headline tiles** from `totals.last_30_days`: addresses, proxycheck.io %, proxy decided %, location agreed %. Under the agreed tile: state agreed % and "states differ".
> - A 100% stacked location-status bar: agreed, nearby, same_state, states differ or missing, one source.
> - A muted all-addresses line.
> - **Chart 1:** stacked by last-seen day.
> - **Chart 2:** rows added per day, with a table. Days above 100,000 rows get a "bulk load" badge.
> - **Day-by-day table.**
> - **Collapsible definitions.**
> - **New "Every address" panel** from `proxy_coverage.json`:
>   - "{with_proxy_answer} of {addresses} addresses have at least one proxy answer (N%)"
>   - "{with_proxycheck} answered by proxycheck.io (N%)"
>   - A progress bar.
>   - Caption: "The daily backfill spends about 78,000 proxycheck.io queries a day, in this order: experiment IPs, IPs seen in the last 30 days, IPs seen in the last 90 days, then everything else."
>
> ## Page — Vendor Scorecards (`/reports/vendor-scorecards`, files `vendor_overview_geo.json`, `vendor_overview_proxy.json`)
>
> Each file is `{ as_of: string; table: string; rows: Record<string, string | number | boolean | null>[] }`.
> - Two tabs: **Location** and **Proxy**.
> - Render a sortable table with one column per key of the first row, in the order they arrive. Humanise the headers: snake_case → words.
> - Numbers get thousands separators. Keys ending in `_pct` or `_rate` show as percentages when the value is ≤ 1 (× 100) or already 0–100.
> - Under each table: "Mirrors {table}. Snapshot as of {as_of}."
> - If `rows` is empty, show "The scorecard is being recalculated; it appears in the next snapshot."
>
> # Check before finishing
>
> - The app builds with no TypeScript errors.
> - Searching for `IPINTEL_API` finds nothing.
> - The token appears only in server code, read from `IP_LOOKUP_API_TOKEN`.
> - Every page loads, including when a `public/data` file is missing (calm panel).
> - IP Lookup works for `107.127.28.97`, shows the 400 message for `not-an-ip`, and the bulk tab downloads a CSV.

## Addendum (17 Sep): report data without manual uploads

Already built in the app: the **Data Upload** page, which stores the 9 files privately. Reports read the uploaded copy first, then the bundled files.

When the AWS admin has created the read-only key (`ADMIN_DELETION_STEPS.md`, Request 2):
1. Add the Lovable secrets `APP_S3_ACCESS_KEY_ID` and `APP_S3_SECRET_ACCESS_KEY`.
2. Paste:

> Add a server function `getSnapshot(name)` that reads `ip-intelligence/serving/app/<name>` from S3 bucket `datalake-landingzone-221490242148-us-west-2` (region `us-west-2`) with the AWS SDK, using the secrets `APP_S3_ACCESS_KEY_ID` and `APP_S3_SECRET_ACCESS_KEY` read inside the handler. Allow only the 9 snapshot file names. The report loader tries, in order: `getSnapshot` → the Data Upload copy → the bundled file. Cache each file for 15 minutes. Keep the Data Upload page as a manual backup.

## Addendum 2 (17 Sep): Bot verdict section

**Before pasting:** upload the new `session_ip_labels.json` on the Data Upload page. It now carries a `verdict` block; the file name is unchanged.

> On the **Bot / Not bot** page, add a section **"Bot verdict (evidence-based)"** above the MoM label tiles. It reads `verdict` from `session_ip_labels.json`; if `verdict` is missing or null, hide the section.
>
> ```ts
> type SignalTest = { signal: string; ips_hit: number; paying_hit: number; paying_ips: number; FPR_pct: number
>   no_lead_hit: number; no_lead_hit_pct: number; testable: boolean; points_away_from_humans: boolean; strength: 'strong' | 'weak' }
> type Verdict = { window: [string, string]; session_ips: number; paying_ips: number; max_fpr_pct: number
>   strong_signals: string[]; weak_signals: string[]
>   verdicts: { human: number; likely_human: number; unknown: number; suspicious: number; bot: number }
>   verdict_pct: Record<string, number>; combined_rule_fpr_on_paying_pct: number
>   signal_test: SignalTest[]
>   by_mom_label: Record<string, string | number>[]      // mom_label, ips, <verdict>, <verdict>_pct
>   bot_reasons: { signal: string; bot_ips: number }[]
>   per_experiment: Record<string, string | number>[] }  // experiment_id, ips, <verdict>..., bot_pct, bot_or_suspicious_pct, human_or_likely_pct
> ```
>
> - **Callout:**
>   - "proxycheck.io has no bot field, and proxy/VPN flags hit many paying customers. This verdict combines vendor network signals with session behaviour, and every bot rule is tested on the {paying_ips} IPs that produced revenue."
>   - "A signal counts as strong only if it flags at most {max_fpr_pct}% of paying IPs and fires more often on IPs without leads."
> - **Five tiles** in this order and colour: human (success), likely human (success, lighter), unknown (muted), suspicious (warning), bot (danger). Each shows the count and `verdict_pct`. Under the bot tile: "Wrongly flags {combined_rule_fpr_on_paying_pct}% of paying IPs".
> - **A 100% stacked bar** of the five verdicts.
> - **"Signal test" table** from `signal_test`: Signal (humanised), IPs hit, Paying IPs hit with FPR %, No-lead hit %, Strength chip (strong = danger, weak = muted). Tooltip on weak rows:
>   - "can't be tested" when `testable` is false;
>   - "common on shared networks" when `points_away_from_humans` is false;
>   - otherwise "flags too many paying customers".
> - **"Why IPs are called bot"**: a bar chart from `bot_reasons`.
> - **"Verdict vs MoM label"** table from `by_mom_label`, with a note: "No revenue is not the same as bot: most IPs without revenue show no hard bot evidence."
> - **"Per experiment"** sortable table from `verdict.per_experiment`: Experiment, IPs, Human + likely %, Unknown, Suspicious, Bot, Bot %. Default sort: IPs, descending. Highlight Bot % ≥ 2 in the warning colour.
> - **Signal display names:**
>
>   | Id | Display name |
>   |---|---|
>   | `ua_botlike` | Automation / crawler browser |
>   | `fraudlogix_bot` | FraudLogix bot reason |
>   | `datacenter` | Datacenter network |
>   | `compromised` | Compromised host |
>   | `tor` | Tor |
>   | `velocity` | 100+ sessions in a day |
>   | `bot_click_all` | All sessions are bot clicks |
>   | `bounce_repeat` | Repeated instant bounces |
>   | `tz_mismatch` | Browser / IP time zone differ |
>   | `vpn_proxy` | VPN or proxy |

## Addendum 3 (19 Sep): bad signals, new columns, daily flow

**Before pasting:** on the Data Upload page, upload the new file `app-data/bad_signals.json` (the 10th file). The other 9 files are unchanged.

> **1. Data files.** Add `bad_signals.json` to the list of allowed snapshot files everywhere it is checked (Data Upload page, `getSnapshot` allow-list if present, and `manifest.json` handling). A missing file shows the usual calm "not exported yet" panel.
>
> **2. IP Lookup, Risk card.** Extend `LookupRisk` in `src/lib/api/contract.ts` with optional fields (the lookup API may or may not send them yet):
> ```ts
> is_bot?: boolean | null; is_flagged?: boolean | null; flagged_reason?: string | null; bot_reason?: string | null
> ```
> - **Verdict chip at the top of the Risk card:**
>   - "**Bad signal**" (danger) when `is_bot` is true.
>   - Otherwise the existing Flagged / Clean / Unknown logic.
> - **Under the chip, when present:**
>   - "Why: {bot_reason}". Show `bot_reason` humanised: replace `_` with spaces and title-case. `CLOUD_ASN:AS16509` shows as "Cloud network AS16509"; `PROXYCHECK_IO:VPN` shows as "VPN (from proxycheck.io)".
>   - "Vendor reason: {flagged_reason}" in muted text.
> - **Hidden values:** hide `NOT_BOT` and `NOT_FLAGGED`. If none of the new fields is present, show nothing new.
> - **Bulk tab:** add the columns "Bad signal" (Yes/No/—) and "Reason" (`bot_reason`), and include them in the CSV.
>
> **3. New page "Bad Signals"** (`/reports/bad-signals`, under Reports, file `bad_signals.json`):
> ```ts
> type BadSignals = { as_of: string; standard: string; proxy_only_reasons: string[]
>   per_ip: { ips: number; answered_ips: number; bad_ips: number; bad_ips_strict: number; proxy_vpn_only_ips: number }
>   vendors: { vendor: string; rows_: number; bad: number; not_bad: number; no_answer: number }[]
>   reasons: { vendor: string; reason: string; ips: number }[]
>   truth_test: { measured_on: string; paying_ips: number; paying_marked_bad: number; paying_marked_bad_strict_max: number
>                 fake_ips: number; fake_marked_bad: number; paying_bad_by_reason: Record<string, number> } }
> ```
> - **Header:** "Bad Signals". **Subtitle:** "Which IPs a vendor flags as bad traffic (bots, fraud, automation, proxy / VPN), and why."
> - **Callout (always visible):**
>   - "`is_bot` in `unified.ip_intelligence` means **bad signal**, not only bot.
>   - An IP counts as bad when FraudLogix's latest decision is FLAGGED for any reason, or proxycheck.io reports a proxy, VPN, TOR, datacenter, compromised server, scraper, cloud network or risk 67+.
>   - Each row's reason is in `bot_reason`."
> - **Four tiles from `per_ip`:**
>   - IPs with an answer: `answered_ips` of `ips`.
>   - **Bad IPs:** `bad_ips` (danger) with its %.
>   - **Bad, excluding proxy/VPN-only:** `bad_ips_strict` (warning) with its %.
>   - **Proxy / VPN only:** `proxy_vpn_only_ips` (muted).
> - **Toggle "Hide proxy / VPN-only reasons"** (default off). When on, the reasons chart and table leave out any reason in `proxy_only_reasons`.
> - **Per-vendor table** from `vendors`: Vendor (display names), Rows, Bad, Not bad, No answer, Bad %. Note under it: "No answer = the vendor has no record for the IP (IP2Proxy only lists known proxies)."
> - **"Why IPs are bad"**:
>   - a horizontal bar chart of the top 20 `reasons`, coloured by vendor;
>   - a searchable, sortable table of all rows: Vendor, Reason (humanised as in part 2), IPs.
> - **"Checked against real customers" panel** from `truth_test`:
>   - "{paying_marked_bad} of {paying_ips} paying IPs are marked bad, almost all for VPN or proxy. Without proxy / VPN-only reasons, at most {paying_marked_bad_strict_max} are."
>   - "{fake_marked_bad} of {fake_ips} known fake-lead IPs are marked bad."
>   - A small bar chart of `paying_bad_by_reason`.
>   - Muted footnote: "Measured {measured_on} on leads joined to sessions. Use the strict view to exclude clicks; use the full view for monitoring."
>
> **4. Enrichment Coverage page.** Replace the caption under the "Every address" panel with: "Every IP now gets a proxycheck.io answer. A one-time backfill of the remaining ~4.2M IPs runs 18–19 Sep. After that, new IPs are answered the same day they are loaded, and returning IPs whose answer is older than 30 days are re-checked."
>
> **5. New "How the data updates" panel.** Put it at the bottom of the Enrichment Coverage page, collapsible, open by default. Use a simple numbered list:
>   1. **13:00 IST daily:** new IPs from TUNE clicks, website sessions and experiment router events are added. Returning IPs get FraudLogix's latest decision, and a proxycheck.io re-check when their answer is over 30 days old.
>   2. **Right after:** proxycheck.io answers them (50,000/day budget).
>   3. **Checks:** every run is checked; only a run whose checks all pass refreshes the unified tables and these reports.
>   4. **05:45 IST daily:** a second proxycheck.io run.
>
> **6. Bot / Not bot page.** Under the page subtitle add a muted note: "This page is the stricter, evidence-based bot analysis. The vendor `is_bot` column now means 'bad signal' (including proxy / VPN); see the Bad Signals report."
>
> **Check before finishing:**
> - No TypeScript errors.
> - The Bad Signals page loads, including without the file (calm panel).
> - The lookup still works for `107.127.28.97`.
> - The bulk CSV has the two new columns.
