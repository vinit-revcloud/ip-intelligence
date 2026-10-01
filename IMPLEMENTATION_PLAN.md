# Implementation Plan — Final

**Date:** 2026-09-11
**Goal:** every IP we have ever seen is geo-enriched, every IP that still matters is risk-enriched,
and a daily job keeps both current without anyone touching it.

---

## The shape of it, in one picture

```
       raw.raw_tune_clicks  +  unified.unified_session_summary
                          │
                          ▼
              4,956,391 unique IP addresses
                          │
        ┌─────────────────┴─────────────────┐
        ▼                                   ▼
  FILE VENDORS                        API VENDORS
  DB11 · PX12 · MaxMind               proxycheck.io
  DB-IP · authoritative lists         (ipinfo, ipwho.is)
  no quota → ALL 4.96M                80K/day → last 90 days
        │                                   │
        └─────────────────┬─────────────────┘
                          ▼
     ip_geo            ip_intelligence          ← what people query
     ip_geo_analytics  ip_intelligence_analytics ← the working out
                          │
                          ▼
     vendor_overview_geo · vendor_overview_proxy ← vendor scorecards
```

**Why two vendor tiers:** file vendors are downloaded databases, so looking up 5 million IPs costs
nothing. API vendors charge per call. That is a physical difference, not a design preference.

**Why 90 days for the API tier:** only 46,903 of the 4.96M IPs have been seen in the last 30 days.
The rest are historical, and IPs get reassigned — a proxy verdict on an IP last seen in 2022
describes whoever held it then. Ninety days covers 226,821 IPs and stays true.

---

## Step 1 — Split the two tables in half

**What:** `ip_geo` and `ip_intelligence` keep only the columns Ahsan listed. Everything else moves
to a twin table.

| Table | Keeps |
|---|---|
| `unified.ip_geo` | ip_address, vendor, state, city, zip_code, latitude, longitude, timezone, created_at, updated_at |
| `unified.ip_geo_analytics` | consensus values, vote counts, match flags, truth comparison, agreement percentages |
| `unified.ip_intelligence` | ip_address, vendor, is_proxy, is_vpn, is_tor, is_datacenter, is_bot, **is_compromised, is_scraper, is_anonymous**, isp, asn, created_at, updated_at |
| `unified.ip_intelligence_analytics` | risk, confidence, first_seen, last_seen, times_seen, fraud_reason, is_masked_device, has_answer, flagged, verdict_class, agreement |

**Why:** someone consuming the API wants "what does this vendor say about this IP" — ten columns.
The scoring machinery is a different job and belongs in a different table.

**Joining them back:**
```sql
FROM unified.ip_geo g
JOIN unified.ip_geo_analytics a
  ON a.ip_address = g.ip_address AND a.vendor = g.vendor
```
Works on `ip_address` alone too, when you want every vendor's analytics for one IP.

**Time:** 45 minutes · **Needs:** nothing

---

## Step 2 — Fix the proxycheck call

**What:** change the request to `&vpn=3&asn=1&risk=1&seen=1`, and map the three new columns.

**Why each flag matters:**

- **`vpn=3`** makes proxycheck answer proxy and VPN as *separate questions*. Today with `vpn=1` the
  same IP comes back `proxy:"yes", type:"VPN"`; with `vpn=3` it comes back `proxy:"no", vpn:"yes"`.
  Both are "true", but they populate different columns. If we mix the flags the data contradicts
  itself.
- **`seen=1`** is the only way `last_seen` is returned at all. Without it that column is always
  empty.

**New columns, mapped from proxycheck's `type` field:**

| Column | Set when |
|---|---|
| `is_compromised` | `type = "Compromised Server"` |
| `is_scraper` | `type = "Scraper"` |
| `is_anonymous` | `operator.anonymity` present, or proxy/vpn is true |

**Three fields we cannot fill from proxycheck** — I checked its complete response:

| Field | What we do |
|---|---|
| `confidence` | **NULL.** proxycheck never returns it. Writing 100 would claim a certainty the vendor did not express |
| `first_seen` | **Derive from our own traffic** — the first date the IP appeared in sessions or clicks |
| `times_seen` | **Derive from our own traffic** — how many times we have seen it |

Deriving the last two is better than a vendor's number anyway: it answers "how long have *we* seen
this IP", which is what matters for our own bot detection.

**Time:** 30 minutes · **Needs:** the new paid proxycheck key

---

## Step 3 — Fill the geo tables for all 4.96M IPs

