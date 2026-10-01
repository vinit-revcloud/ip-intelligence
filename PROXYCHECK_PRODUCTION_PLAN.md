# proxycheck.io — what to buy, and exactly where it gets used

**Date:** 2026-09-11 · Every number below is measured against live data or read off proxycheck's own
pricing and API pages today. No estimates.

---

## 1. The short answer

Buy the **Starter plan at $5.99/month, 40,000 daily queries**.

It backfills the IPs that actually matter in **6 days**, then runs the live pipeline forever at
**6% utilisation**. If you also want proxycheck on the full 4.96M archive, take **$19.99 / 320K
daily for one month**, finish in 16 days, then downgrade to $3.99. Downgrades are prorated, so the
one-time cost of full coverage is roughly **$20**.

Yearly billing charges 11 months instead of 12, so $5.99/mo becomes **$65.89/year**.

---

## 2. Why proxycheck and not another vendor

It is the only paid API in the comparison, and the benchmark settled the question: it is the
**top-scoring vendor on both leaderboards at once**.

| Board | Rank | Score | What it does |
|---|---|---:|---|
| Geo | **1 of 7** | **76.9** | 95.6% fill, 80.5% agreement with the other vendors |
| Proxy | **1 of the real vendors** | **75.6** | 97.6% fill, **97.2% recall** on known infrastructure |

The one source above it on the proxy board, `authoritative_lists`, scores 100 because it *is* the
reference being measured against. It is a set of published ranges, not a detector. It cannot find
anything that is not already on a public list.

Every other API vendor is capped at 1,000 queries/day on a free tier that has no paid path we can
use at this volume. proxycheck is the only one that scales at all.

**Losing proxycheck costs you the best signal on both sides of the product simultaneously.**

---

## 3. The population, measured today

Distinct IPv4 across `unified.unified_session_summary` + `raw.raw_tune_clicks`:

| Pool | IPs | What it is |
|---|---:|---|
| All time | **4,956,391** | the full archive |
| Active last 180 days | 604,908 | 12.2% of the archive |
| Active last 90 days | **226,821** | 4.6% |
| Active last 30 days | 46,903 | 0.9% |
| **New per day** | **~850** | 25,669 first-seen in the last 30 days |

Two facts from the earlier analysis drive everything:

- **3,369,752 IPs (68.0%) were seen on exactly one day and never again.** An IP's reputation only
  pays off the next time that IP shows up. For two thirds of the archive there is no next time.
- **1,000 addresses carry 19.5% of all sessions.** A small hot set does most of the work and changes
  most often.

---

## 4. The rule that makes 4.9M affordable

**Two tiers. File vendors cover everything. proxycheck covers what is live.**

| Tier | Vendors | Coverage | Marginal cost |
|---|---|---:|---|
| **File** | IP2Location DB11 · IP2Proxy PX12 · MaxMind GeoLite2 · DB-IP · authoritative lists | **all 4,956,391** | **$0** |
| **API** | proxycheck.io | the live subset | the subscription |

The file vendors ship as downloadable range tables. They already sit in S3 and resolve through an
Athena range join on the `prefix16` bucket key. A full pass over all 4.96M IPs is about an hour of
Athena and no vendor call at all. There is no quota to respect and no reason to hold back.

So **every one of the 4.96M IPs gets enriched**. The only question is how many of them additionally
get proxycheck's opinion. `has_answer` keeps that honest in the tables: an IP with no proxycheck row
reads as *not asked*, never as *clean*.

---

## 5. Plan choice

proxycheck bills per IP checked. Two details from their API docs change the arithmetic:

- A registered account may send **1,000 IPs per POST request**, and the whole batch counts as one
  request against the rate limit. The rate ceiling in North America is 875 requests/second, so
  **quota is the only real constraint**. Throughput never is.
