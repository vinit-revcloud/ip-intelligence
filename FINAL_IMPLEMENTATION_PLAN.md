# Final Implementation Plan

Status as of 17 Sep 2026, 10:15 UTC.

## Scope (mentor's notes and owner's decisions)
1. **One-time lead-IP vendor analysis:** grade vendors on lead IPs using revenue, lead stage and FPR.
2. **Delete the API I built** (`ipintel-findings-api`).
3. **`unified`: keep all six project tables** (`ip_geo`, `ip_intelligence`, `ip_geo_analytics`, `ip_intelligence_analytics`, `vendor_overview_geo`, `vendor_overview_proxy`) and keep them updated with the latest data.
4. **Remove any other useless table.**

5. **(17 Sep, owner)** Bot / not-bot for every session IP, a proxy answer for every IP (experiment IPs first), and the final Lovable prompt.

**Later, not now:** a daily evaluation job and new tables.

## Status

| # | Step | Status | Who |
|---|---|---|---|
| 1 | Lead-IP analysis: 834 missing proxycheck.io answers filled, queries run, report and CSVs written, all checks passed | **Done** | Me |
| 2 | 15 unused `ipintel_curated` tables: definitions backed up, dropped from the catalog, data files untouched | **Done** | Me |
| 3 | Our API blocked (every call refused, HTTP 429); settings saved; teammate API healthy | **Done** | Me |
| 4 | Our API code, the app prompts and the old plan moved to `archive/` | **Done** | Me |
| 5 | All six `unified` project tables refreshed with the latest data after every passed daily run: `publish.py` extended from 2 to 6 tables; dry run and real run passed (19:51 UTC); counts equal `ipintel_curated`; 11 Sep originals archived | **Done** | Me |
| 6 | Other useless tables found: 4 in `ipintel_analytics` and `ipintel_reference.zip_centroid` (all from this project's 3–8 Sep benchmark, unused). Definitions backed up. (`ip-database` is pre-existing and not ours, so it is left alone) | **Backed up** | Me |
| 7 | Docs updated: `docs/USER_MANUAL.md`, `docs/SYSTEM_GUIDE.md`, `ADMIN_DELETION_STEPS.md` | **Done** | Me |
| 8 | Delete the API's Function URL, Lambda, log group and role; drop the 5 unused tables from step 6 | **Waiting** (`ADMIN_DELETION_STEPS.md`) | AWS admin |
| 9 | After step 8: delete the API's lookup cache `proxycheck/live/by-ip/` | Waiting on 8 | Me |
| 10 | Delete the data files of the 15 tables dropped in step 2 (only those 15 folders under `ip-intelligence/curated/`) | On or after 23 Sep, once you say go | Me |
| 11 | proxycheck.io budget 78,000 / keep 2,000 (was 50,000 / 30,000); new backfill order with experiment IPs first; deployed; today's remaining quota spent (27,712 queries, 10/10 checks, publish passed) | **Done** 17 Sep | Me |
| 12 | Bot / not-bot labels for 133,954 session IPs (`SESSION_IP_BOT_LABELS.md`), 5/5 checks | **Done** 17 Sep | Me |
| 13 | Proxy answer for every IP: experiment IPs 100%, 90-day session IPs 99.2% (1,047 left for 18 Sep 07:30), all addresses 90.8% (about 6 days) | **In progress, automatic** | Pipeline |
| 14 | App v2 built in Lovable; 9 data files uploaded on the Data Upload page (as of 17 Sep 11:30) | **Done** 17 Sep | You |
| 15 | Pipeline writes the 9 app files to S3 `ip-intelligence/serving/app/` after every passed run (`app_export.py`), tested | **Done** 17 Sep | Me |
| 16 | Read-only S3 key for the app so it reads those files itself (`ADMIN_DELETION_STEPS.md`, Request 2), then paste the addendum in `LOVABLE_PROMPT_APP_V2.md` | **Waiting** | AWS admin, then you |
| 17 | Presentation document `IP_INTELLIGENCE_SYSTEM_OVERVIEW.md` | **Done** 17 Sep | Me |
| 18 | Evidence-based bot verdict (`SESSION_IP_BOT_VERDICT.md`): 1,848 bot IPs at 0.23% FPR on paying IPs, 6 / 6 checks; in app data and S3 | **Done** 17 Sep | Me |
| 19 | Upload the new `session_ip_labels.json`; paste Addendum 2 of `LOVABLE_PROMPT_APP_V2.md` | **To do** | You |
| 20 | Mentor review of the verdict rules; then a daily version in `ipintel_curated` | Later | Mentor / me |
| 21 | "Acceptable answer" rule (FraudLogix or proxycheck.io; IP2Proxy does not count): new priority and a new run check, deployed and dry-run | **Done** 17 Sep | Me |
| 22 | Your 30k unresolved sessions: now 1 of 103,905 in the last 30 days. Re-run the report | **Done**; re-run your report | Me / you |
| 23 | 457,438 addresses without an acceptable answer (all over 90 days old): enriched newest first, about 6 days | **In progress, automatic** | Pipeline |
| 25 | Completeness of both tables: audit, `completeness.py`, two new run checks, recency-first order, `DATA_COMPLETENESS.md` | **Done** 17 Sep | Me |
| 26 | Reach 100% complete (458,578 addresses left, about 6 days, around 23 Sep) | **In progress, automatic** | Pipeline |
| 24 | Third source `experiment_router_events`: registered but off; needs read access to `mlbucket-sagemaker` (`ADMIN_DELETION_STEPS.md` Request 3) | **Waiting** | AWS admin |

AWS's permission simulator confirms the builder role is refused every step-8 action. I won't use any other credentials to get around that.

## What is in place now

**Running every day:**
- 07:30 UTC load of new IPs.
- proxycheck.io run: 78,000 queries a day (experiment IPs, then the last 30 and 90 days, then the rest), 10:00 fallback, 22:00 top-up.
- After every passed run, the **six** `unified` project tables are refreshed.
- Weekly maintenance.

**Tables:**

| Database | Tables |
|---|---|
| `unified` (project tables, all kept and refreshed) | `ip_geo`, `ip_intelligence`, `ip_geo_analytics`, `ip_intelligence_analytics`, `vendor_overview_geo`, `vendor_overview_proxy` |
| `ipintel_curated` (12, all used) | `ip_geo`, `ip_intelligence`, `ip_geo_analytics`, `ip_intelligence_analytics`, `ip_resolved`, `ip_occurrences`, `proxycheck_queue`, `vendor_overview_geo`, `vendor_overview_proxy`, `db11_bucketed`, `px12_bucketed`, `qualified_lead_ips` |
| `ipintel_analytics`, `ipintel_reference` | 5 unused tables, waiting for the admin to drop them |
| `ip-database` | Not ours; left untouched |

**API:** the teammate's IP Lookup API is the only one.

**Production:** only read.

**Known limitation:** in `unified.vendor_overview_proxy`, `bot_metric_status` is cut to 25 characters, because the unified definition allows only 25 and we may not change it. The full text is in `ipintel_curated`.

## Analysis results (`LEAD_IP_VENDOR_ANALYSIS.md`)
- **Population:** 2,768 lead IPs, 427 with revenue.
- **FPR:** FraudLogix 22.4%, proxycheck.io 32.6%, session table 36.1%.
- **FraudLogix:** 80 wrong flags on real people.
- **Revenue by stage:** none below intro-qualified; 85% of meeting IPs have revenue.

## Open points
1. **Blank revenue:** 1,315 "bot" IPs have blank `expected_revenue`. Is blank 0 or unknown?
2. **Budget:** confirm the 78,000 / 2,000 split. The teammate API does not use our key (16 Sep: proxycheck.io counted 50,354, our reservations 50,859).
3. **Teammate API answers:** it doesn't read `ip_resolved`.
4. **Old HTML pages:** the old HTML docs and pages are no longer maintained. Tell me if you want them deleted.

## Next checks
- **18 Sep, after 07:30:** re-run `sql/checks/proxy_coverage_now.sql`. Session IPs from the last 90 days should be 100%, apart from the 12 IPv6 / private addresses.
- **About 23 Sep:** every address should have at least one proxy answer. On or after 23 Sep, step 10 needs your go-ahead.
- **After each run:** refresh the app with `python analysis/export_app_data.py`, then copy `app-data/` into `public/data/`.

The full list of work, with evidence, is in `WORK_DONE_REVIEW.md`.


| 27 | Upgrade proxycheck.io to 5.12M/day, then run `backfill_chunks.py` (test chunk 250k, then 1M chunks) | **Waiting for the upgrade** | You, then me |
| 28 | `VENDOR_ANALYTICS.md`: why each vendor, fill rates, accuracy | **Done** 18 Sep | Me |


| 29 | Router table access granted, source enabled, 28,477 new IPs loaded, unified refreshed | **Done** 18 Sep | Admin / me |
| 30 | Enrichment 50k/day at 05:45 IST; 30k/day left for the owner; guard for the owner's own queries | **Done** 18 Sep | Me |


| 31 | `is_bot` filled per vendor with tested rules; 0 answered rows left empty; unified refreshed | **Done** 18 Sep | Me |
| 32 | After tonight's plan upgrade: `python backfill_chunks.py` (keeps the owner's 30,000) | **Waiting for the upgrade** | You, then me |


| 33 | Step 1: every public IP has a FraudLogix or proxycheck.io answer; empty FraudLogix rows filled (is_bot left empty); verified on unified | **Done** 18 Sep 13:25 UTC | Me |
| 34 | Step 2: agree the bot standard | **Next**, with you | You / me |
| 35 | Step 3: proxycheck.io for the remaining ~4.23M decided IPs | After step 2 | Me |
