# Consensus Accuracy Scoring — Plan

**Date:** 2026-09-04
**Problem it solves:** we have no location ground truth (confirmed — the lead address is the
property). So vendors must be scored against **each other**, plus the small amount of real truth
we do have.

---

## 1. The two accuracy types

They are measured completely differently and must never be merged into one number.

### Type A — Location accuracy (consensus-based)

No truth, so the yardstick is what most independent sources agree on.

| Metric | Formula |
|---|---|
| **Fill rate** | non-null answers ÷ 511, per field (state, city, ZIP, lat/lon) |
| **Pairwise agreement** | for every pair, matches ÷ IPs where *both* answered |
| **Consensus value** | per IP per field, the majority answer across independent sources |
| **Agreement with consensus** | how often a source matches the majority, on IPs it answered |
| **Composite score** | `agreement_with_consensus × fill_rate` |

The composite is the ranking column. It is deliberately multiplicative: a source that answers 20%
of the time and is always right is not more useful than one that answers 100% of the time and is
right 90% of the time.

### Type B — Proxy/VPN detection (precision-based)

**Detection rate is not accuracy.** A source that flags every IP scores 100% detection and is
useless. So proxy is scored on precision against the only proxy truth that exists:

| Metric | Formula |
|---|---|
| **Fill rate** | IPs where the source returned any verdict ÷ 511 |
| **Detection rate** | flagged ÷ answered — *descriptive only, never ranked* |
| **Precision vs published ranges** | of the IPs it flagged, how many are on Tor / AWS / GCP / Cloudflare / Fastly / iCloud lists |
| **Recall vs published ranges** | of the IPs on those lists, how many it flagged |
| **False-positive rate** | flagged IPs that produced a qualified lead ÷ flagged |
| **Composite score** | `F1(precision, recall) × fill_rate` |

---

## 2. The trap that would break this — and the fix

> **Correlated sources double-vote.** geojs.io returns byte-identical values to MaxMind on all 511
> IPs. If both vote, MaxMind's opinion counts twice, and "consensus" becomes "whoever has the most
> mirrors".

**Fix: collapse before voting.** Any pair whose lat/lon agreement is ≥ 99.5% is one voter. geojs
and MaxMind become a single vote. The pairwise matrix is computed *first* and drives the collapse,
so it is data-driven, not a hardcoded list.

Two further honesty rules:

- **Never call this "accuracy".** It is *agreement with the majority*. If five of six sources
  license the same upstream data, the consensus is that upstream's opinion, not the truth. Column
  header must say **Agreement**.
- **Report the voter count.** A consensus over 3 independent voters is much weaker than over 6.
  Show `n_voters` beside every consensus figure.

---

## 3. Source roster changes

### Remove from the scorecard

| Source | Why |
|---|---|
| **authoritative_lists** | Not a vendor — it is a set of operator-published ranges. It cannot detect residential proxies, non-Apple VPNs or bots at all, so its 100% "answer rate" is an artefact of how I coded it. **It becomes the validator for Type B precision/recall, not a scored row.** |
| **icloud_private_relay** | Already moved to `truth_sources`. Stays as the geo ground truth for 30 IPs. |
| **geojs.io** | Keep as a row but mark **mirror of MaxMind**; excluded from voting. |

### Combine the three DB-IP files into one source

You have all three downloaded. Merged on IP range they give DB-IP a fuller record than any single
file:

| File | Columns | Adds |
|---|---|---|
| `dbip-city-lite` | start, end, continent, country, state, city, lat, lon | geo |
| `dbip-asn-lite` | start, end, asn, org | **ASN + ISP** |
| `dbip-country-lite` | start, end, country | country fallback |

Result: `dbip_combined` with country, state, city, lat, lon, ASN, org. Still no ZIP — DB-IP Lite
does not publish one, so its ZIP column stays "not supplied", never 0%.

### New sources