- The `&vpn=3` flag we use costs **2 queries instead of 1** when a single IP comes back as both a
  proxy and a VPN. Measured on our own 2,055 answered IPs, that happens **0.39%** of the time, so
  the real multiplier is **1.004**. Negligible, but it is in the budget below.

### Days to finish a backfill

| Plan | $/mo | Daily | Active 90d (227.7K) | Full archive (4.98M) |
|---|---:|---:|---:|---:|
| Free | 0 | 1K | 228 days | 13.6 years |
| Starter | 3.99 | 10K | 23 days | 498 days |
| Starter | 4.99 | 20K | 12 days | 249 days |
| **Starter** | **5.99** | **40K** | **6 days** | 124 days |
| Pro | 9.99 | 80K | 3 days | 62 days |
| Pro | 14.99 | 160K | 2 days | 31 days |
| **Pro** | **19.99** | **320K** | 1 day | **16 days** |
| Business | 29.99 | 640K | — | 8 days |
| Business | 49.99 | 1.28M | — | 4 days |

### What steady state actually costs

| Job | Cadence | Queries/day |
|---|---|---:|
| New IPs arriving | every day | 850 |
| Refresh the active-30d pool (46,903) | 30-day cycle | 1,564 |
| Refresh the top 1,000 hot IPs | weekly | 143 |
| **Total** | | **≈ 2,560** |

The free tier's 1,000/day cannot even carry steady state. The $5.99 plan carries it at **6.4%
utilisation**, which leaves room to widen the refresh pool to active-180d later without changing
plans.

### Recommendation

1. **Subscribe to $5.99 / 40K daily.**
2. Backfill the **226,821 active-90d IPs over 6 days**. That is the set with a next sighting.
3. Run steady state at ~2,560/day.
4. **Optional, if you want the full archive covered:** upgrade to $19.99 / 320K for one month, let
   the backfill run 16 days, then downgrade. Prorated both ways. Be clear-eyed about what it buys:
   3.37M of those IPs will never appear again, so this is for archive completeness, not for
   production decisions.

Buy before **October 2026** — proxycheck has announced a price rise on Starter, Pro and Business,
and a subscribed price is locked for the life of the subscription.

---

## 6. Where it plugs in

```
unified.unified_session_summary.session_ip   raw.raw_tune_clicks.ip
                │                                     │
                └──────────────┬──────────────────────┘
                               ▼
              ipintel_curated.ip_universe          ← NEW. the work queue.
              one row per distinct IP:
              ip, first_seen, last_seen, days_seen, hits,
              pc_fetched_at, pc_next_due_at, tier
                               │
          ┌────────────────────┴────────────────────┐
          ▼                                         ▼
  FILE TIER (no quota)                      API TIER (quota'd)
  Athena range join on prefix16             ipintel-pc-worker  ← NEW Lambda
  DB11 · PX12 · GeoLite2 · DB-IP            EventBridge, every 30 min
  · authoritative lists                     picks IPs where pc_next_due_at <= now
  ALL 4,956,391 IPs                         1,000 IPs per POST
          │                                 s3://…/vendor/proxycheck/dt=…/*.ndjson
          │                                         │
          └────────────────────┬────────────────────┘
                               ▼
                  ipintel_curated.geo_src / intel_src
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    unified.ip_geo      unified.ip_intelligence   the two *_analytics twins
                               │
                               ▼
             unified.vendor_overview_geo / _proxy   → the Lovable UI
```

### What one proxycheck response fills

A single call returns both halves of the product, which is why one subscription covers two
leaderboards:

| Response field | Lands in | Column |
|---|---|---|
| `region`, `city`, `postcode`, `latitude`, `longitude`, `timezone` | `unified.ip_geo` | state, city, zip_code, latitude, longitude, timezone |
| `proxy`, `vpn` | `unified.ip_intelligence` | is_proxy, is_vpn |
| `type` = TOR / Hosting / Compromised Server / Scraper | `unified.ip_intelligence` | is_tor, is_datacenter, is_compromised, is_scraper |
| `operator.anonymity` | `unified.ip_intelligence` | is_anonymous |
| `provider`, `asn` | `unified.ip_intelligence` | isp, asn |
| `risk` | `ip_intelligence_analytics` | risk_score |
| `last seen unix` | both base tables | updated_at |

