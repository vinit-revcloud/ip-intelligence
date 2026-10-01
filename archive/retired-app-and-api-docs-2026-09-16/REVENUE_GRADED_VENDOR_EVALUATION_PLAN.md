# Revenue-Graded Vendor Evaluation Plan

Grade every IP address by what its sessions and leads actually earned, then score every IP vendor against that grade, daily. At the same time, make the teammate's IP Lookup API the only API.

**Status:** plan, not built yet · **Sources:** `unified.unified_session_summary`, `sampledb.revenue_leads_plus` · **Cadence:** daily · **Date:** 16 Sep 2026

## Summary

Three pieces of work: a daily evaluation job that labels recent session IPs by lead revenue and scores every vendor on them; switching off our API so the teammate's API is the only one; and the app pages for per-vendor tables and metrics, served through the teammate's API.

- **20k+ sessions per evaluation:** starting 7 days ago, going back until there are 500 revenue IPs (about 60 days), 90 days at most.
- **7 sources scored per IP:** 6 vendors plus the session table's own IP fields.
- **2 labels, as in the MoM:** revenue > 0 = human, otherwise = bot.
- **Headline metrics per vendor:** FPR and accuracy, plus precision, recall, coverage and location match.

**Measured today, for the MoM window as written (sessions 4–9 Sep):** 20,003 sessions, 8,791 IPs, 175 leads, 159 IPs with a lead, **49 IPs with non-zero revenue**. Every one of these IPs is already in our tables, and 10,285 of the 10,286 IPs seen those days have a proxycheck.io answer. Leads join to sessions reliably on `utm_content = session_id`. 49 revenue IPs are too few for a stable FPR, which is why the window keeps extending back until it holds at least 500.

## Decisions and assumptions

### Decided (16 Sep)

| Topic | Decision |
|---|---|
| APIs | The teammate's IP Lookup API (`GET /v1/ip/{ip}`) is the only API. Ours (`ipintel-findings-api`) is removed completely. |
| Labels | Strict, as in the MoM. An IP with a lead whose revenue is above 0 is **human**. Every other IP in the window (zero-revenue lead, or no lead) is **bot**. |
| Window | Sessions from 7 days ago backwards until there are 20,000 sessions and at least 500 revenue IPs, never further than 90 days. The last 7 days are always left out, so lead revenue has time to appear, and nothing old is applied to today. |
| Cadence | Daily, after the morning load. Each day's results are kept, so trends can be compared. |
| Leads source | `sampledb.revenue_leads_plus`, joined on `utm_content = session_id`. |

### Assumptions to confirm (the plan uses these unless told otherwise)

1. **"Revenue" means `expected_revenue`.** About 12% of recent leads have it above 0. The `calculated_value_*` columns are empty for recent leads.
2. **Lead stage:** `lead_status_category` gives the ladder below_intro → intro_qualified → meeting → listing → closed. `furthest_stage` and `stage` are kept for detail. This is the MoM's `lead_category`.
3. **MoM step 6, where the note has a blank:** read as "if FraudLogix says bot or proxy, but the lead reached the meeting stage or later, that flag is *wrong*". The plan reports this as a separate "stage override" view next to the strict label, so the headline numbers stay strict.
4. **"Flagged" for a vendor** means any of proxy, VPN, Tor, datacenter, bot, compromised or scraper. A separate "bot only" score uses just `is_bot`, which only FraudLogix and the session table answer.
5. **Lead dates:** only leads created on or after the window's first session day count. Leads from years ago are never used.

> **Consequence of strict labels.** Most IPs have no lead, so under strict labels about 99% of the window is "bot". A vendor that flags nobody will therefore show very low accuracy, and one that flags everybody will show high accuracy. FPR, which only looks at revenue IPs, is not affected. The app will show accuracy next to precision and recall, plus the stage-override view, so nobody reads accuracy alone.

## What exists today, and what changes

