# Benchmark Run 1 — Results and a Blocking Validity Finding

**Date:** 2026-09-03 · **Sample:** 485 ground-truth IPs · **Sources run:** 8

---

## 1. What was built and run

| Table | Rows | Contents |
|---|---:|---|
| `ipintel_curated.lead_truth` | 552 | IP ↔ lead address, via `uct_leads.alyson_session_id → session → session_ip` |
| `ipintel_curated.ip_geo_observations` | 1,198 | geo claims from 4 sources |
| `ipintel_curated.ip_intel_observations` | 685 | proxy/bot claims from 2 sources |
| `ipintel_reference.zip_centroid` | 33,791 | Census 2024 gazetteer, ZIP → lat/long (public domain) |
| `ipintel_analytics.geo_accuracy` | 5 | the scorecard |

**Sources that returned data:** ipinfo.io (485), ipwho.is (485), IP2Location DB11 (485),
proxycheck.io (200), authoritative lists (485), iCloud Private Relay (28 matched).

### Truth field availability — corrected

An earlier count of "485 with full address" was wrong: `uct_leads` uses **empty strings, not NULL**,
so an `IS NOT NULL` test passed blank values. Actual populated counts across the 552 IPs:

| Field | Populated |
|---|---:|
| `truth_state` | 485 |
| `truth_zip` | 485 |
| `truth_address` | 552 |
| **`truth_city`** | **54** |
| `county`, `phone_number` | 0 |

ZIP is the usable anchor — it derives city, county, metro and a lat/long centroid, and avoids
city-name normalisation entirely.

---

## 2. 🛑 Blocking finding: the lead address is probably not the user's location

The scorecard came out far below every published vendor claim:

| Vendor | IPs | Answer % | State match % | ZIP match % | Median error | P90 error |
|---|---:|---:|---:|---:|---:|---:|
| ipinfo.io | 485 | 100 | **58.8** | 11.5 | 59.3 mi | 810.9 mi |
| ipwho.is | 485 | 100 | **58.4** | 9.3 | 59.5 mi | 834.5 mi |
| IP2Location DB11 | 485 | 100 | **54.8** | 7.0 | 74.4 mi | 972.2 mi |
| proxycheck.io | 200 | 100 | **53.5** | 6.5 | 78.5 mi | 821.2 mi |
| iCloud Private Relay | 28 | 100 | 0.0 | 0.0 | — | — |

Vendors claim ~98% state accuracy. Measuring 55% would be an extraordinary result — so it was
tested before being believed.

### The diagnostic

> **Two independent vendors agree with *each other* on state 93.2% of the time,
> but with the "truth" only ~58% of the time.**

If the truth were the user's location, independent vendors could not agree with each other and
simultaneously disagree with the truth at that rate. They are measuring the same real thing — where
the connection is — and the lead address is measuring something else.

It is not a mobile-geolocation artefact either. The sample is mostly fixed residential broadband:
Comcast 26, Charter 39, Verizon 24, AT&T 22, Cox 7 — T-Mobile only 12.

### The most likely explanation

These are real-estate / home-offer leads. `uct_leads.address_line_1` is almost certainly **the
property the lead is about, not where the person was sitting**. Someone in Florida can request an
offer on a house in Missouri. `revenue_leads_plus` carrying `property_uuid` supports this.

### Consequence

**The geo accuracy numbers above must not be published.** Shipping them would have the console
assert that IP2Location is 55% accurate, which is not a finding about IP2Location — it is an
artefact of comparing a connection location to a property address.

Everything else built here stands. The pipeline, the tables, the scoring queries and the UI design
are all correct; only the truth column is in question.

### What unblocks it

1. **Confirm with the business what `uct_leads.address_line_1` represents.** One conversation.
   If it is the property, this truth source is unusable for geo accuracy — full stop.
2. **Find a user-location truth.** Candidates: billing address distinct from property, browser
   geolocation, form-prepop location, phone area code (coarse but independent), or a delivery
   address on a converted sale.
3. **Until then, report agreement, not accuracy.** Vendor-vs-vendor consensus is publishable and
   genuinely useful — it identifies outliers — as long as it is labelled *agreement* and never
   *accuracy*.

---

## 3. Findings that hold regardless

These do not depend on the disputed truth column.

- **28 of 485 qualified-lead IPs (5.8%) are iCloud Private Relay.** Apple's published egress list
  matched them exactly. Any vendor calling these a proxy is technically right; blocking them costs
  real qualified leads. This is now measurable rather than anecdotal.
- **Vendors disagree with each other far more than their marketing implies.** 93.2% state agreement
  between two vendors means ~1 in 14 IPs gets a different state depending on who you ask. On ZIP the
  spread is much wider.
- **A worked example.** `172.59.171.92` (T-Mobile): proxycheck says Maryland Heights 63043,
  ipwho.is says St. Louis 63103, ipinfo says St. Louis 63101. Three sources, three ZIPs.
- **The ProxyCheck API key is not being honoured.** The API replied
  *"100 queries exhausted, if you sign up for a free API key you'll be able to make 1,000 free
  queries per day"* — it is treating the requests as anonymous, and the usage endpoint returns
  `"No usage Found."`. Only 200 of 485 completed. **Verify the key in the ProxyCheck dashboard
  before buying the $5.99 plan.**
- **ipwho.is free tier returns no `security` block**, so it is a geo source only, not a proxy source.

---

## 4. Cost

The entire run — 8 sources, 485 IPs, all tables, all scoring — cost roughly **$0.02** in Athena
scans and nothing in API fees. The narrow-and-deep approach is essentially free to repeat, which
means re-running it against a corrected truth source costs an afternoon, not a budget.
