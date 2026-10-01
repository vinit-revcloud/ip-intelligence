# Lovable prompts: Alyson Traffic Intelligence (SaaS)

These prompts turn the existing app (v2 + Addendum 3) into the product in `SAAS_PRODUCT_BLUEPRINT.md`.

**How to use them:**
- **Start with Prompt 0 (Project Knowledge),** then send one prompt per message, in order. Check the result before sending the next.
- **Rules:** every prompt follows **your requirements** (blueprint, "Your requirements" section). The ones that matter for the app:
  - **Bad-signal standard (step 2):** an IP is **bad** if FraudLogix's latest decision is FLAGGED for any reason, **or** proxycheck.io's `is_bot` is true (proxy, VPN, TOR, datacenter, compromised, scraper, any proxy/threat type, cloud network, risk 67+). IP2Proxy is supporting evidence only. There is no "suspicious" verdict: **bad / clean / unknown**. `signal_type` (automation / behaviour / anonymiser) is only a breakdown and filter.
  - **Nothing dummy:** no sample, placeholder or made-up numbers. A page without real data shows an honest empty state.
  - **Design:** the **Alyson brand guidelines** only.
  - **Data:** arrives via the Data Upload page, and via S3 once the read-only key exists. No direct push from the pipeline, and no GitHub.
- **Data files:** prompts 2–4 read `traffic_analytics.json`, a new daily file the pipeline will write (contract at the end). I build it after step 3 finishes. Until then those pages show the empty state.

---

## Prompt 0: Project Knowledge (paste once into Lovable's Project settings → Knowledge)

Lovable reads "Knowledge" on every change, so these company rules apply to every prompt that follows.

> **Product:** Alyson Traffic Intelligence: traffic-quality and IP intelligence for our own traffic first, later sold as SaaS.
>
> **Data rules (never change them in the UI):**
> 1. **Source of truth.** The data comes from two company tables, `unified.ip_geo` and `unified.ip_intelligence`. The app only **reads** them:
>    - through the lookup API;
>    - through daily snapshot files (`*.json`: Data Upload page, or S3 once the read-only key exists).
>    The app never writes to company data and never calls vendors (FraudLogix, proxycheck.io, IP2Location) directly.
> 2. **Vendor rows.** Each IP has one row per vendor: FraudLogix (`fraudlogix_tune`), proxycheck.io (`proxycheck_io`), IP2Proxy (`ip2proxy_px12`), IP2Location (location).
>    - **Reliable answer** = FraudLogix decided, or proxycheck.io answered. IP2Proxy alone is supporting evidence only.
>    - A FraudLogix row filled from proxycheck.io has a `flagged_reason` starting `PROXYCHECK_IO:`; label it "filled from proxycheck.io".
> 3. **Verdict (company standard, never soften it):**
>    - **Bad** when FraudLogix's latest decision is FLAGGED for **any** reason (PROXY, VPN, MOBILE_PROXY_SIGNALS, ABNORMAL_TRAFFIC_PATTERNS, BASIC_FRAUD, MASKED_DEVICES, BOT_GENERATED, NON_HUMAN_SCRIPT, SPOOFED, DATA_CENTER, TOR, OTHER_REASON, 8, 9, 10…), **or** proxycheck.io's `is_bot` is true (proxy, VPN, TOR, datacenter, compromised, scraper, proxy/threat type, cloud network, risk 67+).
>    - **Clean** when FraudLogix or proxycheck.io answered and neither says bad.
>    - **Unknown** otherwise.
>    - There is **no "suspicious" verdict**. `signal_type` (automation / behaviour / anonymiser) is only a breakdown and a filter.
>    - The reason is in `bot_reason`; the vendor's own reason is in `flagged_reason`.
> 4. **Latest answer wins:** show `first_seen` / `last_seen` and "Data as of" everywhere.
> 5. **Nothing dummy:** never show sample, placeholder, example or made-up numbers, prices or charts. When real data is missing, show an honest empty state saying what is missing and when it arrives.
> 6. **Revenue and leads:** only from the leads data in the snapshot files. Never use a session "has_revenue" flag.
> 7. **Security:**
>    - Tokens and keys live only in server-side secrets, never in the browser or logs.
>    - No raw IPs in URLs or analytics tools.
>    - Every table has row-level security by organisation.
>
> **Design:** the **Alyson brand guidelines** only:
> - **Colours:** background `#F8FAFC`; white cards with `#E5E7EB` border, 12px radius, 16px padding; single accent `#2563EB` (hover `#3B82F6`).
> - **Type and spacing:** Inter; 8px spacing grid.
> - **Structure:** 240px sidebar `#F1F5F9`; Lucide outline icons; every page is header → metric cards → secondary cards → large panels → detail panels.
> - **Charts:** thin accent lines with light gradient fills.
> - **Verdict colours** (bad `#DC2626`, clean `#059669`, unknown `#9CA3AF`) only as small dots and chips.
>
> **Delivery constraints:**
> - Company Lovable account, no GitHub.
> - Data arrives only via the Data Upload page or S3 snapshots.
> - Don't add features that need data or services that don't exist yet. Build the UI with its empty state and label it "not live yet".

