# IP Project — Final Plan

**Date:** 14 September 2026 · **Status:** final plan for sign-off · **Replaces:** `DAILY_PIPELINE_PLAN.md`

This is the plan to finish the IP project. It covers how the IP tables grow incrementally as the two
production source tables grow, how each of the six IP tables is updated, and how that is done without
modifying, deleting or adding anything that could disturb the existing production system.

Every fact marked *checked* was read from the live AWS account or from proxycheck.io on 14 September
2026, using read-only calls. Figures marked *projection* are calculated from those checks.

---

## 1. What "finished" means

The project is complete when all of these are true:

1. Both daily jobs have run on their own for **7 days in a row** with every assertion passing.
2. **Every IP address** in the two source tables is present in `ipintel_curated.ip_geo`.
3. The API and the Lovable app read the `ipintel_curated` tables, switched after 3 clean days in shadow mode.
4. Every address seen in the last 90 days has a proxycheck.io answer. At 50,000 a day that takes about
   5 days.
5. The live lookup uses the paid proxycheck key and the shared query counter.
6. The Safety, Base Tables, Daily Jobs and proxycheck Budget pages work in the Lovable app.
7. Every alarm has been triggered once on purpose and was received.
8. The daily permission check and activity review have passed every day, confirming the pipeline
   never wrote to production.

---

## 2. Production is not disturbed

### 2.1 The rule

**This project reads production. It never writes to it.** The daily jobs have no write permission on
any production database, including `unified`. Everything they write lives in this project's own
database, `ipintel_curated`, and its own S3 folder. Everything added is new, named `ipintel-…`, and
connected to nothing that exists today.

### 2.2 Where the updated tables live

The incrementally updated tables are **new tables in this project's own database, `ipintel_curated`**:

| New table, updated daily | Same columns as the existing table |
|---|---|
| `ipintel_curated.ip_geo` | `unified.ip_geo` |
| `ipintel_curated.ip_geo_analytics` | `unified.ip_geo_analytics` |
| `ipintel_curated.ip_intelligence` | `unified.ip_intelligence` |
| `ipintel_curated.ip_intelligence_analytics` | `unified.ip_intelligence_analytics` |
| `ipintel_curated.vendor_overview_geo` | `unified.vendor_overview_geo` |
| `ipintel_curated.vendor_overview_proxy` | `unified.vendor_overview_proxy` |

**The six existing `unified` tables are never changed.** They stay exactly as they are, holding the data
as of 11 September. Nothing is converted, renamed, replaced or turned into a view.

Updating the existing tables directly was ruled out for two reasons. It would change existing tables on
every run. It would also require write access inside `unified`, the database that holds
`unified_session_summary` and about 200 other production tables, which removes the strongest
protection in 2.4.

The API and the Lovable app are pointed at the `ipintel_curated` tables once shadow mode has passed.
Whether the frozen `unified` copies are later removed or kept is a separate decision for your team,
and is not part of this plan.

### 2.3 Everything the project touches, in five groups

**Read only — never changed**

| Object | What is read |
|---|---|
| `raw.raw_tune_clicks` | IP addresses, click times, FraudLogix decisions, and the table's write log |
| `unified.unified_session_summary` | IP addresses, session dates, and the table's write log |
| `unified.uct_leads` | Customer postal addresses, once a month, for the location comparison |
| AWS Glue catalog | Table and column names, so the UI can offer them as choices |
| proxycheck.io | Answers about IP addresses |

**Never touched in any way**

- Every other table in `unified`, `raw`, and every other database
- Every existing Lambda, Glue job, Glue crawler, EventBridge rule and Step Function
- Every S3 bucket setting: bucket policy, versioning, lifecycle rules, event notifications
- Lake Formation, and every IAM role and policy not named `ipintel-…`
- Every Athena workgroup not named `ipintel…`

**Created earlier by this project, and never changed again**

| Object | Created | What happens to it |
|---|---|---|
| `unified.ip_geo`, `unified.ip_geo_analytics` | 11 September | Nothing. Kept exactly as it is |
| `unified.ip_intelligence`, `unified.ip_intelligence_analytics` | 11 September | Nothing. Kept exactly as it is |
| `unified.vendor_overview_geo`, `unified.vendor_overview_proxy` | 11 September | Nothing. Kept exactly as it is |

