# How This Works — Plain Explanation

**Date:** 2026-09-03

Answering four questions: what the pipeline actually is, which tables I used and why,
what I changed in your AWS, and where the proxy/VPN/bot results are.

---

## 1. The picture — this is exactly what you described

```
                    ┌─────────────────────────┐
                    │  A LIST OF IPs TO TEST  │
                    │      (485 today)        │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │        fan out to every source      │
              ▼                  ▼                  ▼
   ┌──────────────────┐ ┌────────────────┐ ┌──────────────────┐
   │ LOOKUP FILES     │ │ LIVE APIs      │ │ OFFICIAL LISTS   │
   │ IP2Location DB11 │ │ proxycheck.io  │ │ Tor exit nodes   │
   │ IP2Proxy PX12    │ │ ipwho.is       │ │ AWS / Google IPs │
   │                  │ │ ipinfo.io      │ │ Cloudflare/Fastly│
   │                  │ │                │ │ iCloud Relay     │
   └────────┬─────────┘ └───────┬────────┘ └────────┬─────────┘
            │                   │                   │
            └───────────────────┼───────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
   ┌─────────────────────┐           ┌──────────────────────────┐
   │  TABLE 1: ip_geo    │           │ TABLE 2: ip_proxy_check  │
   │  where is this IP?  │           │ is it a proxy/VPN/bot?   │
   │                     │           │                          │
   │  one row per        │           │  one row per             │
   │  IP × source        │           │  IP × source             │
   └─────────────────────┘           └──────────────────────────┘
```

Two tables, exactly as you specified. One row per IP per source in each. Add a source, get more
rows — never more columns.

---

## 2. Which tables I used, and why

There are **two separate jobs** here, and mixing them up is what made my earlier explanation
confusing. Let me separate them.

### Job A — *Which* IPs do we test? (choosing the sample)

This is the only place `uct_leads` was used.

| Table | Database | Why |
|---|---|---|
| `unified.uct_leads` | existing, read-only | It is the **only** table with a customer-typed postal address that can be traced back to an IP |
| `unified.unified_session_summary` | existing, read-only | The bridge: `uct_leads.alyson_session_id` → `session_id` → `session_ip` |
| `raw.raw_tune_clicks` | existing, read-only | FraudLogix fraud verdicts, and part of the 4.9M IP universe |

**Why I reached for `uct_leads` at all:** you asked for an accuracy score. Accuracy means comparing a
vendor's answer to a *correct* answer. A correct location has to come from somewhere that is not an
IP lookup — otherwise you are just checking whether two vendors agree. The only non-IP location in
the warehouse is the address a lead typed in themselves. That is in `uct_leads`.

**And here is the problem I found:** that address is probably the *property being sold*, not where
the person was sitting when they filled the form. Evidence: two independent vendors agree with each
other 93% of the time, but with that address only 58%. Independent vendors cannot agree with each
other and disagree with the truth unless the "truth" is measuring something else.

**What this means for you:** `uct_leads` is fine for *picking* which IPs to test. It is not yet
proven usable for *scoring* accuracy. Those are separable — the pipeline works either way.

### Job B — What does each source say? (the actual fan-out)

`uct_leads` plays no part here. Feed in any list of IPs and this runs.

| Table I created | What is in it |
|---|---|
| `ipintel_curated.ip_geo_observations` | every source's **location** answer |
| `ipintel_curated.ip_proxy_check` | every source's **proxy / VPN / Tor / datacenter / bot** answer |
| `ipintel_curated.ip_dim` | IP2Location + IP2Proxy results for all 4.9M IPs |
| `ipintel_curated.ip_flags` | FraudLogix verdicts per IP |
| `ipintel_reference.zip_centroid` | ZIP → lat/long, to measure distance in miles |

---

## 3. What I changed in your AWS — the complete list

### Created (all new, all namespaced `ipintel*`)

- **2 Athena workgroups:** `ipintel`, `ipintel_etl`
- **3 databases:** `ipintel_reference`, `ipintel_curated`, `ipintel_analytics`
- **13 tables** inside those three databases
- **New S3 folders** under the existing `ip-intelligence/` prefix: `curated/`, `reference/`,
  `analytics/`, `athena-results/`, `_rescue/`
- **3 uploaded files:** the geo results, the proxy results, the ZIP reference

### Changed or deleted

**Nothing.** Specifically:

