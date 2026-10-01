> **Replaced on 14 September 2026 by `IP_PROJECT_FINAL_PLAN.md`.** Follow that plan, not this one.

# Daily IP Pipeline — Complete Plan

**Date:** 14 September 2026 · **Status:** plan for sign-off, nothing built yet

Every timing, count and test result in this document was read from the live data lake or from
proxycheck.io on 14 September 2026. Nothing was written to either production table while producing
it. Figures labelled *projection* are calculated from those measurements, not measured directly.

---

## 1. The answer first: yes, buy the $9.99 plan

$9.99 is the cheapest proxycheck.io plan that fits what you asked for. The $5.99 plan allows 40,000
queries a day, which is less than the 50,000 a day you want processed.

| What had to be true before you spend money | Result | Evidence |
|---|---|---|
| The production tables are never written to | Guaranteed by design | The pipeline's AWS role is only allowed to write to our IP tables. See section 4 |
| A Lambda can read the production tables | Confirmed | Neither table is governed by Lake Formation, so ordinary AWS permissions are enough |
| We know when new addresses arrive | Confirmed | Read from both tables' own write log over five days. See section 3 |
| Our IP tables can insert and update single rows | Confirmed | Tested on a full 4,966,911-row copy, then deleted |
| proxycheck.io accepts many addresses in one call | Confirmed | Sent 500 real addresses from our traffic. All 500 answered |
| One call finishes long before Lambda times out | Confirmed | 400 addresses took 0.93 seconds. Lambda allows 900 seconds |
| $9.99 covers the daily volume | Confirmed | The worst case uses 68.5% of the daily limit. See below |
| The key cannot be used up by accident | Needs a fix first | proxycheck's own usage counter runs up to 14 minutes behind. See section 10 |
| proxycheck answers are stored correctly | Needs a fix first | 28% of real addresses would be wrongly marked as datacenter. See section 10 |

### Daily capacity on the $9.99 plan

| Use | Queries per day |
|---|---:|
| Daily proxycheck job | 50,000 |
| Live lookups, if every address seen on the busiest day in the last 30 days missed | 4,364 |
| Addresses proxycheck charges twice, measured at 0.8% | 435 |
| **Worst case total** | **54,799** |
| Daily limit on $9.99 | 80,000 |
| **Spare** | **25,201** |

In today's test, 500 addresses cost 504 queries. The extra 4 were addresses that came back as both a
proxy and a VPN, which proxycheck charges twice.

### Conditions on the green light

- **Buy before 30 September.** proxycheck has announced a price rise in October. A subscribed price
  stays locked.
- **Do not put the new key into AWS until the two fixes in section 10 are deployed.** The live
  lookup already uses whatever key is stored.
- **Nothing spends the paid key before it is ready.** Every part of this plan can be built and
  tested on the free key's 1,000 queries a day first.

---

## 2. What you asked for, and where each part is answered

| Your requirement | Where |
|---|---|
| Do not touch `raw.raw_tune_clicks` or `unified.unified_session_summary` | Section 4 |
| Whenever a new row is inserted into those tables, use it | Section 3 |
| First look in the IP tables we built. If the address is not there, call proxycheck.io | Sections 5, 7, 8 |
| Green light for the $9.99 plan | Section 1 |
| A complete IP source for every use case in the company | Section 9 |
| A daily Lambda that passes new addresses to each vendor and compares them | Section 6 |
| Update the vendor overview tables and the unified tables with the updated data | Section 6 |
| Each address unique, and only addresses not already in our tables are new | Section 4 |
| First find out when new addresses reach the data lake | Section 3 |
| Look up new addresses in the free sources | Section 6 |
| Assertions: an existing address is appended, a new one is inserted | Sections 4, 6 |
| A separate daily Lambda for 50,000 addresses with no proxycheck.io decision | Section 7 |
| Daily incremental upsert of those results into the unified tables | Section 7 |
| Find out whether proxycheck.io allows bulk calls or one address per call | Section 7 |
| A self-loop with no data loss and no downtime | Section 7 |
| Valid API calls, no key exhaustion, no Lambda timeouts | Section 7 |
| Check how tune clicks and session summary refresh each day | Section 3 |
| Add, remove or change base tables from the UI | Section 9 |