| Source | Status | Action |
|---|---|---|
| **vpnapi.io** | Free 1,000/day but **needs a free API key** — unauthenticated hits a Cloudflare challenge | Sign up at vpnapi.io, send me the key |
| **ipinfo.io privacy module** (proxy/VPN) | ❌ **Paid only** — `"Token not passed… please pass a valid token to access 'privacy' module"` | Exclude unless you buy it |
| ipinfo.io geolocation | ✅ already in | — |
| proxycheck.io | ✅ already in | — |
| geojs.io | ✅ in, but a MaxMind mirror | demote |
| DB-IP Lite | ✅ in, to be upgraded to combined | — |

**vpnapi.io is the valuable addition** — it is a genuine second proxy/VPN opinion, and Type B
currently has only two real voters (proxycheck and FraudLogix).

---

## 4. What the UI shows

### Explanation box (both Findings and Vendor Comparison)

A `Callout` above each scorecard, text supplied by the API so it can change without a redeploy:

> **How these scores are calculated.** There is no ground truth for IP location — the lead address
> is the property, not the person. So each source is compared against the majority answer of all
> *independent* sources. **Agreement** is how often a source matches that majority on IPs it
> answered. **Fill rate** is how often it answers at all. **Score** multiplies the two, so a source
> must be both right and present to rank well. Sources returning identical data are collapsed to a
> single vote — otherwise a mirrored database would win by voting twice.

For Type B the box reads:

> **Proxy scores are precision, not detection rate.** A source that flags everything would score
> 100% detection and be useless. Each flag is checked against operator-published ranges — Tor exit
> nodes, AWS, Google Cloud, Cloudflare, Fastly and Apple's iCloud Private Relay — which are facts,
> not opinions. Precision is how many flags land on those ranges; recall is how many of those
> ranges were caught.

### New columns — Location table

Source · Fill Rate % · Answered · **Agreement %** · n Voters · State Agree % · City Agree % ·
ZIP Agree % · Median Distance · **Score** · Independence

### New columns — Proxy table

Source · Fill Rate % · Answered · Detection % · **Precision %** · **Recall %** · F1 ·
False-Positive % · Revenue at Risk (excl. shared) · **Score**

### Granularity — the pairwise matrix

A `HeatMatrix` on Vendor Comparison: every source against every other, per field, showing
agreement % and the comparable-IP count in the cell tooltip. This is the "brute force" view — the
raw evidence behind every composite score, so nobody has to trust the aggregate.

---

## 5. Build steps

| # | Step | Notes |
|---|---|---|
| 1 | Load and merge the three DB-IP files into `dbip_combined` | range join on start/end; adds ASN + ISP |
| 2 | Add vpnapi.io adapter | blocked on the free API key |
| 3 | Build `ipintel_analytics.pairwise_agreement` | every source pair × field; the brute-force table |
| 4 | Derive independent voter groups from step 3 at the ≥99.5% threshold | data-driven, no hardcoded list |
| 5 | Build `consensus_value` — majority answer per IP per field over voter groups | store `n_voters` |
| 6 | Build `geo_score` — fill rate, agreement, composite | replaces `geo_accuracy` |
| 7 | Build `risk_score` — precision/recall vs published ranges, F1, composite | authoritative lists become the validator |
| 8 | Add `scoring_explanation` strings to the API payload | so the UI box is never hardcoded |
| 9 | Rebuild `findings.json` / `console.json`, one Lovable prompt | |

Steps 1 and 3–8 need no new credentials and can run now. Step 2 waits on the vpnapi.io key.

---

## 6. What this will and will not tell you

**Will:** which sources are internally consistent, which are mirrors of each other, which answer
most often, and which flags are verifiable against operator-published fact.

**Will not:** which source is *correct* about location. Consensus measures agreement, and agreement
with a crowd that shares upstream data is not truth. The only genuine location accuracy we have
remains Apple's 30 relay IPs — where IP2Location already placed a Dallas address in Mexico City.

That limit is not fixable by adding sources. It is fixable only by finding a user-location truth,
which is still the highest-value open item.