The exact request stays what the benchmark used, because the flags are not optional:

```
POST https://proxycheck.io/v2/?key=KEY&vpn=3&asn=1&risk=1&seen=1&days=90
body: ips=1.2.3.4,5.6.7.8,...   (up to 1000)
```

- `vpn=3` is the only setting where proxy and VPN come back as **separate answers**. Under `vpn=1`
  a proxy result overwrites the VPN result and the two columns would contradict each other.
- `seen=1` is the **only** way `last seen unix` is returned, and that is what `updated_at` maps to.
- `asn=1` fills `isp` and `asn`. `risk=1` fills `risk_score`.

---

## 7. The quota guard

The worker must never blow the daily cap, because an exhausted key returns an error for the rest of
the day and silently starves the pipeline.

Before each run the Lambda reads:

```
https://proxycheck.io/dashboard/export/usage/?key=KEY
```

which returns `Queries Today`, `Daily Limit`, `Burst Tokens Available`. Rules:

1. Compute `remaining = Daily Limit - Queries Today`.
2. Stop at **95% of the daily limit**. The last 5% is reserve for the next day's new IPs, which must
   never be starved by a backfill.
3. Size the batch as `min(remaining × 0.95, 1000)` per request.
4. Write every response to S3 as raw NDJSON **before** normalising. A re-run must never re-spend
   quota on an IP already fetched.
5. On a non-`ok` status, stop the run and record it. Do not retry in a loop.

Burst tokens multiply the daily allowance by 5 for one day and the plan grants 3 on Starter. They
are a manual lever for finishing a backfill early, not something the scheduler should spend on its
own.

---

## 8. Priority order inside the queue

When the queue is longer than the day's quota, spend it in this order:

1. **New IPs from the last 24 hours** — always first, never deferred. ~850/day.
2. **Hot set** — the top 1,000 IPs by session count, on a 7-day cycle. These carry a fifth of all
   traffic and a wrong verdict on one of them is expensive.
3. **Recurring IPs** — seen on 2+ days, on a 30-day cycle.
4. **Backfill** — everything else, oldest `last_seen` first, with whatever quota is left.

Transient IPs, the 68% seen on exactly one day, are enriched once at first sight and **never
refreshed**.

---

## 9. What has to be built

| # | Item | Notes |
|---|---|---|
| 1 | `ipintel_curated.ip_universe` | the work queue. Built once from both sources, updated daily. |
| 2 | `ipintel-pc-worker` Lambda | EventBridge every 30 min. Quota guard, 1,000-IP batches, raw NDJSON to S3. |
| 3 | File-vendor backfill over all 4.96M | Athena range join on `prefix16`. One hour, no quota. |
| 4 | `ipintel-daily-refresh` Lambda | rebuilds geo_src/intel_src, the four unified tables, both overview tables. |
| 5 | Partition `unified.ip_geo` / `ip_intelligence` by `prefix16` | at 4.96M × 7 vendors the tables stop being scannable unpartitioned. |
| 6 | Serving-layer switch | at this scale the Lambda cannot load a JSON file into memory. It must query Athena or a materialised per-IP store. |

Item 6 is the one that has no answer yet. The current API reads whole-table JSON from S3 into the
Lambda, which works at 14,735 rows and will not work at 34 million. It needs deciding before the
backfill lands, not after.

---

## 10. Build SQL is not the risk — the shell is

A heredoc mangled an IPv4 regex during the benchmark and FraudLogix silently returned 0 rows for a
full run. Every query in the production path must be written to a file and submitted with `file://`,
never assembled as a shell string. The worker builds no SQL at all; it only reads the queue and
writes NDJSON.
