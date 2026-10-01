# Traffic Quality Intelligence: SaaS product blueprint

Drafted 19 Sep 2026. It builds on what already runs:
- the daily pipeline;
- `unified.ip_geo` and `unified.ip_intelligence`;
- the step 2 bad-signal standard;
- the Lovable app v2.

Build prompts for Lovable are in `LOVABLE_PROMPT_SAAS.md`.

---

## Your requirements: carried over unchanged (nothing below may override them)

Every requirement you set for this project applies to the product. **The master copy is `CLAUDE.md`** (it also holds later decisions: the FraudLogix tie-break of 21 Sep and the budget change of 20 Sep). Where anything disagrees, `CLAUDE.md` wins.

**Data and tables**
1. **The two tables are the product core:** `unified.ip_geo` and `unified.ip_intelligence` are the source of truth. Anything added (the lookup store, analytics files) is a **copy built from them**, never a replacement.
2. **Sources:** `raw.raw_tune_clicks`, `unified.unified_session_summary` and `experimentation_tools.experiment_router_events` feed the tables. **All three are read only:** nothing is ever written to them.
3. **Every unique public IP** from the three sources is in both tables. New IPs are **appended**; IPs already present are **updated**.
4. **Latest timestamp wins:** when an IP returns, the latest answer replaces the old one (FraudLogix latest decision; proxycheck.io re-checked when its answer is over 30 days old).
5. **Every IP has at least one reliable answer:** FraudLogix decided, or proxycheck.io answered. **IP2Proxy PX12 on its own never counts as an answer.**
6. **FraudLogix (`fraudlogix_tune`) is a stand-alone reliable source.** Its real decisions are never overwritten. Empty FraudLogix rows are filled from proxycheck.io and marked `FILLED_FROM_PROXYCHECK_IO`.
7. **Every column is filled wherever a vendor gives data.** A cell is empty only when the vendor gave no answer or never supplies that column.
8. **Schema:** no column is changed or removed without your approval. Columns added so far with your approval: `is_flagged`, `flagged_reason`, `bot_reason`.

**Bot / bad-signal standard (step 2, your decision of 19 Sep)**

9. **`is_bot` = bad signal**, not only bot:
   - **FraudLogix:** latest decision FLAGGED for **any** reason: PROXY, VPN, MOBILE_PROXY_SIGNALS, ABNORMAL_TRAFFIC_PATTERNS, BASIC_FRAUD, MASKED_DEVICES, BOT_GENERATED, NON_HUMAN_SCRIPT, SPOOFED, DATA_CENTER, TOR, TOR_EXIT_NODE, OTHER_REASON, 8, 9, 10, NOT_APPLICABLE.
   - **proxycheck.io:** proxy, VPN, TOR, datacenter/hosting, compromised server, scraper, any proxy or threat type, a cloud network, or risk score 67+.
   - **IP2Proxy:** listed.
10. **Per IP:** an IP is **bad if FraudLogix or proxycheck.io says so.** IP2Proxy is supporting evidence only (see 5).
11. **Every bad row carries its reason:** `bot_reason`; the vendor's own reason is in `flagged_reason`.

**How every IP is handled (your rule of 19 Sep, applies to every current and future source)**

23. **Any IP from any source table** (TUNE clicks, session summary, experiment router events, or a source added later) is checked for a reliable, complete answer:
    - **Answered by its original source:** inserted or updated by the **latest timestamp**.
    - **Partially answered:** e.g. FraudLogix decided but never supplies ISP, ASN, compromised, scraper or anonymous. The row is **combined** with proxycheck.io's answer; only the empty columns are filled, and FraudLogix's own values always stay.
    - **Not answered:** FraudLogix never decided, or the IP came only from sessions or router events. **proxycheck.io resolves it**, and empty FraudLogix rows are filled and marked `FILLED_FROM_PROXYCHECK_IO`.
    - **In every case where proxycheck.io is asked,** its **full answer is also stored as its own row** `(IP, proxycheck_io)`, so the vendors can be compared.
24. **Any unresolved IP**, whatever its age or source, is queued automatically every day and resolved first, as above.
    - The only exceptions are private addresses and IPs proxycheck.io has no record of. These are reported, not hidden.

**Budget and schedule**

