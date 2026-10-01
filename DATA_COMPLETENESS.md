# Data Completeness: every IP in the data lake, usable in both tables

Written 17 Sep 2026, 20:40 UTC. It explains what "complete" means, where we stand, how the gap is closed and how anyone can check it.

## 1. What "complete" means

An IP address is complete when **both** are true:

| Part | Rule | Where |
|---|---|---|
| **Risk** | At least one row from **FraudLogix** or **proxycheck.io** with `is_proxy` filled in | `ip_intelligence` |
| **Location** | At least one row with a state or a city | `ip_geo` |

**Why IP2Proxy PX12 doesn't count.** It is a list of known proxies. If an address is absent, that means "not on the list", not "this address is clean". FraudLogix decides on every ad click we send it, and proxycheck.io answers any address we ask, so those two can confirm an address is clean.

**Excluded:** private and reserved addresses (such as `10.255.220.18`). No vendor can say anything about them. There are 87, and one was seen in the last 30 days.

## 2. Where we stand (17 Sep 2026)

| | Addresses |
|---|---|
| Seen in our data lake | 4,959,913 |
| **Complete** | **4,501,335 (90.75%)** |
| Incomplete | 458,578 |

**Nothing is missing outright.** Every address has rows in both tables. The gaps are empty fields, not missing records.

| State | Addresses | Seen in the last 90 days | What it means |
|---|---|---|---|
| Complete | 4,501,335 | 194,500 | Risk and location usable |
| No acceptable risk answer | 454,946 | 0 | FraudLogix saw a click but never decided; proxycheck.io not asked yet |
| Only IP2Proxy answered | 2,408 | 0 | Listed as a proxy, but nothing confirms the rest |
| Risk fine, no usable location | 1,224 | 14 | FraudLogix decided, but no vendor gave a state or city |
| No row in either table | **0** | 0 | — |

**The last 90 days, which reporting uses: 194,514 addresses, 194,500 complete.** The remaining 14 are queued and go out in the next run.

## 3. How the gap is closed

All 458,578 incomplete addresses have one thing in common: **proxycheck.io has never been asked about them.** One proxycheck.io answer fills both the risk fields and the location, so a single backfill closes both gaps.

**Daily order** (in `job_proxycheck._selection_sql`):
1. Queued addresses (new rows in the base tables, and anything the completeness audit queued).
2. Addresses first seen today.
3. Addresses seen in the last 30 days, then the last 90 days. Recent addresses matter most for reporting.
4. **Addresses with no acceptable answer, newest first.** This is the 458,578.
5. Experiment IPs, then addresses with no conclusion, then the rest.

**Speed:** 78,000 queries a day. 458,578 addresses is about **6 days**, so complete around **23 September 2026**. The daily report says exactly how many are left.

## 4. How it stays correct

Two checks run on **every** daily job, and a failure stops the `unified` tables from being refreshed:

| Check | Passes when |
|---|---|
| Every address seen in the last 90 days has a FraudLogix or proxycheck.io answer | No public address in the window is unanswered, unless it is already queued |
| Every address seen in the last 90 days is complete in both tables | The same, for risk **and** location |

A third line, "Table completeness exported", records the progress figure ("90.75% of 4,959,913 addresses complete; 458,578 still to ask proxycheck.io, about 5.9 days") in the run log.

**The report file:** `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/ipintel_curated/table_completeness.json`, rebuilt after every run. It also travels to the app inside `proxy_coverage.json`, under `completeness`.

**New addresses** are handled automatically: the daily load adds them, the queue sends them to proxycheck.io the same day, and the checks confirm it.

## 5. How to check it yourself

```bash
cd build/pipeline
python run_sql.py sql/checks/table_completeness.sql --show   # the table in section 2
python run_sql.py sql/checks/gap_detail.sql --show           # what exactly is empty
python run_sql.py sql/checks/acceptable_vendor_gap.sql --show # the gap by how recently the IP was seen
```

Or read the run log: DynamoDB `ipintel-pipeline-state`, items `run#proxycheck-daily` and `run#free-daily`, newest first. Every run lists its checks.

In the app, the **Enrichment Coverage** page shows the same numbers.

## 6. Limits, stated plainly

- **Complete means "we have a usable answer", not "the answer is right".** Accuracy is measured separately: location against customer addresses (Location Accuracy) and risk against revenue (`SESSION_IP_BOT_VERDICT.md`).
- **Answers age.** An address answered months ago may have changed hands. There is no re-check policy yet; it should be agreed once the backfill finishes.
- **Private and reserved addresses can never be completed.**
- **City and ZIP are unreliable from any vendor** (best city accuracy is about 11%). "Usable location" therefore means a state or a city is present, and the state is the level to trust.
- **The third source** (`experimentation_tools.experiment_router_events`) is not included yet: the project roles cannot read its S3 bucket. See `ADMIN_DELETION_STEPS.md`, Request 3. Its addresses will go through the same rules once access is granted.

## 7. Files

| File | What it is |
|---|---|
| `build/pipeline/src/completeness.py` | Builds the report and the two checks |
| `build/pipeline/sql/checks/table_completeness.sql` | The completeness audit |
| `build/pipeline/sql/checks/gap_detail.sql` | What is empty for the incomplete addresses |
| `build/pipeline/sql/checks/acceptable_vendor_gap.sql` | The gap by recency |
| `build/pipeline/sql/checks/session_resolution_now.sql` | Whether recent sessions can be resolved |
| `serving/ipintel_curated/table_completeness.json` | The report, rebuilt after every run |