| Part | Today | From now on |
|---|---|---|
| Daily load `ipintel-free-daily` | 07:30 UTC: new IPs from both base tables, free vendors, resolved answers, queue, reports | **keep** + starts the evaluation job when it finishes |
| proxycheck.io job `ipintel-proxycheck-daily` | 50k/day: queue, last 30 days, then backlog; merges answers from our API's live lookups | **keep** + IPs in the evaluation window go right after the queue. The live-lookup merge stays for the teammate API if it saves answers (part D). |
| Unified refresh | After each passed run, `unified.ip_geo` / `unified.ip_intelligence` are replaced with checked copies | **keep**. This is what the teammate API reads. |
| Tables in `ipintel_curated` | ip_geo, ip_intelligence, analytics, scorecards, ip_occurrences, ip_resolved, proxycheck_queue | **keep** + 5 new evaluation tables |
| Truth for location `qualified_lead_ips` | 2,105 fixed customer addresses, built 10 Sep | **replace** for scoring with the daily revenue-graded window. Keep it for history. |
| Vendor scorecards `vendor_overview_geo/_proxy` | Agreement between vendors; FPR on 210 confirmed humans | **replace** in the app with the evaluation metrics. The tables stay, but are no longer the headline. |
| Reports (`geo_accuracy.json`, `enrichment_coverage.json`) | Rebuilt after every run, served by our API | **keep** the files; served by the teammate API (part D) |
| Our API `ipintel-findings-api` | /lookup, bulk, /tables, pipeline control, reports, vendor registry; the Lovable app uses it for every page | **remove** (part A) |
| Teammate API `9w07dr3qq2` | `GET /v1/ip/{ip}`; reads the unified tables; calls proxycheck.io live without saving | **the only API** + read-only report endpoints and saving live answers (part D) |
| Lovable app | Lookup, tables, pipeline control, reports, all through our API | **rebuild data access** on the teammate API; new vendor-evaluation pages (part C) |
| Pipeline control in the app | Pause, run now, budget, base tables (writes through our API) | **read-only** status in the app; changes are made in AWS by the owner (runbooks) |
| Safety fence, alarms, email alerts | Boundary, IAM checks, CloudTrail review, 6 alarms | **keep** + checks for the evaluation job |

## How it will work

1. **07:30 UTC:** the daily load adds new IPs (unchanged).
2. **Right after:** the proxycheck.io job runs. The queue goes first, then any evaluation-window IP without an answer, then the last 30 days, then the backlog. The unified tables are refreshed.
3. **Then, the evaluation job (new):** choose the window, join leads, label IPs, collect every vendor's answer, score, save the day's results, and export JSON for the app.
4. **Any time:** the teammate API answers IP lookups from the unified tables, and serves the evaluation and report JSON read-only to the app.

## A · Retire our API

"Removed completely" is done in two stages, because the safety fence deliberately forbids deleting this function and its role.

1. **Switch off (by us, reversible):** set the function's reserved concurrency to 0 so every call is refused, and remove its public Function URL. Keep the code and role, so it can be brought back in minutes.
2. **Clean up what depended on it:**
   - Remove the lookup, bulk, table, control and report sections from the Lovable prompts.
   - Mark it retired in the User Manual and System Guide.
   - Stop the checks that call it (the scheduled check, `compare_resolved.py`).
   - Its S3 answer cache (`proxycheck/live/by-ip/`) stops being written; nothing else uses it.

3. **Delete (by an AWS admin, after 7 quiet days):** the Lambda `ipintel-findings-api` and the role `ipintel-api-role`. The fence blocks the builder role from doing this, so it has to be an admin action.

> **What stops working when it is switched off.** • Every Lovable page that reads data, until part C and part D are live. • Pausing, running jobs and changing the budget from the app. • Our rule "API miss → ask proxycheck.io → save → merge into the tables", unless the teammate API starts saving its live answers (D2). For that reason, stage 1 is done last, once C and D are ready.

## B · Vendor evaluation pipeline

A new step in `ipintel-free-daily` (`action: "evaluate"`), started when the daily load and the proxycheck.io run finish. It writes only to `ipintel_curated`.

### B1 · Choose the window (MoM step 1)

- **Sessions:** `unified.unified_session_summary` rows with a session IP and `session_date` in [today − 90, today − 7].
- **Order:** newest first, then by session_id.
- **Where to stop:** the earliest day at which the running totals reach both **20,000 sessions** and **500 IPs with revenue**. At 90 days it stops anyway and the run is marked "small sample".
- **Saved:** the window's first and last day, session count, IP count and lead count, in `eval_runs`.
- **Private and reserved IPs** are dropped, as everywhere else.

### B2 · Join the leads (MoM step 2)