12. **proxycheck.io budget:** enrichment uses **50,000 queries/day**, and **30,000/day are yours**. Any product feature that uses more (e.g. live lookups for unknown IPs) needs your approval first. The plan is $199.99/month (5.12M/day).
13. **Schedule:** timed for IST. Daily load 13:00 IST, enrichment 05:45 IST (after the 05:30 IST quota reset).

**Safety and access**

14. **Production is untouched:** nothing in production is modified, deleted or added in a way that disturbs the existing system or any dependency.
    - **Read only:** `raw`, `unified.unified_session_summary`, `experimentation_tools`, `sampledb`.
    - **Never touched:** `ip-database`.
15. **Athena:** only the `ipintel_etl` workgroup, never `primary`.
16. **AWS:** only the `ipintel-builder` profile.
17. **Keys:** stay in Secrets Manager and are never shown.
18. **Nothing dummy or benchmark:** no sample, placeholder or made-up numbers anywhere in the product. A page with no real data yet shows an honest empty state.

**Delivery**

19. **Docs:** written as Markdown files, never HTML pages.
20. **Lovable:** company account, no GitHub. Data reaches the app via the Data Upload page, and via S3 once the read-only key exists. A direct push from the pipeline to Lovable is not rebuilt without your OK.
21. **Design:** the **Alyson brand guidelines** are the only source.
22. **Truth for accuracy:** `sampledb.revenue_leads_plus` (`expected_revenue > 0`, `fake = true`), joined on `utm_content = session_id`. The session `has_revenue` flag is not revenue and is never used.

---

## 0. Read first: two things decide whether this can be sold

1. **Vendor licences.** The tables combine data we **bought or received**: IP2Location / IP2Proxy databases, proxycheck.io answers, and FraudLogix decisions via TUNE. Data licences usually allow **internal use** but restrict **resale or redistribution**, including through an API. **Before charging anyone outside the company, check each contract** (or buy a redistribution / OEM licence).
   - **Safe to sell today:** our own derived outputs (combined verdict, reasons, analytics, revenue-validated accuracy), where the contracts allow derived data.
   - **Not safe to sell until checked:** raw vendor fields passed through one-to-one.
2. **Privacy.** IP addresses are personal data under GDPR and some US state laws (e.g. CCPA). A paid product needs:
   - a privacy policy;
   - a data processing agreement (DPA) for customers;
   - a retention policy you decide (nothing is deleted until you do);
   - a lawful basis (fraud prevention is the usual one).

Neither blocks building the product. **Both block the first external sale.** Everything below is designed so the product is **useful internally first** (your own traffic) and sellable once 1 and 2 are cleared.

---

## 1. The product in one paragraph

**"Know which clicks are real before you pay for them."** A traffic-quality platform for lead-gen and affiliate businesses:
- **What it gives:** every visitor IP gets a verdict (bad or clean under your step 2 standard), the reason, and location.
- **Where:** in real time (API), in bulk (CSV) and in dashboards.
- **Every traffic source is scored:** each affiliate, campaign, experiment and device gets a quality score.
- **What competitors don't have:**
  1. **Revenue-validated accuracy:** every rule is tested against real paying customers, and we publish how often it's wrong (competitors don't).
  2. **Multi-vendor consensus:** FraudLogix, proxycheck.io and IP2Location/IP2Proxy combined into one answer with a reason, instead of one vendor's opinion.
  3. **Traffic analytics, not just lookups:** bad-traffic rate per affiliate, campaign and experiment, and what bad traffic costs in lost leads.

**Who buys:** performance-marketing teams, lead-gen companies, affiliate networks and ad-ops teams paying per click or per lead. **Their pain:** paying for bot, VPN-farm and fraud traffic that never converts.

---

## 2. What exists today vs. what the product needs

