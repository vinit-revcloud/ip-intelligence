# Truth Source Correction — Map and Fix Plan

**Date:** 2026-09-03
**Trigger:** the benchmark used `unified.uct_leads`; the correct table is `sampledb.revenue_leads_plus`.

**Short version: this is contained.** It touches one table and everything downstream of it —
a few hours of work, not a rebuild. The whole 4.9M-IP foundation is unaffected. And the new table
answers the open question that was blocking us, though not in the direction we hoped.

---

## 1. What actually breaks

| Layer | Affected? | Why |
|---|---|---|
| `ip_list`, `ip_dim`, `db11_bucketed`, `px12_bucketed`, `ip_flags`, `ip_business_outcome`, `ip_vendor_result` | ❌ **No** | Dataset A never touched leads. All 4.9M-IP work stands, all validation gates still hold |
| `lead_truth` | ✅ Rebuild | Wrong source table |
| `geo_accuracy` | ✅ Recompute | Scored against the wrong truth |
| `ip_geo_observations`, `ip_proxy_check` | ⚠️ Extend | Need 31 more IPs enriched; existing 485 stay valid |
| `findings.json`, `console.json` | ✅ Rebuild | Downstream of the above |
| Lovable UI | ❌ No code change | It renders whatever the API returns |

**Nothing measured about the vendors is invalidated.** Vendor-vs-vendor agreement, source
independence, PX12 coverage, the iCloud relay finding and the Apple ground-truth proof are all
independent of which lead table we used. Only the *location accuracy scoring* changes.

---

## 2. The join path — measured, not assumed

`revenue_leads_plus` has **no session id and no IP column**. I tested every candidate:

| Path | Result |
|---|---|
| `revenue_leads_plus.user_id` ↔ `unified_session_summary.user_id` | ❌ 2,862 vs 49 distinct values, **0 overlap** |
| `raw_tune_clicks` → leads | ❌ no email or lead identifier on the clicks table |
| **`revenue_leads_plus.email` ↔ `uct_leads.email` → `alyson_session_id` → session → IP** | ✅ **works** — 1,556 of 2,394 emails match |

So `uct_leads` does not disappear. **It stays as the bridge to an IP; `revenue_leads_plus` replaces
it as the source of truth values.** That is the whole correction.

```
sampledb.revenue_leads_plus     ← truth: address, zip, city, MSA, phone_verified, qualification
        │  join on email
        ▼
unified.uct_leads               ← bridge only: alyson_session_id
        │
        ▼
unified.unified_session_summary ← session_ip
```

---

## 3. What improves

The IP pool barely moves, because it is capped by the `uct_leads` bridge (632 distinct sessions).
The **truth quality** improves a lot.

| Truth field | Old (`uct_leads`) | New (`revenue_leads_plus`) | Change |
|---|---:|---:|---|
| IPs with state + ZIP | 485 | **516** | +31 |
| IPs with **city** | 54 | **298** | **5.5× more** |
| IPs with **metro (MSA)** | 0 | **344** | new dimension |
| IPs **phone-verified** | 0 | **146** | new, and a much stronger truth tier |
| IPs intro-qualified | — | 137 | real qualification |
| IPs talked-to-client | — | 330 | real qualification |
| IPs that became deals | — | 137 | real outcome |

Three of these matter a lot:

- **City accuracy becomes measurable.** 298 IPs instead of 54. City is where vendors actually
  differ, so this is the most useful column in the whole benchmark.
- **Metro accuracy becomes measurable**, and `msa_name` is supplied directly — no ZIP→CBSA
  crosswalk needed.
- **A phone-verified tier of 146 IPs.** These are leads someone actually spoke to, so the record is
  far less likely to be junk. Report the benchmark on all 516 *and* on this subset; if the two
  disagree, the difference is data quality.

---

## 4. The blocking question is now answered — and the answer is "no"

`revenue_leads_plus` carries `property_type`, `property_use`, `sell_reason`, `already_has_agent`,
`msa_name`, `price`, `property_uuid`.

**This is unambiguously a property record.** The address is the house being sold, not where the
person was sitting when they filled the form. That confirms the hypothesis from the first
benchmark — two vendors agreeing with each other 93.2% but with the address only ~59%.

### What that means

❌ **This truth source cannot measure vendor geolocation accuracy.** No amount of switching tables
fixes that; the column is measuring a different thing. Reporting "IP2Location is 55% accurate" would
be wrong no matter which lead table it came from.

✅ **But it measures something the business actually cares about:** *does the visitor's IP location
match the property they are enquiring about?* For a real-estate lead business that is a genuine
signal — a large mismatch may indicate an out-of-area enquiry, a broker, or fraud. It is a **fraud
and lead-quality metric**, not a vendor scorecard.

So the metric gets renamed rather than deleted: **"IP-to-property distance"**, not "location
accuracy".

### Vendor accuracy still has one valid anchor

Apple's published iCloud Private Relay city, on 28 IPs. That is the operator's own statement and it
already caught IP2Location placing a Dallas IP in Mexico City. Small, but real. Everything else
stays labelled **disagreement**.

---

## 5. The fix, in order

| # | Step | Effort |
|---|---|---|
| 1 | Rebuild `lead_truth` from `revenue_leads_plus` via the email bridge; keep `uct_leads` for `alyson_session_id` only | 30 min |
| 2 | Add `truth_city`, `truth_msa`, `phone_verified`, `is_intro_qualified`, `talked_to_client`, `is_deal` | included |
| 3 | Enrich the 31 new IPs across all sources (existing 485 unchanged) | 15 min |
| 4 | Rebuild `geo_accuracy` on 516, adding **city match %** and **metro match %** | 30 min |
| 5 | Add a second scorecard restricted to the 146 phone-verified IPs | 20 min |
| 6 | Rename the metric to *IP-to-property distance*; keep vendor accuracy scoped to the 28 Apple IPs | 15 min |
| 7 | Rebuild `findings.json` + `console.json`, upload | 10 min |
| 8 | Update `AWS_BUILD_LOG.md` §7, §8.1 and §13 | 20 min |

**No Lovable change is required** — the UI reads whatever the API returns. The only visible edit is
the table heading and the caveat text, both of which already come from the API.

Total: roughly half a day, about $0.05 in Athena.

---

## 6. What this does not fix

**The pool is still ~552 IPs, capped by the `uct_leads` bridge**, which holds only 632 distinct
sessions. `revenue_leads_plus` has 14,966,619 leads and we can reach 552 of them. That is
**0.0037%**.

So the highest-value remaining question is unchanged and now sharper:

> **Is there any table that carries both an IP (or a session id) and a lead identifier, other than
> `uct_leads`?**

If one exists, the benchmark could jump from hundreds to hundreds of thousands of IPs, and every
number in it would get sharper. That single question is worth more than adding ten more vendors.

Worth asking whoever owns the lead pipeline directly, because it is not discoverable from the
catalog — I checked `unified`, `raw` and `optimized` and found no other table carrying both.
