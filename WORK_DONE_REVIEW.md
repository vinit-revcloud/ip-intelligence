# Work Done — Review Document

Everything changed in the IP intelligence project on 15–17 Sep 2026: what was done, why, where it lives, how it was checked, how to check it yourself, and how to undo it. Items marked **Decision by me** are judgement calls to review.

All AWS work used the `ipintel-builder` role (profile `ipintel-builder`), account 221490242148, us-west-2. Times are UTC.

---

## 1. Summary

| Area | Result |
|---|---|
| **Daily pipeline** | Running. 07:30 load, then the proxycheck.io run (78,000/day since 17 Sep; experiment IPs first), then a refresh of all six `unified` project tables |
| **Bot / not bot** | Done for all 133,954 session IPs: `SESSION_IP_BOT_LABELS.md` (section 15) |
| **Proxy answer for every IP** | Experiment IPs 100%; last-90-day session IPs 99.2%; all addresses 90.8%, about 6 days to 100% |
| **App** | New prompt `LOVABLE_PROMPT_APP_V2.md` with data in `app-data/` |
| **Last 30 days of IPs** | 42,768 of 42,769 addresses answered by proxycheck.io. One is still undecided (last seen 9 Sep) |
| **One-time lead-IP analysis** | Done: `LEAD_IP_VENDOR_ANALYSIS.md` |
| **Our API** | Blocked. The AWS admin still has to delete it |
| **`unified` project tables** | All 6 kept and refreshed with the latest data |
| **Unused tables** | 15 dropped from `ipintel_curated`. 5 more, in `ipintel_analytics` and `ipintel_reference`, are waiting for the admin |
| **Production tables** | Only read. No project write touched anything outside the project (CloudTrail check, section 11) |
| **Documentation** | Markdown: `docs/USER_MANUAL.md`, `docs/SYSTEM_GUIDE.md`, `FINAL_IMPLEMENTATION_PLAN.md`, `ADMIN_DELETION_STEPS.md` |

---

## 2. proxycheck.io budget: 50,000 for enrichment, 30,000 for lookups (15 Sep 13:00; replaced on 17 Sep, section 15a)

- **What:** DynamoDB table `ipintel-pipeline-state`, item `job / proxycheck-daily`. The values are:
  - `daily_budget` = 50000
  - `live_reserve` = 30000
  - `topup_keep` = 30000
  - `queue_extra` = 0
- **Code:** `job_proxycheck.py` now reads `queue_extra`, so queued addresses no longer borrow from the lookup share.
- **Why:** owner request.
- **Check:** the values above were read back on 16 Sep 20:05. Daily use on 16 Sep: 49,999 by the pipeline.
- **Review note:** the 30,000 lookup share was for our API, which is now retired, so it is **unused**. The 22:00 top-up also stops at 50,000 in total. Lowering `live_reserve` and `topup_keep` would give that capacity to enrichment. **Decision for you.**
- **Undo:** set the old values (`daily_budget` 70000, `live_reserve` 10000, `topup_keep` 2000); the earlier values are in the audit items.

## 3. Refreshing the `unified` tables ("publish")

- **What:** after every Job B run that passes all its checks, the pipeline replaces the **files** behind the six project tables in `unified` with checked copies of the `ipintel_curated` tables. The Glue catalog is never changed; the project's safety rules forbid it.
- **Code:** `build/pipeline/src/publish.py`, run as `{"action":"publish"}` inside `ipintel-proxycheck-daily`.
- **History:**
  - **15 Sep 13:09:** first publish, 2 tables (`ip_geo`, `ip_intelligence`).
  - **16 Sep 19:51:** extended to all 6, on your instruction to keep the overview tables and update them with the latest data. Dry run at 19:49, real run at 19:51; all checks passed.
- **Steps, per table:**
  1. Check the unified table still has its expected location, columns and layout.
  2. Archive the 11 Sep original once.
  3. Build a copy in the table's own layout.
  4. Check the copy: rows, duplicates, file layout, identical rows.
  5. Save a rollback copy, then swap the files.
  6. Re-check. On failure, the previous files are put back automatically.
- **Result (16 Sep 19:51):**