| Layer | Exists today | Needed for the product |
|---|---|---|
| **Ingestion** | Daily pipeline from 3 sources (TUNE clicks, sessions, router events). New IPs are added; returning IPs are updated (latest FraudLogix decision, proxycheck.io re-check after 30 days). Checked before every publish | Same, plus a **customer ingestion** path (customers send their own IPs or events), plus a `rule_version` on every row so answers can be traced when rules change |
| **Enrichment** | FraudLogix, proxycheck.io (5.12M/day plan), IP2Location DB11, IP2Proxy PX12. Every IP has a reliable answer | Same. Unknown IPs a customer looks up are queued for the next enrichment run; live proxycheck.io lookups only if you approve a budget for them (requirement 12) |
| **Tables** | `unified.ip_geo`, `unified.ip_intelligence` (with `is_bot`/`is_flagged`/`flagged_reason`/`bot_reason`), analytics and overview tables | **Unchanged as the core.** Plus a serving copy (`ip_profile`, one row per IP: verdict, reasons, location, network, first/last seen) built from the two tables |
| **Serving** | Teammate API `GET /v1/ip/{ip}` (reads unified via Athena, which takes seconds); S3 snapshot files for the app | A **fast lookup store** (DynamoDB, under 50 ms), an **API gateway** with keys, rate limits and usage metering, and **bulk** endpoints |
| **Analytics** | Coverage, location accuracy, vendor scorecards, bad signals (JSON snapshots) | A **traffic analytics mart**: daily aggregates by source, affiliate, campaign, experiment, device, geo, ISP and reason, plus **outcome** metrics (lead rate and revenue, clean vs bad) |
| **App** | Lovable v2: lookup, bot/not bot, lead-IP evaluation, location accuracy, coverage, scorecards, data upload | A **multi-tenant SaaS**: sign-up, organisations, roles, API keys, usage and billing, dashboards, alerts, bulk enrichment, docs portal, admin console |
| **Operations** | Checks on every run, rollback snapshots, audit review, alerts | Status page, freshness guarantees (SLA), data-quality dashboard, incident runbook |

---

## 3. Architecture

```
            ┌────────────────────────── DATA PLANE (AWS, exists) ──────────────────────────┐
 Sources →  │ Job A (daily 13:00 IST) → Job B proxycheck.io (05:45 IST + after Job A)        │
 clicks     │   → ipintel_curated (Iceberg, checked) → publish → unified.ip_geo / ip_intelligence │
 sessions   │   → analytics mart (NEW: daily aggregates) → S3 serving/app/*.json               │
 router     └──────────────────────────────────────┬──────────────────────────────────────┘
                                                   │ after each publish (changed IPs only)
            ┌──────────────── SERVING PLANE (NEW, AWS) ───────────▼────────────────────────┐
            │ ip_profile store (DynamoDB, one item per IP)                                   │
            │ API Gateway + Lambda: /v1/ip/{ip}, /v1/ip/bulk, /v1/analytics/*                 │
            │   API keys per customer · usage plans · rate limits · usage metering           │
            │   cache miss → queued for the next enrichment run (live calls only if approved) │
            └──────────────────────────────────────┬──────────────────────────────────────┘
                                                   │ HTTPS (server-side only)
            ┌──────────────── APP PLANE (Lovable + Lovable Cloud/Supabase) ▼────────────────┐
            │ Auth, organisations, roles · API key management · Stripe billing · usage       │
            │ Dashboards (read analytics JSON / API) · IP lookup · bulk CSV · alerts · docs  │
            └──────────────────────────────────────────────────────────────────────────────┘
```

**Why this shape:**
- **Athena is slow and costly per lookup.** It stays the engine for building and checking the tables; customers are served from DynamoDB (millisecond lookups, pay per request, ~5M items ≈ a few GB).
- **The app never holds vendor keys or AWS credentials.** It calls our API with a server-side token, as the app v2 already does.
- **The data plane is unchanged.** All its safety rules stay: production tables are read only, only checked runs are published, and every run is audited.

### 3.1 The `ip_profile` record (a fast serving copy of the two unified tables)

One item per IP, rebuilt after each publish from `unified.ip_intelligence`, `unified.ip_geo` and `ip_occurrences`. It adds no new judgement: every value comes from the two tables under the rules above (requirement 1).

| Field | Meaning |
|---|---|
| `ip` | IPv4 address |
| `verdict` | `bad` / `clean` / `unknown` (rules below: your step 2 standard) |
| `signal_type` | For bad IPs, which kind of signal it is: `automation` (bots, scripts, spoofing, datacenter, cloud, TOR, open proxies, compromised, scraper), `behaviour` (ABNORMAL_TRAFFIC_PATTERNS, BASIC_FRAUD, MASKED_DEVICES, HIGH_RISK, OTHER_REASON, 8/9/10, NOT_APPLICABLE) or `anonymiser` (VPN, PROXY, MOBILE_PROXY_SIGNALS). **A breakdown only: it never changes `bad`** |
| `reasons` | e.g. `["BOT_GENERATED (FraudLogix)", "CLOUD_ASN:AS16509 (proxycheck.io)"]` |
| `is_proxy`, `is_vpn`, `is_tor`, `is_datacenter`, `is_cloud`, `is_compromised`, `is_scraper` | Combined flags (any reliable vendor) |
| `country`, `state`, `city`, `zip`, `lat`, `lng`, `timezone` | Resolved location (existing agreed/nearby rules) |
| `isp`, `asn`, `connection_type` | proxycheck.io network (Residential / Business / Wireless / Hosting) |
| `first_seen`, `last_seen`, `days_seen`, `seen_in` | From `ip_occurrences` |
| `sources` | Which vendors answered, and when |
| `rule_version` | Version of the rules that made this answer |
| `updated_at` | When the answer last changed |

