# IP Project — Verification Against Your Requirements

Every row below is checked against the running system, not the plan. "Proof" is a query, a run log or a
test that was actually executed; the SQL files are under `build/pipeline/sql/checks/`.

Last verified: 15 September 2026.

---

## 1. Production safety

| Your requirement | What is in place | Proof |
|---|---|---|
| Do not touch `raw.raw_tune_clicks` or `unified.unified_session_summary` | The pipeline only reads them. Its role is denied every write to them by AWS, not by code | IAM simulator before every run: "Pipeline cannot write to any production table" PASS on every run. Table update times only move with their own schedules (tune every 6 h at :06; session summary daily ~06:21) |
| Nothing in production modified, deleted or added | All writes go to `ipintel_curated` and `s3://…/ip-intelligence/` only. The frozen `unified.ip_*` tables were never written after 11 Sep | CloudTrail review after every run: "Nothing outside the project was touched in the last 24 hours" PASS; `unified.*` update times still 11 Sep |
| No writes to the `primary` workgroup | Jobs use `ipintel_etl`, the API uses `ipintel`; both roles are denied every other workgroup | Permissions boundary `ipintel-boundary`; simulator proofs 61/61 (builder) and 64/64 (pipeline) |
| Most safety options | Permissions boundary on every project role; emergency stop (pauses jobs and live proxycheck calls); automatic pause when a safety check fails; one copy of each job at a time; dead-letter queue; 6 alarms; 10 GB scan cap | `/safety`, `/safety/pause`, `/safety/resume` tested (resume refused while a check fails) |

## 2. The tables — a complete IP source

All in `ipintel_curated`, Iceberg, partitioned by `bucket(ip_address, 64)`, one row per address and vendor.

| Table | Rows (15 Sep) | What it is |
|---|---:|---|
| `ip_geo` | 4.96M addresses | Every location vendor's own answer |
| `ip_intelligence` | 9.49M | Every proxy/risk vendor's own answer |
| `ip_geo_analytics` | per compared address | Consensus and agreement per vendor where at least two vendors answered |
| `ip_intelligence_analytics` | 9.49M | Flagged, verdict and risk score per vendor answer |
| `vendor_overview_geo` / `_proxy` | 4 / recalculating | Scorecards of the vendors the system runs |
| `ip_occurrences` | 6.54M | Where each address was seen: base table, first seen, last seen, days, rows |
| `ip_resolved` | 4.96M | **One row per address: the answer to use**, and which vendors it rests on |

| Check | Result |
|---|---|
| Every address in the two source tables is present | 4,956,801 source addresses; 0 missing IP2Location, 0 missing IP2Proxy, 0 tune addresses missing FraudLogix, 0 missing occurrences |
| No address twice for the same vendor | 0 duplicates in ip_geo, ip_intelligence, both analytics tables, ip_occurrences, ip_resolved |
| Every intelligence row has its analytics row | 9,492,663 = 9,492,663, 0 without |
| The table and the API give the same answer | 47 addresses across every status compared field by field: 47 identical (`compare_resolved.py`) |
| Only vendors the system runs | MaxMind GeoLite2, DB-IP, GeoJS and the published ranges ran only in the 8–10 Sep benchmark. Removed 14 Sep with your approval; copy in `ip-intelligence/archive/benchmark-vendors-2026-09-14/`; switched off in the registry |

### Should vendor rows be modified to make them correct?

No. Each vendor's row stays exactly as that vendor answered. The correct answer is **resolved** from
them, the same way in the table (`ip_resolved`) and in the API (`/lookup/{ip}`):

- **Location:** the place most vendors agree on (state and city) wins; the best-scoring vendor in that
  group supplies the fields. Otherwise the best-scoring vendor that answered.
- **Proxy:** proxycheck.io decides once it has answered (`confirmed` when another vendor agrees,
  `proxycheck_overrides` when all disagree). Without it: `clean_by_vendors` when every answering vendor
  says clean; otherwise no conclusion (`vendors_disagree`, `flagged_unconfirmed`, `no_answer`).

## 3. Job A — daily, free sources (`ipintel-free-daily`, 07:30 UTC)

| Your requirement | How it works | Proof |
|---|---|---|
| Runs daily | EventBridge schedule `ipintel-free-daily`, on/off from the Daily Jobs page | **First scheduled run 15 Sep 07:30:23: 108 new addresses, 540 rows inserted, 5 added, 12 updated, 11 of 11 checks PASS** |
| Picks up new rows in session summary and tune clicks | Reads each base table at one pinned version; skips when neither changed; a full comparison against `ip_geo` catches late or rewritten data | Run 14 Sep 14:58: 405 new addresses; repeat run skipped "No base table has changed" |
| Passes new IPs to each vendor | IP2Location DB11, IP2Proxy PX12, FraudLogix (new addresses plus clicks in the last 3 days), ipinfo.io and ipwho.is (up to 500 a day each) | 405 of 405 asked of each web vendor |
| Unique IPs; existing ones appended, new ones inserted | MERGE on (address, vendor): `inserted` new address, `added` new vendor answer, `updated` changed answer; created_at kept | Assertions every run: no duplicates, no table shrank, created_at kept |
| Compare and update vendor overviews | Analytics and both scorecards recalculated every run over addresses asked of every running vendor (at least 1,000) | Location scorecard on 1,564 addresses and proxy scorecard on 49,614 addresses, 15 Sep |
| Updates the tables everyone uses | All seven tables, plus the scorecard exports the app reads | Run logs `rows_after`, `resolved_changed` |
| Base tables controllable from the UI | Add, remove, pause, change and validate from the Base Tables page | `/input-tables` endpoints tested, including refusals |