---

## 3. When new addresses reach the data lake

Both production tables are Iceberg tables. Iceberg keeps a log of every write, with the time and
the number of rows added. That log is where these timings come from. Reading the log does not read
or lock the table itself.

### How each production table refreshes

| | `raw.raw_tune_clicks` | `unified.unified_session_summary` |
|---|---|---|
| Kind of write | Adds new rows only | Rewrites existing rows |
| When | Every 6 hours: 00:06, 06:06, 12:06, 18:06 UTC | Once a day, normally 06:21 to 06:26 UTC |
| Rows per write | 11 to 156 | 46,714 to 766,277 rewritten |
| Size of table | about 16.3 million rows | 21,632,319 rows |
| Written by | EventBridge rule `acquire_tune_polling_lambda` | pipeline `incremental-daily-combined-v2-dates` |

### Writes over the last two days

| Time, UTC | Table | Rows added |
|---|---|---:|
| 13 Sep 00:06 | tune clicks | 82 |
| 13 Sep 06:05 | tune clicks | 20 |
| 13 Sep 06:21 | session summary | 46,714 |
| 13 Sep 12:06 | tune clicks | 11 |
| 13 Sep 18:05 | tune clicks | 28 |
| 14 Sep 00:06 | tune clicks | 98 |
| 14 Sep 06:06 | tune clicks | 22 |
| 14 Sep, as of 09:51 | session summary | **no write yet** |

### Three facts that shape the design

**1. Ad clicks have nearly stopped growing.** About 200 new rows a day. They still bring 53 to 193
brand-new addresses a day, so they stay in the pipeline, but sessions now supply most new addresses.

**2. Session addresses arrive days late.** The session pipeline rebuilds a rolling window of recent
days, so addresses for a given day keep appearing for two or three days afterwards.

| Day | Brand-new addresses | First seen in sessions | First seen in tune clicks |
|---|---:|---:|---:|
| 12 Sep | 90 | 0 | 90 |
| 11 Sep | 158 | 105 | 53 |
| 10 Sep | 477 | 413 | 64 |
| 09 Sep | 990 | 912 | 78 |
| 08 Sep | 1,086 | 893 | 193 |
| 04 Sep | 1,260 | 1,086 | 174 |
| 30 Aug | 552 | 417 | 135 |

The last three days are incomplete because those sessions have not been processed yet. Complete days
bring **552 to 1,260 brand-new addresses**. A job that only looked at yesterday would miss most of
them, so the job compares the whole history against our tables every run. That reads 0.24 GB, about
a tenth of a cent.

**3. The session pipeline does not always run on time.** On 14 September it had not written 3.5
hours after its usual time. On 10 September it rebuilt in bulk, writing nine times and adding
8,114,990 rows in one of those writes. The pipeline has to cope with both.

### How "whenever a new row is inserted" is detected

There are only two ways to react to new rows in someone else's table. One is to hook into the
writes, by adding S3 event notifications to the production buckets or changing the jobs that write
them. The other is to read the write log on a schedule.

The first changes production, which you ruled out. So the pipeline reads the write log on a
schedule, and **every row written since the last successful run is processed on the next run**.

- **For tune clicks,** which only add rows, the log says exactly which rows are new.
- **For session summary,** which rewrites rows, a rewrite also touches addresses we already have.
  So new addresses are found by comparing the table against our IP tables, which gives the same
  result however late a row arrives.

The job runs daily, as you asked. It is cheap enough to run after every tune-click write, about
every 6 hours, if you ever want new addresses to flow through sooner.

---

## 4. Rules that hold everywhere

### The production tables are only ever read

This is enforced by AWS permissions, so it holds even if the code has a bug.

| Protection | What it stops |
|---|---|
| The pipeline runs under its own AWS role, used by nothing else | It cannot borrow permissions from another system |
| That role may write to exactly our IP tables, each named individually | Every other table, including any added later, is read-only automatically |
| An explicit deny on writing anywhere outside our IP tables' storage | An explicit deny overrides any allow, so a mistyped name is refused by AWS |
| No write permission on a whole database | Our IP tables share the `unified` database with `unified_session_summary`. A database-wide grant would have reached it |