---

## Prompt 1: Alyson brand foundation (restyle the whole app)

> Restyle the entire app to the **Alyson brand guidelines**. Change only styling and layout, not behaviour or data.
>
> **Style:** modern SaaS data platform, like Stripe, Vercel, Linear and Segment dashboards. Calm, data first, modular cards, predictable structure, low cognitive load.
>
> **Design tokens** (put them in one place: `tailwind.config` theme + CSS variables, and use them everywhere):
> - Page background `#F8FAFC`; cards `#FFFFFF`; borders `#E5E7EB` (or `rgba(0,0,0,0.06)`).
> - **Single accent** `#2563EB`, hover/lighter `#3B82F6`. Use it only for chart lines, primary buttons, highlights, links and focus rings.
> - Text: primary `#111827`; muted labels `#6B7280`.
> - **Verdict colours:** bad `#DC2626`, clean `#059669`, unknown `#9CA3AF`.
>   - Only as small status dots and chips (text in the colour on a 10% tint of it). Never as large areas or chart fills.
>   - Signal types (automation, behaviour, anonymiser) are grey chips with text, not new colours.
> - Radius: cards 12px, buttons and nav items 8px.
> - Spacing on an 8px grid: 4, 8, 12, 16, 24, 32px. Card padding 16px; large data panels 20–24px. Sections separated by 24–32px.
>
> **Typography:** Inter (fallback: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif).
> - Page title 24px/600.
> - Section headers 16–18px/600.
> - Card titles 13–14px/500–600 (uppercase with slight letter-spacing is allowed).
> - Metric numbers 28px/700, with tabular figures.
> - Labels 12–13px/400–500 in `#6B7280`.
>
> **Layout, on every page:**
> - Left sidebar 240px, background `#F1F5F9`, containing:
>   - logo "Alyson" and product name "Traffic Intelligence";
>   - section labels (small uppercase muted);
>   - primary nav, secondary nav;
>   - user profile at the bottom.
> - Nav items: Lucide outline icon (1.5px stroke, 16–20px, monochrome) + label. The active item has a white background, radius 8px, weight 600.
> - Main content, in this order:
>   1. header bar: title, subtitle, "Data as of …";
>   2. summary metric cards grid;
>   3. secondary cards;
>   4. large visualisation panels;
>   5. supporting detail panels.
>
> **Components:**
> - **Cards:** `background:#fff; border:1px solid #E5E7EB; border-radius:12px; padding:16px`, with hover `box-shadow:0 1px 2px rgba(0,0,0,0.05)`.
> - **Metric card:** title → big number → trend indicator (▲/▼ with % vs previous period, muted; hidden when there is no previous period) → small sparkline.
> - **Buttons:**
>   - Primary: `#2563EB`, white text, radius 8px, padding 8px 14px, weight 500, slightly darker on hover.
>   - Secondary: white with a `#E5E7EB` border.
> - **Charts (Recharts):** thin 2px accent line, smooth (monotone) curves, area gradient `rgba(37,99,235,0.2)` → `rgba(37,99,235,0.02)`, minimal axes, no heavy gridlines (at most faint horizontal lines).
>   - Multi-series charts use shades of the accent blue and greys, never rainbow colours.
>   - Tooltips are white cards.
> - **Tables:** dense but airy. 13px text, muted uppercase header row, row hover `#F8FAFC`, right-aligned numbers with thousands separators, sticky header.
> - **Motion:** hover elevation, subtle chart animation on load, button colour shift. Nothing flashy.
> - **Empty states:** a small outline icon, one sentence on what data is missing, one on when or how it arrives. **Never fill a page with sample or made-up numbers.**
>
> **Check before finishing:**
> - Every existing page still works and follows the layout above.
> - No colour outside the tokens.
> - Inter loads.
> - The sidebar is 240px.

---

## Prompt 2: navigation and Overview