## 4. Job B — daily proxycheck.io backfill (`ipintel-proxycheck-daily`)

| Your requirement | How it works | Proof |
|---|---|---|
| 50,000 addresses a day without a proxycheck decision | Budget 50,000 on the paid key (80,000/day); 10,000 held for live lookups | `/quota`: Subscription, 80,000, budget 50,000 |
| No-conclusion rows first | Order: first seen today; then no conclusion (disagree, flagged-unconfirmed, no answer), seen in the last 90 days first; then clean. Private and reserved addresses are never sent | **First real run 15 Sep 07:36:** 49,504 addresses (48,555 flagged-unconfirmed, 860 disputed, 89 new today) |
| Bulk calls | 1,000 addresses per request | 50 of 50 batches of 1,000 in one Lambda run, 15 Sep |
| No data loss | Every response saved to S3 before use; a batch is done only when its file exists; answers merged only from saved files | Repeat run the same day re-sent nothing |
| No key exhaustion | Atomic reservation in a shared DynamoDB counter before every request (batches and live lookups) | 15 Sep: our counter reserved 50,017; proxycheck's own counter 49,550 = queries the job recorded. Never above budget |
| No Lambda timeout | Hands over to a fresh copy with 3 minutes left, and before the final merge when under 10 minutes remain; at most 30 hand-overs a day | Hand-over logic in `job_proxycheck.py`; DLQ alarm |
| Upsert into the tables | Same MERGE, analytics, scorecards, resolved refresh and assertions as Job A | 15 Sep: 98,807 rows added, `ip_resolved` updated for 49,504 addresses, 7 of 7 checks PASS |

## 5. Live lookup — `GET /lookup/{ip}`

| Your requirement | How it works | Proof |
|---|---|---|
| Where the IP occurs | `occurrences` from `ip_occurrences` | 152.232.101.74 → raw.raw_tune_clicks, 7 Jul |
| Geo and proxy from the tables | Every vendor's rows plus the resolved answer | 74.47.226.105 answered from tables, no call |
| Not there, or no conclusion → proxycheck.io with geo | Called only when there is no location answer, or no proxycheck answer and no conclusion; never twice for the same address | 185.220.101.1 (unseen): Tor, Berlin, risk 100. 152.232.101.74 (flagged-unconfirmed): VPN confirmed; repeat lookup served from the saved answer |
| Ingested into the tables | Answer saved to S3; the next proxycheck job merges it into ip_geo, ip_intelligence, analytics and ip_resolved | Run 14 Sep 21:11: both live answers applied, `resolved_changed` 2 |

## 5b. One rule for proxycheck.io — API calls and base-table inserts

The same rule decides in both places: `lookup.needs_proxycheck` in the API and `pcqueue.reason_sql` in the
pipeline.

| Situation | proxycheck.io asked? | Reason code |
|---|---|---|
| Private or reserved address (10.x, 127.x, 192.168.x, 224+ …) | Never | — |
| proxycheck.io has already answered the address | No (API: only with `?refresh=true`) | — |
| Address not in `ip_geo` / `ip_intelligence` | **Yes** | `new_address` |
| In the tables, but no vendor gave a location | **Yes** | `no_location` |
| No vendor gave a proxy answer | **Yes** | `no_answer` |
| Proxy vendors disagree | **Yes** | `vendors_disagree` |
| Flagged, nothing confirms it | **Yes** | `flagged_unconfirmed` |
| Location vendors disagree | **Yes** | `location_disagree` |
| In the tables with a location and a clean or confirmed proxy answer | No | — |

**Direct API call** (`GET /lookup/{ip}`): the rule runs on the spot; the answer is saved and folded into
the tables by the next proxycheck job.

**Row inserted into a base table:** Job A upserts the free vendors, then checks every address whose
base-table rows changed since the previous successful run, plus every address that is new to the tables.
Each one that needs proxycheck.io goes into `ipintel_curated.proxycheck_queue` with its reason. Job B, which
Job A starts as soon as it finishes, sends every waiting queued address first, the same day. It may use
half of the live-lookup reserve for them. It then closes each queue row once the answer is in
`ip_intelligence`, `ip_geo` and `ip_resolved`. Both jobs check this: "Every base-table address that
needs proxycheck.io is queued" and "Every queued base-table address was sent to proxycheck.io".