**This project changes no object in any production database.**

**Created earlier by this project, and updated by the pipeline**

| Object | Created |
|---|---|
| Glue database `ipintel_curated`, where the six new incrementally updated IP tables are created | this project's working area |
| S3 folder `datalake-landingzone-221490242148-us-west-2/ip-intelligence/` | this project's storage |
| Lambda `ipintel-findings-api`, role `ipintel-api-role` | the API the Lovable app calls. Its code is switched to read `ipintel_curated` |
| DynamoDB table `ipintel-sources` | the vendor list |
| Athena workgroups `ipintel`, `ipintel_etl` | this project's queries |
| Secrets `ipintel/proxycheck` (free), `ipintel/proxycheck-paid` | proxycheck keys |

**New, added by this plan**

| Object | Purpose |
|---|---|
| IAM role `ipintel-builder-role` | The only identity used to build this project. See 2.7 |
| IAM role `ipintel-pipeline-role` | The only identity the daily jobs run as |
| Lambda `ipintel-free-daily` | Daily job A |
| Lambda `ipintel-proxycheck-daily` | Daily job B |
| Two schedules in EventBridge Scheduler | Start the jobs. Scheduler is separate from EventBridge rules, so nothing is added to the default event bus that production rules listen on |
| DynamoDB table `ipintel-pipeline-state` | Base table list, shared query counter, run log |
| SQS queue `ipintel-proxycheck-dlq` | Holds a failed hand-over so it is never lost silently |
| CloudWatch alarms `ipintel-…` | Alerts |

No new Glue database is created. Everything the jobs write goes into `ipintel_curated`, which this
project already owns.

### 2.4 How it is enforced

Every protection below is enforced by AWS itself, so it still holds if the code has a bug.

| Protection | What it stops |
|---|---|
| The jobs run as `ipintel-pipeline-role`, used by nothing else | They cannot borrow permissions from any existing system |
| That role may write only to `ipintel_curated`, the project's S3 folder, and its own DynamoDB table and queue | It cannot write to `unified`, `raw`, or any other database, including tables added in future |
| **An explicit deny on every write to the `unified` and `raw` databases**, and to every other database except `ipintel_curated` | An explicit deny overrides every allow, so even a wrongly added permission cannot reach production |
| **An explicit deny on writing to the `datalake-raw` and `datalake-unified` buckets**, and to every path in `datalake-landingzone` outside `ip-intelligence/` | Production data files cannot be created, changed or deleted |
| **An explicit deny on using any Athena workgroup except `ipintel` and `ipintel_etl`**, including `primary` | The jobs cannot run anything in the workgroups your team uses |
| An explicit deny on changing any bucket setting, EventBridge rule, Glue job, Glue crawler, Lake Formation setting or IAM object | The jobs cannot change how the existing system is wired |
| **A permissions boundary on the role** | A ceiling no attached policy can exceed. If someone later adds a broad policy to the role by mistake, AWS still refuses anything outside the project |
| The API role `ipintel-api-role` gets the same denies on `unified`, `raw`, other workgroups and production buckets | The live lookup is held to the same rules |
| Queries run one at a time, and each is capped at 10 GB read | The jobs cannot crowd out production queries or run an accidental huge scan |
| All new resources are tagged `project=ipintel`, with a monthly spend alarm | Any unexpected cost shows up quickly |

### 2.5 Safety controls that run every day

| Control | What it does |
|---|---|
| **Permission check before every run** | AWS's permission simulator confirms the role still cannot write to `unified`, `raw`, the production buckets or any other workgroup. If it could, the run stops and the jobs are paused |
| **Activity review after every run** | The job reads CloudTrail, AWS's own audit log, for every call its role made in the last 24 hours. Any call touching something outside the project pauses the jobs and raises an alarm |
| **Emergency stop** | One switch on the Safety page stops both jobs and every live proxycheck call immediately. Nothing is deleted. Resuming is refused while a safety check is failing |
| **Shadow mode first** | For the first 3 days the jobs update `ipintel_curated` while the API and app keep reading today's tables. They switch to the new tables only after 3 clean days and your approval |
| **Your approval at every step that changes anything** | Nothing is built or changed without your go for that specific step, and each step is reported with proof before the next one starts |