> Reorganise the sidebar into these sections, keeping all existing pages:
> - **Monitor:** Overview (new, the home page), Traffic Quality (new), Reasons (new), Network (new), Geography (new), Outcomes (new)
> - **Investigate:** IP Lookup, Saved Addresses, Bad Signals, Bot / Not bot, Lead-IP Evaluation
> - **Trust:** Vendors & Accuracy (move Vendor Scorecards and Location Accuracy here as tabs), Data Health (new; move Enrichment Coverage here)
> - **Settings (secondary nav):** Data Upload, Activity, Team, Developers (new), Billing (new)
>
> Add the file name `traffic_analytics.json` to the allowed snapshot files (Data Upload page, `getSnapshot` allow-list if present, manifest handling). Types are in "Data contract" below. Put them in `src/lib/analytics/types.ts`, plus one loader `useTrafficAnalytics()` that caches the file for the session. When the file is missing, every page using it shows the empty state "Traffic analytics has not been exported yet".
>
> **Overview page** (`/`), reading `traffic_analytics.json`:
> - **Header:** "Overview". Subtitle: "Traffic quality for {window.start} – {window.end}". Right side: "Data as of {as_of}".
> - **Summary metric cards** (from `overview`, with a sparkline from `overview.by_day`):
>   - Visits (`events`);
>   - Unique IPs (`unique_ips`), with "new: {new_ips}" underneath;
>   - Bad traffic % (`bad_pct`, red status dot);
>   - Clean traffic % (`clean_pct`, green dot);
>   - Quality score (`quality_score`, 0–100).
> - **Secondary cards:**
>   - "Bad, excluding anonymiser-only" (`strict_bad_pct`);
>   - "Bad by signal type": three small bars from `overview.bad_by_signal` (automation / behaviour / anonymiser);
>   - "Bad visits" (`outcomes.wasted.bad_events`).
> - **Large panel:** a line chart of daily bad % from `overview.by_day`, with visits as faint bars behind.
> - **Supporting panels:**
>   - "Worst 5 affiliates" and "Worst 5 campaigns" by quality score (from `by_dimension.affiliate` and `by_dimension.utm_campaign`, only rows with `events ≥ 100`), each linking to Traffic Quality filtered to that row;
>   - "Top reasons" (top 5 from `reasons.mix`).
> - **Footer** under the page: "An IP is bad when FraudLogix's latest decision is FLAGGED for any reason, or proxycheck.io reports a bad signal (proxy, VPN, TOR, datacenter, compromised, scraper, cloud network or high risk). Signal type is a breakdown only. Rules version {rule_version}."

---

## Prompt 3: Traffic Quality, Reasons, Network, Geography

> Build four pages. All read `traffic_analytics.json`, follow the Alyson layout, and show the file's 30-day window as read-only text in the header.
>
> **Traffic Quality** (`/traffic`):
> - Tabs, one per `by_dimension` key, labelled Affiliate, Offer, Advertiser, UTM source, UTM campaign, Experiment, Landing brand, Device, Browser, OS, State, Source.
> - Each tab shows a sortable, searchable table: Name (`label` or `key`), Visits, Unique IPs, Quality score (small bar), Bad %, Bad % excl. anonymiser-only, Clean %, Leads, Lead rate %, Revenue, and a sparkline of bad % from `trend`.
> - Colour the quality score chip: ≥ 90 clean colour, < 90 bad colour. The number is the point; the colour only marks below 90.
> - Filter "min visits" (default 100).
> - Row click opens a right-side drawer with that row's metrics, its bad-by-signal-type split and a trend chart.
> - Download CSV per tab.
>
> **Reasons** (`/reasons`):
> - Summary cards: bad IPs, top reason, share of reasons from FraudLogix vs proxycheck.io.
> - Horizontal bar chart of `reasons.mix` (top 20). Each bar shows the reason in words, the vendor in muted text, and a grey signal-type chip (`signal_type`).
> - Stacked area chart of `reasons.by_day` (top 6 reasons, others grouped), in accent shades.
> - A toggle "Hide anonymiser-only reasons (VPN / proxy)". It only filters the view; it never changes the verdict.
> - Reason names in words: `BOT_GENERATED` → "Bot generated"; `CLOUD_ASN:AS16509` → "Cloud network AS16509"; `PROXYCHECK_IO:VPN` → "VPN (proxycheck.io)"; `HIGH_RISK` → "High risk score"; numeric codes `8`, `9`, `10` → "FraudLogix code 8/9/10 (undocumented)".
>
> **Network** (`/network`):
> - Summary cards from `network.shares`: cloud %, datacenter %, VPN %, proxy %, mobile %, TOR %.
> - Table of `network.top_asn`: ASN, Provider, Connection type, IPs, Visits, Bad %, and a "Cloud" chip when `is_cloud`.
> - Donut of connection types (Residential / Business / Wireless / Hosting / Unknown) in accent shades.
>
> **Geography** (`/geography`):
> - US state map (choropleth in accent-blue shades) of visits, with a toggle to colour by bad %. It uses only US state names from `geo.states`.
> - A "State / region" table next to it with every row, including non-US regions: Region, Visits, IPs, Bad %.
> - A "Location confidence" card from `geo.confidence`: agreed, nearby, same state, vendors disagree, single source.