**Verdict rules (your step 2 standard, unchanged):**

| Verdict | Rule |
|---|---|
| `bad` | FraudLogix's latest decision is FLAGGED for any reason, **or** proxycheck.io's `is_bot` is true (requirements 9–10) |
| `clean` | FraudLogix and/or proxycheck.io answered, and neither says bad |
| `unknown` | Neither FraudLogix nor proxycheck.io answered. Only the ~90 private addresses today |

**What the UI does with `signal_type`:** it lets a user **filter** (e.g. "show bad IPs excluding anonymiser-only") without changing the verdict. This is the same "strict view" as on the Bad Signals page you already approved.

**Accuracy is reported honestly, next to the numbers:** under this standard, 535 of 1,044 paying IPs (51%) are marked bad, mostly VPN/proxy; excluding anonymiser-only, at most 49 (≈5%). Buyers see both.

### 3.2 Incremental growth: the guarantees

These already exist (see `docs/SYSTEM_GUIDE.md`, last section) and become the product's **data contract**:

1. **New IP** in any source → added at the next daily load, answered by proxycheck.io, and published after checks. Worst case about 24 hours today. A faster target (e.g. a second daily load) is possible later, but only within the 50k/day budget and with your approval (requirement 12).
2. **Returning IP** → FraudLogix's latest decision wins; proxycheck.io is re-checked when its answer is over 30 days old.
3. **Every run is checked** (about 14–18 checks). Any failure means nothing is published; the previous version keeps serving.
4. **Rollback** by snapshot for every table.
5. **Audit:** every write outside the project is detected (incremental review).

**To add for the product:**
- `rule_version` and `answered_at` per row: **only with your approval**, since it is a schema change to `unified.ip_intelligence` (requirement 8), and an admin runs the ALTER as for the last three columns;
- a data-quality page (freshness, coverage and check history);
- a documented changelog whenever a rule changes.

---

## 4. Analytics catalogue (everything the UI shows)

Each metric comes from a daily aggregate the pipeline writes (the analytics mart). No Athena query runs from the UI.

| # | Area | Metrics | Breakdowns | Source |
|---|---|---|---|---|
| A | **Traffic overview** | Events, unique IPs, new vs returning IPs, events per IP | Day; source (clicks / sessions / router) | All 3 sources + `ip_occurrences` |
| B | **Traffic quality** | Bad %, clean %, unknown %; bad % split by signal type (automation / behaviour / anonymiser); strict bad % (excluding anonymiser-only); quality score | Day, source, **affiliate**, **offer**, **advertiser**, **utm_source / campaign / medium**, **experiment**, landing page / brand / vertical, device, browser, OS, state | Sources joined to `ip_profile` |
| C | **Why traffic is bad** | Reason mix and its trend; top reasons per affiliate / campaign | Reason, vendor, day | `bot_reason` |
| D | **Network intelligence** | Top ISPs / ASNs; cloud and datacenter share (AWS, Google, Azure…); VPN / proxy share; mobile-carrier share; TOR | ASN, provider, connection type | proxycheck.io network fields |
| E | **Geography** | Traffic and bad % by state / city; location confidence (agreed / nearby / disagree) | State, city | `ip_geo` resolved |
| F | **Outcomes (the money slide)** | Lead rate, qualified rate and revenue per 1,000 visits: clean vs bad (and bad by signal type); **estimated wasted spend** on bad traffic | Affiliate, campaign, experiment | `revenue_leads_plus` joined to sessions |
| G | **Repeat & velocity** | IPs with many sessions a day, IPs across many affiliates (click farms), first seen vs last seen | Day | Sessions + `ip_occurrences` |
| H | **Vendor performance** | Coverage, agreement, wrong-flag rate on paying customers, freshness, cost per answer | Vendor | Existing scorecards + truth test |
| I | **Data health** | Last run, checks passed, rows added / updated, queue backlog, quota used vs budget, answer age | Day | DynamoDB run log (`run#*`) |