### 2.6 Ways the pipeline could disturb production indirectly, all checked

Writing only to our own folder is not enough on its own. Other systems in the account react to files
appearing in S3, so I checked each of them.

| Could our file writes… | Checked | Result |
|---|---|---|
| …be picked up by a Glue crawler and create tables in a production database? | 90 crawler targets on this bucket | **No.** Every one points at a different folder. None at `ip-intelligence/` or the bucket root |
| …trigger a bucket event notification? | All 11 notifications | **No.** They watch `sms-source-onboarding-gar/pitchprfct/…`, `client_data/`, `OpenAQ/process/` and `onesignal_raw/` only |
| …trigger an EventBridge rule? The bucket sends every write to EventBridge | 26 event-driven rules on 11 event buses | **No.** Two rules match S3 writes in general, `BounceEvents` and `raw-trigger-rule`, and both have **no targets**, so a match does nothing. `raw-trigger-rule` also watches only a different bucket |
| …be deleted by the bucket's lifecycle rule? | The one bucket-wide rule | **No.** It moves files older than 30 days to Intelligent-Tiering and removes only superseded versions after 1 day. It never deletes a current file. Iceberg never overwrites files, so this is compatible |
| …collide with an existing resource name? | Lambda, IAM, DynamoDB, EventBridge | **No.** The only existing `ipintel` resources are this project's own three |
| …need a Lake Formation grant? | Both source tables | **No.** Neither is governed by Lake Formation |
| …have run anything in the `primary` workgroup your team uses? | CloudTrail for every query this login started since 1 September, then Athena's own record of what each statement was | **Three plain reads, nothing changed.** This project's scripts ran 3 `SELECT` queries there on 2 September, before its own workgroups existed. All other project queries used `ipintel` or `ipintel_etl`. The project's Lambda is refused access to `primary` by AWS |
| …change any Athena workgroup's settings? | CloudTrail since 1 September | **No.** The only workgroup calls are this project creating `ipintel` and `ipintel_etl` on 2 September. `primary` was never updated or deleted |

### 2.7 The AWS login is shared, so the build gets its own fenced identity

The audit in 2.6 found that the login this project uses, `source_creation_tool_user`, is also used
by at least two other things:

| Used by | Queries in `primary` since 1 September | What it changed |
|---|---:|---|
| The Athena web console, from a Windows browser | 277 | Created and dropped tables and views in `ip-database`, the IP project's earlier database. Nothing in `unified` or `raw` |
| A separate Claude Code session on this computer, project `Source-Creation-Tool-SMS-Migration` | 107 | On 1 September: `UPDATE unified.lu_connector SET name='Klaviyo FluxaLeads' WHERE id='77'`, and `DROP TABLE IF EXISTS de_temp.klaviyo_uct_events`. Two `ALTER TABLE unified.lu_connector` attempts failed and changed nothing |
| This IP project's scripts | 3 | Nothing. All three were plain reads |

The two production changes on 1 September were not made by this project. This project's session log
contains neither statement. That session's log contains both, from 31 August onward.

Because any tool holding this login can change production, the login alone is not a safe fence. So:

- **Every build step runs through a new role, `ipintel-builder-role`**, not through the shared login's
  own permissions. It carries the same permissions boundary and denies as the pipeline role, plus
  permission to create resources named `ipintel-…` only.
- **AWS itself then refuses** any production write attempted during the build, including one made by
  mistake.
- **Every build action is recorded under that role's name** in CloudTrail, so it can never be confused
  with the console or with another session.

Worth doing separately, outside this project: give each person and each tool its own login, so a
change like the one to `unified.lu_connector` can always be traced to who made it.

### 2.8 Every change can be undone