---

## Prompt 4: Outcomes (the money page)

> **Outcomes** (`/outcomes`), from `outcomes` in `traffic_analytics.json`:
> - **Summary cards:** lead rate for clean traffic, lead rate for bad traffic, revenue per 1,000 clean visits, revenue per 1,000 bad visits.
>   - Show "Bad traffic converts {x}× worse" only when the data says so.
> - **Bar chart:** lead rate % for clean vs bad (`outcomes.by_verdict`), plus bad split by signal type (`outcomes.by_signal`), in accent shades with verdict dots in the legend.
> - **Table:** by UTM source (`outcomes.by_utm_source`): UTM source, Visits, Bad %, Leads, Lead rate %, Revenue. Sortable; default sort bad %, descending.
> - **Note:** affiliates come from TUNE clicks, which can't be matched to leads, so they have no lead rate. Show `notes` from the file in a muted info box.
> - **Wasted-spend calculator card:**
>   - input "Cost per visit ($)", **empty by default** (the user types their real cost);
>   - output "Spend on bad visits: ${bad_events × cost}".
>   - Never saved.
> - **Muted footnote:** "Leads come from the leads table matched to website sessions (`utm_content = session_id`). Revenue is expected revenue from that table. The session 'has_revenue' flag is not used."

---

## Prompt 5: Investigate upgrades (IP Lookup)

> In IP Lookup (single and bulk), add a verdict card above the Location and Risk cards:
> - Big verdict chip: **Bad / Clean / Unknown**, in verdict colours.
> - Reasons as a list, each in words, with the vendor in muted text and a grey signal-type chip.
> - "First seen / last seen" when present.
>
> **Deriving the verdict until the API sends `verdict`**, using only the FraudLogix and proxycheck.io rows:
> - **Bad** when either row has `is_bot = true`.
> - **Clean** when at least one of them answered and neither is bad.
> - **Unknown** when neither answered.
> - IP2Proxy is shown in the Risk card as supporting evidence only. It never decides the verdict.
>
> **Signal type of a reason:**
> - **Anonymiser:** VPN, PROXY, MOBILE_PROXY_SIGNALS (incl. `PROXYCHECK_IO:VPN` / `PROXYCHECK_IO:PROXY`).
> - **Behaviour:** ABNORMAL_TRAFFIC_PATTERNS, BASIC_FRAUD, MASKED_DEVICES, HIGH_RISK, OTHER_REASON, NOT_APPLICABLE, 8, 9, 10.
> - **Automation:** everything else.
>
> Bulk results table: add Verdict, Signal type and Reasons columns, and include them in the CSV.

---

## Prompt 6: Trust pages (Vendors & Accuracy, Data Health)

> **Vendors & Accuracy** (`/trust/vendors`): tabs for Proxy scorecard, Location scorecard, Location accuracy (existing pages, restyled) and a new **"How accurate are the verdicts"** tab from `bad_signals.json` → `truth_test`:
> - cards: paying IPs tested, marked bad (all reasons), marked bad excluding anonymiser-only, fake-lead IPs marked bad;
> - one sentence: "Every rule is tested on IPs of real paying customers; these numbers are published, not hidden."
>
> **Data Health** (`/trust/health`): the existing Enrichment Coverage content plus:
> - a **freshness card:** "Last update {as_of}", green dot if under 26 hours old, red otherwise;
> - the "How the data updates" steps (from Addendum 3).

---

## Prompt 7: SaaS shell (organisations, team, developers, billing)

