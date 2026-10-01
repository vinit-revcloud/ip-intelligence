# Showing the Findings in the Lovable UI

**Date:** 2026-09-03 · **Status:** API is live and tested.

---

## 1. The API is deployed

Lovable cannot reach Athena. So the findings are precomputed into one JSON file on S3 and served by
a single read-only Lambda.

```
https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/
```

| Route | Returns |
|---|---|
| `GET /health` | run id + timestamp — use for the "data is live" indicator |
| `GET /summary` | sample stats, both scorecards, and the truth caveat (~4 KB) |
| `GET /findings` | everything including all 485 IPs of evidence (~596 KB) |
| `GET /ip/{ip}` | one IP's full evidence trail |

Every request needs `Authorization: Bearer <token>`. Without it the API returns `401`. The token
was generated at deploy time and is in the Lambda's environment — **it goes in Lovable's
server-side secret store only, never in a component or a client bundle.** I'll give it to you
separately rather than write it into a file in your OneDrive.

Verified working: `/health` returns 200 with the token and 401 without it.

### Why this shape

It is the smallest thing that works and it touches nothing you already have. One Lambda, one IAM
role scoped to a single S3 prefix, one JSON file. No API Gateway, no VPC, no database, no
dependency on `ip-database`, `raw` or `unified`. Refreshing the data is re-uploading one file — the
Lambda picks it up on the next cold start.

---

## 2. Nothing in your existing infrastructure was touched

| Resource | What happened |
|---|---|
| `unified.unified_session_summary` | **read only** — used for every session lookup, as you asked. Never written |
| `unified.uct_leads`, `raw.raw_tune_clicks` | read only |
| `ip-database` (22 tables) | untouched |
| `primary` Athena workgroup | untouched — I use `ipintel_etl` |
| Existing S3 data | nothing deleted or overwritten |

Everything new is prefixed `ipintel`: 2 workgroups, 3 databases, 14 tables, 1 IAM role, 1 Lambda,
and new folders under `ip-intelligence/`. Deleting everything with that prefix returns the account
to its prior state. No existing dependency reads any of it.

---

## 3. What the API actually contains

### Sample

485 IPs · 3,798 leads · $346,515 revenue · **28 shared-infrastructure IPs carrying $346,245 of it**

### Location scorecard (5 sources)

| Vendor | IPs | Answered | State match | ZIP match | Median error | P90 error |
|---|---:|---:|---:|---:|---:|---:|
| ipinfo.io | 485 | 100% | 58.8% | 11.5% | 59 mi | 811 mi |
| ipwho.is | 485 | 100% | 58.4% | 9.3% | 60 mi | 835 mi |
| IP2Location DB11 | 485 | 100% | 54.8% | 7.0% | 74 mi | 972 mi |
| proxycheck.io | 200 | 100% | 53.5% | 6.5% | 79 mi | 821 mi |

### Risk scorecard (4 sources)

| Vendor | Sent | Answered | Proxy | VPN | Bot | Flagged IPs | Revenue on flagged (all) | (excl. shared infra) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Authoritative lists | 485 | 485 | 28 | 28 | 0 | 28 | $346,245 | $0 |
| FraudLogix (TUNE) | 485 | 237 | 47 | 0 | 67 | 81 | $305,758 | $2,193 |
| proxycheck.io | 485 | 200 | 9 | 9 | 0 | 9 | $88,617 | $0 |
| IP2Proxy PX12 | 485 | **1** | 1 | 0 | 0 | 1 | $0 | $0 |

The last two columns are why the split matters. FraudLogix appears to put $305,758 at risk — but
$303,565 of that sits on shared infrastructure where per-IP revenue is meaningless. The real
exposure is **$2,193**.

---

## 4. A genuinely valid truth source appeared

The lead-address problem (see `BENCHMARK_RESULTS.md` §2) does not affect this one.

**Apple publishes the city for every iCloud Private Relay egress range.** That is the operator's own
statement of where the relay exit is — not an inference. For those 28 IPs we have real ground truth.

Worked example, `146.75.164.0`:

| Source | Says |
|---|---|
| **Apple (authoritative)** | **Dallas, TX** |
| ipwho.is | Dallas, TX 75202 ✅ |
| ipinfo.io | Dallas, TX 75201 ✅ |
| **IP2Location DB11** | **Mexico City, Mexico** ❌ |
| IP2Proxy PX12 | no answer |
| FraudLogix | flagged: MASKED_DEVICES, ABNORMAL_TRAFFIC_PATTERNS, NON_HUMAN_SCRIPT |