| Change | How it is undone |
|---|---|
| Building the incrementally updated tables in `ipintel_curated` | Delete them. The existing `unified` tables are untouched throughout |
| Pointing the API at `ipintel_curated` | Redeploy the saved previous package, which reads the `unified` tables again |
| Deploying new code to `ipintel-findings-api` | Redeploy the saved previous package |
| Adding the new role, Lambdas, schedules, table, queue, alarms | Delete them. Nothing existing depends on them |
| A daily run | Every change is recorded in the run log, and Iceberg keeps earlier versions of each table |

---

## 3. How the increment in the two source tables is detected

### 3.1 How each source table grows

Both are Iceberg tables, which keep a log of every write. *Checked* over the last five days.

| | `raw.raw_tune_clicks` | `unified.unified_session_summary` |
|---|---|---|
| Kind of write | Adds new rows only | Rewrites existing rows |
| When | Every 6 hours: 00:06, 06:06, 12:06, 18:06 UTC | Once a day, normally 06:21 to 06:26 UTC |
| Rows per write | 11 to 156 | 46,714 to 766,277 rewritten |
| Written by | `acquire_tune_polling_lambda` | `incremental-daily-combined-v2-dates` |
| On 14 September | On time | **No write as of 09:51 UTC** |

### 3.2 Why reading the write log is the only option

To react the moment a row is written, something would have to be added to production: an S3 event
notification on the production bucket, or a change to the jobs that write these tables. Both are ruled
out. Reading each table's write log on a schedule changes nothing, so that is what the pipeline does.
**Every row written since the last successful run is handled on the next run.**

### 3.3 How the increment is worked out

| Source | Increment | Why |
|---|---|---|
| Tune clicks | Rows added since the last run's recorded version, read straight from the write log | The table only adds rows, so the log says exactly what is new |
| Session summary | Addresses in the table that are not yet in `ipintel_curated.ip_geo` | Each rewrite also touches addresses we already have, and a day's addresses keep arriving for 2 to 3 days. Comparing against our tables catches every new address however late it lands. It reads 0.24 GB, about a tenth of a cent |

*Checked* evidence that session addresses arrive late: on 12 September, sessions had contributed 0 new
addresses so far. Complete days bring **552 to 1,260** brand-new addresses in total.

### 3.4 One consistent version per run

A run records the version of each source table it read and uses only that version throughout. A write
landing mid-run cannot make two steps disagree. The next run starts from those recorded versions.

---

## 4. How each of the six IP tables is updated

### 4.1 Rules that apply to all four per-address tables

- **One row per address per vendor.** The key is `(ip_address, vendor)`.
- **New address:** every vendor's row is inserted.
- **Existing address, new vendor answer:** that vendor's row is added. This is the "append".
- **Existing row whose answer changed:** the values and `updated_at` change. `created_at` never changes.
- **Existing row with no change:** left untouched, so nothing is rewritten for no reason.
- **A vendor asked about an address but with no answer** still gets a row, marked as no answer. Without
  it, "never asked" and "asked, no answer" would look the same.
- **Yes, No and no answer** are three different values. No answer is never stored as No.

### 4.2 Table by table

The jobs write only to the new `ipintel_curated` tables. The `unified` tables are not written.

| Table the jobs write | Same columns as | Grows when | Written by | Rows affected each run |
|---|---|---|---|---|
| `ipintel_curated.ip_geo` | `unified.ip_geo` | A new address appears. A downloadable database is reloaded and changes an answer. proxycheck answers an address | Job A, Job B | New addresses times the location vendors, plus any changed rows |
| `ipintel_curated.ip_intelligence` | `unified.ip_intelligence` | A new address appears. An address gets new tune clicks, so its FraudLogix decision may change. proxycheck answers an address. A live lookup misses | Job A, Job B, live lookup | New addresses times the risk vendors, plus changed rows |
| `ipintel_curated.ip_geo_analytics` | `unified.ip_geo_analytics` | Any `ip_geo` row for that address changed | Job A, Job B | Only addresses whose location answers changed |
| `ipintel_curated.ip_intelligence_analytics` | `unified.ip_intelligence_analytics` | Any `ip_intelligence` row for that address changed, or the published range lists were reloaded | Job A, Job B | Only addresses whose risk answers or list membership changed |
| `ipintel_curated.vendor_overview_geo` | `unified.vendor_overview_geo` | Any location data changed | Job A, Job B | All rows, one per location vendor |
| `ipintel_curated.vendor_overview_proxy` | `unified.vendor_overview_proxy` | Any risk data changed | Job A, Job B | All rows, one per risk vendor |