**Scoring a traffic source** (per affiliate / campaign / experiment):
`quality_score = 100 × (1 − bad_share)`, using your standard (every flagged reason counts), shown next to its lead rate and the strict bad share. A source with a low score **and** a low lead rate is where money is being wasted.

**Outcome metrics use real leads only** (`expected_revenue > 0`). The session `has_revenue` flag is **not** used: profiling showed it's inflated (1.15M sessions 'on' vs about 1.2k real revenue leads).

---

## 5. API (the product surface)

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /v1/ip/{ip}` | Full `ip_profile` | Under 50 ms from DynamoDB. On a miss, the IP is queued for the next enrichment run. **Live proxycheck.io calls are off** until you approve a budget for them (requirement 12) |
| `POST /v1/ip/bulk` | Up to 1,000 IPs | Same, batched |
| `POST /v1/jobs/enrich` | CSV / S3 file, up to 1M rows | Async job; results file plus summary |
| `GET /v1/analytics/{report}` | Any section A–I, per tenant | Tenant sees own traffic only |
| `POST /v1/events` (phase 3) | Customer sends click / session events | Feeds their own analytics |
| Webhooks (phase 3) | Alerts: bad-traffic spike per source, new cloud ASN, etc. | |

- **Auth:** API key per organisation, hashed at rest.
- **Rate limits:** set per plan.
- **Usage:** every call metered and billed monthly through Stripe.
- **Tenancy:** customer traffic never mixes with another customer's in analytics. The shared **IP knowledge** (verdicts) is the network effect: every customer's traffic makes the verdicts better.

---

## 6. SaaS app (Lovable + Lovable Cloud)

**Brand:** Alyson. Working product name: **Alyson Traffic Intelligence** (placeholder; rename freely).

**Tenancy and roles:**
- **Organisations:** Owner / Admin / Analyst / Viewer.
- **Sign-in:** email and Google SSO.
- **Row-level security:** enforced on every tenant table.

**Main screens:**
1. **Overview.** Traffic today vs 7-day average, bad %, wasted spend estimate, top 5 worst sources, data freshness badge.
2. **Traffic Quality.** Table and heat-map of sources (affiliate / campaign / experiment), with quality score, bad %, lead rate and trend sparkline. Drill-down to one source.
3. **Reasons.** Reason mix, reason trend, reason by source.
4. **Network.** Top ISPs / ASNs, cloud/VPN/mobile shares, and an ASN detail page.
5. **Geography.** Map and state table.
6. **Outcomes.** Clean vs bad lead rate and revenue, and wasted-spend calculator.
7. **IP Lookup.** Single and bulk lookup, CSV enrichment jobs, saved lists, watchlists.
8. **Alerts.** Rules (e.g. "affiliate X bad % > 20% today"), delivered by email / Slack / webhook.
9. **Vendors & Accuracy.** Coverage, agreement, and wrong-flag rate on paying customers (the trust page).
10. **Data Health.** Freshness, checks, runs, quota.
11. **Developers.** API keys, docs (OpenAPI), usage charts, webhooks.
12. **Billing.** Plan, usage, invoices (Stripe).
13. **Admin (internal only).** Tenants, plans, quotas, feature flags, audit log.

**Design system: the Alyson brand guidelines (`Alyson Brand Guidelines - UI _UX.pdf`) are the only source.**

| Token | Value |
|---|---|
| Style | Modern SaaS data platform (Stripe / Vercel / Linear / Segment): calm, data first, modular cards, predictable layout |
| Page background | `#F8FAFC` |
| Cards | `#FFFFFF`, border `1px solid #E5E7EB`, radius 12px, padding 16px (large panels 20–24px), hover shadow `0 1px 2px rgba(0,0,0,0.05)` |
| Sidebar | 240px, `#F1F5F9`: logo, section labels, primary and secondary navigation, user profile. Active item: white background, radius 8px, weight 600 |
| Accent (the only accent) | `#2563EB` (hover / lighter `#3B82F6`) for chart lines, primary buttons, highlights and links, used sparingly |
| Typography | Inter (then -apple-system, Segoe UI, Roboto, Helvetica, Arial). Page title 24px/600; section header 16–18px/600; card title 13–14px/500–600; metric 28px/700; labels 12–13px/400–500 `#6B7280` |
| Spacing | 8px grid: 4 / 8 / 12 / 16 / 24 / 32px |
| Charts | Thin 2px accent line, smooth curve, area gradient `rgba(37,99,235,0.2)` → `rgba(37,99,235,0.02)`, minimal axes, no gridline clutter; sparklines in cards |
| Buttons | Primary: `#2563EB`, white text, radius 8px, padding 8px 14px, weight 500. Secondary: white with `#E5E7EB` border |
| Icons | Lucide, outline, 1.5px stroke, 16–20px, monochrome |
| Motion | Hover elevation, subtle chart animation, button colour shift; nothing flashy |
| Page structure (every page) | Header → summary metric cards → secondary cards → large visualisation panels → supporting detail panels |
| Card pattern | Title → primary metric → trend indicator → sparkline |

