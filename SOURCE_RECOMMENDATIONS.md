# Which Sources to Use, and Why

**Date:** 2026-09-05 · **Evidence:** 511 IPs, 11 sources, run `run-2026-09-04-02`
**Purpose:** a report-ready explanation of the recommendations and exactly how every number
behind them was produced.

---

## 1. The short answer

| Need | Use | Why |
|---|---|---|
| **Geolocation, bulk (millions of IPs)** | **IP2Location LITE DB11** | Only free source that scales. Downloadable file, no API limit, 100% fill on state/city/ZIP, 3rd on consensus (72.2) |
| **Geolocation, per-lookup accuracy** | **ipinfo.io** | Highest consensus agreement (84.8), 100% fill, free 50k/month |
| **Geolocation, hardest cases** | **MaxMind GeoLite2** | The only source right where we have *real* ground truth |
| **Proxy / VPN / bot detection** | **proxycheck.io** | 90.9% precision, 100% recall, 100% coverage, free 1,000/day |
| **Do not rely on** | IP2Proxy PX12 | Answered **1 of 511** |

---

## 2. Why ipinfo.io for geolocation

It ranks first on the consensus scorecard:

| Source | Fill rate | Agreement | **Score** |
|---|---:|---:|---:|
| **ipinfo.io** | 100% | 84.8% | **84.8** |
| ipwho.is | 100% | 79.7% | **79.7** |
| IP2Location DB11 | 100% | 72.2% | **72.2** |
| proxycheck.io | 97.0% | 70.3% | **68.2** |
| MaxMind GeoLite2 | 96.9% | 61.8% | **59.9** |
| DB-IP combined | 66.7% | 74.8% | **49.9** |

Three reasons it wins:

1. **It answers every time.** 100% fill on state, city *and* ZIP across all 511 IPs. DB-IP scores
   66.7% because it publishes no postal code at all.
2. **It agrees with the majority most often** — 95.7% on state, 76.8% on city, 81.3% on ZIP. Its
   ZIP agreement is far ahead of everyone else's.
3. **It is free at the volume most lookups need** — 50,000/month with a token.

### ⚠️ But read this before quoting that ranking

**Agreement is not accuracy.** Consensus measures how often a source matches the crowd. If several
sources license the same upstream data, the "crowd" is that upstream vendor's opinion.

We have real ground truth on exactly 30 IPs — Apple publishes the city for every iCloud Private
Relay egress range, which is the operator's own statement, not an inference. On those:

| Source | On `146.75.164.0` |
|---|---|
| **Apple (authoritative)** | **Dallas, TX** |
| MaxMind · ipinfo · ipwho.is | Dallas, TX ✅ |
| **IP2Location DB11** | **Mexico City, Mexico** ❌ wrong country |

**MaxMind ranks 1st against real truth but 5th on consensus.** It disagrees with the crowd more
often — and where we can check, it is the one that is right. Consensus rewards conformity.

So: ipinfo for the best general answer, MaxMind when being right on unusual traffic matters more
than agreeing with everyone.

---

## 3. Why IP2Location LITE DB11 is the right fallback — and often the better primary

**At your real scale it is not a fallback, it is the only option.**

You have 4.9M unique IPs. ipinfo's free tier is 50k/month — enriching your universe once would take
**eight years**. IP2Location DB11 is a downloadable file: no API, no rate limit, no per-call cost,
and you already run it over all 4.9M IPs today.

| | IP2Location DB11 | ipinfo.io |
|---|---|---|
| Consensus score | 72.2 | 84.8 |
| Fill rate | 100% | 100% |
| Volume limit | **none — local file** | 50k/month |
| Cost at 4.9M IPs | **$0** | not feasible on free tier |
| Refresh | monthly download | live |

It ranks 3rd of seven and is only 12.6 points behind the leader — while being the only source that
can answer for every IP you own, instantly, at zero marginal cost.

**And it already earns its place on business value:** DB11 fills geolocation for **644,539 session
IPs that have none today** — IPs carrying **$7,074,034**, or 44% of all attributed revenue.

Its one weakness is unusual infrastructure — it placed a Dallas relay IP in Mexico City. So the
sensible architecture is: **DB11 for bulk enrichment, ipinfo or MaxMind for the disputed minority.**

---

## 4. Why proxycheck.io for proxy and bot detection

It is not close.

| Source | Coverage | Flagged | Precision | Recall | F1 | **Score** |
|---|---:|---:|---:|---:|---:|---:|
| **proxycheck.io** | 511/511 | 33 | **90.9%** | **100%** | **95.2** | **95.2** |
| FraudLogix (TUNE) | 249/511 | 84 | 9.5% | 27.6% | 14.2 | **6.9** |
| IP2Proxy PX12 | **1/511** | 1 | 0% | 0% | — | — |

**proxycheck caught all 30 known-infrastructure IPs with only 3 extra flags.** Perfect recall,
90.9% precision, and it answered for every IP in the sample. It is free at 1,000 lookups/day, and
because batch POST accepts 100 IPs per request it barely touches that quota — 511 IPs cost
effectively nothing.