### What "unique", "appended" and "inserted" mean

You asked for every address to be unique, and also for an existing address to be appended and a new
one inserted. Both hold when uniqueness is counted per **address and vendor**.

| Situation | What happens | Your words |
|---|---|---|
| Address not in our tables at all | Every vendor's answer is inserted | "if it doesn't, it gets inserted" |
| Address exists, but this vendor has not answered it yet | This vendor's answer is added beside the others | "if the IP exists it gets appended" |
| Address exists and this vendor's answer changed | That one row is updated. `updated_at` moves, `created_at` stays | "upserts" |
| Address exists and nothing changed | Left untouched, nothing rewritten | |

There is never more than one row for the same address from the same vendor.

### Every vendor records every address it was asked about

A vendor that was asked and had no answer still gets a row, with `has_answer = false`. Without this,
"never asked" and "asked but no answer" look identical, and the vendor scorecards would compare
vendors over different sets of addresses.

### Yes, No and no answer are three different things

Every yes/no column has three states. `true` means yes, `false` means no, and empty means the vendor
never answered. Empty is never counted as no.

---

## 5. The whole flow

```
 PRODUCTION (read only)                     OUR IP TABLES
 raw.raw_tune_clicks          ─┐
 unified.unified_session_summary ─┤  write log checked daily
 + any base table added in the UI ┘
                │
                ▼
 ┌─────────────────────────────────────────────────────────┐
 │ LAMBDA A  ipintel-free-daily            07:30 UTC        │
 │                                                          │
 │  1. which addresses are new or changed?                  │
 │  2. already in our IP tables? ── yes ──► skip or refresh │
 │                               └─ no ───► ask vendors     │
 │  3. ask every free vendor                                │
 │  4. compare their answers                                │
 │  5. upsert unified.ip_geo, unified.ip_intelligence       │
 │  6. refresh both analytics tables and both scorecards    │
 │  7. assertions ── any fail ──► stop, record nothing      │
 └───────────────────────────┬─────────────────────────────┘
                             │ succeeded: start Lambda B
                             ▼
 ┌─────────────────────────────────────────────────────────┐
 │ LAMBDA B  ipintel-proxycheck-daily                       │
 │                                                          │
 │  1. addresses in our tables with no proxycheck answer    │
 │     today's new ones first, then most recently seen      │
 │  2. up to 50,000, in batches of 1,000                    │
 │  3. reserve queries ─► call proxycheck ─► save response  │
 │  4. near the time limit? hand over to a fresh copy       │
 │  5. all saved ─► upsert unified.ip_intelligence          │
 │  6. refresh analytics and the proxy scorecard            │
 └─────────────────────────────────────────────────────────┘

 LIVE LOOKUP  GET /lookup/{ip}   any time
   our IP tables ── found ──► answer
                └─ missing ──► reserve 1 query ─► proxycheck ─► answer and append
```

Lambda B starts as soon as Lambda A succeeds, so addresses that arrived today reach proxycheck the
same day. It also has its own daily schedule at 10:00 UTC. If Lambda A failed, Lambda B still works
through the backlog.

---

## 6. Lambda A — `ipintel-free-daily`

**Runs:** daily at 07:30 UTC (13:00 IST), about an hour after sessions normally land.
**Spends:** no paid queries. Stays inside every free vendor's own limit.

### Which vendors it asks

"Each vendor" means every enabled vendor in the vendor registry except proxycheck.io, which has its
own job. Nine vendors are enabled today.

| Vendor | Answers | How it is asked | Limit | Covers |
|---|---|---|---|---|
| IP2Location DB11 | location | Range lookup in Athena against the downloaded file | none | every address |
| MaxMind GeoLite2 | location | Range lookup against the downloaded file | none | every address |
| DB-IP City Lite | location | Range lookup against the downloaded file | none | every address |
| IP2Proxy PX12 | proxy | Range lookup against the downloaded file | none | every address |
| Published range lists | known proxy ranges | Match against Tor, Apple, AWS, Google, Cloudflare, Fastly lists | none | every address |
| FraudLogix | proxy, bot | Latest decision for the address in tune clicks | none | addresses in tune clicks |
| ipinfo.io | location | Web API, paced | 50,000 a month with a token | new addresses only |
| ipwho.is | location | Web API, paced | fair use | new addresses only |
| proxycheck.io | proxy, location | **Not asked here.** Lambda B | | |