**Verdict colours (the one exception to "single accent"):** a traffic-quality product must show bad / clean / unknown.
- **Where:** only small status dots and chips, never large areas or chart fills.
- **Shades:** muted tints, bad `#DC2626`, clean `#059669`, unknown `#9CA3AF`, each on a 10% tint background. Signal types (automation / behaviour / anonymiser) use grey chips with text, not new colours.
- **Charts:** stay in the blue accent plus greys. Verdict splits use accent-blue shades, with the verdict name in the legend.

Every number shows its date range and a "how is this calculated" tooltip. Empty states say what to do next.

**Pricing** (a proposal for you to decide; not shown in the app until you set real prices):

| Plan | For | Includes |
|---|---|---|
| Free | Trial | 1,000 lookups/month, dashboards on the customer's own data (no sample or dummy data, requirement 18) |
| Growth | Small advertisers | 250k lookups, 3 seats, traffic analytics, alerts |
| Business | Lead-gen / affiliate networks | 5M lookups, 10 seats, bulk jobs, webhooks, SSO |
| Enterprise | Networks / platforms | Custom volume, SLA, dedicated support, data export |

---

## 7. Roadmap

| Phase | What | Who | Blocker |
|---|---|---|---|
| **0: finish** (now) | Step 3 done; final verification; Lovable Addendum 3 | Me + you | None |
| **1: internal product** | Analytics mart (sections A–I as daily JSON, written only under our project's S3 folder); `ip_profile` verdict (your standard); app dashboards (Overview, Traffic Quality, Reasons, Network, Geography, Outcomes, Vendors, Data Health) on your own traffic | Me (pipeline) + Lovable (UI) | None |
| **2: fast API** | DynamoDB `ip_profile`; API Gateway with keys, usage plans and metering; bulk endpoint (live proxycheck.io only with your budget approval) | Me (code) + **AWS admin** (create table, API Gateway, IAM role: the builder role can't create these) | Admin time |
| **3: SaaS shell** | Sign-up, orgs, roles, API keys page, Stripe billing, usage, docs portal, alerts | Lovable | Stripe account |
| **4: customer data** | Customers upload or stream their own traffic; per-tenant analytics; webhooks | Me + Lovable + admin | Legal (section 0) |
| **5: sell** | Pricing page, trial, DPA, privacy policy, status page, SOC 2 roadmap | You + legal | **Vendor licences + privacy** |

**Phase 1 can start as soon as step 3 finishes.** It needs no admin and no new AWS services.

---

## 8. Risks and how they are handled

| Risk | Handling |
|---|---|
| Reselling vendor data breaks licences | Legal check before any external sale; sell derived verdicts |
| Real customers on VPN/proxy are marked bad under the standard | Keep your standard; show `signal_type` and the strict view, and publish the wrong-flag rate (51% all reasons, ≈5% excluding anonymiser-only) so buyers choose their own cut-off |
| proxycheck.io cost as usage grows | Cache-first; re-check only after 30 days; stay inside 50k/day enrichment + your 30k; any increase is your decision |
| FraudLogix coverage shrinking (TUNE clicks fell to about 5k/month) | proxycheck.io now covers every IP; FraudLogix becomes a bonus signal |
| Stale answers | Latest-wins rules, 30-day re-check, freshness shown on every page |
| A bad run corrupts the tables | Checks before publish, snapshots, rollback copies |
| Personal data | DPA, access logs, no raw IPs in URLs or logs. A retention rule (removing old IPs) is **your decision**: nothing is deleted without it (requirement 14) |