| Thing | State |
|---|---|
| `ip-database` (your original 22 tables) | untouched — I verified the newest table there was created two hours before my session started |
| `raw.*`, `unified.*` | read-only. Never written to |
| `primary` Athena workgroup | untouched. I made new ones instead |
| Existing S3 data | nothing deleted or overwritten |
| `ip_analytics` + `dashboard_summary` | **copied** to `_rescue/` as a backup, originals left in place |

Everything I made is in new databases with an `ipintel` prefix. Deleting all of it would leave your
account exactly as it was.

---

## 4. The proxy / VPN / bot results — you were right, these were missing

I had built the geo side properly and left the proxy side half-finished. It is complete now.
**Four sources, all 485 IPs:**

| Source | IPs sent | Gave an answer | Proxy | VPN | Tor | Datacenter | Bot |
|---|---:|---:|---:|---:|---:|---:|---:|
| Authoritative lists | 485 | **485** | 28 | 28 | 0 | 0 | 0 |
| FraudLogix (TUNE) | 485 | **237** | 47 | 0 | 0 | 0 | 67 |
| proxycheck.io | 485 | **200** | 9 | 9 | 0 | 0 | 0 |
| IP2Proxy PX12 | 485 | **1** | 1 | 0 | 0 | 1 | 0 |

### What this table is really telling you

**IP2Proxy PX12 answered 1 IP out of 485.** The free proxy database is effectively empty for your
traffic. It is not "saying these IPs are clean" — it has no opinion at all. That distinction is
built into the table as a separate `has_answer` column, exactly as you specified: no row and a
"not a proxy" row mean completely different things.

**FraudLogix only covers 237 of 485.** The other 248 IPs never appeared in TUNE click data, so
there is no verdict for them. Again: no opinion, not a clean verdict.

**proxycheck.io covers 200 of 485** — and that is a quota problem on our side, not the vendor's.
The API is rejecting the key and treating us as anonymous (100/day). Worth checking in the
dashboard before you pay for the $5.99 plan.

**28 IPs are iCloud Private Relay**, confirmed against Apple's own published list. These are real
Apple customers whose traffic is relayed. Any vendor calling them a proxy is technically correct —
and blocking them costs you qualified leads.

So on 485 qualified-lead IPs, the sources agree on almost nothing, and the free proxy database
contributes essentially zero. That is a genuine, useful finding.

---

## 5. The location results

| Source | IPs | Answered | State match | ZIP match | Median error | P90 error |
|---|---:|---:|---:|---:|---:|---:|
| ipinfo.io | 485 | 100% | 58.8% | 11.5% | 59 mi | 811 mi |
| ipwho.is | 485 | 100% | 58.4% | 9.3% | 60 mi | 835 mi |
| IP2Location DB11 | 485 | 100% | 54.8% | 7.0% | 74 mi | 972 mi |
| proxycheck.io | 200 | 100% | 53.5% | 6.5% | 79 mi | 821 mi |

**Do not circulate these as accuracy figures yet** — see §2. Vendors claim ~98% state accuracy. The
gap is almost certainly the property-vs-person address problem, not the vendors being terrible.

What *is* safe to say from the same data: **the sources disagree with each other about 1 IP in 14
on state, and far more often on ZIP.** That is measured, not inferred, and it is the real argument
for having this console.

---

## 6. What to do next

**You (30 minutes, unblocks everything):**

1. Ask whoever owns the lead pipeline: is `uct_leads.address_line_1` the customer's own address, or
   the property they are asking about? This single answer decides whether accuracy is measurable.
2. Log into proxycheck.io and confirm the API key is active. The API is not recognising it.

**Me, once you confirm:**

- If the address is the *customer's* → the accuracy numbers are real and we publish them.
- If it is the *property's* → we switch to reporting vendor **agreement** (still valuable), and hunt
  for a genuine location truth separately.
- Either way: add MaxMind GeoLite2 and DB-IP (both free) to get to six geo sources, and re-run.

Re-running everything costs about **$0.02** and takes a few minutes, so nothing here is expensive
to redo.

---

## 7. One thing I would change about my earlier framing

I led with accuracy scoring, which needs a truth source, which turned out to be shaky — and that
made the whole thing sound more fragile than it is.

The fan-out you described is the solid part: take a list of IPs, ask every source, store two tables.
That works today, cost almost nothing, and already produced real findings. Accuracy scoring is a
layer that sits **on top** and can wait for a proper truth source without holding up anything else.