- `sampledb.revenue_leads_plus` rows where `utm_content = session_id`, `date_pst` ≥ the window's first day, and `fake` kept as a field.
- **Kept per lead:** id, date, `expected_revenue`, `lead_status_category`, `furthest_stage`, `stage`, `is_meeting`, `is_listing`, `is_closed`, `is_deal`, `fake`, `phone_verified`, and the lead's `state_name`, `city_name` and `zip_code` (for location scoring).
- **Not copied:** names, emails, phones or street addresses.

### B3 · Grade each IP (MoM steps 3 and 5)

One row per IP in the window:

- **Activity:** sessions, bot-click sessions (`is_bot_click`), leads, and total `expected_revenue`.
- **Stage:** the best `lead_status_category` reached (the `lead_category`) and the furthest stage.
- **`revenue_class`:** `nonzero` or `zero`, or `no_lead` when the IP has no lead.
- **Strict label:** **human** if revenue > 0, otherwise **bot**.
- **Stage-override label (assumption 3):** **human** if revenue > 0 or the best stage is meeting, listing or closed; otherwise **bot**.

An IP with several leads takes its best result: any revenue makes it human.

### B4 · Every vendor's answer (MoM step 4)

| Source | Location | Proxy / bot | Coverage in the 4–9 Sep window |
|---|---|---|---|
| IP2Location DB11 | yes | — | every IP |
| IP2Proxy PX12 | — | proxy, VPN, Tor, datacenter | every IP (answers only for listed proxies) |
| FraudLogix | — | proxy, VPN, Tor, datacenter, **bot** | 5,039 IPs (tune-click IPs only) |
| proxycheck.io | yes | proxy, VPN, compromised, risk score | 10,285 of 10,286 |
| ipinfo.io, ipwho.is | yes | — | partial; tie-breakers fill in about 1,000 a day |
| Session table's own fields (`ip_is_proxy`, `is_bot_click`, `ip_region_name`…) | yes | proxy, **bot click** | every session; region filled on 45% |
| Our resolved answer | yes | yes | every IP |

Answers are read from the tables, which the daily jobs keep full. The proxycheck.io job gets one new rule: IPs in today's evaluation window that it has not answered go right after the queue. Session IPs from the last 90 days (excluding the last 7) number 133,964, and 44,180 of them have no proxycheck.io answer yet. The first catch-up therefore takes about one day's 50,000 budget. After that, about 1k a day. Answers are taken as they were on evaluation day and saved with the day's results, so earlier days can be reproduced.

### B5 · Score every IP against every vendor

One row per day × IP × source:

- **The vendor's own answer:** location fields and flags.
- **`flagged`:** any flag set, or empty if the vendor gave no proxy answer.
- **`bot_flag`**, where the vendor answers bot.
- **Outcome** under the strict label and again under the stage-override label: `TP`, `FP`, `TN` or `FN`, with "bot" as the positive class. A vendor with no answer gets `no_answer`.
- **Location match** for IPs whose lead has an address: state, city and ZIP, using the same matching rules as today.

### B6 · Which lead stages decide the bot status (MoM "identify which stages")

For each lead category and furthest stage, per source:

- number of IPs;
- share with revenue;
- share the vendor flagged;
- share flagged as bot.

A stage where revenue is common but a vendor flags many IPs shows that vendor's false alarms. A stage with no revenue and a high flag rate shows where flags are useful. This table is also the evidence for (or against) the stage-override rule.

### B7 · FraudLogix check (MoM step 6)

A dedicated view lists IPs that FraudLogix flags as bot or proxy while their lead has non-zero revenue, or reached the meeting stage or later. It shows each IP's stage, revenue and flag reason. These are FraudLogix's wrong calls, and they are counted as false positives in both label views.

### B8 · Daily run, checks and exports

- Runs as a hand-over from the daily chain. Staging tables are removed at the end. Results are merged by run date, so re-running a day replaces that day only.
- **Checks:**
   - The window reached 20,000 sessions (and 500 revenue IPs, or is marked small sample).
   - Every window IP has exactly one label.
   - Every IP × source row exists.
   - TP + FP + TN + FN + no_answer adds up to the window's IP count for every source.
   - No personal fields were copied.
   - The usual production-safety checks pass.

- Exports `serving/ipintel_curated/vendor_eval_latest.json` (metrics, stage table, window) and a per-day history file for the app.

## Metrics, defined (MoM step 8)

"Bot" is the positive class. Each source is scored only on IPs it answered. Coverage shows how many that is.