**IP2Proxy LITE PX12 should not be relied on.** It answered 1 IP out of 511. Critically, it is *not*
saying the other 510 are clean — it has no opinion. Absence is recorded as `has_answer = false`,
never as a clean verdict, because treating silence as "clean" is how a proxy becomes a customer.

### Be fair to FraudLogix

Its 9.5% precision looks damning but is **not** evidence it is wrong. proxycheck detects
*infrastructure* — datacenters, VPNs, relays — which is exactly what the published ranges contain.
FraudLogix mostly detects *behaviour* — bots, abnormal traffic patterns, masked devices — which by
definition never appears on an infrastructure list.

Its score means **unverifiable by this method**, not inaccurate. The two are complementary, not
competing: use proxycheck for infrastructure, FraudLogix for behaviour.

---

## 5. Exactly how every number is calculated

### 5.1 The population

511 IPs. Not a sample — it is every IP where a location exists that did **not** come from an IP
lookup, reached via:

```
sampledb.revenue_leads_plus  →(email)→  unified.uct_leads
                             →(alyson_session_id)→  unified_session_summary.session_ip
```

### 5.2 Fill rate — "how often does it answer?"

```
fill_rate = (state_filled + city_filled + zip_filled) / (3 × 511)
```

A field a source never publishes counts as **unfilled, never wrong**. DB-IP Lite has no postal code,
so its ZIP is "not supplied" — showing 0% would call it inaccurate when it simply does not answer.

### 5.3 Consensus — "what does the majority say?"

1. Compute the **pairwise agreement matrix**: all 21 source pairs × 4 fields (state, city, ZIP,
   lat/lon), agreement measured only on IPs where *both* sources answered.
2. **Collapse duplicates.** Any pair agreeing ≥99.5% on lat/lon becomes **one voter**. geojs.io is
   byte-identical to MaxMind on all 511 IPs, so it is scored but does not vote. Without this,
   MaxMind would vote twice and consensus would just measure who has the most mirrors. → **6 voters
   from 7 sources.**
3. For each IP and field, the **consensus** is the majority value, requiring at least 2 votes.

### 5.4 Agreement and score

```
agreement = (state_hit + city_hit + zip_hit) / (state_judged + city_judged + zip_judged)
score     = agreement × fill_rate
```

Multiplicative deliberately: a source must be **both present and consistent**. One that answers 20%
of the time and is always right is not more useful than one that always answers and is right 90% of
the time.

### 5.5 Risk — precision, not detection rate

Detection rate is meaningless alone: flag everything and you score 100%. Instead each flag is
checked against **operator-published ranges** — Tor exits, AWS, Google Cloud, Cloudflare, Fastly,
Apple iCloud Relay. Those are facts, not vendor opinions.

```
precision = flagged ∩ known_infrastructure / flagged
recall    = flagged ∩ known_infrastructure / known_infrastructure
f1        = 2 · precision · recall / (precision + recall)
score     = f1 × fill_rate
```

### 5.6 Where the numbers live

| Table | Contents |
|---|---|
| `ipintel_analytics.pairwise_agreement` | 21 rows — the raw brute-force evidence |
| `ipintel_analytics.geo_score` | fill, agreement, composite per source |
| `ipintel_analytics.risk_score` | precision, recall, F1, composite per source |
| `ipintel_curated.ip_geo_observations` | every location claim, one row per IP × source |
| `ipintel_curated.ip_proxy_check` | every risk claim, one row per IP × source |
| `ipintel_curated.lead_truth` | the 511-IP truth set |

API: `GET /summary` returns all three scorecards plus the explanation text. Every figure in this
document is reproducible from those tables.

---

## 6. Caveats that must travel with any report

1. **"Agreement", never "accuracy".** The location column measures conformity with the majority.
   Real accuracy exists only on Apple's 30 relay IPs.
2. **The location truth is the property, not the person.** `revenue_leads_plus` is a property
   record. Restricting to the 140 phone-verified leads gives 64.0% state match versus 64.3%
   overall — cleaner records do not help, which proves the gap is not data quality. The metric is
   therefore **IP-to-property distance**, a lead-quality signal, not a vendor scorecard.
3. **FraudLogix's low precision means unverifiable, not wrong.**
4. **No answer is not a clean verdict.** PX12's silence on 510 IPs says nothing about them.
5. **Sample size 511** — roughly ±4.4% at 95% confidence. Sources within ~9 points of each other
   are not reliably separable. ipinfo (84.8) versus ipwho.is (79.7) is inside that band; ipinfo
   versus MaxMind (59.9) is not.
6. **Two sources are one database.** geojs.io ≡ MaxMind. DB-IP and proxycheck agree on 88.6% of
   lat/lon, suggesting shared upstream data — below the collapse threshold, but worth watching.

---

## 7. What would change these conclusions

- **A user-location truth source.** 552 of 4.9M IPs is 0.011% coverage, and the truth we have is
  the wrong thing. This is worth more than ten additional vendors.
- **vpnapi.io** — free, 1,000/day, needs a signup key. Risk scoring currently rests on two voters;
  a third would materially strengthen it.
- **A paid tier.** proxycheck at $5.99/month lifts the daily cap; MaxMind and ipinfo both sell
  higher-accuracy commercial databases. Nothing here has been tested against a paid product.