The four downloadable databases need no calls, so they cover all 4.96 million addresses as well as
each day's new ones. The two web APIs are asked only about new addresses. That keeps them inside
their free limits, because complete days bring at most 1,260 new addresses. Anything a web API cannot
answer today carries over to tomorrow using the same saved-progress method as Lambda B.

`geojs.io` stays disabled on purpose. It returns MaxMind's answers exactly, so enabling it would
count one opinion twice.

### Steps

1. **Read the base table list.** Take every enabled base table that passed its last check. A table
   that fails its check is skipped and named in the run log, so one bad entry cannot stop the rest.
2. **Check the write logs.** If no base table has a new write since the last successful run, record
   "nothing new" and stop. If a base table has had no write for more than 30 hours, raise a warning,
   because that is a problem upstream.
3. **Pin one version of each base table.** Every later step reads that same version, so a write
   landing mid-run cannot make two steps disagree.
4. **Look in our IP tables first.** Find every distinct address in the base tables that is not in
   `unified.ip_geo`. These are the new addresses.
5. **Find addresses whose answer may have changed.** Addresses with tune-click rows added since the
   last run, because their FraudLogix decision can change.
6. **Ask every free vendor** about those addresses, writing the answers to a staging table.
7. **Compare the answers.** For location: what the vendors agree on, how many back each answer, and
   whether each vendor matches. For risk: whether a flag is confirmed by a published list.
8. **Upsert** into `unified.ip_geo` and `unified.ip_intelligence`, following the rules in section 4.
9. **Refresh** `unified.ip_geo_analytics` and `unified.ip_intelligence_analytics` for the affected
   addresses.
10. **Rebuild both vendor overview tables**, `unified.vendor_overview_geo` and
    `unified.vendor_overview_proxy`, and republish the files the dashboard reads.
11. **Run the assertions** below.
12. **Record progress** only if every assertion passed, then start Lambda B.

### Assertions

If any of these fails, the run is marked failed, progress is not recorded, and the next run covers
the same ground again.

| Assertion | What it catches |
|---|---|
| No address appears twice for the same vendor | A lookup that matched two ranges and doubled rows |
| Every enabled vendor has rows from this run | A vendor that silently returned nothing |
| No IP table has fewer rows than before the run | An upsert that deleted instead of updating |
| Every new address found in step 4 is now in `unified.ip_geo` | An address that fell through |
| Every address updated in step 8 kept its original `created_at` | An update that replaced a row instead of changing it |
| The pipeline role still has no permission to write to any base table, checked with AWS's permission simulator | A permission change that would let the pipeline write to production |
| Every vendor overview is scored over addresses that every vendor on that board was asked about | Fill rates computed over different addresses |

### Safe to run twice

Step 4 skips what is already present, and step 8 changes only what differs. A second run the same
day leaves every table exactly as the first run left it.

---

## 7. Lambda B — `ipintel-proxycheck-daily`

**Runs:** when Lambda A succeeds, and on its own at 10:00 UTC as a fallback.
**Spends:** up to 50,000 proxycheck queries a day. The budget is set in the UI and capped on the
server.

### Bulk or one address per call?

**Bulk.** proxycheck documents a limit of 1,000 addresses per request for registered accounts. Today
I sent real addresses from our traffic in two batches, using the exact settings the job will use.

| Batch | Time | Response size | Answered |
|---:|---:|---:|---:|
| 100 addresses | 0.56 s | 133 KB | 100 of 100 |
| 400 addresses | 0.93 s | 355 KB | 400 of 400 |

Time grows much more slowly than batch size. *Projection:* a full 1,000-address batch takes about 2
seconds, and all 50 batches a few minutes, against Lambda's 15-minute limit.

### Which addresses

Addresses in our IP tables with no `proxycheck_io` row:

1. Addresses that arrived today, from Lambda A
2. Then the rest, most recently seen first