The two analytics tables are recalculated only for affected addresses, because an address's consensus
depends on every vendor's answer for that address and nothing else.

The two scorecards are small and recalculated in full each run. Each is scored over the addresses that
**every vendor on that scorecard was asked about**, and shows how many that is. Scoring each vendor
over a different set of addresses would make the fill rates incomparable.

### 4.3 proxycheck's location answer goes into `ip_geo`

proxycheck returns a location in the same response as its proxy answer, at no extra cost. `ip_geo`
already has `proxycheck_io` as a vendor. So Job B writes proxycheck's location to `ip_geo` as well as
its proxy answer to `ip_intelligence`.

---

## 5. Job A — `ipintel-free-daily`

**Starts:** 07:30 UTC (13:00 IST), about an hour after session summary normally lands.
**Spends:** no paid queries.

### 5.1 Vendors it asks

Every enabled vendor except proxycheck.io, which has its own job. *Checked:* nine vendors are enabled.

| Vendor | Answers | How | Limit | Addresses |
|---|---|---|---|---|
| IP2Location DB11 | location | Lookup in the downloaded database | none | every address |
| MaxMind GeoLite2 | location | Lookup in the downloaded database | none | every address |
| DB-IP City Lite | location | Lookup in the downloaded database | none | every address |
| IP2Proxy PX12 | proxy | Lookup in the downloaded database | none | every address |
| Published range lists | known proxy ranges | Match against Tor, Apple, AWS, Google, Cloudflare, Fastly lists | none | every address |
| FraudLogix | proxy, bot | Latest decision in tune clicks | none | addresses in tune clicks |
| ipinfo.io | location | Web API, paced | 50,000 a month | new addresses |
| ipwho.is | location | Web API, paced | fair use | new addresses |

The web APIs are asked only about new addresses, at most 1,260 on a complete day, so they stay inside
their free limits. Anything they cannot answer today carries over to tomorrow.

### 5.2 Steps

1. Check `ipintel-pipeline-role` with the permission simulator. If it could write to production, stop.
2. Read the enabled base tables that passed their last check. Skip any that failed and name them in the
   run log.
3. Read each base table's write log. If nothing changed since the last run, record "nothing new" and
   stop. If a base table has been silent for over 30 hours, raise an alarm.
4. Record the version of each base table being read.
5. Work out the increment, as in section 3.3.
6. Ask every vendor in 5.1 and write the answers to a staging table in `ipintel_curated`.
7. Compare the answers.
8. Upsert `ipintel_curated.ip_geo` and `ipintel_curated.ip_intelligence`, following section 4.1.
9. Recalculate both analytics tables for the affected addresses and upsert them.
10. Recalculate both scorecards and republish the files the dashboard reads.
11. Run the assertions in 5.3.
12. If all pass, record the base table versions as the new starting point and start Job B.

### 5.3 Assertions

If any fails, the run is marked failed, the starting point does not move, and the next run repeats the
same increment.

| Assertion | Catches |
|---|---|
| No address appears twice for the same vendor in any of the four tables | A lookup that matched twice |
| Every enabled vendor has rows from this run | A vendor that silently returned nothing |
| No IP table has fewer rows than before | An upsert that deleted instead of updated |
| Every new address from step 5 is in `ipintel_curated.ip_geo` | An address that fell through |
| Every updated row kept its original `created_at` | A row replaced instead of changed |
| Every scorecard is scored over addresses all its vendors were asked about | Incomparable fill rates |
| The pipeline role still cannot write to `unified`, `raw`, the production buckets or any other workgroup | A permission change |

### 5.4 Safe to run twice

Step 5 skips addresses already present and step 8 changes only what differs. Running the same day
twice leaves every table exactly as one run does.

---

## 6. Job B — `ipintel-proxycheck-daily`

