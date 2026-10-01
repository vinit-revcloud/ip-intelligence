# IP Intelligence User Manual

> Replaces ip-intelligence-*.html (no longer maintained).

**For analysts using Athena and the teammate's IP Lookup API · 16 Sep 2026**

How to find out where an IP address is and whether it is a proxy, VPN, Tor exit or bot, using Athena or the teammate's IP Lookup API. It also covers how the daily system runs and how an engineer controls it.

| Addresses | Updated | proxycheck.io |
|---|---|---|
| 4,959,406 (16 Sep 10:42 UTC) | daily from 07:30 UTC | 80,000 queries/day plan, 78,000 used for enrichment (since 17 Sep) |

## Contents

1. [Start here](#start-here)
2. [What changed on 16 Sep](#what-changed-on-16-sep)
3. [Reading an answer](#reading-an-answer)
4. [IP lookups: the teammate's IP Lookup API](#ip-lookups-the-teammates-ip-lookup-api)
5. [Using Athena](#using-athena)
6. [Many IPs at once](#many-ips-at-once)
7. [Reports](#reports)
8. [How fresh the data is](#how-fresh-the-data-is)
9. [The proxycheck.io budget](#the-proxycheckio-budget)
10. [Alert emails](#alert-emails)
11. [Controlling the pipeline (engineers)](#controlling-the-pipeline-engineers)
12. [Common tasks](#common-tasks)
13. [Troubleshooting](#troubleshooting)
14. [Glossary](#glossary)

---

## Start here

Every IP address seen in the ad-click and website-session tables has a location and a proxy verdict. There are two ways to get them.

| Tool | Best for | Notes |
|---|---|---|
| **Athena** | Reports, lists of addresses, joining to other data | Query `ipintel_curated.ip_resolved`: one row per address. Never spends proxycheck.io queries. |
| **Teammate's IP Lookup API** | One address from a script or another system | `GET /v1/ip/{ip}`. Uses its own vendor order, not our resolved answer (see below). |

**The one table most people need.** `ipintel_curated.ip_resolved` holds the answer to use for every address: location, proxy verdict, the vendors it rests on, and where the address was seen. The other tables hold each vendor's own answer and the working behind the verdicts.

## What changed on 16 Sep

- **Our API is retired.** `ipintel-findings-api` was blocked at 17:00 UTC: every call now returns HTTP 429. An AWS admin will delete it. The `/lookup`, bulk lookup, `/tables`, `/coverage`, `/accuracy/geo`, `/publish` and control endpoints are gone.
- **The Lovable app is retired.** Every page called our API, so the app no longer works. The Lovable prompt files are no longer used.
- **IP lookups:** use the teammate's IP Lookup API ([below](#ip-lookups-the-teammates-ip-lookup-api)).
- **Pipeline control** (pause, budget, run now) is done directly in AWS by an engineer ([below](#controlling-the-pipeline-engineers)).
- **The daily jobs are unchanged.** They still load new addresses, ask proxycheck.io and rebuild the reports.
- **All six `unified` tables are now kept current.** Since 16 Sep 19:51 UTC, every passed proxycheck.io run refreshes all six: `ip_geo`, `ip_intelligence`, `ip_geo_analytics`, `ip_intelligence_analytics`, `vendor_overview_geo` and `vendor_overview_proxy`. Before that, only the first two were refreshed.
- **Location rules v2** went live at 10:42 UTC: new location statuses `nearby` and `same_state`.
- **15 unused tables** were removed from `ipintel_curated`. The tables that remain are listed under [Using Athena](#using-athena).

## Reading an answer

Each answer in `ip_resolved` has a location part and a proxy part. Each part has a status that says how sure it is.

### Location status (`geo_status`, rules v2 since 16 Sep 10:42 UTC)

| Status | Meaning | How much to trust it |
|---|---|---|
| `agreed` | Two or more vendors name the same state and city | Strongest |
| `nearby` | Two or more vendors name the same state, and two of them are within 25 km | State is solid; city is the same area |
| `same_state` | Two or more vendors name the same state; the cities are more than 25 km apart | State is solid; treat city as uncertain |
| `single_source` | Only one vendor answered, almost always IP2Location | State is usually right; treat city as approximate |
| `vendors_disagree` | No two vendors name the same state | Weakest; the vendor most often right for this kind of conflict is shown |
| `no_answer` | No vendor has a location | — |

City names are compared in full, without accents or punctuation. "Saint", "Mount" and "Fort" count the same as "St", "Mt" and "Ft", and a trailing "City" or "Township" is ignored. So "St. Louis" equals "Saint Louis", but "New York" no longer matches "New Hyde Park".

When vendors differ, the answer comes from the vendor most often right for that kind of conflict against customer addresses:

- **State:** ipinfo.io, then ipwho.is, then IP2Location, then proxycheck.io.
- **City within the agreed state:** ipinfo.io, then IP2Location, then ipwho.is, then proxycheck.io.

Last 30 days on 16 Sep 10:42 UTC: agreed 19,596 (45.8%), nearby 6,541 (15.3%), same state 9,181 (21.5%), states differ 7,448 (17.4%), one source 3.

> **An IP location is not a home address.** It places the network hub. State matches a customer's own postal address about 6 times in 10, and city about 1 time in 7, for every vendor (see [Reports](#reports)). Use it for regional analysis, never as a person's address. Do not use IP ZIP codes for anything finer than a region.

### Proxy status (`proxy_status`)

| Status | Meaning | `flagged` |
|---|---|---|
| `confirmed` | proxycheck.io answered and at least one other vendor agrees | true or false |
| `proxycheck_only` | proxycheck.io is the only vendor that answered | true or false |
| `proxycheck_overrides` | proxycheck.io answered the opposite of every other vendor, and its answer is used | true or false |
| `clean_by_vendors` | No proxycheck.io answer; every vendor that answered says clean | false |
| `flagged_unconfirmed` | A vendor flags it and nothing confirms the flag | empty |
| `vendors_disagree` | Vendors disagree and proxycheck.io has not answered yet | empty |
| `no_answer` | No vendor gave a proxy answer | empty |

**Empty means "no conclusion", never "clean".** Every yes/no field has three states: true, false, and empty (no answer). Treating empty as false is the most common mistake. In SQL, `WHERE NOT flagged` silently drops the empty rows, so write `WHERE flagged = false` or `WHERE flagged IS NULL` on purpose.

### The flags

`is_proxy`, `is_vpn`, `is_tor`, `is_datacenter`, `is_bot`, `is_compromised`, `is_scraper`, `is_anonymous`. `flagged` is true when any of the first seven is true. Things to know:

- proxycheck.io labels most datacenter traffic as VPN. For "not an ordinary home connection" use `is_vpn OR is_proxy OR is_datacenter`.
- Only FraudLogix answers `is_bot`. No bot flag is confirmed by a second vendor.
- About two in three flagged addresses belong to Akamai, Google and Cloudflare. These carry Apple iCloud Private Relay, Google One VPN and Cloudflare WARP traffic from ordinary people. Treat a VPN flag as "not a direct home connection", not as fraud, and judge it together with behaviour.
- The 16 Sep lead-IP analysis found the same thing: 137 of proxycheck.io's 139 false positives on paying customers were VPN flags on Akamai, Fastly and Cloudflare (see `LEAD_IP_VENDOR_ANALYSIS.md`).

## IP lookups: the teammate's IP Lookup API

Our own API is retired. For one address at a time, use the teammate's IP Lookup API. It is not our code; ask its owner for the token and keep the token out of shared code and documents.

```
Base URL:  https://9w07dr3qq2.execute-api.us-west-2.amazonaws.com
```

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Is the API up |
| `GET /v1/ip/{ip}` | `Authorization: Bearer <API_TOKEN>` | Location and risk for one IPv4 address |

```bash
curl "https://9w07dr3qq2.execute-api.us-west-2.amazonaws.com/health"

curl -H "Authorization: Bearer $API_TOKEN" \
  "https://9w07dr3qq2.execute-api.us-west-2.amazonaws.com/v1/ip/8.8.8.8"
```

### The response

```json
{
  "ip-address": "8.8.8.8",
  "ip-geolocation": {
    "source": "...", "lookup": "...",
    "state": "...", "city": "...", "zip": "...",
    "lat": 0.0, "lng": 0.0, "timezone": "..."
  },
  "ip-risk": {
    "source": "...", "lookup": "...",
    "is_proxy": false, "is_vpn": false, "is_tor": false, "is_datacenter": false,
    "is_compromised": false, "is_scraper": false, "is_anonymous": false,
    "isp": "...", "asn": "...", "risk": 0, "confidence": "..."
  }
}
```

`source` names where the part came from, and `lookup` says how it was found. A `null` value means the source gave no value for that field. As in our tables, `null` is "no answer", not "false".

### Errors

| Code | Body | Meaning |
|---|---|---|
| 401 | `unauthorized` | Missing or wrong token |
| 400 | `invalid_ipv4` | Not a valid IPv4 address |
| 404 | `not_found` | No answer for this address |
| 502 | `lookup_failed` | A lookup behind the API failed; retry |

### How it works

- **Location:** from `unified.ip_geo`, preferring the `ip2location_db11` row. If there is none, it falls back to the IP2Location range database.
- **Risk:** from `unified.ip_intelligence`, preferring `fraudlogix_tune`, then `authoritative_lists`, then `ip2proxy_px12`. The first decisive row wins. If none is decisive, it calls proxycheck.io live. That live answer is **not** saved to our tables.
- `unified.ip_geo` and `unified.ip_intelligence` are refreshed by our daily jobs, so the API sees our vendor rows with up to a day's lag.

> **It does not use our resolved answer.** The API does not read `ipintel_curated.ip_resolved`. It ignores the resolved location and proxy status, the v2 location statuses, and the vendor priorities above. `authoritative_lists` rows were removed on 14 Sep, and IP2Proxy answers only for listed proxies, so the proxycheck.io rows in the table are seldom reached. For the answer this manual describes, use Athena.

## Using Athena

Everything is in the `ipintel_curated` database. Queries that filter on `ip_address` read only a few megabytes.

```sql
-- The answer for a list of addresses
SELECT ip_address, state, city, zip_code, geo_status, flagged, is_vpn, is_proxy, is_datacenter,
       proxy_status, isp, proxycheck_risk_score, last_seen
FROM ipintel_curated.ip_resolved
WHERE ip_address IN ('8.8.8.8', '152.232.101.74');

-- Join to your own data: sessions with the IP verdict
SELECT s.session_date, s.session_ip, r.state, r.geo_status, r.flagged, r.proxy_status
FROM unified.unified_session_summary s
LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = s.session_ip
WHERE s.session_date = date '2026-09-10';

-- Addresses with no proxy conclusion yet
SELECT proxy_status, count(*) FROM ipintel_curated.ip_resolved
WHERE proxy_status IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed') GROUP BY 1;

-- Every vendor's own answer for one address
SELECT * FROM ipintel_curated.ip_geo WHERE ip_address = '8.8.8.8';
SELECT * FROM ipintel_curated.ip_intelligence WHERE ip_address = '8.8.8.8';

-- Where an address was seen
SELECT * FROM ipintel_curated.ip_occurrences WHERE ip_address = '8.8.8.8';
```

### The tables in `ipintel_curated`

The database holds exactly these 12 tables.

| Table | One row per | Use it for |
|---|---|---|
| `ip_resolved` | address | **The answer to use** |
| `ip_geo` | address + vendor | Each vendor's location |
| `ip_intelligence` | address + vendor | Each vendor's proxy flags, ISP, ASN |
| `ip_geo_analytics` | address + vendor | Consensus and agreement, where 2+ vendors answered |
| `ip_intelligence_analytics` | address + vendor | Has-answer, flagged, masked device, risk score, verdict class |
| `ip_occurrences` | address + base table | Where and when an address was seen |
| `proxycheck_queue` | address | Addresses from new base-table rows that needed proxycheck.io, and whether they were answered |
| `vendor_overview_geo` | vendor | Location vendor scorecard (agreement) |
| `vendor_overview_proxy` | vendor | Proxy vendor scorecard |
| `db11_bucketed`, `px12_bucketed` | IP range | The downloaded IP2Location and IP2Proxy databases |
| `qualified_lead_ips` | customer address | Truth for location accuracy |

The 15 older tables (`ip_pool`, `pc_live`, `ip_dim` and similar) were dropped on 16 Sep. Their definitions are saved in `archive/curated-legacy-tables-2026-09-16/`.

Five unused benchmark tables from 3–8 Sep (`ipintel_analytics.geo_accuracy`, `geo_score`, `pairwise_agreement`, `risk_score` and `ipintel_reference.zip_centroid`) are backed up and listed for an AWS admin to drop. The `ip-database` database is older than this project and is never changed.

More ready-made queries and column meanings are in `ATHENA_REVIEW_QUERIES_LIVE.md` in the project folder. Every timestamp is UTC as `YYYY-MM-DDTHH:MM:SSZ`.

> **Please use your own workgroup for reading.** The `ipintel_etl` workgroup belongs to the daily jobs. Reading the tables from your usual workgroup is fine; writing to `ipintel_curated` is reserved for the pipeline.

### The `unified` copies

| Table | State |
|---|---|
| `unified.ip_geo`, `unified.ip_intelligence` | Copies of the `ipintel_curated` tables, refreshed after each passed proxycheck.io run. The teammate's API reads them. They can lag by up to a day. |
| `unified.ip_geo_analytics`, `unified.ip_intelligence_analytics` | Copies of the `ipintel_curated` tables, refreshed the same way (since 16 Sep 19:51 UTC) |
| `unified.vendor_overview_geo`, `unified.vendor_overview_proxy` | Copies of the `ipintel_curated` scorecards, refreshed the same way (since 16 Sep 19:51 UTC). In `vendor_overview_proxy`, `bot_metric_status` is cut to 25 characters, because the unified table's definition allows only 25 |

For your own queries, use `ipintel_curated`.

## Many IPs at once

There is no bulk lookup endpoint any more. For a list of addresses:

1. **Load the list into Athena** (any table or `VALUES` list you can read) and join it to `ipintel_curated.ip_resolved` on `ip_address`. This is free of proxycheck.io queries and gives our resolved answer.
2. **Addresses not in our tables** return no row. They are either new since the last 07:30 load, private or reserved, or never seen in the base tables. Look them up one at a time through the teammate's API if you need them now.

```sql
WITH list(ip) AS (VALUES '8.8.8.8', '152.232.101.74', '10.0.0.1')
SELECT l.ip, r.state, r.city, r.zip_code, r.geo_status,
       r.flagged, r.is_vpn, r.is_proxy, r.proxy_status, r.isp,
       r.ip_address IS NULL AS not_in_tables
FROM list l
LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = l.ip;
```

Looping thousands of addresses through the teammate's API is not recommended: each address it cannot decide may cost a live proxycheck.io query, and those answers are not saved.

## Reports

Two report files are rebuilt at the end of both daily jobs, in
`s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/ipintel_curated/`:

- `geo_accuracy.json`: Location Accuracy.
- `enrichment_coverage.json`: Enrichment Coverage.

There is no app page or API route for them any more. Read the files from S3 (engineers, with the `ipintel-builder` profile), or recompute the numbers in Athena.

### Location Accuracy

The truth is the postal address of 2,105 qualified customers (full state name and 5-digit ZIP), in `qualified_lead_ips`. For each vendor, and for our resolved answer, the report counts how often the IP location matches:

- **State:** the same state name, ignoring case.
- **City:** the same city name, letters only, ignoring case.
- **ZIP:** the same first five digits.
- **State + city:** both match.

Two pools are shown. **Every address each vendor answered** gives each vendor as many tests as it can take. **Same addresses** uses only the 1,049 addresses every location vendor answered, so the vendors are compared on equal terms. The by-state table marks states with fewer than 20 tested addresses as `small_sample`.

| Vendor (16 Sep) | Tested (all) | State / City / ZIP (all answered) | State / City / ZIP (same 1,049) |
|---|---|---|---|
| IP2Location DB11 | 2,105 | 59.0% / 14.5% / 3.4% | 47.0% / 9.5% / 2.2% |
| proxycheck.io | 2,105 | 59.7% / 11.9% / 5.4% | 51.6% / 7.2% / 2.9% |
| ipinfo.io | 1,050 | 54.3% / 11.1% / 4.0% | 54.2% / 11.1% / 4.0% |
| ipwho.is | 1,050 | 53.7% / 10.5% / 1.8% | 53.7% / 10.5% / 1.8% |
| **Our answer (resolved)** | 2,105 | 62.5% / 15.3% / 4.1% | 54.1% / 11.0% / 3.6% |

Replaying the 2,105 customers through the old and the v2 location rules gave the same state result (1,316 right, 62.5%), and state + city 282 before, 283 after.

> **No vendor reaches 100%, and that is expected.** A postal address is where the customer lives, not always where the connection is (mobile carriers, work networks). Use the numbers to compare vendors with each other, not as the chance a single answer is right.

**Accuracy and agreement are different.** "Agreement" on the vendor scorecards means how often a vendor matches the other vendors. "Accuracy" means how often a vendor matches customers' postal addresses, and is used only for the Location Accuracy report.

### Enrichment Coverage

Totals for addresses **last seen in the last 30 days** and for **all addresses**: how many proxycheck.io answered, how many have a proxy conclusion or none, and how many have an agreed, nearby or same-state location, a single-vendor location, or states that differ or no location. The file also has rows added per day (by `created_at`), new addresses per day (by first seen), and the 30-day window split by last-seen day.

| Measure | 15 Sep 19:00 UTC | 16 Sep 10:42 UTC |
|---|---|---|
| Addresses in the 30-day window | 39,508 | 42,769 |
| Answered by proxycheck.io | 18,034 (45.6%) | 42,768 (100%) |
| Proxy decided | 30,208 (76.5%) | 42,768 (100%) |
| Proxy undecided | 9,300 | 1 |
| State agreed by 2+ vendors | — | 35,318 (82.6%) |
| State and city agreed | 8,443 (21.4%) | 19,596 (45.8%) |

All addresses on 16 Sep: 127,216 answered by proxycheck.io (2.6%) and 814,185 still undecided (848,403 on 15 Sep).

A quick recount of the 30-day window in Athena:

```sql
WITH occ AS (SELECT ip_address, max(last_seen) AS ls FROM ipintel_curated.ip_occurrences GROUP BY 1),
pc AS (SELECT DISTINCT ip_address FROM ipintel_curated.ip_intelligence WHERE vendor = 'proxycheck_io')
SELECT count(*) AS addresses,
       count(pc.ip_address) AS proxycheck_answered,
       count_if(r.proxy_status NOT IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed')) AS proxy_decided,
       count_if(r.geo_status = 'agreed') AS geo_agreed,
       count_if(r.geo_status = 'nearby') AS geo_nearby,
       count_if(r.geo_status = 'same_state') AS geo_same_state,
       count_if(r.geo_status = 'vendors_disagree') AS geo_states_differ
FROM occ o
JOIN ipintel_curated.ip_resolved r ON r.ip_address = o.ip_address
LEFT JOIN pc ON pc.ip_address = o.ip_address
WHERE o.ls >= date_add('day', -30, current_date);
```

## How fresh the data is

The tables update once a day in the early morning (UTC). An address that first appears after 07:30 is in the tables the next morning.

| When (UTC) | What happens |
|---|---|
| every 6 h, :06 | New ad clicks land in `raw.raw_tune_clicks` (their own job) |
| ~06:21 | `unified.unified_session_summary` is rewritten (their own job) |
| 07:30 | **Daily load:** new addresses get every free vendor's answer; all tables, scorecards and `ip_resolved` refresh |
| straight after | **proxycheck.io:** addresses from new rows that need it go first, then the daily backfill; together up to 78,000 |
| after proxycheck.io | **Unified tables refreshed:** if every check passed, `unified.ip_geo` and `unified.ip_intelligence` are replaced with fresh copies |
| end of each job | **Reports rebuilt:** Location Accuracy and Enrichment Coverage |
| 10:00 | proxycheck.io run starts here if the daily load did not start it |
| 22:00 | **Top-up:** spends what is left of today's 80,000 except 2,000 |
| Sun 03:00 | Weekly table maintenance |

## The proxycheck.io budget

The plan allows 80,000 queries a day. A shared counter reserves every query before it is sent, so the pipeline cannot go over its share.

| Use | Queries | Notes |
|---|---|---|
| Enrichment: addresses from new base-table rows, then the daily backfill | up to 78,000 | Queued addresses count inside the 78,000 |
| 22:00 top-up | whatever is left, up to 78,000 in total | Also covers queries charged twice |
| Kept free | 2,000 | Safety margin. The 30,000 lookup reserve was for our retired API; on 17 Sep it moved to enrichment |

The teammate's API makes its own live proxycheck.io calls. They are **not** counted on our counter. proxycheck.io's own count for 16 Sep (50,354) was below our reservations (50,859), so it does not use our key.

### What the backfill sends first (since 17 Sep)

1. Addresses queued from new base-table rows.
2. Addresses first seen today.
3. **Experiment IPs:** every address with a session that has an `experiment_id` in `unified.unified_session_summary` (37,995 addresses, 38 experiments).
4. Every address seen in the base tables in the last 30 days.
5. Every address seen in the last 90 days.
6. Addresses with no conclusion (`no_answer`, `vendors_disagree`, `flagged_unconfirmed`), then by kind of no-conclusion and most recently seen.

Only addresses proxycheck.io has not answered yet are picked.

The 16 Sep run sent 49,512 queries: the 3,410 queued addresses first, then 12,769 window addresses other vendors called clean, then 33,325 without an answer. All 10 checks passed. Since 17 Sep, at 78,000 a day, the undecided backlog takes about 10 more days *(projection)*.

An address that is both proxy and VPN is charged twice by proxycheck.io; about 1% extra is reserved for that.

## Alert emails

Alerts come from the `ipintel-alerts` topic. Most say exactly what failed. The run log is in DynamoDB (`ipintel-pipeline-state`, items `run#<job>`); an engineer can read it.

| Email about | Meaning | What to do |
|---|---|---|
| proxycheck use passed 90% | May fire on busy days | Nothing |
| A job failed / an assertion failed | A daily run stopped; nothing half-written is kept, and the next run picks up the same work | Engineer reads the run's message, fixes the cause, runs the job by hand |
| No run for 26 hours | The daily load has not finished | Check the schedule is on and the pipeline is not paused |
| Hand-over in the dead-letter queue | A long proxycheck run could not start its next copy | Engineer runs the proxycheck job by hand; saved answers are not lost |
| proxycheck rejected the key | The key in Secrets Manager (`ipintel/proxycheck-paid`) is wrong or the plan lapsed | Renew the plan or update the secret, then run the job by hand |
| Paused: safety check failed | The pipeline saw a way to write to production and stopped itself | Contact the project owner; do not resume until the check passes |
| A base table has not been written for 30 hours | Its own production job has not delivered new rows | Tell the owner of that table |
| Weekly maintenance failed | Table compaction did not finish | Nothing urgent; it retries next week |

## Controlling the pipeline (engineers)

With the app and our API gone, control is done directly in AWS. Always use the `ipintel-builder` profile, never the default profile (it is a different IAM user). Region `us-west-2`.

Settings live in the DynamoDB table `ipintel-pipeline-state` (keys `pk`, `sk`).

| What | Item | Fields |
|---|---|---|
| Emergency stop | `pk=safety`, `sk=state` | `paused` (true/false), `paused_reason` |
| Enrichment budget | `pk=job`, `sk=proxycheck-daily` | `daily_budget` (78000), `live_reserve` (2000), `topup_keep` (2000) |
| Job on/off | `pk=job`, `sk=free-daily` or `proxycheck-daily` | `enabled` |

For every change, write an `audit` item (`sk` = `<time>#update_job`, with the old value, the new value and the reason), as was done on 17 Sep, and note it in `AWS_BUILD_LOG.md`.

### Pause everything

```bash
aws dynamodb update-item --profile ipintel-builder --region us-west-2 \
  --table-name ipintel-pipeline-state \
  --key '{"pk":{"S":"safety"},"sk":{"S":"state"}}' \
  --update-expression "SET paused = :p, paused_reason = :r" \
  --expression-attribute-values '{":p":{"BOOL":true},":r":{"S":"why you paused"}}'
```

Both jobs and every proxycheck.io call stop. Nothing is deleted. To resume, set `paused` to false the same way. Do not resume while a safety check in the same item is failing.

### Change the enrichment budget

```bash
aws dynamodb update-item --profile ipintel-builder --region us-west-2 \
  --table-name ipintel-pipeline-state \
  --key '{"pk":{"S":"job"},"sk":{"S":"proxycheck-daily"}}' \
  --update-expression "SET daily_budget = :b" \
  --expression-attribute-values '{":b":{"N":"78000"}}'
```

The job never spends more than the 80,000 limit minus `live_reserve`. With `live_reserve` 2000, the cap is 78,000. To go back to the old split, set `daily_budget` and `budget_cap` to 50000, and `live_reserve` and `topup_keep` to 30000.

### Run a job by hand

```bash
aws lambda invoke --profile ipintel-builder --region us-west-2 \
  --function-name ipintel-free-daily --invocation-type Event \
  --cli-binary-format raw-in-base64-out --payload '{"trigger":"manual"}' out.json
```

Use `ipintel-proxycheck-daily` for the proxycheck job. A manual run ignores the on/off switch but not the pause. When the daily load finishes, it starts the proxycheck job itself.

## Common tasks

### Look up one address

Call `GET /v1/ip/{ip}` on the teammate's API, or query `ipintel_curated.ip_resolved` in Athena for our resolved answer.

### Look up a list and download it

Join the list to `ip_resolved` in Athena ([Many IPs at once](#many-ips-at-once)) and download the result as CSV from the Athena console.

### Stop everything now

Ask an engineer to [pause the pipeline](#pause-everything) with a reason.

### Get today's new addresses in now instead of tomorrow

Ask an engineer to [run `ipintel-free-daily` by hand](#run-a-job-by-hand). It starts the proxycheck job when it finishes.

### Change how much the backfill spends

Ask an engineer to [change `daily_budget`](#change-the-enrichment-budget) (at most 78,000 while `live_reserve` is 2,000).

### Check whether the last 30 days are enriched

Run the coverage query under [Enrichment Coverage](#enrichment-coverage), or read `enrichment_coverage.json`. Look at `proxycheck_answered` and `proxy_decided` against `addresses`.

### Compare vendor accuracy by state

Read the by-state section of `geo_accuracy.json`. Use the **same addresses** pool for a fair comparison, and ignore states marked `small_sample` (fewer than 20 tested).

### Check the unified tables were refreshed

Ask an engineer to read the DynamoDB item `pk=publish`, `sk=unified`. `last_published_at` should be today, after the proxycheck run. The newest `run#publish-unified` item lists its checks and each table's row count.

### Add a base table

This used to be a page in the app. It now needs an engineer: see "Add a base table" in `docs/SYSTEM_GUIDE.md`.

## Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| An address I know is new is not in Athena | It arrived after today's 07:30 load | Wait for tomorrow, use the teammate's API, or ask an engineer to run the daily load by hand |
| Our old API returns 429 | It was retired on 16 Sep and blocks every call | Use the teammate's API or Athena |
| The Lovable app shows errors | It depended on our retired API | Use Athena or the teammate's API |
| Teammate API returns 401 | Missing or wrong token | Check the `Authorization: Bearer` header; ask its owner for the token |
| Teammate API answer differs from `ip_resolved` | It uses its own vendor order, not our resolved answer | Use `ip_resolved` for our answer |
| `flagged` is empty | No conclusion yet | It is in the backfill queue; expect an answer within about 17 days *(projection)* |
| `geo_status` is `nearby` or `same_state` | Vendors agree on the state but name different cities | Trust the state; treat the city as approximate |
| A private address has no answer | No vendor has records for private or reserved ranges | Expected |
| No new session addresses for days | `unified_session_summary` is not being rewritten by its own job. It stalled 11–15 Sep; the 16 Sep load picked up 2,490 addresses first seen 11–15 Sep | Check new addresses per day in `enrichment_coverage.json`; if it stalls again, tell that table's owner |
| A report file looks stale | The last job run failed its report check | Ask an engineer to check the run and run the job by hand |
| `unified.ip_intelligence` is behind `ipintel_curated` | It is refreshed only after a proxycheck run that passes every check | Use `ipintel_curated` |
| `unified.vendor_overview_proxy.bot_metric_status` looks cut off | The unified definition allows 25 characters | Read it from `ipintel_curated.vendor_overview_proxy` |
| `ipintel_analytics.*` or `ipintel_reference.zip_centroid` is missing | Unused benchmark tables, dropped by an AWS admin (`ADMIN_DELETION_STEPS.md`) | Nothing uses them; definitions are archived |

## Glossary

- **base table:** a production table IP addresses are collected from: `raw.raw_tune_clicks` (ad clicks) and `unified.unified_session_summary` (website sessions). Only ever read.
- **vendor:** a source that answers questions about an address: IP2Location DB11, IP2Proxy PX12, FraudLogix, ipinfo.io, ipwho.is, proxycheck.io.
- **resolved answer:** the one answer to use, worked out from every vendor's answer by fixed rules. In `ip_resolved`.
- **no conclusion:** no vendor answered, vendors disagree, or a flag has nothing confirming it.
- **nearby / same_state:** vendors agree on the state; their cities are within 25 km (nearby) or further apart (same_state).
- **backfill:** the daily job that asks proxycheck.io about addresses that have no proxycheck.io answer yet: queued, today's and the last 30 days' addresses first, then no-conclusion addresses.
- **top-up:** the 22:00 UTC run that spends what is left of the day's 80,000, keeping 2,000.
- **enrichment:** spending proxycheck.io queries on addresses from the base tables (queue and backfill).
- **enrichment coverage:** how many addresses have a proxycheck.io answer, a proxy conclusion and an agreed location.
- **agreement:** how often a vendor matches the other vendors. Used on the vendor scorecards.
- **accuracy:** how often a vendor's location matches customers' postal addresses. Used only for the Location Accuracy report.
- **publish:** refreshing the six project tables in `unified` with checked copies of the `ipintel_curated` tables, after each proxycheck run that passes.
- **queue:** `proxycheck_queue`: addresses from new base-table rows that need proxycheck.io, sent before the backfill.
- **teammate's API:** the IP Lookup API at `9w07dr3qq2`, owned by another team. It reads `unified.ip_geo` and `unified.ip_intelligence`.
- **privacy relay:** a service (Apple iCloud Private Relay, Cloudflare WARP, Google One VPN) that hides a user's address behind a shared one. Shows as VPN.
- **residential proxy:** a home connection used to route other people's traffic, often a compromised device. Shows as proxy on a home ISP.
- **UTC:** Coordinated Universal Time. 07:30 UTC is 00:30 Pacific daylight time and 13:00 India time.

---

For how the system is built, every decision and its evidence, see `docs/SYSTEM_GUIDE.md`. Requirement-by-requirement proof: `IP_PROJECT_VERIFICATION.md`.

## The app (since 17 Sep)

The Lovable app has a live **IP Lookup** page (teammate API) and five report pages: Bot / Not bot, Lead-IP Vendor Evaluation, Location Accuracy, Enrichment Coverage, Vendor Scorecards. Every report page shows "Snapshot as of …".

**Refreshing the report data (until the admin key exists):**
1. On the computer with AWS access, in `build/pipeline`, run `python analysis/export_app_data.py`.
2. In the app, open **Data Upload** and pick all 9 files from `app-data/`. Each must show **Uploaded**.

After every passed daily run, the pipeline already writes the same 9 files to `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/app/`. Once an AWS admin creates the read-only key (see `docs/SYSTEM_GUIDE.md` → The app and its data), the app reads them there and step 2 is no longer needed.

Presentation summary: `IP_INTELLIGENCE_SYSTEM_OVERVIEW.md`.

## Which vendor answers count (since 17 Sep)

An address is "answered" when **FraudLogix** decided on it (from our ad clicks) or **proxycheck.io** answered it.
IP2Proxy PX12 only lists known proxies: if an address is missing from its list, that is not an answer, so it does
not count. The daily backfill sends addresses with no acceptable answer first, newest first.

Today every public address seen in the last 90 days (194,514 of them) has an acceptable answer. The remaining
457,438 addresses without one were all last seen more than 90 days ago, and take about 6 days at 78,000 a day
*(projection)*.

## Is there data for every IP?

An IP counts as **complete** when we have a usable risk answer (FraudLogix or proxycheck.io, not IP2Proxy) and a usable location (state or city).

- Today: **90.75%** of 4,959,913 addresses are complete, and **194,500 of the 194,514** seen in the last 90 days.
- Nothing is missing outright: every address has rows in both tables. The rest are waiting for a proxycheck.io answer, about 6 days' work.
- Every daily run checks this and stops the refresh if a recent address is incomplete.
- Details and how to check: `DATA_COMPLETENESS.md`, or the Enrichment Coverage page in the app.

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