### Tests run 15 Sep 2026

| Test | Result |
|---|---|
| Rule, offline: 9 cases including private, documentation and multicast ranges | 9 / 9 |
| API, real addresses: `location_disagree` 108.28.34.35, `flagged_unconfirmed` 76.108.16.71, `no_answer` 75.112.80.5, `new_address` 1.0.0.1 | 4 / 4 called, answers saved |
| API, must not call: clean with a location 72.24.76.19, already answered 47.205.216.142, private 192.168.1.20 | 3 / 3 not called |
| API, repeat lookups of 108.28.34.35 and 1.0.0.1 | 2 / 2 not called again |
| Answers folded into the tables | 10:00 scheduled proxycheck run: 4 live answers applied, 8 / 8 checks PASS |
| Base-table path on today's 07:30 load (dry run) | 191 addresses touched: 108 new (all already answered by today's backfill), 31 re-seen with an answer, 52 clean with a location, so 0 needed a call, which is correct |
| Base-table path end to end on a new tune load | Not run: cancelled at your request to stop waiting. The next scheduled run (07:30 UTC) exercises it, and both jobs fail loudly if a queued address is missed |

## 5c. Corrections made 15 Sep 2026

| Item | Before | After |
|---|---|---|
| FraudLogix `created_at` / `updated_at` | `2023-01-11 15:00:35.000000`: Pacific time, no zone | `2023-01-11T23:00:35Z`, UTC, the same format as every other table. 4,533,365 rows converted; originals in `archive/fraudlogix-timestamps-before-utc-2026-09-15/`. Proof the source is Pacific: `datetime` always equals `date_pst`, and each 6-hourly load's newest click is 7–8 h before the load was written |
| `vendor_overview_proxy.false_positive_rate_pct` | Bot flags ÷ whole pool, so it repeated `bot_identification_pct` | The approved definition: of confirmed humans (`qualified_lead_ips.confirmed_human`) the vendor gave a bot answer for, the share flagged as bot. FraudLogix 2.9% (6 of 210); blank for vendors with no bot answers; sample size in `bot_metric_status` |
| `precision_infra_pct` / `recall_infra_pct` | 0.0 with no published-range addresses to measure against | Blank until such addresses exist |

## 5d. Using the full 80,000 queries a day

| Run | When (UTC) | Spends |
|---|---|---|
| Queued base-table addresses | Right after Job A, first | Up to the budget plus half the 10,000 live reserve |
| Daily backfill | After Job A (fallback 10:00) | 70,000 (the most allowed while 10,000 stay reserved for live lookups) |
| Top-up | 22:00, schedule `ipintel-proxycheck-topup` | Whatever is left of 80,000, keeping 2,000 for late live lookups |

Proof, 15 Sep 2026: 50 backfill batches + 28 top-up batches sent and merged; counter 77,999 of 80,000;
follow-up run 8/8 checks PASS with 5,889 CloudTrail events reviewed. The top-up's first run hit CloudTrail's
2-requests-a-second limit in the final review (answers were already merged); the review is now paced.

## 6. Keeping it reliable

| Item | State |
|---|---|
| Weekly table maintenance (compaction, old versions) | Schedule `ipintel-weekly-maintenance`, Sundays 03:00 UTC; tested on all 8 tables, 16/16 statements succeeded; reconciliation unchanged afterwards |
| Leftovers from a crashed run | Staging tables older than 3 hours are swept at the start of each daily run |
| Alarms | Job failed (×2), Job A missed 26 h, hand-over dead-letter, proxycheck over 90%, maintenance failed |
| Old benchmark endpoints | Removed from the API 15 Sep; `LOVABLE_PROMPT_REMOVE_BENCHMARK.md` removes the pages |

## 7. What the first day changed

| Measure | Before the backfill | After 15 Sep |
|---|---:|---:|
| Addresses seen in 90 days, flagged with nothing confirming it | 69,071 | 20,781 |
| FraudLogix flags proxycheck.io judged clean (`proxycheck_overrides`) | 150 | 46,420 |
| Flags confirmed by proxycheck.io and another vendor | 137 | 3,372 |
| Addresses with an agreed location | 2,459 | 21,234 |

Full reconciliation after both runs: 4,956,909 source addresses, 0 missing, 0 duplicates, 9,540,283
intelligence rows each with its analytics row; 56 of 56 addresses identical between the table and the API.

## 8. The app reads the live tables

Approved by you on 15 September 2026 after the first scheduled runs: mode set to `live` (audit record in
`ipintel-pipeline-state`). Every table page now reads `ipintel_curated`; nothing in `unified.*` was
touched. Switching back is setting `mode` to `shadow` in the safety item.

## 9. Open items that need you

| Item | Why it matters |
|---|---|
| ~~Subscribe an email to SNS topic `ipintel-alerts`~~ | Done 15 Sep 2026: one email subscription, confirmed |
| Paste the Lovable prompts in this order: Pipeline Control, IP Lookup, Remove Benchmark | The app still has pages built on the removed endpoints |