**Starts:** as soon as Job A succeeds, and at 10:00 UTC (15:30 IST) if Job A did not start it.
**Spends:** up to 50,000 proxycheck queries a day, set in the UI and capped on the server.
**Key:** `ipintel/proxycheck-paid`. *Checked:* readable, plain text, accepted by proxycheck, plan
"Subscription", 80,000 a day.

### 6.1 Bulk calls

proxycheck accepts **up to 1,000 addresses per request**. *Checked* with real addresses and the exact
settings the job uses:

| Batch | Time | Size | Answered |
|---:|---:|---:|---:|
| 100 | 0.56 s | 133 KB | 100 of 100 |
| 400 | 0.93 s | 355 KB | 400 of 400 |

*Projection:* a 1,000-address batch takes about 2 seconds, and 50 batches a few minutes, against Lambda's
15-minute limit. Requests must identify themselves with their own request header: proxycheck's firewall
refused Python's default header in testing.

### 6.2 Which addresses

Addresses in `ipintel_curated` with no `proxycheck_io` answer, in this order:

1. Addresses first seen today.
2. Addresses the other vendors leave **without a conclusion**, seen in the last 90 days (from
   `ip_occurrences`), then older ones. Within that: vendors disagree, then flagged with nothing
   confirming it, then no vendor answered.
3. Addresses every answering vendor calls clean, most recently seen first.

*Checked 14 September:* 925,606 addresses have no conclusion, 124,689 of them seen in the last 90 days.
The first day's 49,504 addresses (1% of the 50,000 is kept for addresses charged twice) are 47,961
flagged-unconfirmed and 1,543 disputed, all seen in the last 90 days. Every unresolved address is asked
in about 19 days; all 4,956,391 in about 100.

### 6.3 The loop

1. **Plan the day once.** The first run picks the addresses and saves them as batch files of 1,000.
   Later runs that day reuse those files.
2. **A batch is done only when its saved response file exists.** That file is the single record of
   progress.
3. **Reserve before sending.** Reserve 1,000 queries in the shared counter in `ipintel-pipeline-state`.
   The reservation succeeds only if it stays within budget. Live lookups reserve from the same counter,
   so two callers can never both take the last queries.
4. **Send, then save the response immediately**, before anything else happens.
5. **Watch the clock.** With under 2 minutes left, stop starting batches and start a fresh copy of the
   job to continue. A failed hand-over goes to `ipintel-proxycheck-dlq` with an alarm.
6. **When every batch is saved,** upsert `ipintel_curated.ip_intelligence` and `ipintel_curated.ip_geo`,
   then the two analytics tables and both scorecards.
7. Run the same assertions as Job A.

Only one copy of Job B may run at a time.

### 6.4 Your five requirements

| Requirement | How it is met |
|---|---|
| No data loss | Every response is stored before it is used. The upsert reads only stored files |
| No downtime | Readers always see the last finished version of each table while a write is in progress |
| Valid API calls | One request per batch of at most 1,000 addresses, with settings proven in testing |
| No key exhaustion | Queries reserved in a shared counter before sending, 10,000 a day held back for live lookups, one copy at a time |
| No Lambda timeout | Batches take about a second, and the job hands over well before the limit |

### 6.5 Capacity on the $9.99 plan

| Use | Queries per day |
|---|---:|
| Job B | 50,000 |
| Live lookups, if every address on the busiest day of the last 30 missed | 4,364 |
| Addresses charged twice, *checked* at 504 queries for 500 addresses | 435 |
| **Worst case** | **54,799** |
| **Daily limit** | **80,000** |

### 6.6 When something goes wrong

| Failure | What happens | Answers lost | Queries wasted |
|---|---|---:|---:|
| proxycheck slow or server error | That batch is retried three times, waiting longer each time | 0 | 0 |
| proxycheck returns a warning | The answer is kept. Warnings still carry the full result | 0 | 0 |
| Daily budget reached | Stops. Tomorrow resumes from the saved files | 0 | 0 |
| Key rejected | Stops, alarms, sends nothing more | 0 | 0 |
| Crash after saving a response | The next copy skips that batch | 0 | 0 |
| Crash between the answer arriving and being saved | That batch is sent again | 0 | up to 1,000 |
| Two copies start together | Prevented | 0 | 0 |
| Hand-over fails | Retried, then held in the queue with an alarm | 0 | 0 |