> Using Lovable Cloud (Supabase) auth and database:
>
> 1. **Organisations and roles:**
>    - Tables `organizations`, `memberships` (`user_id`, `org_id`, `role`: owner/admin/analyst/viewer), `invitations`.
>    - Row-level security on every table, scoped by `org_id`.
>    - Sign-in with email and Google.
>    - The first user who signs up creates the organisation.
>    - The org switcher sits in the sidebar user menu.
> 2. **Team page:** invite by email, change role, remove member. Owner-only actions are disabled for others with a tooltip.
> 3. **Developers page:**
>    - API keys table `api_keys` (`org_id`, `name`, `prefix`, `hash`, `created_by`, `created_at`, `last_used_at`, `revoked_at`).
>    - "Create key" shows the full key **once**. Store only a SHA-256 hash and the first 8 characters.
>    - A docs panel with the request format and the response fields (verdict, signal_type, reasons, location, network, first_seen, last_seen).
>    - Show the section as "API not live yet" until the serving API exists.
>    - **No usage chart until real usage data exists.**
> 4. **Billing page:** show "Billing is not set up yet" until **both** a Stripe secret and real plan prices exist. Do not show example prices.
> 5. **Alerts (in Settings):**
>    - rules table `alert_rules` (`org_id`, `metric`: bad_pct | strict_bad_pct | quality_score, `dimension`: affiliate | utm_campaign | experiment, `key`, `operator`, `threshold`, `channel`: email | slack_webhook, `enabled`);
>    - UI to create, edit and delete rules.
>    - **Evaluation:** a scheduled function checks rules against the latest `traffic_analytics.json` once a day and sends email or Slack messages. Log each firing to `alert_events`, shown in a list.
> 6. **Admin (only for users with `is_platform_admin`):** organisations list, member count, API key count.
>
> Keep the Alyson styling for every new screen. Never expose secrets in the browser.

---

## Data contract: `traffic_analytics.json` (written by the pipeline, daily)

```ts
type Verdict = 'bad' | 'clean' | 'unknown'
type SignalType = 'automation' | 'behaviour' | 'anonymiser'
type Row = { key: string; label?: string; events: number; unique_ips: number
  bad_pct: number; strict_bad_pct: number; clean_pct: number; quality_score: number
  bad_by_signal: Record<SignalType, number>            // % of events, sums to bad_pct
  leads: number; lead_rate_pct: number | null; revenue: number
  trend: { d: string; bad_pct: number; events: number }[] }
type TrafficAnalytics = {
  as_of: string; rule_version: string
  window: { start: string; end: string; days: number }
  overview: { events: number; unique_ips: number; new_ips: number; returning_ips: number
    bad_pct: number; strict_bad_pct: number; clean_pct: number; unknown_pct: number; quality_score: number
    bad_by_signal: Record<SignalType, number>
    by_day: { d: string; events: number; unique_ips: number; new_ips: number; bad_pct: number }[] }
  by_dimension: Record<'affiliate' | 'offer' | 'advertiser' | 'utm_source' | 'utm_campaign' | 'experiment'
    | 'brand' | 'device' | 'browser' | 'os' | 'state' | 'source', Row[]>
  reasons: { mix: { reason: string; vendor: string; signal_type: SignalType; ips: number; events: number }[]
             by_day: { d: string; reason: string; ips: number }[] }
  network: { shares: { cloud_pct: number; datacenter_pct: number; vpn_pct: number; proxy_pct: number; mobile_pct: number; tor_pct: number }
             top_asn: { asn: string; provider: string; connection_type: string; ips: number; events: number; bad_pct: number; is_cloud: boolean }[] }
  geo: { states: { state: string; events: number; ips: number; bad_pct: number }[]
         confidence: { agreed: number; nearby: number; same_state: number; vendors_disagree: number; single_source: number } }
  outcomes: { by_verdict: { verdict: Verdict; events: number; leads: number; lead_rate_pct: number | null; revenue: number; revenue_per_1k: number | null }[]
              by_signal: { signal_type: SignalType; events: number; leads: number; lead_rate_pct: number | null }[]
              by_utm_source: Row[]                  // session traffic only (the only visits matched to leads)
              wasted: { bad_events: number } }
  notes: string[]                                   // show in a muted info box on Overview and Outcomes
}
// Row.lead_rate_pct is over session visits only; null for rows with no sessions (e.g. affiliate, offer).
// geo.states holds US states and non-US regions.
```

**Definitions:**
- Percentages are 0–100.
- **Verdict per IP** is your step 2 standard: bad if FraudLogix's latest decision is FLAGGED (any reason) or proxycheck.io's `is_bot` is true; clean if either answered and neither is bad; unknown otherwise.
- `quality_score = 100 × (1 − bad_share)`.
- `strict_bad_pct` = bad excluding IPs whose only reasons are anonymiser (VPN / PROXY / MOBILE_PROXY_SIGNALS).

**Sources** (all read only):
- **Visits:** TUNE clicks (affiliate / offer / advertiser), website sessions (UTM, brand, device, browser, OS, experiment) and router events (experiment, device).
- **Verdicts:** `unified.ip_intelligence`.
- **Location:** `unified.ip_geo`.
- **Leads and revenue:** `sampledb.revenue_leads_plus` (`expected_revenue > 0`).

**Written only to:** our project's S3 folder `ip-intelligence/serving/app/`.