| Metric | Formula | Reads as |
|---|---|---|
| **FPR** (false positive rate) | FP / (FP + TN) | Of the revenue-earning (human) IPs, the share the vendor flagged. Lower is better. This is the main metric. |
| **Accuracy** | (TP + TN) / (TP + FP + TN + FN) | Share of IPs the vendor classed the same way as the label |
| Precision | TP / (TP + FP) | When the vendor flags, how often the IP earned nothing |
| Recall (detection rate) | TP / (TP + FN) | Of the non-earning IPs, the share the vendor flagged |
| Coverage | answered / window IPs | How many window IPs the vendor answered at all |
| Bot-only FPR and accuracy | the same, with `is_bot` in place of "any flag" | FraudLogix and the session table only |
| Location match | state / city / ZIP match ÷ IPs with a lead address and a vendor answer | The geo comparison, now on recent revenue-graded leads |

Every metric is computed under both label views and shows its sample size. A 95% confidence interval (Wilson) is shown next to FPR and accuracy, so small samples are visible.

## New tables (all in `ipintel_curated`, Iceberg)

| Table | One row per | Main columns |
|---|---|---|
| `eval_runs` | run day | run_date, window_start, window_end, sessions, ips, leads, revenue_ips, small_sample, status |
| `eval_ip_labels` | run day × IP | ip_address, sessions, bot_click_sessions, leads, revenue_total, revenue_class, lead_category, furthest_stage, meeting_or_later, label_strict, label_stage, lead_state, lead_city, lead_zip |
| `eval_vendor_ip` | run day × IP × source | source, answered, flagged, bot_flag, is_proxy, is_vpn, is_tor, is_datacenter, is_compromised, state, city, zip_code, outcome_strict, outcome_stage, state_match, city_match, zip_match |
| `eval_vendor_metrics` | run day × source × label view × segment | ips, answered, tp, fp, tn, fn, fpr, fpr_low, fpr_high, accuracy, accuracy_low, accuracy_high, precision, recall, coverage, bot_fpr, bot_accuracy, state_pct, city_pct, zip_pct |
| `eval_stage_signal` | run day × source × lead category × furthest stage | ips, revenue_ips, flagged_ips, bot_flagged_ips, revenue_share, flag_share |

Kept for 400 days. Weekly maintenance adds them to its compaction list.

## C · The app (MoM step 7)

### Data access

With our API removed, the app reads everything through the teammate's API, using the endpoints listed in part D and the same bearer token. Pipeline status in the app is read-only.

### Pages

1. **Vendor Evaluation (overview).**
   - The window: dates, sessions, IPs, leads, revenue IPs, and a small-sample warning.
   - A label-view switch: strict or stage override.
   - One row per source: FPR (with interval), accuracy (with interval), precision, recall, coverage, bot-only FPR, and state/city match.
   - A 30-day trend of FPR and accuracy per source.

2. **One table per vendor.** One tab each: IP2Location, IP2Proxy, FraudLogix, proxycheck.io, ipinfo.io, ipwho.is, session table, our resolved answer. Each row is an IP in the window with:
   - the label, revenue, lead category and furthest stage;
   - the vendor's location and flags, and the outcome (TP/FP/TN/FN);
   - location match.

   Filters: outcome, label, lead category, flagged. Paged, with a CSV download.

3. **IP comparison.** Search an IP to see one row per source, location and risk side by side, with its label and leads (stage and revenue only, no personal data).
4. **Stage signal.** The B6 table as a heat map: lead category × source, coloured by flag share, with the revenue share alongside.
5. **FraudLogix check.** The B7 list.
6. **Kept:** IP Lookup (now calling `GET /v1/ip/{ip}`), Location Accuracy, Enrichment Coverage, and a read-only pipeline status. Removed: Resolved IPs browsing, bulk lookup, pipeline control and budget editing, unless part D adds them.

## D · Teammate API changes (owned by the teammate)

