# IP Intelligence System Guide

> Replaces ip-intelligence-*.html (no longer maintained).

**Complete reference for engineers · as built and verified 16 Sep 2026**

Everything about the company IP source: what it is for, how every part works, why each decision was made, the evidence that it works, what was done along the way, and what is still open.

| AWS account | Region | Database | Status |
|---|---|---|---|
| 221490242148 | us-west-2 | `ipintel_curated` | live (daily jobs); our API retired 16 Sep |

## Contents

1. [Summary](#summary)
2. [Requirements and how they are met](#requirements-and-how-they-are-met)
3. [Architecture](#architecture)
4. [The daily cycle](#the-daily-cycle)
5. [When proxycheck.io is asked](#when-proxycheckio-is-asked)
6. [How the answer is resolved](#how-the-answer-is-resolved)
7. [The tables](#the-tables)
8. [Refreshing the unified tables](#refreshing-the-unified-tables)
9. [Reports](#reports)
10. [Vendors and mappings](#vendors-and-mappings)
11. [proxycheck.io in detail](#proxycheckio-in-detail)
12. [IP lookups and the retired API](#ip-lookups-and-the-retired-api)
13. [Lead-IP vendor analysis (16 Sep)](#lead-ip-vendor-analysis-16-sep)
14. [Production safety](#production-safety)
15. [AWS resources](#aws-resources)
16. [Operations and runbooks](#operations-and-runbooks)
17. [State on 16 Sep 2026](#state-on-16-sep-2026)
18. [What was done, in order](#what-was-done-in-order)
19. [Limitations and open items](#limitations-and-open-items)
20. [Files in the project](#files-in-the-project)
21. [Glossary](#glossary)

---

## Summary

The system gives every IP address the company sees a location and a proxy/VPN/bot verdict, and keeps both current every day.

- **Sources of addresses:** the production tables `raw.raw_tune_clicks` (ad clicks) and `unified.unified_session_summary` (website sessions). They are only ever read.
- **Answers from:** IP2Location DB11 and IP2Proxy PX12 (downloaded databases), FraudLogix decisions carried on tune clicks, ipinfo.io and ipwho.is (free APIs), and proxycheck.io (paid, $9.99 a month, 80,000 queries a day).
- **Kept in:** 12 Iceberg and supporting tables in `ipintel_curated`. The main one is `ip_resolved`, one row per address with the answer to use.
- **Kept current by:** a daily load at 07:30 UTC for new addresses; a proxycheck.io run straight after (new-row addresses first, then the backfill, together up to 78,000); a 22:00 UTC top-up that spends what is left of the day's 80,000 except 2,000; and weekly maintenance.
- **Shared with another team:** after every proxycheck.io run that passes its checks, `unified.ip_geo` and `unified.ip_intelligence` are refreshed with checked copies of the `ipintel_curated` tables (files only, no catalog change). The teammate's IP Lookup API reads them.
- **Reported by:** a Location Accuracy report (vendors against customer postal addresses) and an Enrichment Coverage report, rebuilt at the end of both daily jobs as JSON files in S3.
- **Used through:** Athena (`ipintel_curated.ip_resolved`) and the teammate's IP Lookup API (`GET /v1/ip/{ip}`).
- **Retired on 16 Sep:** our API `ipintel-findings-api` (blocked at 17:00 UTC, awaiting admin deletion) and the Lovable app that depended on it. Pipeline control is now done directly in AWS.
- **Safety:** every project role sits inside a permissions boundary that makes writing to any production table, bucket or workgroup impossible. Every run proves it and reviews its own AWS activity.

## Requirements and how they are met

Each requirement the owner set, in the owner's terms, with where it lives. Evidence for every row is in `IP_PROJECT_VERIFICATION.md`.

| Requirement | How it is met |
|---|---|
| Do not touch `raw.raw_tune_clicks` or `unified.unified_session_summary`; nothing in production modified, added or deleted | Read-only access enforced by AWS (permissions boundary); IAM simulator check before every run; CloudTrail review after every run. The 16 Sep analysis also only read `sampledb.revenue_leads_plus` |
| New rows in those tables drive the process | Job A reads each base table at a pinned version, detects change, finds new addresses and addresses whose rows changed |
| Look up our IP tables first; call proxycheck.io if the address is missing or the information is bad | One rule in the pipeline ([below](#when-proxycheckio-is-asked)); Job A queues addresses and Job B sends them first the same day. The teammate's API makes its own live calls ([below](#ip-lookups-and-the-retired-api)) |
| Daily job: new IPs to each vendor, compare, update vendor overview and unified tables | Job A: IP2Location, IP2Proxy, FraudLogix, ipinfo.io, ipwho.is; analytics, scorecards, `ip_resolved`. Job B refreshes `unified.ip_geo` and `unified.ip_intelligence` after each passed run ([publish](#refreshing-the-unified-tables)) |
| Unique IPs; existing appended, new inserted | MERGE on (address, vendor): inserted, added, updated; duplicate check every run |
| Separate daily job: 50,000 addresses with no proxycheck.io decision; bulk; self-loop; no data loss, no downtime, valid calls, no key exhaustion, no timeouts | Job B: 1,000 per request, responses saved before use, shared reservation counter, hand-over to a fresh copy, Iceberg snapshots so readers never see half a write. Budget 50,000 (owner's choice, 15 Sep 13:00 UTC) |
| Use the full 80,000 queries a day | 15 Sep 13:00 to 17 Sep 09:47 UTC: 50,000 for enrichment and 30,000 kept for our API's lookups. Since 17 Sep 09:47 UTC (API retired): 78,000 for enrichment, 2,000 kept |
| Base tables controllable | DynamoDB `base_table/*` items, validated by Job A (`{"action":"validate"}`). The UI for this was retired with the app |
| API usable directly, with geo and proxy | The teammate's `GET /v1/ip/{ip}` for one address; Athena on `ip_resolved` for many. Our API is retired |
| Where does the IP occur | `ip_occurrences` |
| Correct information every time, without modifying vendor data | Vendor rows are kept as answered; `ip_resolved` applies the resolution rules |
| Nothing dummy or benchmark | Benchmark-only vendors, old sample endpoints and 15 legacy tables removed; every row comes from a vendor the system runs |
| Most safety options | Boundary, emergency stop, automatic pause, alarms and email alerts, one copy of each job, dead-letter queue, scan caps |

## Architecture

Two Lambda functions do all the work. Everything they write lives in one Glue database and one S3 folder that belong to the project. The six project tables in `unified` that they refresh keep their files in that same folder.

```
1. Where addresses come from          2. Scheduled jobs                          3. Tables and use
---------------------------------     ---------------------------------------    ------------------------------------
raw.raw_tune_clicks                   ipintel-free-daily (Job A)                 ipintel_curated
  ad clicks, every 6 h, read only  -->  07:30 UTC: new addresses, free     -->    ip_geo, ip_intelligence, analytics,
unified.unified_session_summary         vendors, analytics, occurrences,           scorecards, ip_occurrences,
  website sessions, daily, read only    resolved answers, queue, reports           ip_resolved, proxycheck_queue
IP2Location, IP2Proxy, FraudLogix,           |  starts                                  |
ipinfo.io, ipwho.is (free answers)           v                                          v
                                      ipintel-proxycheck-daily (Job B)           the six project tables in unified
                                        after Job A, 10:00 fallback,               checked copies, files in
                                        22:00 top-up; queue first, then     -->    ip-intelligence/unified/
                                        backfill; up to 78,000                     read by the teammate's IP Lookup API
                                        <--> proxycheck.io (1,000 per request)
                                        then {"action":"publish"}                Report files (S3): geo_accuracy.json,
                                                                                   enrichment_coverage.json
                                                                                 Athena, other systems
```

Flow: base tables → Job A → tables; Job A starts Job B → proxycheck.io → tables → publish to the six project tables in `unified`. Both jobs rebuild the report files at the end.

| Component | What it does |
|---|---|
| `ipintel-free-daily` | Job A: new addresses, free vendors, analytics, scorecards, occurrences, resolved answers, queue, reports. Also validates base tables (`{"action":"validate"}`), runs weekly maintenance (`{"action":"maintain"}`) and can rebuild the resolved answers on demand (`{"action":"refresh_resolved"}`: rebuild, reports, publish). Python 3.12, 15 min, 1 GB, one copy at a time |
| `ipintel-proxycheck-daily` | Job B: queue, backfill and top-up batches to proxycheck.io; merges saved answers; after a passed run, invokes itself with `{"action":"publish"}` to refresh the `unified` copies. Same limits |
| `ipintel-pipeline-state` (DynamoDB) | Settings and run history: safety state, job settings, base tables, the daily query counter, run logs |
| `ipintel-sources` (DynamoDB) | The vendor registry (which vendors are switched on) |
| S3 `…/ip-intelligence/` | Iceberg table files, proxycheck.io plans and responses, staging, report files, the files behind `unified.ip_geo` and `unified.ip_intelligence`, their rollback copy, archives |
| Athena workgroup `ipintel_etl` | Used by the jobs (10 GB per query cap) |
| EventBridge Scheduler | Four schedules ([operations](#operations-and-runbooks)) |
| SNS `ipintel-alerts` + CloudWatch | Email alerts and six alarms |
| `ipintel-findings-api` | **Retired.** Blocked since 16 Sep 17:00 UTC (reserved concurrency 0, every call returns 429). Awaiting admin deletion |

## The daily cycle

### Job A — the incremental load (07:30 UTC)

1. Stops if the pipeline is paused or the job is switched off (a manual run ignores the switch).
2. Removes staging tables older than 3 hours left by any crashed run.
3. Asks the IAM simulator whether its role could write to production. Any "yes" fails the run and pauses the pipeline.
4. Takes the enabled, validated base tables and records the latest Iceberg snapshot of each. If none changed since the last successful run, it stops ("skipped").
5. **New addresses:** every valid IPv4 in any base table, at the pinned snapshot, that IP2Location has not answered yet. A full comparison is used, so rows that arrive late or are rewritten are never missed.
6. **FraudLogix targets:** new addresses plus addresses with clicks in the last 3 days, because a FraudLogix decision can change.
7. Looks up IP2Location DB11 and IP2Proxy PX12 (range joins on the downloaded databases) and FraudLogix (latest decision per address from tune clicks).
8. **Free web vendors (ipinfo.io, ipwho.is), up to 500 each per run, paced.** Since 16 Sep they are the location tie-breakers. Order: addresses seen in the last 30 days whose location vendors name different states (`vendors_disagree`), then same state but far-apart cities (`same_state`), then addresses new since 14 Sep. The two vendors take different addresses, so about 1,000 conflicts a day get a third vote.
9. Counts what will change (inserted / added / updated / unchanged), then MERGEs into `ip_geo` and `ip_intelligence`. `created_at` is never overwritten.
10. Refreshes `ip_intelligence_analytics` and `ip_geo_analytics` for the affected addresses.
11. Recomputes `ip_occurrences` from every base table and merges it (first seen only moves earlier, last seen only later).
12. Recalculates both vendor scorecards over addresses asked of every running vendor (at least 1,000).
13. Recomputes `ip_resolved` for every address and merges only rows that changed.
14. **Queue:** every address new or touched since the last successful run that needs proxycheck.io goes into `proxycheck_queue` with its reason.
15. Rebuilds the Location Accuracy and Enrichment Coverage reports ([reports](#reports)).
16. Runs the checks below and a CloudTrail review. If any fails, progress is not recorded, so the next run repeats the same work.
17. Records each base table's new snapshot as its watermark and starts Job B.

**Job A checks (14):** pipeline cannot write to production · no address twice for a vendor · no table shrank · every new address is in `ip_geo` · IP2Location has every new address · IP2Proxy has every new address · updated geo rows kept `created_at` · updated intelligence rows kept `created_at` · every address has exactly one resolved answer · every new address has an occurrence row · every address needing proxycheck.io is queued · location accuracy per vendor exported · enrichment coverage exported · nothing outside the project was touched in 24 hours.

### Job B — proxycheck.io (after Job A; 10:00 fallback; 22:00 top-up)

1. Same pause, switch and permission checks. Reads the key from Secrets Manager and proxycheck.io's own usage page (plan, limit, queries used).
2. **Plans the day once:** picks up to 78,000 × 99% addresses without a proxycheck.io answer (`job_proxycheck._selection_sql`), in this order (since 17 Sep):
   - **0** queued from base tables;
   - **1** first seen today;
   - **2** experiment IPs: any `session_ip` of a `unified.unified_session_summary` row with a non-empty `experiment_id` (37,995 addresses, 38 experiments), so the bot / not-bot analysis has a proxycheck.io answer for every experiment IP;
   - **3** last seen in the base tables in the last 30 days, then in the last 90 days, even if the other vendors agree the address is clean;
   - **4** no conclusion (`no_answer`, `vendors_disagree`, `flagged_unconfirmed`), then by class rank and most recently seen.

   Private and reserved addresses are never picked. Saves the list as batch files of 1,000 and a manifest.
3. **Queue batches:** on every run, queued addresses not in today's batches become extra batches sent first, so addresses queued after the plan still go out the same day. They count inside the 78,000 (`queue_extra` 0).
4. **Top-up batches (22:00 run only):** the next addresses in the same order, sized to what is left of today's 80,000 minus 2,000 (`topup_keep`), judged by the larger of our counter and proxycheck.io's.
5. For each batch without a saved response: reserve its queries atomically, send 1,000 addresses in one request, save the response file immediately, then account for addresses charged twice.
6. With under 3 minutes left, or under 10 minutes when the merge is still to do, it starts a fresh copy of itself and stops (at most 30 hand-overs a day; a failed hand-over lands in the dead-letter queue with an alarm).
7. Merges every saved response not yet applied into `ip_intelligence` and `ip_geo`; refreshes analytics, scorecards and `ip_resolved`. It also still folds any answers under `proxycheck/live/` from the last 7 days; since our API was retired, no new ones arrive. Writes an "applied" marker per file only if every check passes.
8. Closes queue rows whose answer is now in the tables (or that proxycheck.io had no record for), rebuilds the two reports, then runs its checks and the CloudTrail review.
9. **Publish:** only when every check passed and `publish_unified` is true on `job/proxycheck-daily`, invokes itself with `{"action":"publish"}` to refresh the six project tables in `unified` ([below](#refreshing-the-unified-tables)).
10. **App export (since 17 Sep):** after a full, successful publish, `app_export.run()` writes the app's 9 report files to `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/app/`.
    - **Rebuilt each time:** coverage, location accuracy, proxy coverage and both vendor scorecards.
    - **Copied as they are:** the one-time analysis files, from `serving/app/static/`.
    - **Finish:** `manifest.json` is written last. The status is stored in DynamoDB `app/export`.
    - **Failure handling:** a failure sends an alert but never fails the publish.
    - **Manual run:** invoke `ipintel-proxycheck-daily` with `{"action":"app_export"}`.

**Job B checks (10):** pipeline cannot write to production · no duplicates · no table shrank · `created_at` kept (geo and intelligence) · one resolved answer per address · every queued base-table address was sent · location accuracy per vendor exported · enrichment coverage exported · nothing outside the project touched.

**16 Sep run:** 49,512 queries. The 3,410 queued addresses went first, then 12,769 window addresses other vendors called clean, then 33,325 without an answer. All 10 checks passed. Afterwards 42,768 of the 42,769 addresses seen in the last 30 days had a proxycheck.io answer; the one left was last seen on 9 Sep.

### Why it cannot lose data or overspend

| Failure | What happens |
|---|---|
| Crash after a response is saved | The next copy skips that batch and merges the file |
| Crash between answer and save | That batch is sent again; up to 1,000 queries wasted, no answer lost |
| Two copies at once | Impossible: each function allows one running copy |
| Budget reached | Stops; tomorrow's plan continues from the same order |
| Key rejected | Stops, marks the key invalid, emails |
| A check fails | Nothing is marked done; the next run repeats the work |
| Readers during a write | Iceberg serves the last complete version until the new one commits |
| A publish check fails | Before the swap: the unified table is not touched. During or after the swap: the previous files are put back automatically |

## When proxycheck.io is asked

One rule, in `pcqueue.reason_sql` (build/pipeline/src/pcqueue.py). Our API had a second copy (`lookup.needs_proxycheck`); it is archived with the API.

1. Not a public address (0/8, 10/8, 100.64/10, 127/8, 169.254/16, 172.16/12, 192.0.0/24, 192.0.2/24, 192.168/16, 198.18/15, 198.51.100/24, 203.0.113/24, 224/3) → never.
2. proxycheck.io has already answered → no.
3. Not in the IP tables → yes, `new_address`.
4. No location → yes, `no_location`.
5. Proxy status `no_answer`, `vendors_disagree` or `flagged_unconfirmed` → yes, that status.
6. Location status `vendors_disagree` (since 16 Sep this means states differ) → yes, `location_disagree`.
7. Otherwise → no.

Since the v2 location rules, `nearby` and `same_state` addresses no longer count as location conflicts. That cut location-conflict reasons by about two thirds.

Tested 15 Sep: 9 of 9 offline cases. On 16 Sep the queue path ran end to end on real rows: 3,410 queued addresses, all sent and answered the same day.

## How the answer is resolved

Vendor rows are never changed to make them agree. The answer to use is worked out from them by fixed rules in `resolved.py` (SQL, for `ip_resolved`). On 16 Sep the API's Python copy matched it on 1,500 of 1,500 addresses before the API was retired.

### Location (rules v2, live since 16 Sep 10:42 UTC)

- A vendor "answered" if it gave a state, a city or coordinates. GeoJS never votes (it repeats MaxMind); it is also no longer running.
- **Normalising:** state and city are lower-cased, accents and punctuation removed. In cities, "saint", "mount" and "fort" become "st", "mt" and "ft", and a trailing "city" or "township" is dropped. The **full** city name is compared. (The old rule compared only the first word, so "New York" matched "New Hyde Park".)
- **Status:**

  | Status | Rule |
  |---|---|
  | `agreed` | Two or more vendors name the same normalised state and city |
  | `single_source` | Only one vendor votes |
  | `nearby` | Two or more name the same state, and two of them are within 25 km (`NEARBY_KM`, haversine on their coordinates) |
  | `same_state` | Two or more name the same state, further apart |
  | `vendors_disagree` | No two vendors name the same state |
  | `no_answer` | No location from any vendor |

- **Which vendor supplies the fields** (evidence-based priorities, from who was right against the 2,105 customer addresses in each kind of conflict):
  - `STATE_PRIORITY`: ipinfo.io, ipwho.is, IP2Location, proxycheck.io.
  - `CITY_PRIORITY`: ipinfo.io, IP2Location, ipwho.is, proxycheck.io.
  - For `agreed`, the best city vendor of the agreeing group. For `nearby` and `same_state`, the best city vendor of the agreeing state group. Otherwise the best state vendor. Vendors not in a list come last, by id.
- **Evidence:** where states differed, ipinfo.io beat IP2Location 80 to 4 and proxycheck.io 53 to 25; ipwho.is beat IP2Location 76 to 6 and proxycheck.io 47 to 25; with only IP2Location and proxycheck.io, IP2Location was right 76 times to 42. For city in the same state: ipinfo.io, then IP2Location, then ipwho.is; every vendor beat proxycheck.io (IP2Location 90 to 47).
- **Replay check:** the 2,105 customer addresses gave the same state result under old and new rules (1,316 right, 62.5%); state + city 282 before, 283 after. A first version that put proxycheck.io before IP2Location on state lost 34 correct states and was corrected before going live. Always replay the truth set before changing priorities.
- **Effect:** 73,205 resolved rows changed across all addresses. In the 30-day window, "vendors disagree" fell from 22,583 to 7,448; "agreed" went from 20,183 to 19,596 (764 moved out under the stricter city match, 704 of them to `nearby`; 177 moved in through the spelling rules).
- The previous `resolved.py`, `job_free.py`, `coverage.py` and `lookup.py` are in `archive/geo-rules-before-2026-09-16/`.

### Proxy

- A vendor "answered" if `is_proxy` is not empty. It is "flagged" if any of proxy, VPN, Tor, datacenter, bot, compromised, scraper is true.
- If proxycheck.io answered, its flags are used: `confirmed` when another answering vendor has the same flagged/clean verdict, `proxycheck_only` when no other vendor answered, `proxycheck_overrides` when all others disagree.
- Without proxycheck.io: `clean_by_vendors` when every answering vendor says clean (all flags false); `vendors_disagree` when some flag and some do not; `confirmed_by_published_range` when all flag and a published range agrees (no range data is loaded now); otherwise `flagged_unconfirmed`. No answers at all is `no_answer`.
- ISP and ASN come from proxycheck.io when present, otherwise the first answering vendor by id.

## The tables

`ipintel_curated` holds exactly 12 tables. The main ones are Iceberg, partitioned by `bucket(ip_address, 64)` (the queue by 16), stored under `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/iceberg/`.

| Table | One row per | Rows | Written by | Holds |
|---|---|---|---|---|
| `ip_resolved` | address | 4,959,406 (16 Sep 10:42) | A, B | The answer to use: location fields, `geo_status`, `geo_decided_by`, `geo_agreeing_vendors`, `geo_vendors_answered`; `proxy_status`, `flagged`, eight flags, `proxy_decided_by`, `proxy_agreeing_vendors`; ISP, ASN, `proxycheck_risk_score`; `seen_in_base_tables`, first/last seen; `updated_at` |
| `ip_geo` | address + vendor | 5,091,972 (16 Sep 10:42) | A, B | state, city, zip_code, latitude, longitude, timezone, created_at, updated_at |
| `ip_intelligence` | address + vendor | 9,620,351 (16 Sep 10:42) | A, B | is_proxy, is_vpn, is_tor, is_datacenter, is_bot, is_compromised, is_scraper, is_anonymous, isp, asn, created_at, updated_at |
| `ip_intelligence_analytics` | address + vendor | = intelligence | A, B | has_answer, flagged, fraud_reason, is_masked_device, risk_score, known_infrastructure, infrastructure_list, verdict_class |
| `ip_geo_analytics` | address + vendor | grows daily | A, B | Only where 2+ vendors answered: consensus state/city/zip, votes, matches-consensus per field, customer-address truth and matches, row agreement % |
| `ip_occurrences` | address + base table | 6,543,790 (15 Sep) | A | source_table, first_seen, last_seen, days_seen, rows_seen |
| `proxycheck_queue` | address | grows daily | A queues, B closes | reason, source, queued_at, queued_by_run, answered_at, outcome (answered / no_record_from_proxycheck) |
| `vendor_overview_geo` | vendor | 4 | A, B | ips_tested, fill_rate_pct, agreement_pct, state/city/zip truth %, score (agreement × fill) |
| `vendor_overview_proxy` | vendor | 3 | A, B | ips_tested, answered, fill, flagged, bot counts, false_positive_rate_pct (bot flags on confirmed humans), precision/recall, score |
| `db11_bucketed` | IP range | — | loaded once | The downloaded IP2Location DB11 database, bucketed by /16 prefix for fast range joins |
| `px12_bucketed` | IP range | — | loaded once | The downloaded IP2Proxy PX12 database, bucketed the same way |
| `qualified_lead_ips` | customer address | 2,105 with full address | loaded once | Customer addresses and confirmed humans, the truth for location accuracy and false positives |

**Removed on 16 Sep:** 15 legacy tables from the 3–11 Sep build phases were dropped from the catalog: `geo_src`, `intel_src`, `ip_business_outcome`, `ip_dim`, `ip_flags`, `ip_geo_observations`, `ip_intel_observations`, `ip_intel_pc`, `ip_list`, `ip_pool`, `ip_proxy_check`, `ip_vendor_result`, `lead_truth`, `lead_truth_v2`, `pc_live`. Their definitions are saved in `archive/curated-legacy-tables-2026-09-16/` and `s3://…/ip-intelligence/archive/curated-legacy-tables-2026-09-16/`. Their data files are kept for now under `ip-intelligence/curated/<table>/`. Only those 15 folders may be deleted later; `curated/db11_bucketed/` and `curated/px12_bucketed/` belong to live tables, and `curated/db11/` and `curated/px12/` belong to `ip-database` (not ours).

**Unused benchmark tables in other project databases (backed up, for the admin to drop):** `ipintel_analytics.geo_accuracy`, `geo_score`, `pairwise_agreement`, `risk_score` and `ipintel_reference.zip_centroid`, all created 3–8 Sep and unused by running code. Definitions: `archive/other-project-tables-2026-09-16/` and `s3://…/ip-intelligence/archive/other-project-tables-2026-09-16/`. The builder role may not drop tables outside `ipintel_curated`. **`ip-database` is not ours:** it existed before this project and its tables are only read.

**Conventions:** every yes/no is three-state (true, false, empty = no answer). Every timestamp is UTC `YYYY-MM-DDTHH:MM:SSZ`; FraudLogix times were converted from Pacific time on 15 Sep.

### S3 folder layout

```
ip-intelligence/
  iceberg/<table>/                          table data and metadata
  curated/db11_bucketed/, px12_bucketed/    live tables (keep)
  curated/<table>/                          data files of the 15 dropped legacy tables (kept for now)
  proxycheck/plan/dt=<date>/                manifest.json, batch-NNNNN (backfill), batch-q… (queue), batch-t… (top-up)
  proxycheck/responses/dt=<date>/           raw proxycheck.io response per batch, saved before use
  proxycheck/applied/dt=<date>/             marker once a batch is merged and checked
  proxycheck/live/dt=<date>/                answers saved by our retired API; folded in by Job B (no new ones)
  proxycheck/live/by-ip/<ip>.json           our retired API's lookup cache (to be removed after the admin deletion)
  proxycheck/live-applied/                  markers for folded live answers
  staging/<run>/                            short-lived working tables, removed after each run
  serving/ipintel_curated/                  scorecard exports, geo_accuracy.json, enrichment_coverage.json
  unified/<table>/d=2026-09-11/             files behind the six project tables in unified (replaced by each publish)
  publish-previous/<table>/                 rollback copy: the files the last publish replaced
  archive/                                  backups: removed benchmark vendors, FraudLogix timestamps before UTC
  archive/unified-2026-09-11/<table>/       the original 11 Sep unified files, kept forever
  archive/curated-legacy-tables-2026-09-16/ definitions of the 15 dropped ipintel_curated tables
  archive/unified-removed-2026-09-16/       extra backup of unified.vendor_overview_geo and _proxy (16 Sep, before they were kept and refreshed)
  archive/other-project-tables-2026-09-16/  definitions of the 5 unused benchmark tables listed for the admin
  athena-results/                           query output
```

### The `unified` tables

This project built six `unified` tables on 11 Sep. All six are kept and refreshed with the latest data. Their state on 16 Sep:

| Table | State |
|---|---|
| `unified.ip_geo`, `unified.ip_intelligence` | Kept. Refreshed after every passed Job B run; the teammate's API reads them |
| `unified.ip_geo_analytics`, `unified.ip_intelligence_analytics` | Kept. Refreshed the same way since 16 Sep 19:51 UTC (before that, the 11 Sep copies) |
| `unified.vendor_overview_geo`, `unified.vendor_overview_proxy` | Kept (owner decision, 16 Sep evening; the earlier plan to drop them was cancelled). Refreshed the same way since 16 Sep 19:51 UTC |

No other table in `unified` was created by this project, so nothing else there is touched.

## Refreshing the unified tables

After every Job B run that passes all its checks, Job B replaces the files behind the six project tables in `unified` (`ip_geo`, `ip_intelligence`, `ip_geo_analytics`, `ip_intelligence_analytics`, `vendor_overview_geo` and `vendor_overview_proxy`) with a checked copy of the matching `ipintel_curated` table. It never changes the Glue catalog.

The teammate's IP Lookup API reads `unified.ip_geo` and `unified.ip_intelligence`. All six are Hive tables in Parquet, with files in the project's own folder `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/unified/<table>/d=2026-09-11/`. Each is refreshed in its existing shape:

| Table | Layout | Rows compared after each copy |
|---|---|---|
| `ip_geo`, `ip_intelligence`, `ip_intelligence_analytics` | 64 buckets on `ip_address` | about 200 sample addresses (every vendor plus random) |
| `ip_geo_analytics` | plain Parquet | about 200 sample addresses |
| `vendor_overview_geo`, `vendor_overview_proxy` | plain Parquet | every row |

Some unified columns are declared `varchar(n)` where `ipintel_curated` has `string`. Values are cut to `n` characters, which is all unified can show. Only `vendor_overview_proxy.bot_metric_status` (`varchar(25)`, values up to 103 characters) is affected today. The full text stays in `ipintel_curated`. Because the files are ours, the refresh can swap them without any catalog write. Code: `build/pipeline/src/publish.py`. Switch: `publish_unified` on `job/proxycheck-daily` (true).

### Steps, per table

1. **Guard.** The unified table still has the expected S3 location, the same column names and types as `ipintel_curated.<table>` (`varchar(n)` counted as `string`), the expected bucketing, and Parquet. Anything else stops the publish.
2. **Archive (first publish only).** Copy the 11 Sep files to `ip-intelligence/archive/unified-2026-09-11/<table>/`, kept forever.
3. **Build.** CTAS a Parquet copy of `ipintel_curated.<table>` into staging, in the unified table's layout and column types.
4. **Check the copy.** Same row count as the source; no duplicate keys (`ip_address` + `vendor`, or `vendor` for the scorecards); 64 bucket files where bucketed; identical rows (whole-row fingerprints) for the sample addresses, or for every row of the scorecards.
5. **Swap.** Copy the current files to `ip-intelligence/publish-previous/<table>/` (the rollback copy), copy the new files in, then delete the old ones. For a few seconds readers may see old and new rows together; they never see an empty table.
6. **Re-check.** Run the same checks on `unified.<table>`. On any failure, the previous files are put back automatically.

| Item | Value |
|---|---|
| Trigger | Job B invokes itself with `{"action":"publish"}` after a passed run. Job A's `{"action":"refresh_resolved"}` also publishes. Dry run: `{"action":"publish","dry_run":true}` builds and checks without swapping |
| Run log | DynamoDB `run#publish-unified`; state item `publish/unified` (`last_published_at`, `tables`) |
| Catalog | No Glue change. The table definitions' `UpdateTime` stays 2026-09-11 |
| First real publish | 15 Sep 13:09 UTC, passed: `unified.ip_geo` 5,039,539 rows, `unified.ip_intelligence` 9,567,985 rows, 64 files each. `proxycheck_io` rows in `unified.ip_intelligence` went from 1 to 77,710. The benchmark vendors (`maxmind_geolite2`, `dbip_combined`, `geojs_io`, `authoritative_lists`) are no longer in the unified copies |
| Later publishes | 15 Sep 22:05; 16 Sep 07:49, 10:01, 10:42, 16:47: all passed (two tables) |
| Six tables | 16 Sep 19:49 dry run and 19:51 real publish of all six: all checks passed. Counts after: `ip_geo` 5,092,551 · `ip_intelligence` 9,621,189 · `ip_intelligence_analytics` 9,621,189 · `ip_geo_analytics` 262,108 · `vendor_overview_geo` 4 · `vendor_overview_proxy` 3, each equal to `ipintel_curated`. The 11 Sep originals of the four newly refreshed tables were archived to `archive/unified-2026-09-11/<table>/` first |

## Reports

Two JSON reports are rebuilt at the end of both daily jobs and saved under `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/ipintel_curated/`. Each has its own check in both jobs. Our API served them until 16 Sep; now read them from S3 (profile `ipintel-builder`) or recompute them in Athena (queries in `docs/USER_MANUAL.md`).

```bash
aws s3 cp --profile ipintel-builder \
  s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/ipintel_curated/enrichment_coverage.json -
```

### Location Accuracy

Code `build/pipeline/src/accuracy.py`; file `geo_accuracy.json`; check "Location accuracy per vendor exported".

- **Truth:** `ipintel_curated.qualified_lead_ips` rows with a full postal address: 2,105 customers, full state names, 5-digit ZIP.
- **Compared:** every location vendor in `ip_geo`, plus our resolved answer from `ip_resolved` ("Our answer (resolved)").
- **Match rules:** state = same name, case ignored; city = same name, letters only, case ignored; ZIP = same first five digits; state + city = both.
- **Pools:** "every address each vendor answered", and "same addresses" (the 1,049 addresses every location vendor answered).
- **By customer state:** states with fewer than 20 tested addresses are flagged `small_sample`.
- Only totals are exported, never lead data.

| 16 Sep | Tested (all) | State / city / ZIP % (all answered) | State / city / ZIP % (same 1,049) |
|---|---|---|---|
| IP2Location DB11 | 2,105 | 59.0 / 14.5 / 3.4 | 47.0 / 9.5 / 2.2 |
| proxycheck.io | 2,105 | 59.7 / 11.9 / 5.4 | 51.6 / 7.2 / 2.9 |
| ipinfo.io | 1,050 | 54.3 / 11.1 / 4.0 | 54.2 / 11.1 / 4.0 |
| ipwho.is | 1,050 | 53.7 / 10.5 / 1.8 | 53.7 / 10.5 / 1.8 |
| Our answer (resolved) | 2,105 | 62.5 / 15.3 / 4.1 | 54.1 / 11.0 / 3.6 |

> **Why no vendor reaches 100%.** A postal address is where the customer lives, not always where the connection is (mobile carriers, work networks). The numbers compare vendors with each other; they are not the chance that one answer is right.

**Wording rule (15 Sep).** "Agreement" means vendors against each other, on the vendor overview scorecards. "Accuracy" means a vendor against customer postal addresses, and is used only for the Location Accuracy report.

### Enrichment Coverage

Code `build/pipeline/src/coverage.py`; file `enrichment_coverage.json`; check "Enrichment coverage exported".

- **Totals** for the last 30 days (by last seen) and for all addresses: `addresses`, `proxycheck_answered`, `proxy_concluded`, `proxy_no_conclusion`, `geo_agreed`, `geo_nearby`, `geo_same_state`, `geo_single_source`, `geo_disagree_or_missing` (no two vendors name the same state, or no location), with percentages, plus `geo_state_agreed_pct` (agreed + nearby + same_state).
- `inserted_by_day`: `geo_rows` and `intel_rows` by `created_at`; `new_addresses` by first seen.
- `window_by_last_seen_day`: the 30-day window split by last-seen day.

| Measure | 15 Sep 19:00 UTC | 16 Sep 10:42 UTC |
|---|---|---|
| Addresses in the 30-day window | 39,508 | 42,769 |
| Answered by proxycheck.io | 18,034 (45.6%) | 42,768 (100%) |
| Proxy decided | 30,208 (76.5%) | 42,768 (100%) |
| Proxy undecided | 9,300 | 1 |
| Location: agreed / nearby / same state / states differ / one source | — | 19,596 / 6,541 / 9,181 / 7,448 / 3 |
| State agreed by 2+ vendors | — | 35,318 (82.6%) |
| All addresses: answered by proxycheck.io / undecided | 77,710 / 848,403 | 127,216 / 814,185 |

**What the daily counts show.** New addresses ran at about 450–1,100 a day. `unified.unified_session_summary` held sessions only up to 11 Sep until its owner's job rewrote it on 15 Sep 14:20 UTC; the 16 Sep 07:30 load then added 2,490 new addresses, all first seen 11–15 Sep. Bulk load days: 11 Sep (about 4.96 million rows in each table), 15 Sep (about 77,000 rows each, first backfill) and 16 Sep (about 52,000 rows each, 30-day backfill).

## Vendors and mappings

| Vendor | Kind | Gives | Coverage |
|---|---|---|---|
| IP2Location DB11 | downloaded database | location | every address |
| IP2Proxy PX12 | downloaded database | proxy | every address asked; only listed proxies answer (0.3% of all addresses) |
| FraudLogix | decisions on tune clicks | proxy, VPN, Tor, datacenter, bot | tune-click addresses only |
| ipinfo.io, ipwho.is | free APIs | location | up to 500 each a day: 30-day location conflicts first, then addresses new since 14 Sep |
| proxycheck.io | paid API, 80,000/day | location and proxy, risk score, ISP, ASN | queue, backfill and top-up; 127,216 addresses by 16 Sep 10:42 |

### FraudLogix mapping

Latest decision per address. Not `FLAGGED` → every flag false, reason `ACCEPTED`. `FLAGGED` with reason `PROXY` or `MOBILE_PROXY_SIGNALS` → proxy; `VPN` → VPN; `TOR` or `TOR_EXIT_NODE` → Tor; `DATA_CENTER` → datacenter; `BOT_GENERATED` or `NON_HUMAN_SCRIPT` → bot; `MASKED_DEVICES` → no flag, `is_masked_device` true (a device fingerprint signal, not a bot signal). Clicks with no decision → no answer.

### proxycheck.io mapping

`proxy: yes` → proxy; `vpn: yes` → VPN; type Tor → Tor; type **Hosting** → datacenter; type Compromised Server → compromised; type Scraper → scraper; operator anonymity, proxy or VPN → anonymous; bot is always empty. **Business is not datacenter:** in a test of 400 real addresses, 112 were Business, mostly Charter, Cox, AT&T, CenturyLink and Verizon Business home and office broadband. `last seen unix` becomes `updated_at`.

### Removed vendors

MaxMind GeoLite2, DB-IP, GeoJS and the published cloud ranges (`authoritative_lists`) ran only in the 8–10 Sep benchmark on 2,105 addresses. They were removed on 14 Sep with the owner's approval and switched off in the registry. Every removed row is in `archive/benchmark-vendors-2026-09-14/`. They can be reintroduced as real monthly loads, which would need downloads (and a free MaxMind licence key).

## proxycheck.io in detail

| Item | Value |
|---|---|
| Plan | $9.99 a month, tier "Subscription", 80,000 queries a day, 5 burst tokens |
| Key | Secrets Manager `ipintel/proxycheck-paid` (the free key `ipintel/proxycheck` was used for testing) |
| Request | `POST https://proxycheck.io/v2/?key=…&vpn=3&asn=1&risk=1&seen=1&days=90`, body `ips=a,b,c`, up to 1,000 addresses |
| Why those flags | `vpn=3` is the only setting that returns proxy and VPN separately; `seen=1` returns last-seen time; `asn=1` and `risk=1` return network and risk |
| Cost quirk | An address that is both proxy and VPN is charged twice (504 queries measured for 500 addresses); 1% is reserved extra and topped up afterwards |
| Firewall quirk | Python's default User-Agent is refused; every request sends its own |
| Status "warning" | Still carries full answers; treated as success |
| Usage page | `/dashboard/export/usage/` gives plan, limit and queries today; it lags 1–14 minutes, so our own counter is the one that decides |
| Counter | DynamoDB item `quota/<date>`: `reserved` (everything), `batch_reserved` (jobs), `live_reserved` (our retired API). Each reservation is a conditional update that fails if it would pass the cap |
| Split (since 17 Sep 09:47 UTC) | On `job/proxycheck-daily`: enrichment (queue + backfill) 78,000 (`daily_budget` and `budget_cap` 78000); `queue_extra` 0; `live_reserve` 2000; the 22:00 top-up fills to 80,000 − 2,000 (`topup_keep` 2000). The audit item `audit/2026-09-17T09:47:23Z#update_job` holds the old values |
| Why the 30,000 reserve moved | It was for our API's lookups, and that API is retired. The teammate's API does not use our key: proxycheck.io counted 50,354 queries on 16 Sep against our 50,859 reservations |
| Earlier splits | Before 15 Sep 10:33 UTC: backfill 50,000. 10:33–13:00 UTC: backfill 70,000, reserve 10,000, queue could use half the reserve, top-up keeping 2,000. 15 Sep 13:00 to 17 Sep 09:47 UTC: 50,000 enrichment, 30,000 reserve, top-up keeping 30,000 |
| Throughput | 1,000 addresses in about 1–2 s; a 50-batch backfill and its merge fit in one Lambda run |
| Use on 16 Sep | 49,999 by the pipeline before 10:42, plus 834 for the lead-IP analysis in the afternoon, of 80,000 |

## IP lookups and the retired API

### The teammate's IP Lookup API (the only API)

Not our code. Base URL `https://9w07dr3qq2.execute-api.us-west-2.amazonaws.com`.

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Up or not |
| `GET /v1/ip/{ip}` | `Authorization: Bearer <API_TOKEN>` (ask the API's owner) | Location and risk for one IPv4 address |

**Response:** `ip-address`; `ip-geolocation` {`source`, `lookup`, `state`, `city`, `zip`, `lat`, `lng`, `timezone`}; `ip-risk` {`source`, `lookup`, `is_proxy`, `is_vpn`, `is_tor`, `is_datacenter`, `is_compromised`, `is_scraper`, `is_anonymous`, `isp`, `asn`, `risk`, `confidence`}. `null` means the source gave no value.

**Errors:** 401 `unauthorized`, 400 `invalid_ipv4`, 404 `not_found`, 502 `lookup_failed`.

**How it works:**

- Geolocation from `unified.ip_geo`, preferring `ip2location_db11`; fallback to the IP2Location range database.
- Risk from `unified.ip_intelligence`, preferring `fraudlogix_tune`, then `authoritative_lists`, then `ip2proxy_px12`; the first decisive row wins. Otherwise a live proxycheck.io call, which is **not** saved to our tables.
- It does not read `ipintel_curated.ip_resolved`, so it does not use the resolved answer, the v2 location statuses or the evidence-based priorities. `authoritative_lists` rows were removed on 14 Sep and IP2Proxy answers only for listed proxies, so the proxycheck.io rows now in `unified.ip_intelligence` are seldom reached. A recommendation is pending with its owner.

### Our API `ipintel-findings-api` (retired)

- **What it was:** a Lambda behind a Function URL (`https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr…lambda-url.us-west-2.on.aws`) with a bearer token. It served lookups (single and bulk), table browsing, the two reports, the publish status and pipeline control for the Lovable app.
- **Blocked:** 16 Sep 2026 17:00 UTC, by setting reserved concurrency to 0. Every call returns HTTP 429.
- **To be deleted by an AWS admin:** the Lambda, its Function URL, the log group `/aws/lambda/ipintel-findings-api` and the role `ipintel-api-role` with its five inline policies. The project roles cannot delete them (the boundary protects them). Steps: `ADMIN_DELETION_STEPS.md`.
- **Archived:** code, URL config, resource policy and settings (no secrets) in `archive/api-removed-2026-09-16/`. Undo before deletion: `aws lambda delete-function-concurrency --function-name ipintel-findings-api`.
- **Also retired:** the Lovable app (every page called this API) and the `LOVABLE_PROMPT_*.md` files. The older prompt files are in `archive/retired-app-and-api-docs-2026-09-16/`.
- **Nothing in the pipeline depends on it.** The daily jobs never called it.
- **The `mode` field** on `safety/state` (`live`/`shadow`) only switched which tables the API's pages read. It has no effect now.
- **After the admin deletion,** the project owner removes the API's lookup cache `ip-intelligence/proxycheck/live/by-ip/`. From 23 Sep, with the owner's go-ahead, the `ip-intelligence/curated/<table>/` folders of the 15 dropped tables are removed (only those 15).

## Lead-IP vendor analysis (16 Sep)

A one-time, read-only analysis. Full report: `LEAD_IP_VENDOR_ANALYSIS.md`. Data: `analysis/lead-ip-vendor-2026-09/`. Code: `build/pipeline/analysis/lead_ip_vendor.py` (re-runnable, changes nothing). Queries: `build/pipeline/sql/analysis/`.

- **Population:** sessions in `unified.unified_session_summary` from 18 Jun to 9 Sep 2026, joined to `sampledb.revenue_leads_plus` on `utm_content = session_id`, with the lead date on or after the session date. Private and reserved IPs excluded. **2,768 lead IPs, 3,235 leads.**
- **Label:** summed `expected_revenue` above 0 → real person (427 IPs); otherwise bot (2,341 IPs, as in the MoM). 1,315 of the "bot" IPs have blank revenue rather than 0.
- **Gap fill:** the 834 lead IPs without a proxycheck.io answer were sent first (834 queries) and folded into the tables at about 16:4x UTC, so proxycheck.io covers all 2,768.

| Vendor | Answered | False positive rate (real people flagged) |
|---|---|---|
| FraudLogix | 2,326 (84%) | **22.4%** |
| proxycheck.io | 2,768 (100%) | 32.6% |
| Session table (`ip_is_proxy`, `is_bot_click`) | 2,768 (100%) | 36.1% |
| IP2Proxy | 14 | too few to judge |

Findings:

- No `below_intro` IP had revenue; 85% of `meeting` IPs did. Revenue appears only from `intro_qualified` onwards.
- FraudLogix tracks lead stage best: it flags 44.6% of `below_intro` IPs but 22–30% of later stages. proxycheck.io and the session table flag the opposite way.
- FraudLogix wrongly flagged 80 IPs that earned revenue or reached a meeting; 77 of them with reason `PROXY`.
- proxycheck.io's false positives are almost all VPN (137 of 139), on Akamai, Fastly and Cloudflare: Apple iCloud Private Relay users.
- FPR is the reliable comparison (±4–5 points at 95% confidence). Accuracy and recall are low for every vendor because "bot" here means "earned nothing".

A daily version of this evaluation is planned for later. It is not built.

## Production safety

The pipeline cannot harm production because AWS will not let it, and every run proves that before it starts. Production tables are only ever read: `raw.raw_tune_clicks`, `unified.unified_session_summary`, and (for the 16 Sep lead-IP analysis) `sampledb.revenue_leads_plus`.

### The fence

Every project role has the permissions boundary `ipintel-boundary`. Whatever a role's own policy says, the boundary explicitly denies:

- any Glue write outside `ipintel_curated`;
- any S3 write outside `datalake-landingzone-221490242148-us-west-2/ip-intelligence/*`, and every bucket-settings change;
- queries in any Athena workgroup other than `ipintel` and `ipintel_etl`;
- any Lambda outside `ipintel-*`;
- loosening the boundary itself, and deleting the project's own safety resources.

| Role | Used by | Proof |
|---|---|---|
| `ipintel-builder-role` | Every build step (profile `ipintel-builder`) | IAM simulator 61 / 61 refusals |
| `ipintel-pipeline-role` | Both jobs | IAM simulator 64 / 64 refusals; re-checked at the start of every run |
| `ipintel-scheduler-role` | Schedules | Can only start the two job functions |
| `ipintel-api-role` | The retired API | Hardened earlier (write access to `unified` removed). To be deleted by the admin |

### Every run

- **Before:** the IAM simulator is asked whether the pipeline role could update or delete the production tables, write their buckets, change bucket notifications or lifecycle, or query in `primary`. Any "allowed" fails the run and pauses everything.
- **After:** CloudTrail is read for every call the job functions made in 24 hours. Any write aimed outside the project is a failed check and an automatic pause.

### Publishing to the unified tables

The refresh of the six project tables in `unified` stays inside the fence. It only copies and deletes files under `ip-intelligence/`, which the boundary already allows. It makes no Glue change at all: `ipintel-boundary` denies Glue writes in the `unified` database, and the builder role cannot loosen the boundary. Publish runs only after the before-run and after-run checks have passed for that Job B run. For the same reason, dropping the unused `ipintel_analytics` and `ipintel_reference` tables needs an admin.

### Found during the audit

A review of the shared login's history found that this project ran only 3 read queries in the `primary` workgroup. Two production changes in that period came from other users of the shared login (the console and a separate assistant session): an `UPDATE` of `unified.lu_connector` and a `DROP` of `de_temp.klaviyo_uct_events`. They were reported to the owner and are unrelated to this project. Also noted: the `BounceEvents` EventBridge rule matches every S3 write in the account but has no target today.

## AWS resources

All created for this project and tagged `project=ipintel` unless noted.

| Type | Name |
|---|---|
| IAM | `ipintel-boundary` (policy); roles `ipintel-builder-role`, `ipintel-pipeline-role`, `ipintel-scheduler-role`; `ipintel-api-role` (pending admin deletion) |
| Lambda | `ipintel-free-daily`, `ipintel-proxycheck-daily`; `ipintel-findings-api` (blocked, pending admin deletion) |
| Scheduler | `ipintel-free-daily` 07:30 · `ipintel-proxycheck-daily` **00:15** (05:45 IST, since 18 Sep; was 10:00) · `ipintel-proxycheck-topup` 22:00 · `ipintel-weekly-maintenance` Sun 03:00 (all UTC) |
| DynamoDB | `ipintel-pipeline-state`, `ipintel-sources` |
| SQS / SNS | `ipintel-proxycheck-dlq` / `ipintel-alerts` (one confirmed email subscription) |
| CloudWatch alarms | `ipintel-free-daily-run-failed`, `ipintel-proxycheck-daily-run-failed`, `ipintel-free-daily-no-run-26h`, `ipintel-proxycheck-dlq-not-empty`, `ipintel-proxycheck-quota-90pct`, `ipintel-maintenance-run-failed` |
| Athena | workgroups `ipintel_etl` (10 GB cap, the jobs) and `ipintel` (20 GB cap, used by the retired API) |
| Glue | database `ipintel_curated` (12 tables); databases `ipintel_analytics` (4 unused tables) and `ipintel_reference` (1 unused table), both listed for the admin to drop |
| S3 | folder `ip-intelligence/` in `datalake-landingzone-221490242148-us-west-2` (versioning on; Intelligent-Tiering after 30 days; nothing auto-deleted). See the [folder layout](#s3-folder-layout) |
| Glue (not ours to change) | the six project tables in `unified` (`ip_geo`, `ip_intelligence`, `ip_geo_analytics`, `ip_intelligence_analytics`, `vendor_overview_geo` and `vendor_overview_proxy`): created by this project on 11 Sep, definitions never changed, files refreshed by publish. `ip-database` tables: pre-existing, read only |
| Secrets Manager | `ipintel/proxycheck-paid`, `ipintel/proxycheck` |

**DynamoDB items in `ipintel-pipeline-state`** (keys `pk`, `sk`):

| Item | Holds |
|---|---|
| `safety` / `state` | `paused`, `paused_reason`, `mode` (no effect since the API was retired), checks, last audit |
| `job` / `free-daily`, `job` / `proxycheck-daily` | `enabled`, schedule, budget, key secret, top-up settings. On the proxycheck job: `daily_budget` 78000, `live_reserve` 2000, `queue_extra` 0, `topup_keep` 2000, `publish_unified` true |
| `base_table/*` | table, columns, validation, watermark |
| `quota/<date>` | the daily query counter |
| `run#<job>` / `<time>` | every run's counts and checks |
| `run#publish-unified` / `<time>` | every publish run and its checks |
| `publish` / `unified` | `last_published_at`, `tables` |
| `audit/<time>` | changes made through the retired API (none are written now) |

**Cost.** proxycheck.io $9.99 a month. AWS usage is small: the jobs read a few GB in Athena a day (Athena charges $5 per TB, so cents a day) *(projection)*; Lambda, DynamoDB, SQS, SNS and S3 are within cents to a few dollars a month *(projection)*.

## Operations and runbooks

| When (UTC) | What |
|---|---|
| 07:30 daily | Job A, then Job B, then publish to the six unified tables if Job B passed; both jobs rebuild the reports |
| 10:00 daily | Job B fallback (does nothing if already done) |
| 22:00 daily | Job B top-up (spends the rest of the day's 80,000, keeping 2,000) |
| Sun 03:00 | Maintenance: `OPTIMIZE … REWRITE DATA USING BIN_PACK` and `VACUUM` on the 8 main tables (table names must be unquoted) |

All commands below use `--profile ipintel-builder --region us-west-2`. Never use the default profile: it is a different IAM user. Settings changes are not audit-logged any more, so note each one and its reason in `AWS_BUILD_LOG.md`.

### Pause everything

Set `paused` = true and `paused_reason` on item `pk=safety`, `sk=state`:

```bash
aws dynamodb update-item --profile ipintel-builder --region us-west-2 \
  --table-name ipintel-pipeline-state \
  --key '{"pk":{"S":"safety"},"sk":{"S":"state"}}' \
  --update-expression "SET paused = :p, paused_reason = :r" \
  --expression-attribute-values '{":p":{"BOOL":true},":r":{"S":"why"}}'
```

Both jobs and every proxycheck.io call stop; nothing is deleted. Resume by setting `paused` to false. Do not resume while a safety check is failing.

### Change the budget

Item `pk=job`, `sk=proxycheck-daily`: `daily_budget` (78000), `live_reserve` (2000) and `topup_keep` (2000). The enrichment cap is 80,000 − `live_reserve`. Change `daily_budget` and `live_reserve` together, and write an `audit` item with the old values.

```bash
aws dynamodb update-item --profile ipintel-builder --region us-west-2 \
  --table-name ipintel-pipeline-state \
  --key '{"pk":{"S":"job"},"sk":{"S":"proxycheck-daily"}}' \
  --update-expression "SET daily_budget = :b" \
  --expression-attribute-values '{":b":{"N":"78000"}}'
```

### Run a job by hand

```bash
aws lambda invoke --profile ipintel-builder --region us-west-2 \
  --function-name ipintel-free-daily --invocation-type Event \
  --cli-binary-format raw-in-base64-out --payload '{"trigger":"manual"}' out.json
```

Use `ipintel-proxycheck-daily` for Job B. A manual run ignores the job switch but not the pause. `python build/pipeline/watch_run.py free-daily` waits for the newest run and prints its result.

### A job failed

Read the run's message and checks in the newest `run#<job>` item (or with `watch_run.py`). Nothing half-done is recorded as done. Fix the cause, then run the job by hand. Answers already saved to S3 are merged on the next run.

### A safety check failed and the pipeline paused itself

Do not resume. Compare the role and boundary policies with the copies in `build/iam/`; find what granted access; restore; run the job by hand to re-check; then resume with a reason.

### The key was rejected

Renew the plan or put the new key in `ipintel/proxycheck-paid` (Secrets Manager, us-west-2). Run the proxycheck job by hand and check that the run no longer reports the key as invalid.

### Something in the dead-letter queue

A hand-over did not start. Run the proxycheck job by hand; it continues from the saved batches. Then clear the message from the queue.

### Add a base table

Copy the shape of an existing `base_table/*` item (table, IP column, seen-at column, enabled) into a new item, then invoke `ipintel-free-daily` with `{"action":"validate","id":"<id>"}` and fix anything it lists. The next daily load reads the table. The pipeline only reads base tables, and its own database cannot be one. Do not remove the last enabled base table.

### Check the last publish of the unified tables

Read DynamoDB `publish/unified` and the newest `run#publish-unified` item. `last_published_at` should be after today's Job B run; each table lists its row count and checks.

### Roll back a publish

Copy the files in `ip-intelligence/publish-previous/<table>/` back into `ip-intelligence/unified/<table>/d=2026-09-11/`, then delete every other file in that live folder. To go back to the original copy instead, use `ip-intelligence/archive/unified-2026-09-11/<table>/`. Stop publishing first (below), or the next passed Job B run replaces the files again.

### Stop publishing

Set `publish_unified` to false on the `job/proxycheck-daily` item. Job B keeps running; the unified tables keep their last copy.

### Dry-run a publish

Invoke `ipintel-proxycheck-daily` with `{"action":"publish","dry_run":true}`. It builds and checks the copies without swapping, and logs the run under `run#publish-unified`.

### Rebuild the resolved answers now

Invoke `ipintel-free-daily` with `{"action":"refresh_resolved"}`. It rebuilds `ip_resolved`, the reports, and then publishes. Use it after a rule change in `resolved.py`, after replaying the truth set.

### A report is missing or stale

Check the "Location accuracy per vendor exported" and "Enrichment coverage exported" checks on the last run, then run either job by hand.

### Undo a data correction

Removed benchmark rows: `archive/benchmark-vendors-2026-09-14/` (JSON). FraudLogix timestamps before conversion: `archive/fraudlogix-timestamps-before-utc-2026-09-15/` (Parquet). Dropped legacy tables: recreate from `archive/curated-legacy-tables-2026-09-16/` (data files are still under `ip-intelligence/curated/`). Recent table versions can also be read with Iceberg time travel for 5 days (maintenance removes older ones).

### Add a vendor back as a real source

Load its database into `ipintel_curated` under the table name in `vendors.OPTIONAL_*_DATABASES`, switch it on in the registry (`ipintel-sources`), and the daily job starts asking it about new addresses and scoring it.

### Deploying code

Zip `build/pipeline/src/*.py` (common, vendors, apply, resolved, pcqueue, accuracy, coverage, publish, job_free, job_proxycheck) and update both job functions, `ipintel-free-daily` and `ipintel-proxycheck-daily`:

```bash
aws lambda update-function-code --profile ipintel-builder --region us-west-2 \
  --function-name ipintel-free-daily --zip-file fileb://pipeline.zip
aws lambda update-function-code --profile ipintel-builder --region us-west-2 \
  --function-name ipintel-proxycheck-daily --zip-file fileb://pipeline.zip
```

There is no API to deploy any more.

## State on 16 Sep 2026

| Measure | Value |
|---|---|
| Addresses (10:42 UTC) | 4,959,406 |
| `ip_geo` · `ip_intelligence` · `ip_resolved` rows (10:42 UTC) | 5,091,972 · 9,620,351 · 4,959,406; the unified copies matched exactly |
| 07:30 Job A | 2,490 new addresses, 14 / 14 checks |
| Job B | 49,512 queries, 10 / 10 checks; queue 3,410, all answered; publish passed |
| proxycheck.io answers, all addresses | 127,216 (2.6%) at 10:42, plus 834 lead IPs in the afternoon |
| No proxy conclusion yet, all addresses | 814,185 (848,403 on 15 Sep) |
| Last 30 days (last seen 17 Aug–15 Sep) | 42,769 addresses · 42,768 answered by proxycheck.io · 42,768 proxy decided |
| Last 30 days flagged | 5,126 (12.0%), of which 4,804 VPN; about two in three on Akamai, Google and Cloudflare privacy relays |
| Last 30 days location | agreed 19,596 · nearby 6,541 · same state 9,181 · states differ 7,448 · one source 3 |
| Tie-break backlog (no free-vendor vote yet) | 7,425 states differ, 9,120 same state; about 8 and 17 days at about 1,000 a day *(projection)* |
| Days until every no-conclusion address is asked, at 50,000 a day | about 16–17 *(projection)* |
| `ipintel_curated` tables | 12 (15 legacy tables dropped) |
| Our API | blocked since ~17:00 UTC (HTTP 429); admin deletion pending |
| `unified` project tables | all six kept and refreshed (since 19:51 UTC) |
| Alarms, dead-letter queue, safety pause | all clear (10:42 UTC) |

## What was done, in order

- **8–10 Sep 2026:** benchmark of location and proxy vendors on real addresses: MaxMind GeoLite2, DB-IP, GeoJS, IP2Location, IP2Proxy, ipinfo.io, ipwho.is, proxycheck.io (free key) and published cloud ranges. Scoring settled on "Agreement", not "Accuracy", with customer addresses as truth for location (on 15 Sep "Accuracy" returned, only for the Location Accuracy report).
- **11 Sep:** all 4.96 million addresses loaded into six `unified.*` tables from IP2Location, IP2Proxy and FraudLogix; Athena-backed table API and a first live lookup built. Found and fixed: proxycheck "warning" treated as failure, cursor tokens breaking in URLs, INSERT not allowed on bucketed tables.
- **11–14 Sep:** plans revised with the owner into `IP_PROJECT_FINAL_PLAN.md`: new tables in `ipintel_curated`, `unified` untouched, two daily jobs, UI control. proxycheck.io paid plan bought; key stored as `ipintel/proxycheck-paid`. Found: proxycheck "Business" type is home broadband, not datacenter.
- **14 Sep:** audit of the shared login's workgroup history. Permissions boundary and builder, pipeline and scheduler roles created and proven. Six Iceberg tables built. Job A and Job B built; first runs failed on a SQL detail (a WITH clause inside UNION ALL) before any write, then passed. Control API, schedules, alarms, paid key switch. Added `ip_occurrences` and `ip_resolved`; weekly maintenance; benchmark-only vendors removed with approval; staging sweep; private addresses excluded.
- **15 Sep 07:30:** first scheduled runs: 108 new addresses, all 11 checks; first 50,000-address backfill in one run, all checks.
- **15 Sep morning:** table pages switched to the live tables (owner approval). Old benchmark endpoints removed. Review report on all tables. FraudLogix timestamps converted from Pacific to UTC; `false_positive_rate_pct` set to the approved confirmed-human definition. One proxycheck.io rule for API and base-table inserts, with `proxycheck_queue`.
- **15 Sep 10:33 UTC:** full 80,000 a day: backfill 70,000, lookup reserve 10,000 and a 22:00 top-up keeping 2,000 (the first top-up's final CloudTrail review hit a rate limit after the merge; the review is now paced). Bulk lookup endpoint built and tested. Alert email subscribed and confirmed.
- **15 Sep 13:00 UTC:** budget split at the owner's request: 50,000 a day for enrichment (`daily_budget` 50000, `queue_extra` 0) and 30,000 kept for API lookups (`live_reserve` 30000, `topup_keep` 30000).
- **15 Sep 13:09 UTC:** first real publish of `unified.ip_geo` (5,039,539 rows) and `unified.ip_intelligence` (9,567,985 rows), all checks passed, no catalog change. The 11 Sep files archived. Publishing now follows every passed Job B run.
- **15 Sep 14:20 UTC:** production side: `unified.unified_session_summary` rewritten by its own job, after holding sessions only up to 11 Sep.
- **15 Sep afternoon:** Location Accuracy report (`accuracy.py`) and Enrichment Coverage report (`coverage.py`) added to both daily jobs, each with its own check. Wording rule: "Agreement" for vendors against each other, "Accuracy" only against customer postal addresses. Backfill order gained step 1b: every last-30-day address without a proxycheck.io answer.
- **16 Sep 07:30 UTC:** Job A added 2,490 new addresses (14 / 14 checks), picking up the late session data. Job B sent 49,512 queries (10 / 10 checks), including all 3,410 queued addresses; publish passed. The 30-day window is now fully answered by proxycheck.io.
- **16 Sep 10:42 UTC:** location rules v2 live: full normalised city, statuses `nearby` and `same_state`, evidence-based vendor priorities, free vendors spent on 30-day conflicts first. Replay on 2,105 customers: no loss on state. 73,205 resolved rows changed; resolved answers rebuilt and published.
- **16 Sep 16:4x UTC:** one-time lead-IP vendor analysis run (`LEAD_IP_VENDOR_ANALYSIS.md`); the 834 lead IPs without a proxycheck.io answer were sent and folded into the tables first.
- **16 Sep ~17:00 UTC:** 15 legacy `ipintel_curated` tables dropped (definitions archived, data files kept); `unified.vendor_overview_geo` and `_proxy` backed up for admin drop; our API `ipintel-findings-api` blocked (reserved concurrency 0) and its code archived to `archive/api-removed-2026-09-16/`; the Lovable app retired with it. `ADMIN_DELETION_STEPS.md` written for the admin.
- **16 Sep 19:51 UTC:** owner decision: keep `unified.vendor_overview_*` and keep all six unified project tables current. `publish.py` extended to all six (each in its own layout); dry run and real publish passed; the 11 Sep originals of the four newly refreshed tables archived. Admin list changed: no `unified` drops; instead 5 unused benchmark tables in `ipintel_analytics` and `ipintel_reference` (definitions backed up). `ip-database` confirmed as pre-existing and left alone.
- **16 Sep:** this guide and the user manual rewritten as Markdown (`docs/SYSTEM_GUIDE.md`, `docs/USER_MANUAL.md`); the HTML versions are no longer maintained.

## Limitations and open items

| Item | Effect | What would change it |
|---|---|---|
| **Open:** admin deletions | `ipintel-findings-api` (Lambda, Function URL, log group), role `ipintel-api-role`, and 5 unused tables in `ipintel_analytics` / `ipintel_reference` still exist. The API is blocked, so nothing can call it | AWS admin runs `ADMIN_DELETION_STEPS.md`; then the owner removes the leftover S3 files |
| **Open:** teammate API does not use resolved answers | It ignores `ip_resolved`, the v2 location statuses and the priorities; it prefers FraudLogix, then removed `authoritative_lists`, then IP2Proxy, so the proxycheck.io rows are seldom reached | Not our code; recommendation pending with its owner |
| **Open:** blank `expected_revenue` | 1,315 of the 2,341 "bot" lead IPs have blank revenue, not 0. Counting them as bots changes accuracy and recall a lot, FPR little | Agree with the owner whether blank means 0 or unknown |
| **Open:** daily vendor evaluation job | The lead-IP analysis is one-time only | Build a daily version later (planned, not built) |
| Location Accuracy truth pool is only 2,105 addresses | Only 1,049 are answered by every vendor; many states fall under 20 tested. The v2 priorities were learned from the same addresses, so do not over-read small differences | More qualified leads with full postal addresses |
| Free vendor limits | Without an ipinfo.io token, requests are limited; ipwho.is is "fair use" | Create a free ipinfo.io token; confirm ipwho.is terms for commercial use |
| Tables update daily | An address can take up to about a day to appear in `ip_resolved` | Run Job A by hand |
| Bot flags from one vendor | No second opinion on bots | A vendor with bot classification, or a bot-labelled pool |
| Proxy scorecard sample skewed toward FraudLogix flags, and its score rewards not flagging | Use it to compare vendors, not as accuracy | The lead-IP analysis gives an FPR on real customers instead |
| proxycheck.io answers are not re-checked | An answer can age | A re-check policy once every no-conclusion address has one (about 10 days at 78,000 a day, *projection*) |
| proxycheck.io's daily reset time is not published | Our counter resets at midnight UTC | The counter also respects proxycheck.io's own usage, so it cannot overspend |
| `unified.vendor_overview_proxy.bot_metric_status` is cut to 25 characters | Its unified definition is `varchar(25)` | Read the full text in `ipintel_curated`; changing the definition needs an admin |
| A publish swap is not atomic | For a few seconds readers of the unified tables may see old and new rows together (never an empty table) | Accepted; no catalog change is allowed |
| Monthly database reloads (IP2Location, IP2Proxy) not automated | Databases age month by month | Needs download approval; a monthly load job |
| `test_base_table_trigger.py` step 4 calls our retired API | That step can no longer run | Drop or rewrite that step before using the script again |

## Files in the project

| Path | What it is |
|---|---|
| `docs/USER_MANUAL.md` | How to use everything (analysts) |
| `docs/SYSTEM_GUIDE.md` | This guide (engineers) |
| `docs/ip-intelligence-*.html` | Old HTML versions, no longer maintained |
| `IP_PROJECT_FINAL_PLAN.md` | The agreed plan |
| `FINAL_IMPLEMENTATION_PLAN.md` | The 16 Sep plan: retire our API, drop extra tables, run the lead-IP analysis |
| `ADMIN_DELETION_STEPS.md` | What the AWS admin deletes, and how to undo before that |
| `LEAD_IP_VENDOR_ANALYSIS.md` | The 16 Sep lead-IP vendor analysis report |
| `IP_PROJECT_VERIFICATION.md` | Requirement-by-requirement proof |
| `ATHENA_REVIEW_QUERIES_LIVE.md` | Ready-made queries and column meanings |
| `AWS_BUILD_LOG.md` | The build log |
| `build/pipeline/src/` | `common.py` (AWS helpers, safety, run log), `vendors.py` (vendor lookups and mappings), `apply.py` (merges, analytics, scorecards, checks), `resolved.py` (resolution rules), `pcqueue.py` (the proxycheck.io rule and queue), `accuracy.py` (Location Accuracy report), `coverage.py` (Enrichment Coverage report), `publish.py` (unified tables refresh), `job_free.py`, `job_proxycheck.py` |
| `build/pipeline/sql/` | Table definitions (10–19) and `checks/` (every verification query) |
| `build/pipeline/sql/analysis/` | Queries for the lead-IP analysis (`lead_ip_gaps.sql`, `lead_ip_gap_list.sql`, `recount_proxycheck.sql`) |
| `build/pipeline/analysis/lead_ip_vendor.py` | The lead-IP vendor analysis; re-runnable, read-only |
| `build/pipeline/*.py` | `run_sql.py`, `watch_run.py`, `test_base_table_trigger.py` (step 4 needs the retired API), `remove_benchmark_vendors.py` |
| `build/iam/` | Boundary and role policies, simulator proofs, backups of earlier versions |
| `analysis/lead-ip-vendor-2026-09/` | Lead-IP analysis data: per-vendor IP files, labels, scorecards, stage tables, FraudLogix wrong flags, `summary.json` |
| `archive/api-removed-2026-09-16/` | Our retired API: code (`src/app.py`, `lookup.py`, `bulk.py`, `athena_tables.py`, `control.py`), `compare_resolved.py`, deployment zip, URL config, resource policy, settings without secrets. Formerly `build/api/` |
| `archive/curated-legacy-tables-2026-09-16/` | Definitions of the 15 dropped `ipintel_curated` tables |
| `archive/unified-removed-2026-09-16/` | Extra backup of `unified.vendor_overview_geo` and `_proxy` (they are kept) |
| `archive/other-project-tables-2026-09-16/` | Definitions of the 5 unused benchmark tables listed for the admin |
| `archive/geo-rules-before-2026-09-16/` | Code before location rules v2 |
| `archive/retired-app-and-api-docs-2026-09-16/` | Retired Lovable prompts and API/app docs |

## Glossary

- **Iceberg:** a table format in S3 that allows safe updates (MERGE), versions (snapshots) and time travel. Readers always see a complete version.
- **MERGE:** one SQL statement that updates matching rows and inserts new ones: the "append if it exists, insert if it doesn't" of the requirements.
- **snapshot / watermark:** a table version. Job A records the snapshot it read from each base table, so the next run knows what changed.
- **staging table:** a short-lived working table for one run, removed afterwards.
- **permissions boundary:** an AWS ceiling on what a role can ever do, whatever its own policy grants.
- **IAM simulator:** an AWS service that answers "would this role be allowed to do this?" without doing it.
- **CloudTrail:** AWS's log of every API call made in the account.
- **hand-over:** a Lambda run starting a fresh copy of itself to continue, before its 15-minute limit.
- **dead-letter queue:** where a failed asynchronous start is kept so it is not lost.
- **reservation counter:** the DynamoDB item every proxycheck.io request reserves from first, so two callers can never both take the last queries.
- **resolved answer:** the one answer to use per address, from fixed rules over every vendor's answer.
- **no conclusion:** no vendor answered, vendors disagree, or a flag has nothing confirming it.
- **nearby / same_state:** location statuses for vendors that agree on the state; their cities are within 25 km (nearby) or further apart (same_state).
- **agreement:** how often a vendor matches the other vendors; the vendor overview scorecards measure agreement.
- **accuracy:** how often a vendor's location matches customer postal addresses (`qualified_lead_ips`). Used only for the Location Accuracy report.
- **FPR (false positive rate):** in the lead-IP analysis, the share of real-person IPs (revenue above 0) a vendor flagged.
- **enrichment:** proxycheck.io queries spent on base-table addresses (queue, backfill, top-up), up to 78,000 a day.
- **enrichment coverage:** how many addresses have a proxycheck.io answer, a proxy conclusion and an agreed location; the Enrichment Coverage report.
- **publish:** Job B's refresh of the six project tables in `unified`: build a checked copy in each table's layout, swap the files, re-check, restore on failure. No catalog change.
- **rollback copy:** `ip-intelligence/publish-previous/<table>/`: the files the last publish replaced.
- **confirmed human:** an address a qualified customer lead used (`qualified_lead_ips.confirmed_human`); a bot flag on it is a false positive.
- **teammate's API:** the IP Lookup API at `9w07dr3qq2`, owned by another team; the only API since 16 Sep.

---

Kept in the project folder as `docs/SYSTEM_GUIDE.md`. Companion: `docs/USER_MANUAL.md`. Evidence: `IP_PROJECT_VERIFICATION.md`.

## The app and its data (since 17 Sep)

| Part | Detail |
|---|---|
| **App** | Lovable, company account. Specification: `LOVABLE_PROMPT_APP_V2.md`. Pages: IP Lookup (live, teammate API; token only as the Lovable server secret `IP_LOOKUP_API_TOKEN`), Bot / Not bot, Lead-IP Vendor Evaluation, Location Accuracy, Enrichment Coverage, Vendor Scorecards, Data Upload |
| **Report files** | `lead_ips`, `lead_ip_analysis`, `session_ip_labels` (one-time analyses), `coverage`, `geo_accuracy`, `proxy_coverage`, `vendor_overview_geo`, `vendor_overview_proxy`, `manifest` (all `.json`, each with `as_of`) |
| **Automatic copy** | `app_export.py` (Job B step 10) writes the files to `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/app/` after every full publish. First run 17 Sep 11:34 UTC; all 9 files written |
| **Getting them into the app now** | Manual: run `python analysis/export_app_data.py` (writes `app-data/`), then upload the 9 files on the app's **Data Upload** page. The app reads the uploaded copy first, then the files bundled with the app. First upload 17 Sep, files as of 11:30 UTC |
| **Getting them into the app with no manual step** (pending) | An AWS admin creates IAM user `ipintel-app-reader` with only `s3:GetObject` on `ip-intelligence/serving/app/*`; its key goes into Lovable secrets `APP_S3_ACCESS_KEY_ID` / `APP_S3_SECRET_ACCESS_KEY`; a server function reads the files (prompt in `LOVABLE_PROMPT_APP_V2.md`, addendum). The builder role cannot create IAM users or secrets |
| **Not built** | The pipeline pushing files straight to the app. It was stopped by the safety review because it sends company data to an outside service; not built |
| **Changing the one-time files** | Re-run the analysis script, then `export_app_data.py`, then copy the three files to `serving/app/static/` |
| **Cost** | About 6 MB in S3 and one Athena query per run (about 1 GB scanned): under $0.01 a day |
| **Undo** | Previous code in `archive/deployed-code-before-app-export-2026-09-17/pipeline.zip` |

## The third IP source: experiment router events (added 17 Sep, waiting on access)

| Item | Detail |
|---|---|
| Table | `experimentation_tools.experiment_router_events` (Iceberg, `s3://mlbucket-sagemaker/...`, no partitions, created 11 Jun 2026) |
| Useful columns | `ip_address`, `server_timestamp_entry` (when seen), `is_bot`, `experiment_id`, `user_agent`, `utm_content` |
| Registered as | DynamoDB `base_table` / `router_events`, `ip_column` `ip_address`, `seen_at_column` `server_timestamp_entry`, **`enabled` false** |
| Why it is off | Both project roles are refused `s3:GetObject` on `mlbucket-sagemaker`, so every query fails with PERMISSION_DENIED. `ADMIN_DELETION_STEPS.md` Request 3 asks for read-only access |
| Switching it on | 1. Admin grants access. 2. `aws lambda invoke ... ipintel-free-daily --payload '{"action":"validate","base_table":"router_events"}'` (profiles the table and writes its validation). 3. If the validation says valid, set `enabled` true. 4. The next daily load picks up its addresses like any other source |
| Expected size | About 128,000 distinct addresses (the owner's own count), most of which we already hold from the session table |
| Safety | Read only, like the other two sources; the daily load never writes to a base table |

## Acceptable vendor answer (rule since 17 Sep)

An address counts as answered only when **FraudLogix decided** on it or **proxycheck.io answered** it. IP2Proxy PX12
only lists known proxies, so its silence is not an answer and it does not count.

- **Selection:** addresses with no acceptable answer are sent first, newest first (`no_acceptable_answer` in
  `job_proxycheck._selection_sql`), after queued addresses and addresses new today.
- **Check on every Job B run:** "Every address seen in the last 90 days has a FraudLogix or proxycheck.io answer".
  It counts public addresses only (private ones such as `10.255.220.18` can never be answered) and treats queued
  addresses as in progress, so a normal day's new addresses do not fail the run.

## Table completeness (since 17 Sep)

An address is **complete** when `ip_intelligence` has a FraudLogix or proxycheck.io row with `is_proxy` filled, and `ip_geo` has a row with a state or a city. IP2Proxy PX12 does not count (it only lists known proxies). Private and reserved addresses are excluded.

| Item | Detail |
|---|---|
| Module | `src/completeness.py`; report `serving/ipintel_curated/table_completeness.json`, rebuilt after every run |
| Checks on both daily jobs | "Every address seen in the last 90 days is complete in both tables" (fails the run if an unqueued address in the window is incomplete) and "Table completeness exported" (progress) |
| State on 17 Sep | 4,959,913 addresses; 4,501,335 complete (90.75%); 458,578 waiting for a proxycheck.io answer; 194,500 of 194,514 in the 90-day window complete |
| Closing the gap | One proxycheck.io answer fills risk and location together; about 6 days at 78,000 a day |
| Queries | `sql/checks/table_completeness.sql`, `gap_detail.sql`, `acceptable_vendor_gap.sql` |
| Full write-up | `DATA_COMPLETENESS.md` |

## Budget and timing, as of 18 Sep 2026 (owner decision)

proxycheck.io's day runs **05:30 IST to 05:30 IST** (midnight UTC). The plan allows 80,000 queries a day.

| When (IST) | UTC | What | Queries |
|---|---|---|---|
| **05:45** | 00:15 | Enrichment run (`ipintel-proxycheck-daily` schedule): queued addresses first, then the backfill | **up to 50,000** |
| 13:00 | 07:30 | Daily load of new IPs from all three sources. Its proxycheck.io hand-off sends nothing once the 50,000 are used; new IPs are queued for the next 05:45 run | 0 after the morning run |
| 03:30 (night) | 22:00 | Safety top-up: only finishes the 50,000 if the morning run stopped early | never past 50,000 |
| **Any time** | | **The owner's own use of the key** | **30,000** |

- **Settings** on `job/proxycheck-daily`: `daily_budget` and `budget_cap` 50000; `live_reserve` 30000; `topup_keep` 30000; `queue_extra` 0.
- **Audit:** `audit/2026-09-18T..#update_job`.
- **Your own queries come first.** Queries proxycheck.io counts that are not the pipeline's are yours, and enrichment shrinks to leave room, so the day's total never passes 80,000.
- **Backfill at this pace:** about 457,000 addresses without an acceptable answer take about **9–10 days** at 50,000 a day.

**Code guard (18 Sep):** at the start of each run, `others_today = proxycheck.io's own count − our reserved count`, and the day's budget is capped at `daily_limit − others_today` (`job_proxycheck.handler`). Backup of the previous code: `archive/deployed-code-before-50k-ist-2026-09-18/`.

## Third source live (18 Sep 10:31 UTC)
`experimentation_tools.experiment_router_events` is switched on (`base_table` / `router_events`, validated as the pipeline role: Iceberg, append, 100% valid IPv4 sample).
- **Profile:** 171,988 rows since 7 Apr 2026, written every minute; 129,218 distinct IPs (129,041 public IPv4, 171 IPv6, 6 private); 22 duplicate `router_event_id`; `is_bot` = 1 on 7,163 rows.
- **First load:** 28,477 new addresses; all checks passed; unified refreshed 10:45.

## `is_bot` per vendor (since 18 Sep)
FraudLogix bot/datacenter/spoofed/Tor reasons; proxycheck.io open proxy/compromised/Tor/hosting types; IP2Proxy DCH/CDN/SES usage or a BOTNET/SCANNER/SPAM threat. False when the vendor answered otherwise; empty only when the vendor did not answer. Full mapping and test results: `IS_BOT_MAPPING.md`.

**Top-up guard:** the scheduled top-up stops at `daily_budget`. Going beyond it needs `max_addresses`, which `backfill_chunks.py` sends. `topup_keep` (30,000) is always left for the owner.

## How every new or returning IP is handled, automatically (19 Sep 2026)

**Sources:** `raw.raw_tune_clicks`, `unified.unified_session_summary`, `experimentation_tools.experiment_router_events`. All three are enabled and validated, and they are read only.

| Step | When (IST) | What happens |
|---|---|---|
| 1. Daily load (Job A) | 13:00 | Finds every IP that changed in any of the 3 sources since the last successful run |
| 2a. **New IP** | 13:00 | **Appended**: rows in `ip_geo` and `ip_intelligence` from IP2Location, IP2Proxy and FraudLogix (if it clicked), a row in `ip_occurrences`, and a place in the proxycheck.io queue |
| 2b. **Returning IP** | 13:00 | **Updated**: `last_seen` moves forward. FraudLogix is re-read for every IP clicked in the last 3 days, and its **latest** decision replaces the old one. If proxycheck.io's answer is **older than 30 days**, the IP is queued for a re-check (at most 20,000 a day, most recently seen first) |
| 3. proxycheck.io (Job B) | Right after Job A, and daily at 05:45 | Sends the queue first (new IPs, then re-checks) within the 50,000/day enrichment budget; your 30,000/day is never touched. A new answer **replaces** the old row. Every column, `is_bot` and the reason columns are filled, and empty FraudLogix rows are filled from proxycheck.io |
| 4. Checks | Every run | Row counts, no duplicates, every new IP has a row, every queued IP was sent, every 90-day IP has a FraudLogix or proxycheck.io answer, `is_bot` = `is_flagged`, and every bad row has a reason. **Any failure: nothing is published** |
| 5. Publish | After every run whose checks all pass | `unified.ip_geo`, `unified.ip_intelligence` and the 4 analytics/overview tables are refreshed from the checked copy; the previous files are kept for rollback |

**How long a new IP waits:** it gets rows at the next 13:00 IST load, and the proxycheck.io answer and unified refresh follow straight after, so up to about 24 hours from its first click, session or router event.

**Why location is not re-checked:** IP2Location and IP2Proxy are downloaded databases. Asking them again returns the same answer until the databases themselves are updated.

### The combine rule and new sources (19 Sep 2026, owner's rule)

**For every IP, from any source:**
1. **Checked** for a reliable, complete answer.
2. **Complete answer** from its original source: inserted or updated by the latest timestamp.
3. **Partial answer** (FraudLogix decided, but it never supplies ISP, ASN, compromised, scraper or anonymous): combined with proxycheck.io.
   - Only the empty columns are filled.
   - FraudLogix's decision, flags, `is_bot` and reasons are never changed.
   - When FraudLogix's latest decision is re-read, the filled columns stay (`apply.intel_source`), so the combined answer never flips back to empty.
4. **No answer** (FraudLogix undecided, or an IP only in sessions or router events): proxycheck.io resolves it, and empty FraudLogix rows are filled and marked.
5. **proxycheck.io's full answer** is always kept as its own `(IP, proxycheck_io)` row, for vendor comparison.

**Unresolved IPs of any age:**
- **Queued every day** by `pcqueue.enqueue_unresolved`, and sent first.
- **Checked:** Job B's check "Every public address has a FraudLogix or proxycheck.io answer" covers **all** public IPs, not only the last 90 days.
- **Exceptions:** IPs proxycheck.io returned no record for are reported, not re-sent every day.

**Adding a new source table later.** No code change is needed:
1. **Read access:** an admin grants the pipeline roles read-only access to the new table (as in `ROUTER_IPS_STEPS.md`, Path A).
2. **Register it:** add it to DynamoDB `ipintel-pipeline-state` as `base_table / <id>`, with `database`, `table`, `ip_column`, `seen_at_column` and `enabled = false`.
3. **Validate:** run Job A with `{"action": "validate", "id": "<id>"}`. It checks the columns, the IP format and read access.
4. **Enable:** set `enabled = true`. From the next 13:00 IST load, its IPs follow exactly the rules above.

### Status after step 3 (19 Sep 2026, 18:40 UTC)

`build/pipeline/sql/checks/final_verification.sql` on the live unified tables:

| Check | Result |
|---|---|
| Public IPs in the 3 sources | 4,989,853 |
| With a proxycheck.io answer | 4,989,792 |
| With a FraudLogix decision | 4,534,201 |
| Not in the tables yet | 61 (39 router + 26 click IPs that arrived after the 13:00 IST load; added at the next load) |
| Empty core flags, empty `is_bot`, empty flag columns on answered rows | 0 |
| `is_bot` ≠ `is_flagged`, bad rows without a reason, duplicates | 0 |
| unified = curated row counts | 14,513,895 / 9,990,828 |
| FraudLogix rows with no ISP | 29,773: 29,770 where proxycheck.io has no ISP either, 3 without a proxycheck.io row |