The 226,821 addresses active in the last 90 days are covered in about 5 days. All 4,956,391 take about
99 days.

### How the loop works

1. **Write the day's plan once.** The first run of the day picks the addresses and saves them as
   batch files of 1,000. Every later run that day reuses those files, so the selection cannot change
   halfway through.
2. **Skip what is done.** A batch is done only if its saved response file exists. That file is the
   single record of progress, so there is no separate tracker to fall out of step.
3. **Reserve the queries.** Before each request the job reserves 1,000 queries in a shared daily
   counter. The reservation succeeds only if it stays inside the budget. Live lookups reserve from the
   same counter, so two callers can never both take the last queries.
4. **Send, then save the answer immediately.** The raw response is stored before anything else
   happens.
5. **Watch the clock.** With less than 2 minutes of Lambda's 15 left, stop starting batches and start a
   fresh copy of the job to continue. At measured speed this should not be needed. It is there for a
   slow day.
6. **When every batch is saved,** upsert them all into `unified.ip_intelligence` in one statement,
   then refresh `unified.ip_intelligence_analytics` and `unified.vendor_overview_proxy`.

### Your five requirements

| You asked for | How it is met |
|---|---|
| No data loss | Every response is stored before it is used. The upsert reads only stored files |
| No downtime | Readers of the IP tables always see the last finished version while a write is in progress |
| Valid API calls | One request per batch of at most 1,000 addresses, with the settings proven in the benchmark and today's test |
| No key exhaustion | Queries are reserved before sending in a counter shared with live lookups, 10,000 a day are held back for live lookups, and only one copy of the job runs at a time |
| No Lambda timeouts | A measured batch takes under a second, and the job hands over to a fresh copy long before the limit |

### When something goes wrong

| Failure | What the job does | Answers lost | Queries wasted |
|---|---|---:|---:|
| proxycheck is slow or returns a server error | Retries that batch three times, waiting longer each time | 0 | 0 |
| proxycheck returns a warning, such as nearing the limit | Keeps the answer. A warning still carries the full result | 0 | 0 |
| Daily budget reached | Stops cleanly. The next day resumes from the saved files | 0 | 0 |
| Key rejected | Stops, raises an alarm, sends nothing more | 0 | 0 |
| Lambda crashes after saving a response | The next copy finds the file and skips that batch | 0 | 0 |
| Lambda crashes between the answer arriving and being saved | The next copy sends that batch again | 0 | up to 1,000 |
| Two copies start at the same time | Prevented: the job is limited to one running copy | 0 | 0 |
| Starting the next copy fails | Retried automatically, then sent to a failure queue with an alarm | 0 | 0 |

The only case that can waste queries is a crash in the moment between proxycheck answering and the
answer being saved. At most that costs one batch of 1,000 queries.

---

## 8. Live lookups follow the same rule

`GET /lookup/{ip}` already does what you described: look in our IP tables, and call proxycheck only
if the address has no answer. Two changes bring it in line with this plan:

- It reserves its query from the same shared counter as Lambda B before calling.
- It records `Hosting` as datacenter, and no longer `Business`. See section 10.

---

## 9. A complete IP source for the company

### How people use it

| Need | Use |
|---|---|
| Analysis and reporting | Athena: `unified.ip_geo`, `unified.ip_intelligence` and their analytics tables |
| An answer for one address inside an application | `GET /lookup/{ip}` |
| Comparing vendors | `unified.vendor_overview_geo` and `unified.vendor_overview_proxy`, and the dashboard |
| Running and watching the pipeline | The Lovable app |

### What it guarantees

| Guarantee | How |
|---|---|
| Every address in any base table is in the IP tables | Checked by an assertion every run |
| New addresses appear the day after they land in a base table | Lambda A runs daily and compares the whole history |
| Late-arriving session rows are never missed | The comparison does not depend on dates |
| The downloadable vendor databases stay current | Reloaded monthly. GeoLite2 is reloaded twice a week, range lists weekly |
| One row per address per vendor | Checked by an assertion every run |
| Nobody reads a half-written table | Iceberg serves the last finished version during every write |

### Base tables are set in the UI