| # | Change | Why |
|---|---|---|
| D1 | Read-only endpoints serving the pipeline's JSON files from `s3://…/ip-intelligence/serving/ipintel_curated/`: `/v1/eval/latest`, `/v1/eval/history`, `/v1/reports/coverage`, `/v1/reports/geo-accuracy`, `/v1/pipeline/status`. Per-vendor IP rows come from Athena on `eval_vendor_ip`, paged. | The app's only data path |
| D2 | Save each live proxycheck.io answer to `s3://…/ip-intelligence/proxycheck/live/dt=YYYY-MM-DD/` in the same shape our API used | Keeps "look up → ask proxycheck.io → into the tables"; our proxycheck.io job already merges that folder |
| D3 | Say which proxycheck.io key it uses. If it is the paid key, reserve queries on the shared counter (`ipintel-pipeline-state`, item `quota/<date>`) before calling | So its calls and our 50k/day never exceed 80,000 together |
| D4 | Optional: read location from `ipintel_curated.ip_resolved`, or use its vendor order and statuses | Serves the checked, conflict-aware answer |
| D5 | Grant its role read access to `ipintel_curated` and the serving folder (S3 GetObject, Glue GetTable, Athena in its own workgroup); for D2, PutObject on `proxycheck/live/*` | Its role is outside our fence; an admin or the teammate adds these |

## Production safety

- `sampledb.revenue_leads_plus` and `unified.unified_session_summary` are only read. The fence already blocks writes outside `ipintel_curated` and `ip-intelligence/`. The permission check at the start of each run gains `sampledb.revenue_leads_plus` to its "must be refused" list.
- No personal data leaves the leads table: names, emails, phones and street addresses are never selected.
- The evaluation step reads about 1–2 GB a day in Athena, within the 10 GB-per-query cap.
- Switching off our API is reversible. Deleting it is an admin action after 7 days.

## Acceptance tests ("works 100%")

1. **Window:** the run's first and last day, sessions and revenue IPs match an independent Athena query written from the MoM rules. None of it falls in the last 7 days, and it never goes back more than 90.
2. **Join:** the lead count equals a direct `utm_content = session_id` count for the same window.
3. **Labels:** every window IP has one label. Revenue IPs are all human under both views. A hand-checked sample of 50 IPs matches.
4. **Outcomes:** for every source, TP + FP + TN + FN + no_answer equals the window IP count. Recomputing FPR and accuracy from `eval_vendor_ip` gives exactly `eval_vendor_metrics`.
5. **FraudLogix check:** every listed IP has a FraudLogix flag and revenue > 0 (or meeting or later). None is missing, checked with an independent query.
6. **Location:** match rates for the resolved answer equal those from the existing accuracy code run on the same IPs.
7. **Daily:** two consecutive scheduled runs succeed, keep both days, and re-running a day replaces only that day.
8. **API switch-off:** our Function URL returns nothing. The teammate endpoints (D1) return the same numbers as the tables. Every app page loads from them.
9. **Safety:** the permission check and CloudTrail review pass, and production catalog timestamps are unchanged by us.

## Order of work

| Step | Work | Who | Depends on |
|---|---|---|---|
| 1 | Confirm the five assumptions | Owner | — |
| 2 | Build the evaluation tables and step (B1–B8); dry run on today's data; acceptance tests 1–6 | Us | 1 |
| 3 | Give evaluation-window IPs proxycheck.io priority; first catch-up run | Us | 2 |
| 4 | Schedule it daily; two passing days (test 7) | Us | 3 |
| 5 | Teammate API changes D1–D3 (and D5 grants) | Teammate / admin | 2 |
| 6 | New Lovable prompt: data access on the teammate API, evaluation pages, retired pages removed | Us, then owner pastes | 5 |
| 7 | Switch off our API (stage 1); update the manual, the guide, the scheduled check and memory; test 8 | Us | 6 |
| 8 | Delete our Lambda and role (stage 3) | Admin | 7 + 7 days |

## Risks

- **Strict labels skew accuracy.** Mitigated by showing FPR, precision, recall and the stage-override view together.
- **Few revenue IPs.** About 8 a day (49 in 4–9 Sep). Reaching 500 needs roughly 60 days, and the 90-day cap may be hit, in which case the run is marked small sample. Intervals show the uncertainty.
- **Revenue lag.** Leads keep gaining revenue after 7 days, so recent weeks slightly under-count humans.
- **Changing IPs.** An IP can be a person one day and a relay the next. Vendor answers are taken as of evaluation day.
- **The app goes dark if part A runs before C and D.** The order above prevents that.
- **Budget.** If the teammate API uses the paid key without reserving on the shared counter (D3), the combined daily use can reach 80,000 early.

---

Queries behind the numbers in this plan: `build/pipeline/sql/checks/leads_plus_profile.sql`, `mom_window_probe.sql`, `mom_window_fields.sql`. Nothing in this plan has been built yet.