| unified table | Rows | Equal to `ipintel_curated` | Layout |
|---|---|---|---|
| `ip_geo` | 5,092,551 | yes | 64 buckets |
| `ip_intelligence` | 9,621,189 | yes | 64 buckets |
| `ip_intelligence_analytics` | 9,621,189 | yes | 64 buckets |
| `ip_geo_analytics` | 262,108 | yes | 2 files |
| `vendor_overview_geo` | 4 (all dated 16 Sep) | yes | 1 file |
| `vendor_overview_proxy` | 3 (all dated 16 Sep) | yes | 1 file |

- **Catalog:** the tables' last-change times in Glue are still 11 Sep for all six, so no definition was changed.
- **Backups:**
  - 11 Sep originals: `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/archive/unified-2026-09-11/<table>/`
  - Latest rollback copy: `ip-intelligence/publish-previous/<table>/`
- **Decision by me:**
  - `unified.vendor_overview_proxy.bot_metric_status` is declared `varchar(25)` in `unified`, so its text is cut to 25 characters there. The full text is in `ipintel_curated`.
  - The two analytics tables in `unified` held 11 Sep benchmark rows (MaxMind, DB-IP and others). They now hold the current data, the same as the other four. You asked for all overview tables to be kept on the latest data; tell me if the analytics tables should instead stay frozen.
- **Check yourself (Athena):** `build/pipeline/sql/checks/unified_six_verify.sql`
- **Undo:**
  - **Stop publishing:** set `publish_unified` to false on `job/proxycheck-daily`.
  - **Roll back one table:** copy `publish-previous/<table>/` back into `unified/<table>/d=2026-09-11/`, then remove the other files there.

## 4. Enriching the last 30 days first (15 Sep evening)

- **What:** the proxycheck.io selection (`_selection_sql` in `job_proxycheck.py`) now sends, in order:
  1. queued addresses;
  2. addresses first seen today;
  3. **every address seen in the last 30 days without a proxycheck.io answer**;
  4. undecided addresses from the last 90 days;
  5. older addresses.
- **Result:** after the 16 Sep 07:42 run, 100% of the 42,769 addresses in the window are answered, up from 45.6% the evening before.
- **Check:** `build/pipeline/sql/checks/enrichment_30d_summary.sql`, or `enrichment_coverage.json` in S3.

## 5. Reports rebuilt by the daily jobs (15 Sep)

- **What:**
  - `accuracy.py` writes `serving/ipintel_curated/geo_accuracy.json`: vendor location against 2,105 customer postal addresses.
  - `coverage.py` writes `enrichment_coverage.json`: 30-day enrichment and rows added per day.
  - Both jobs rebuild both files and record a check.
- **Review note:** the retired API used to serve these files. They are still written daily, and can be read from S3 or recomputed in Athena.

## 6. Location rules v2 (16 Sep 10:42)

- **What:** `build/pipeline/src/resolved.py`, which feeds `ip_resolved`.
  - **City matching:** spelling-tolerant (for example, St. Louis = Saint Louis).
  - **New statuses:** `agreed`, `nearby` (same state, within 25 km), `same_state`, and `vendors_disagree` (states differ).
  - **Which vendor wins, based on evidence:**
    - State: ipinfo.io > ipwho.is > IP2Location > proxycheck.io.
    - City: ipinfo.io > IP2Location > ipwho.is > proxycheck.io.
- **Why:** 53% of 30-day addresses were labelled "disagree", but most were the same state with a nearby city.
- **Checks:**
  - The API's Python and the SQL gave identical answers on 1,500 addresses.
  - A replay on the 2,105 customer addresses showed no loss: 1,316 states right before and after.
  - A first version lost 34 correct states. It was caught by that replay and corrected before going live.
- **Result (last 30 days):**

| Location status | Addresses |
|---|---|
| agreed | 19,596 |
| nearby | 6,541 |
| same state | 9,181 |
| states differ | 7,448 |