---

## 7. Live lookup

`GET /lookup/{ip}` (page specified in `LOVABLE_PROMPT_IP_LOOKUP.md`). Built and tested 14 September.

| Step | What happens |
|---|---|
| Read | `ip_geo`, `ip_intelligence` and `ip_occurrences`. In shadow mode each vendor's row comes from `unified` when it has one, otherwise from `ipintel_curated`, so answers bought by the backfill are never bought again |
| Resolve | Vendor rows are **never changed** to make them agree. One row per address and vendor stays as the vendor said it. The answer to use is worked out at read time and returned as `resolved`, naming the vendors it rests on |
| Location answer | The place most vendors agree on (state and city), fields from the best-scoring vendor in that group. Otherwise the best-scoring vendor that answered |
| Proxy answer | proxycheck.io decides once it has answered. Without it: clean when every answering vendor says clean, confirmed when a published range confirms a flag, otherwise no conclusion |
| Ask proxycheck.io when | No location answer, or no proxycheck answer and the other vendors reach no conclusion. Never again for an address it has answered, unless `refresh=true` |
| Before asking | Not paused. Two queries reserved in the shared daily counter |
| After asking | Raw answer saved to S3 before use: one copy for the proxycheck job to fold into `ip_geo` and `ip_intelligence` (same merge and assertions as its batches), one keyed by address so a repeat lookup is free at once |
| Mapping | `Hosting` is datacenter. `Business` is not: 112 of 400 real addresses were `Business`, mostly Charter, Cox, AT&T, CenturyLink and Verizon Business broadband |

### 7.1 Where an address occurs

`ipintel_curated.ip_occurrences`, one row per address and base table: first seen, last seen, days seen,
rows. Job A recomputes it from the pinned versions of the base tables every run and merges, so first
seen only moves earlier and last seen only later. Built 14 September: 2,010,425 session-summary rows and
4,533,252 tune-click rows, no duplicates.

"New address" for Job A means IP2Location has no row yet, so an address first answered by a live lookup
still gets every other vendor once it reaches a base table.

---

## 8. Control from the UI

Specified in `LOVABLE_PROMPT_PIPELINE_CONTROL.md`.

| Page | What it controls |
|---|---|
| Base Tables | Add, remove, pause or change the tables addresses are collected from. Choices come from the real catalog. Every change is checked before a run uses it |
| Daily Jobs | Switch each job on or off, run it now, see each run's counts, assertions and history |
| proxycheck Budget | Key status, today's reserved queries against the limit, and the daily budget up to a server-enforced cap |
| Vendor Sources | Already built |

Adding a base table in the UI does not change production. The table is only read, and the pipeline
role cannot write to it.

---

## 9. One-time preparation

Each row is one step. Nothing in a row happens until you approve that row.

| Step | What changes | Production impact | Undo |
|---|---|---|---|
| **Create `ipintel-builder-role`** with the permissions boundary and denies in 2.4, and switch every later build step to it | A new role | None. It can only create `ipintel-…` resources | Delete it |
| **Create `ipintel-pipeline-role`** with every protection in 2.4, including the permissions boundary | A new role | None. Nothing uses it yet | Delete it |
| **Prove both roles cannot touch production** before either runs anything | Nothing. AWS's permission simulator is asked about every production table, bucket and workgroup | None | Not needed |
| **Add the same denies to `ipintel-api-role`** | This project's own API role | None. It only removes abilities | Remove the added deny |
| **Fix the `Business` mapping and add the shared counter** in the live lookup | This project's own Lambda | None | Redeploy the saved package |
| **Create `ipintel-pipeline-state`**, the dead-letter queue and the alarms | New, isolated resources | None | Delete them |
| **Load GeoLite2, DB-IP and the range lists** into the project's `ip-intelligence/` folder and `ipintel_curated` | Files and tables only this project reads | None | Delete them |
| **Build the six incrementally updated tables** in `ipintel_curated` as Iceberg tables, starting from today's data | New tables in the project's own database | None. `unified` is untouched | Delete them |
| **Shadow mode for 3 days** | The jobs update `ipintel_curated` while the API and app still read today's tables, so results can be compared before anyone relies on them | None | Stop the jobs |
| **Point the API and the Lovable app at `ipintel_curated`** | This project's own Lambda | None. No table is changed | Redeploy the saved package |