**What:** run every file-based vendor against all 4,956,391 IPs.

**How it works:** these vendors ship as downloadable files of IP ranges — "addresses 3.5.140.0
through 3.5.140.255 are in Ashburn, Virginia". We convert each IP to a number and find the range it
falls in. It is a join, not a web request, so five million IPs cost the same as five.

Vendors: IP2Location DB11 · IP2Proxy PX12 · MaxMind GeoLite2 · DB-IP combined · authoritative lists.

**Result:** every IP we have ever seen has geolocation from five independent sources.

**Time:** ~1 hour, about $0.50 of Athena · **Needs:** nothing

---

## Step 4 — Fill the risk tables for the last 90 days

**What:** run proxycheck against the 226,821 IPs seen in the last 90 days.

**How:** proxycheck accepts 100 IPs per request, so this is ~2,270 requests. At 80K queries/day it
finishes in **3 days**, running unattended.

**Why not all 4.96M:** it would take 62 days and most of the answers would describe IPs that have
since changed hands. Ninety days is the window where a risk verdict is still true.

**Time:** 3 days unattended · **Needs:** the paid key

---

## Step 5 — Rebuild the vendor scorecards

**What:** regenerate `vendor_overview_geo` and `vendor_overview_proxy` from the refilled tables.

**Why it changes:** the scores currently describe 2,105 qualified-lead IPs. After steps 3 and 4 they
describe millions, so fill rates and agreement will shift — probably a lot. The qualified-lead
comparison stays available separately, because it is the only place we can measure against a
confirmed human.

**Time:** 20 minutes · **Needs:** steps 3 and 4

---

## Step 6 — The daily job

**What:** `ipintel-daily-refresh` — a Lambda on a schedule, 03:00 UTC every day.

**What it does, in order:**

1. **Find new IPs.** Everything in the last 24 hours of sessions and clicks that is not already in
   `ip_geo`. Measured at **~1,900/day** (30-day range 921–2,943).
2. **Enrich them.** File vendors take all of them. proxycheck takes all of them too — 1,900 is
   **2.4% of the 80K daily quota**, so there is 42× headroom for retries and catch-up.
3. **Load.** Append to all four tables.
4. **Refresh the source of truth.** New qualified leads enter `qualified_lead_ips` automatically.
5. **Rebuild the scorecards.** Both overview tables go current.
6. **Publish.** Refresh the serving files so the API and UI show today's data.

**Safe to re-run.** Every write is partitioned by date, so running a day twice overwrites that day
rather than duplicating it. A failed run is simply run again.

**Time:** 2 hours to build · **Needs:** steps 1–5

---

## Step 7 — Switch the two base tables to Iceberg

**What:** convert `ip_geo` and `ip_intelligence` to Iceberg format.

**Why:** the tables track history — when a vendor changes its mind about an IP, we close the old row
by setting `valid_to` and add a new one. Plain Athena tables cannot update a row, so doing that
today means rewriting whole partitions. At 4.96M rows that gets slow and risky. Iceberg supports
`MERGE`, which updates the rows that changed and leaves the rest alone.

Do this once the daily job is running and the table sizes are real.

**Time:** 1 hour · **Needs:** step 6

---

## Order and timing

| Step | Depends on | Time | Can start |
|---|---|---|---|
| 1 · Split the tables | — | 45 min | **now** |
| 3 · Geo backfill, 4.96M | — | 1 hr | **now** |
| 2 · Fix proxycheck call | new key | 30 min | on key |
| 4 · Risk backfill, 90 days | 2 | 3 days unattended | on key |
| 5 · Rebuild scorecards | 3, 4 | 20 min | after 4 |
| 6 · Daily Lambda | 1–5 | 2 hrs | after 5 |
| 7 · Iceberg conversion | 6 | 1 hr | after 6 |

**Steps 1 and 3 need nothing and can start immediately.** Everything else waits on the paid key,
except the last two which wait on the backfills.

Realistically: steps 1 and 3 today, step 2 the moment the key arrives, step 4 runs itself over three
days, steps 5–7 the day after that. **Roughly four days to fully live.**

---

## What I still need

1. **The new proxycheck API key** after you buy the $9.99 plan. The current one is free-tier and
   will still stop at 1,000/day regardless of what you have paid for.
2. **Confirm 90 days** for the risk backfill, rather than 180 (8 days) or 365 (21 days).
3. **`first_seen` / `times_seen` derived from our own traffic** — agreed? `confidence` stays NULL
   either way, because proxycheck does not provide it.

Nothing else is blocked.