A **base table** is any table addresses are collected from. The ad-click and session tables are the
starting list. You can add, remove or change base tables from the UI:

- **Add** by picking the database, table, address column and date column from the real catalog, so
  no name is ever typed by hand.
- **Before a table is used**, it is checked: the table and columns exist, most values in the address
  column are real IPv4 addresses, the pipeline can read it, and how much one run will read from it.
- **Remove or pause** a table without losing addresses already collected from it.
- **Every base table is read-only automatically**, because the pipeline may write only to our IP
  tables.

The three control pages, Base Tables, Daily Jobs and proxycheck Budget, are specified in
`LOVABLE_PROMPT_PIPELINE_CONTROL.md`. Anything that spends money is capped on the server as well as in
the UI, and the app never accepts or shows the API key.

---

## 10. What must change before it can run

| Change | Why it is required |
|---|---|
| **Move the four IP tables to Iceberg** | You asked for upserts with no downtime. The current format cannot update a single row, and rebuilding it takes the tables offline for about two minutes. Tested: a single-address lookup still reads 1.49 MB, and one statement updated one row and inserted another in 2.5 seconds |
| **Load GeoLite2, DB-IP and the range lists as downloadable files** | They are registered as databases but were only ever queried for 2,105 addresses. Without the files, a new address gets one location answer and there is nothing to compare |
| **Record proxycheck's `Business` type as not datacenter** | In today's test 112 of 400 addresses were `Business`. The top providers were Charter, Cox, AT&T, CenturyLink and Verizon Business, which is ordinary home and office internet. The current code marks all of them datacenter. The two addresses written so far, Google and Quad9, are genuinely infrastructure, so no wrong data exists yet |
| **Add the shared daily query counter** | proxycheck's usage counter showed 0 one minute after 500 queries were sent and 504 fourteen minutes later. A guard that trusted it could overspend in that gap |
| **Create the pipeline's own AWS role** | Section 4 |

---

## 11. What it costs

| Item | Per month | Basis |
|---|---:|---|
| proxycheck.io | $9.99 | Published price, locked once subscribed |
| Athena | under $1 | *Projection:* about 1 GB read a day at $5 per terabyte |
| Lambda | under $1 | *Projection:* two short runs a day |
| Shared counter and run log | under $1 | *Projection:* a few thousand small writes a day |
| Stored proxycheck responses | under $1 | *Projection:* 50 files a day of about 900 KB |

---

## 12. Build order

| Step | Work | Needs the paid key |
|---:|---|---|
| 1 | Create the pipeline role: write to our IP tables only, read everything else | No |
| 2 | Fix the `Business` mapping and add the shared query counter | No |
| 3 | Move the four IP tables to Iceberg | No |
| 4 | Load GeoLite2, DB-IP and the range lists | No |
| 5 | Base table list with its checks, seeded with the two production tables | No |
| 6 | Control endpoints for base tables, jobs and budget, with server-side caps | No |
| 7 | Paste the Lovable prompt. Each page fills in as its endpoint ships | No |
| 8 | Lambda A, run by hand, then scheduled | No |
| 9 | Lambda B, tested end to end with a 1,000-a-day budget on the free key | No |
| 10 | **Buy $9.99, store the new key, raise the budget to 50,000, switch Lambda B on** | **Yes** |
| 11 | Monthly database reloads, weekly table maintenance, alarms, run log | No |

Steps 1 to 9 run on the free key. Buying the plan today is safe, because nothing uses the paid key
until step 10.

---

## 13. Risks still open

| Risk | What is done about it |
|---|---|
| proxycheck's daily reset time is not documented where I could find it | Confirm it in the dashboard after buying. The 25,201 spare queries absorb a reset that does not line up with midnight UTC |
| The session pipeline runs late or rebuilds in bulk | The job pins one version per run, carries on with what arrived, and warns after 30 hours of silence |
| Live lookups and the daily jobs write to the same tables | Iceberg allows this. A clash makes one write fail, and both jobs retry that specific error |
| ipwho.is publishes no hard limit | Calls are paced, and anything throttled carries over to the next day |
| A base table added in the UI is very large | Its check shows how much one run will read before it is enabled |