- **Also:** ipinfo.io and ipwho.is now spend their daily requests (about 500 each) on the 30-day conflicts first (`job_free.py`, step 6).
- **Backup of old rules:** `archive/geo-rules-before-2026-09-16/`
- **Decision by me:** the 25 km threshold, and learning the vendor order from the same 2,105 addresses they are scored on (small differences between vendors shouldn't be over-read).

## 7. One-time lead-IP vendor analysis (16 Sep)

- **What:**
  - **Population:** sessions from 18 Jun to 9 Sep in `unified.unified_session_summary`, joined to `sampledb.revenue_leads_plus` on `utm_content = session_id`, with the lead created on or after the session.
  - **Size:** 2,768 lead IPs and 3,235 leads.
  - **Label:** revenue above 0 → real person (427 IPs); otherwise → bot (2,341 IPs).
  - **Graded:** FraudLogix, IP2Proxy, proxycheck.io and the session table's own fields.
- **Before running:** 834 lead IPs had no proxycheck.io answer. I sent them once through our API's bulk lookup, before it was blocked. That used 834 queries (842 reserved) from the lookup share. Job B then merged the answers (10/10 checks).
- **Results:**

| Vendor | FPR | Accuracy | Precision | Answered |
|---|---|---|---|---|
| FraudLogix | 22.4% | 46.7% | 91.5% | 84% |
| proxycheck.io | 32.6% | 24.5% | 73.7% | 100% |
| Session table | 36.1% | 25.3% | 73.4% | 100% |
| IP2Proxy | — | — | — | 14 IPs only |

- **Findings:**
  - No below-intro IP had revenue; 85% of meeting IPs did.
  - FraudLogix wrongly flagged 80 real-person IPs, 77 of them as `PROXY`.
- **Checks (all passed):**
  - The IP and lead counts equal an independent join.
  - For each vendor, TP + FP + TN + FN + not answered = 2,768.
  - A separate SQL recount of proxycheck.io matches exactly.
  - The FraudLogix list is correct.
- **Files:**
  - `LEAD_IP_VENDOR_ANALYSIS.md`
  - `analysis/lead-ip-vendor-2026-09/` (CSVs and `summary.json`)
  - Code: `build/pipeline/analysis/lead_ip_vendor.py` (read only; can be re-run)
- **Decisions by me, to review:**
  - **Revenue column:** `expected_revenue`.
  - **Blank revenue:** counted as 0. **1,315 of the 2,341 "bot" IPs have blank revenue**, which pulls accuracy down.
  - **"Flagged":** any of proxy, VPN, Tor, datacenter, bot, compromised or scraper.
  - **Window:** the full 90 days, because 500 revenue IPs can't be reached.
  - **Private IPs:** excluded.

## 8. Unused `ipintel_curated` tables removed (16 Sep ~17:00)

- **What:** 15 tables left over from the 3–11 Sep build phases were dropped from the Glue catalog: `geo_src`, `intel_src`, `ip_business_outcome`, `ip_dim`, `ip_flags`, `ip_geo_observations`, `ip_intel_observations`, `ip_intel_pc`, `ip_list`, `ip_pool`, `ip_proxy_check`, `ip_vendor_result`, `lead_truth`, `lead_truth_v2`, `pc_live`.
- **Safety:**
  - Before dropping: confirmed that each one was an external (non-Iceberg) table stored in the project folder, and that no running code used it.
  - Definitions (and partitions) saved to `archive/curated-legacy-tables-2026-09-16/` and to S3.
  - Data files untouched: 170 files under `ip-intelligence/curated/` before and after.
- **Remaining in `ipintel_curated` (12, all used by the daily jobs):** `db11_bucketed`, `ip_geo`, `ip_geo_analytics`, `ip_intelligence`, `ip_intelligence_analytics`, `ip_occurrences`, `ip_resolved`, `proxycheck_queue`, `px12_bucketed`, `qualified_lead_ips`, `vendor_overview_geo`, `vendor_overview_proxy`.
- **Undo:** recreate any of them from its saved definition; the data is still in place.
- **Still to do:** delete only those 15 data folders, on or after 23 Sep with your go-ahead.

## 9. Other unused tables (16 Sep 20:00)

- **Found:** every table in any database whose data is in the project folder.
- **This project's, unused (created 3–8 Sep, benchmark phase):**
  - `ipintel_analytics.geo_accuracy`, `geo_score`, `pairwise_agreement`, `risk_score`
  - `ipintel_reference.zip_centroid`
  - Definitions backed up to `archive/other-project-tables-2026-09-16/` and to S3.
  - The safety rules don't let the builder role drop tables outside `ipintel_curated`, so they are listed for the admin.
- **Not ours:** the `ip-database` tables (`dashboard_summary`, `db11_csv`, `db11_parquet`, `ip_analytics`, `ip_dim`, `isp_value_analysis`, `px12_csv`, `px12_parquet`) existed before this project; the build log records them as pre-existing, read-only input. **Left untouched.**

## 10. Our API retired (16 Sep ~17:00)

- **What:**
  - `ipintel-findings-api` reserved concurrency set to 0, so every call returns HTTP 429 (checked with curl).
  - The teammate's API health check returns 200.
  - URL config, resource policy and settings (without secrets) saved to `archive/api-removed-2026-09-16/`.
  - Code moved there from `build/api/`, along with `compare_resolved.py`.
- **Also retired:** the Lovable app, which depended on this API. Its prompts, `API_AND_UI.md` and the old plan are in `archive/retired-app-and-api-docs-2026-09-16/`.
- **Nothing in the pipeline depends on it.** The daily jobs never called it.
- **Still to do (admin):** delete the Function URL, the Lambda, the log group and the role `ipintel-api-role`. The builder role is refused all of these (explicit denies confirmed with the IAM simulator). Steps are in `ADMIN_DELETION_STEPS.md`.
- **Undo, before deletion:** `aws lambda delete-function-concurrency --function-name ipintel-findings-api`
- **Note:** CloudTrail also shows a role named `ipintel-lookup-api-role`, which is **not** one of ours; it may belong to the teammate's API. It was not touched.

## 11. Production safety evidence (16 Sep 20:05)

- **Only read, never written:** `raw.raw_tune_clicks`, `unified.unified_session_summary`, `sampledb.revenue_leads_plus`.
  - Their catalog times moved today, but CloudTrail shows no write event naming any of them. The changes came from their own jobs.
- **Every project-role write in the last 26 hours** (CloudTrail):
  - Athena queries.
  - Glue create/update/delete in `ipintel_curated` (staging tables, plus the 15 drops).
  - Lambda code updates and the concurrency change on our own functions.
  - Log streams.
  - **No write aimed outside the project.**
- **Pipeline safety item:** not paused; production write access "none"; last activity review found nothing.
- **Alarms:** all 6 OK. Dead-letter queue empty.
- **Deletions:** nothing was deleted without a backup. No production data files were changed.

## 12. Documentation
- **Rewritten as Markdown:** `docs/USER_MANUAL.md` (analysts) and `docs/SYSTEM_GUIDE.md` (engineers), covering everything above. The old HTML docs, report and briefing pages are no longer maintained.
- **Plans and steps:** `FINAL_IMPLEMENTATION_PLAN.md` (status of every step) and `ADMIN_DELETION_STEPS.md` (the admin's commands and undo).
- **This document.**

## 13. Waiting / open

| Item | Owner |
|---|---|
| Delete our API (URL, Lambda, log group, role); drop the 5 unused benchmark tables | AWS admin |
| Delete the API lookup cache `proxycheck/live/by-ip/` after that | Me |
| Delete the data folders of the 15 dropped tables, from 23 Sep | Me, with your go-ahead |
| Blank `expected_revenue`: 0 or unknown? | You / mentor |
| Confirm the 78,000 / 2,000 split (applied 17 Sep, section 15a) | You |
| Copy `app-data/` into the Lovable project and paste `LOVABLE_PROMPT_APP_V2.md`; add `IP_LOOKUP_API_TOKEN` | You |
| Should the unified analytics tables stay current (as now) or frozen? | You |
| Daily evaluation job | Later, when asked |

## 14. How to check the main points yourself
- **Pipeline runs:** DynamoDB `ipintel-pipeline-state`, items `run#free-daily`, `run#proxycheck-daily`, `run#publish-unified` (newest first); each lists its checks.
- **Unified equals curated:** Athena, `build/pipeline/sql/checks/unified_six_verify.sql`.
- **30-day enrichment:** `build/pipeline/sql/checks/enrichment_30d_summary.sql`.
- **Analysis numbers:** `build/pipeline/sql/analysis/recount_proxycheck.sql`, or re-run `python build/pipeline/analysis/lead_ip_vendor.py` (read only).
- **API blocked:** `curl https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/health` returns 429.
- **Proxy coverage:** `build/pipeline/sql/checks/proxy_coverage_now.sql`, then `proxy_missing_profile.sql` for the gaps.
- **Bot labels:** re-run `python build/pipeline/analysis/session_ip_bot_labels.py` (read only).
- **Budget change:** DynamoDB item `audit` / `2026-09-17T09:47:23Z#update_job`.
- **Tables left:** `aws glue get-tables --database-name ipintel_curated --profile ipintel-builder` lists 12 names.

---

## 15. 17 Sep: bot / not-bot labels, proxy coverage for every IP, app v2

### 15a. Budget: 78,000 for enrichment (17 Sep 09:47)
- **What:** on `job/proxycheck-daily` the values changed from `daily_budget` / `budget_cap` 50000, `live_reserve` 30000, `topup_keep` 30000 to **78000 / 78000 / 2000 / 2000**.
- **Audit item:** `audit/2026-09-17T09:47:23Z#update_job`, with the old values and the reason.
- **Why:** the 30,000 reserve was for our retired API. The teammate API does not use our key: proxycheck.io counted 50,354 queries on 16 Sep, below our own 50,859 reservations.
- **Decision by me:** this follows your instruction "implement whatever is needed" for full proxy coverage. It replaces the earlier 50k / 30k split.
- **Undo:** set the old values back (`USER_MANUAL.md` → Change the enrichment budget).

### 15b. New backfill order: experiment IPs first (deployed 17 Sep 09:47)
- **What:** `_selection_sql` in `job_proxycheck.py` now picks, in order:
  1. queued addresses;
  2. addresses new today;
  3. **experiment IPs** (`session_ip` of session rows with an `experiment_id`);
  4. addresses seen in the last 30 days;
  5. addresses seen in the last 90 days;
  6. addresses with no conclusion.
- **Deployed** to `ipintel-free-daily` and `ipintel-proxycheck-daily`. Before deploying, I confirmed nothing was running and that the deployed package differed from the source only in this file.
- **Backup:** the previous package is in `archive/deployed-code-before-selection-2026-09-17/`.
- **Undo:** upload that zip to both functions.

### 15c. Today's remaining quota spent (17 Sep 09:48–09:55)
- **Run:** a manual top-up (`{"trigger":"manual","topup":true}`) sent 27,712 queries in 28 batches and added 55,158 rows. **10 / 10 checks passed.**
- **Publish:** `publish-unified` 09:55, passed.
- **Quota:** 77,999 of 80,000 reserved for 17 Sep.
- **Rows after:** `ip_geo` 5,171,012 · `ip_intelligence` 9,699,074.

### 15d. Proxy coverage now (`sql/checks/proxy_coverage_now.sql`, `proxy_missing_profile.sql`)

| Group | IPs | ≥ 1 proxy answer | proxycheck.io |
|---|---|---|---|
| Experiment session IPs, all time | 38,446 | 38,446 (100%) | 38,446 (100%) |
| Session IPs, last 90 days | 139,418 | 138,359 (99.2%) | 119,951 |
| All addresses in our tables | 4,960,008 | 4,504,977 (90.8%) | 205,265 |

- **90-day gaps:** 1,047 public addresses are missing, first in line on 18 Sep 07:30. The other 12 are IPv6 or private, which no vendor answers.
- **Everything else:** about 455,000 addresses, about 6 days at 78,000 a day *(projection)*.

### 15e. Bot / not-bot labels for every session IP (`SESSION_IP_BOT_LABELS.md`)
- **Script:** `build/pipeline/analysis/session_ip_bot_labels.py` (read only).
- **Scope:** 133,954 IPs and 350,329 sessions, 18 Jun to 9 Sep.
- **Labels:** real person 427 · lead without revenue 2,341 · no lead 131,186.
- **Checks:** all 5 passed.
- **Finding:** vendor flags are higher for real customers (32.6%) than for no-lead IPs (7.2%). 136 of the 139 flagged customers use Akamai, Fastly or Cloudflare, the networks behind iCloud Private Relay. Flags therefore cannot identify bots; the label comes from revenue, as the MoM asked.
- **Other outputs:** a per-experiment table for 32 experiments, in which every experiment IP has a proxy answer.

### 15f. App v2
- **Snapshot:** `build/pipeline/analysis/export_app_data.py` writes `app-data/*.json`. It covers:
  - lead IPs with every vendor's answer;
  - both analyses;
  - the Coverage and Accuracy reports;
  - proxy coverage;
  - both vendor scorecards.

  Ids such as experiment numbers are kept as text.
- **Prompt:** `LOVABLE_PROMPT_APP_V2.md`. It removes everything that used our retired API. Live IP lookup goes through the teammate API (server-side token `IP_LOOKUP_API_TOKEN`). All other pages read `public/data/`.

### 15g. Docs
`docs/USER_MANUAL.md` and `docs/SYSTEM_GUIDE.md` were updated for the new budget and order. `FINAL_IMPLEMENTATION_PLAN.md` and the memory notes were updated too.

### 15h. App data refreshed automatically (17 Sep 11:34)
- **What:** new `build/pipeline/src/app_export.py`. After every full, successful publish it writes the 9 app report files to `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/app/`.
  - The one-time analysis files come from `serving/app/static/` (uploaded 17 Sep).
  - DynamoDB `app/export` records the status.
  - A manual run uses `{"action":"app_export"}`.
- **Deployed** to both job Lambdas (nothing was running). Backup: `archive/deployed-code-before-app-export-2026-09-17/`.
- **Test:** a manual run at 11:34 wrote all 9 files, status `complete`.
- **App today:** you uploaded the 9 files (as of 11:30) on the new Data Upload page.
- **Not built:** pushing the files directly from the pipeline to Lovable. The safety review blocked it because it sends company data to an outside service. I also could not create a Secrets Manager secret (not allowed for my role).
- **Pending:** an AWS admin creates the read-only key `ipintel-app-reader` (`s3:GetObject` on `ip-intelligence/serving/app/*` only). After that the app reads S3 itself.
- **Presentation document:** `IP_INTELLIGENCE_SYSTEM_OVERVIEW.md`.

### 15i. Evidence-based bot verdict (17 Sep 15:00)
- **Why:** proxycheck.io has no bot field; proxy/VPN flags hit 32.6% of paying customers.
- **What:** new read-only `build/pipeline/analysis/session_ip_bot_verdict.py`, report `SESSION_IP_BOT_VERDICT.md`. It combines vendor network signals with session behaviour, and tests every rule on the 427 paying IPs.
- **Strong signals** (at most 2% FPR, and more common without leads): automation browser, FraudLogix bot reason, datacenter, compromised. Together: 0.23% FPR.
- **Verdicts:** human 808 · likely human 32,602 · unknown 49,450 · suspicious 49,246 · **bot 1,848**. Checks: 6 / 6 passed.
- **Data issues found and handled:**
  - the session table's funnel fields are inflated;
  - consent is recorded on page load;
  - `screen_width` is always empty;
  - shared networks produce high session counts.
- **Decisions by me:** the 2% FPR limit; engagement = a partial lead or 3+ events over 5+ seconds; rules that can't be tested stay weak.
- **App:** the verdict is added to `session_ip_labels.json` (same file name). The copy in S3 was refreshed at 15:09. Lovable addendum 2 is in `LOVABLE_PROMPT_APP_V2.md`.

### 15j. Third IP source, and the "acceptable answer" rule (17 Sep 19:00)

**What you asked for:** add `experimentation_tools.experiment_router_events` as a third IP source; make sure every IP
from the three tables has at least one vendor answer that is not IP2Proxy; enrich the missing ones newest first; and
fix the 30,000 unresolved sessions in your report.

| Item | Status | Evidence |
|---|---|---|
| Your 30,000 unresolved sessions | **Already fixed** | `sql/checks/session_resolution_now.sql`: of 103,905 sessions in the last 30 days, 1 is unresolved. 48,461 resolve through FraudLogix and 55,443 through proxycheck.io. Re-run your report against the refreshed `unified` tables |
| Gap across all addresses | **Measured** | `sql/checks/acceptable_vendor_gap.sql`: 457,438 of 4,960,000 have no acceptable answer, **all last seen over 90 days ago**. Everything seen in the last 90 days is answered |
| Priority: missing first, newest first | **Deployed** | `no_acceptable_answer` added to `_selection_sql`. Dry run for 18 Sep picks 78,000 addresses, all without a FraudLogix answer, newest first (23 May) |
| New check on every run | **Deployed** | "Every address seen in the last 90 days has a FraudLogix or proxycheck.io answer". Public addresses only; queued addresses count as in progress. Current result: 194,514 addresses, all answered |
| Third source | **Registered, switched off** | DynamoDB `base_table` / `router_events`, `enabled` false. Both roles are refused `s3:GetObject` on `mlbucket-sagemaker`, so it cannot be read yet: `ADMIN_DELETION_STEPS.md` Request 3 |
| Bigger proxycheck.io plan | **Not needed** | 457,438 addresses at 78,000 a day is about 6 days. The router table adds about 128,000 addresses, mostly ones we already hold |

- **Backup:** `archive/deployed-code-before-acceptable-answer-2026-09-17/`.
- **Safety:** all three sources are read only; no production table was touched.
- **Data profiling of the new table:** its columns and storage are documented in `docs/SYSTEM_GUIDE.md`. Full data
  profiling (row counts, IP formats, freshness, duplicates, overlap) is written and ready in
  `sql/checks/router_profile.sql`, but cannot run until the admin grants read access.

### 15k. Completeness of the two tables (17 Sep 20:40)
- **Question:** which IPs have no usable data at all, and how do we guarantee every IP in the data lake is usable?
- **Answer:** no address is missing a row. Every one of the 4,959,913 addresses has rows in both tables; 4,501,335 (90.75%) are complete. The gaps are empty fields: 454,946 with no acceptable risk answer, 2,408 answered only by IP2Proxy, 1,224 with risk but no usable location. All 458,578 simply have not been asked of proxycheck.io yet, and one answer fills both risk and location.
- **Last 90 days (what reporting uses):** 194,514 addresses, 194,500 complete. The 14 that were not are now queued and go out first.
- **New module** `build/pipeline/src/completeness.py`: writes `serving/ipintel_curated/table_completeness.json` and adds two checks to both daily jobs ("Every address seen in the last 90 days is complete in both tables" and the progress line). A failed check stops the unified refresh.
- **Order fixed:** recent addresses (30 then 90 days) now come before the older no-answer backlog, so a recent address is never delayed behind 457k old ones. Verified by a dry run: the 14 queued addresses come first, then recent ones.
- **App:** the completeness report travels inside `proxy_coverage.json`.
- **Docs:** `DATA_COMPLETENESS.md`.
- **Backups:** `archive/deployed-code-before-completeness-2026-09-17/`.

### 15l. Ready for the one-day full backfill (18 Sep)
- **Fill rates measured** (`sql/checks/vendor_fill_rates.sql`): FraudLogix 89.6% (its ceiling: only IPs that clicked an ad); IP2Proxy 0.3% (a list, not an answer); proxycheck.io 5.7%, the only fill rate money can raise.
- **Chunked backfill added:** top-up runs accept `max_addresses` (chunk size) and `skip_publish` (refresh `unified` only every few chunks). Deployed; backup in `archive/deployed-code-before-chunked-backfill-2026-09-18/`. Runner: `build/pipeline/backfill_chunks.py`, which stops at the first failed run or check.
- **Plan recommendation:** proxycheck.io $199.99 (5.12M a day), about 4.80M queries needed to answer every IP in one day. Details in `VENDOR_ANALYTICS.md`.
- **Vendor analytics for presenting:** `VENDOR_ANALYTICS.md` (fill rate, location accuracy, risk accuracy, bot evidence, the choice and why).
- **Router table:** still PERMISSION_DENIED on `mlbucket-sagemaker` (tested 18 Sep). Its unique appendable IPs can't be counted until the admin grants read access (Request 3).

### 15m. Router source live; enrichment back to 50k, timed for IST (18 Sep)
- **Admin access granted:** access tested and the table profiled. **28,476 of its 129,047 public IPv4 addresses were new to us.** Source validated and enabled (audit item written).
- **Daily load (10:31 UTC):** added **28,477 new addresses**, all checks passed; unified refreshed at 10:45 and passed.
- **Verification** (`sql/checks/router_verify.sql`): 129,053 of 129,060 router IPs are in both unified tables; the other 7 appeared after the load (the table is written every minute) and join tomorrow. 100,098 have an acceptable risk answer; 28,948 are queued for proxycheck.io.
- **Budget, at the owner's request:** enrichment 50,000 a day, 30,000 left for the owner (was 78,000 / 2,000). Enrichment now runs at **00:15 UTC = 05:45 IST**, just after proxycheck.io's daily reset; the top-up never goes past 50,000; a code guard gives way to the owner's own queries.
- **Today (18 Sep):** 77,273 queries were already used by the 07:42 UTC run under the old setting, so only about 2,700 remain until 05:30 IST on 19 Sep.

### 15n. `is_bot` filled per vendor; top-up guarded for the plan upgrade (18 Sep 11:09–11:20 UTC)
- **Rules** (`vendors.py`; each tested on the 427 paying IPs; full table in `IS_BOT_MAPPING.md`):
  - FraudLogix bot, datacenter, spoofed and Tor reasons: 0.23% of paying IPs;
  - proxycheck.io open proxies, compromised servers, Tor and hosting: 0.47%;
  - IP2Proxy listed as datacenter, CDN or spider, or with a botnet/scanner/spam threat: 0%.
- **Existing rows** brought in line with two MERGEs on `ipintel_curated.ip_intelligence`. Row count unchanged (9,805,602), 0 duplicates. Rollback snapshot `4849693903920381688`.
- **Result on `unified.ip_intelligence`:** rows where the vendor answered but `is_bot` is empty = **0** for all three vendors. proxycheck.io `is_bot` filled on 100% of its rows (it was 0%).
- **Refreshed:** the resolved refresh passed all checks; unified refreshed 11:12 UTC, passed.
- **Guard:** the scheduled 22:00 UTC top-up now stops at the daily budget (50,000). Only the chunked backfill (`max_addresses`) may go further, so upgrading the plan can't trigger one giant unchunked run.
- **Backup:** `archive/deployed-code-before-is-bot-fill-2026-09-18/`.

### 15o. Cloud-server bot rule; FraudLogix gaps sent to proxycheck.io; one answer per IP (18 Sep 11:20–11:40 UTC)
- **Stale view explained:** the owner's sample showing empty proxycheck.io `is_bot` came from Athena's cached results. On the live table, proxycheck.io `is_bot` empty = 0.
- **Cloud rule:** proxycheck.io never labels cloud servers "Hosting" (AWS showed as Business or VPN). `is_bot` is now also true when proxycheck.io's ASN is a cloud or server-hosting network (17 ASNs; Akamai, Cloudflare, Fastly, Google AS15169 and Cogent excluded). Tested: 0 of 427 paying customers. proxycheck.io bot rows 2,344 → 13,449.
- **FraudLogix no-decision IPs:** 86,330 public ones without a proxycheck.io answer queued (reason `fraudlogix_undecided`); they are answered first by the next run or the upgrade backfill.
- **One answer per IP** (`sql/checks/one_answer_per_ip.sql`, tested): bot = FraudLogix or proxycheck.io says bot; proxy/VPN = FraudLogix when it decided, else proxycheck.io. Today: 4,542,549 IPs answered with 0 unknown bot values; 446,574 wait for proxycheck.io.
- **Docs:** `IS_BOT_MAPPING.md` (mapping, rules, tests, accuracy overview).

### 15p. 
**Fill rules for FraudLogix rows** (`apply.fill_fraudlogix_from_proxycheck`, run after every proxycheck.io merge):

| FraudLogix row | Filled from proxycheck.io | `is_bot` | Marked |
|---|---|---|---|
| Empty (FraudLogix never decided) | Every data column: proxy, vpn, tor, datacenter, compromised, scraper, anonymous, isp, asn | **Left empty** until the bot standard (step 2) is agreed | `fraud_reason` = `FILLED_FROM_PROXYCHECK_IO` in `ip_intelligence_analytics` |
| Decided by FraudLogix | Only the columns FraudLogix never supplies: compromised, scraper, anonymous, isp, asn | FraudLogix's own value kept | Not marked (FraudLogix's decision stands) |

A later real FraudLogix decision replaces the filled values in the daily load. Accuracy work uses real decisions only
(exclude `FILLED_FROM_PROXYCHECK_IO`).

**Result on `unified.ip_intelligence`:**

| Check | Value |
|---|---|
| Public IPs with no FraudLogix decision and no proxycheck.io answer | **0** (the 90 left are private 10.x / 172.16.x addresses; no vendor can answer them) |
| Empty FraudLogix rows | **0** (86,784 filled and marked) |
| proxycheck.io rows | 757,084, none empty |
| Public IPs complete (risk and location) | 4,989,020 of 4,989,024; the other 4 have no location from any vendor |

**How it got there** (18 Sep, after the plan upgrade to 5.12M/day):
- **12:24 UTC:** a chunk sent 373,482 queries (the queue first); 746,529 rows added; 13 of 13 checks passed.
- **12:49:** 100,029 queries for every remaining unresolved IP; 199,998 rows added; 13 of 13 checks passed.
- **13:14:** 1,209 IPs with no location sent.
- **Code fixes made on the way:** backfill runs now send the day's queued batches from the upgraded headroom; batches already planned count towards a chunk's size; unresolved IPs are selected first.
- **Next:** step 2 (the bot standard), then step 3 (proxycheck.io for the about 4.23M decided IPs, which also fills ISP and ASN on their FraudLogix rows).