---

## 10. Build order

Every step waits for your go. Each ends with a short report and proof before the next begins.

| Step | Work | Production impact | Needs the paid key |
|---:|---|---|---|
| 0 | Create `ipintel-builder-role`, prove with the simulator that it cannot touch production, and use it for every step after this | None | No |
| 1 | Create the pipeline role with the boundary and denies, and prove with the simulator that it cannot touch production | None | No |
| 2 | Tighten `ipintel-api-role` with the same denies | None, removes abilities only | No |
| 3 | Fix the `Business` mapping, add the shared counter, create the state table, queue and alarms | None | No |
| 4 | Load GeoLite2, DB-IP and the range lists | None | No |
| 5 | Build the six Iceberg tables in `ipintel_curated` | None | No |
| 6 | Safety, base table and job endpoints in the API, with server-side caps and the emergency stop | None | No |
| 7 | Paste the Lovable prompt. Each page fills in as its endpoint ships | None | No |
| 8 | Job A run by hand three times, checking every assertion | None. Writes `ipintel_curated` only | No |
| 9 | Job B run by hand on the free key with a 1,000-query budget | None, writes `ipintel_curated` only | No |
| 10 | Point Job B and the live lookup at the paid key, set the budget to 50,000, schedule both jobs | None | Yes |
| 11 | **Shadow mode, 3 days**, both jobs on schedule, `unified` untouched | None | Yes |
| 12 | **With your written approval,** point the API and the Lovable app at `ipintel_curated` | None. No table is changed | No |
| 13 | Monthly database reloads and weekly table maintenance | None | No |
| 14 | Watch 7 days of unattended runs against section 1 | None | Yes |

---

## 11. Running it day to day

| When | What | Who |
|---|---|---|
| Daily 07:30 UTC | Job A | Automatic |
| After Job A, or 10:00 UTC | Job B | Automatic |
| Any time | Live lookup | Automatic |
| Weekly | Reload the published range lists. Merge small files in the Iceberg tables and remove versions older than 7 days | Automatic |
| Twice a week | Reload MaxMind GeoLite2 | Automatic |
| Monthly | Reload IP2Location, IP2Proxy and DB-IP. Refresh the customer postal addresses from `unified.uct_leads` | Automatic |
| When an alarm fires | Read the run log in the Daily Jobs page | Team |

### Alarms

- A job failed, or an assertion failed
- The proxycheck key was rejected
- proxycheck use passed 90% of the daily limit
- A base table has not been written for more than 30 hours
- A hand-over landed in `ipintel-proxycheck-dlq`

---

## 12. What it costs

| Item | Per month | Basis |
|---|---:|---|
| proxycheck.io | $9.99 | Subscribed price, locked |
| Athena | under $1 | *Projection:* about 1 GB read a day |
| Lambda, DynamoDB, SQS, Scheduler | under $1 | *Projection:* two short runs and a few thousand small writes a day |
| S3 | under $1 | *Projection:* 50 response files a day of about 900 KB, plus small Iceberg files |

---

## 13. Risks still open

| Risk | What is done about it |
|---|---|
| proxycheck's daily reset time is not published where I could find it | Confirm it in the dashboard. The 25,201 spare queries absorb a reset that is not midnight UTC |
| Session summary runs late or rebuilds in bulk | Each run pins one version and carries on. An alarm fires after 30 hours of silence |
| Live lookups and the daily jobs write the same tables at once | Iceberg allows this. A clash makes one write fail, and both retry that error |
| ipwho.is has no published limit | Calls are paced, and anything throttled carries over |
| The production owners delete old versions of a source table before a run reads the version it recorded | The run falls back to the latest version and relies on the comparison in 3.3, which does not need old versions |
| `BounceEvents` matches every S3 write in the account and has no target today | Not this project's to change. If someone later gives it a target, it will fire for every write in the account, not only ours. Worth telling its owner |