DB11 places a Dallas IP in **the wrong country**, and we can prove it without relying on any
disputed lead address. Make this the headline example in the UI — it is airtight.

---

## 5. The Lovable prompt

Paste this after prompts 1–2 from `LOVABLE_PROMPTS.md`.

> Add a new route `/findings` called **"Benchmark Findings"** and add it to the sidebar under
> Analytics. It shows the results of a vendor benchmark run.
>
> **Data.** Add `src/lib/api/findings.functions.ts` with a `createServerFn` that fetches
> `${process.env.IPINTEL_API_URL}/summary` with header
> `Authorization: Bearer ${process.env.IPINTEL_API_TOKEN}`. Read both env vars **inside** the
> handler, never at module scope. Add a second server function for
> `/ip/{ip}`. Type both against a new `Findings` type in `src/lib/api/contract.ts`. If the fetch
> fails, surface an error state — never fall back silently to mock data.
>
> **Layout, top to bottom:**
>
> 1. **Sample summary** — five `KpiCard`s: IPs tested 485 · Leads 3,798 · Revenue $346,515 ·
>    Shared-infrastructure IPs 28 · Revenue on shared infrastructure $346,245. The last card uses
>    the warning tone.
>
> 2. **A `Callout` in warning tone directly beneath**, rendering the `truth_caveat` string from the
>    API verbatim. Do not hardcode this text — it changes as the truth source is confirmed. This
>    callout must appear above the location table, never below it.
>
> 3. **Location table** titled *"Vendor Disagreement — Location"* (not "accuracy"). Columns:
>    Source · IPs · Answered · State match · ZIP match · Median error · P90 error. Sort by state
>    match descending. Beneath each percentage show `±4.5%` in muted 11px text. Where two rows'
>    intervals overlap, render both values in the default foreground colour rather than
>    success/warning tones — do not visually declare a winner the data cannot support.
>
> 4. **Risk table** titled *"Proxy, VPN and Bot Detection"*. Columns: Source · Sent · Answered ·
>    Answer rate · Proxy · VPN · Bot · Flagged IPs · Revenue on flagged (all) · Revenue on flagged
>    (excl. shared infra). The two revenue columns sit adjacent under a shared grouped header.
>    A source whose answer rate is under 10% shows a warning `Pill` reading "almost no coverage" —
>    IP2Proxy PX12 answered 1 of 485 and that must be impossible to miss.
>
> 5. **Callout explaining the two revenue columns**: revenue attributed to a shared egress IP is the
>    sum across tens of thousands of different people, so it is not a per-customer figure. Example:
>    `146.75.164.0` has 53,967 sessions and 7 leads.
>
> 6. **Worked example card** titled *"Proven vendor error"*, rendering the `146.75.164.0` comparison
>    from §4 above as a `DataTable`: Source · State · City · ZIP · verdict pill. Apple's row is the
>    truth row — give it a tinted background and a "ground truth" pill. IP2Location's Mexico City
>    row gets a destructive-tone pill. Caption: *"Apple publishes the city for every iCloud Private
>    Relay egress range, so this is the operator's own statement, not an inference."*
>
> **Rules.** A source that returned no answer renders a neutral "no answer" pill — never 0% and
> never "clean"; these mean completely different things. No hardcoded colours, semantic tokens only.
> Every table in `DataTable` with an explicit `minWidth`. Must not overflow horizontally at 390px.

Then a second, smaller prompt:

> On `/ip-explorer`, add a search box that calls the `/ip/{ip}` server function and renders the
> returned evidence: the geo claims table, the risk claims table, and the business outcome
> (sessions, leads, revenue). Show a `shared_infrastructure` badge when that flag is true. Seed the
> box with `146.75.164.0`. If the IP is not in the benchmark sample the API returns 404 — render an
> `EmptyState` saying it wasn't part of this run, not an error.

---

## 6. Refreshing the data

Re-running the benchmark and refreshing the UI is:

1. Re-run the vendor fan-out and the Athena scoring queries
2. Rebuild `findings.json`
3. `aws s3 cp findings.json s3://…/ip-intelligence/serving/findings.json`

The UI picks it up automatically. No redeploy, no schema change. Total cost per run is about $0.02.

When you add a source, it becomes new rows in `ip_geo_observations` / `ip_proxy_check` and a new row
in each scorecard — the tables above grow a row, and no component changes.
