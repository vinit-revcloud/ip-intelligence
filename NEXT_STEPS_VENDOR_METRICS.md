# Next Steps — Qualified-Lead Pool and Vendor Metrics

**Date:** 2026-09-08
**Trigger:** the `utm_content` join and the `furthest_stage` qualified-lead definition.

---

## 1. Your join is better than mine — the pool quadruples

I tested `s.session_id = trim(r.utm_content)` against the 11 qualified stages:

| | Count |
|---|---:|
| Qualified leads (`furthest_stage` in your 11 values) | 1,579,163 |
| Distinct `utm_content` values | 911,053 |
| …that match a `session_id` | **2,442** |
| **Distinct IPs** | **2,071** |
| …with state + ZIP | 2,067 |
| …with city | **1,816** |

**The pool goes from 511 to 2,071 — 4×.** City truth goes from 284 to 1,816, a 6.4× increase, and
city is where vendors actually differ.

### The part that matters most

> **Only 49 of the 2,071 IPs overlap with the current 511.**

The old pool came through `uct_leads` by email; this one comes through `utm_content` from qualified
leads. They are almost entirely *different traffic*. This is not an extension of the existing
benchmark — it largely replaces it, and every published number will move.

**2,022 IPs need enriching.** All eleven sources can cover that: the file-based ones are local
scans, and proxycheck's batch POST of 100 IPs/request barely touches the 1,000/day free cap.

### One caveat to check with the business

Only 2,442 of 911,053 `utm_content` values match a `session_id` — a 0.27% match rate. Either
`utm_content` carries a session id for only some traffic sources, or `unified_session_summary` has a
shorter retention window than the lead history. Worth one question to whoever owns the lead
pipeline, because if it is retention, a wider window could grow this pool a lot further.

---

## 2. The metrics — and one that cannot be computed

### Geo: fill rate · agreement · cost

| Column | Definition | Status |
|---|---|---|
| `fill_rate_pct` | non-null answers ÷ (3 × pool), across state/city/ZIP | ✅ built |
| `agreement_pct` | matches the majority of independent voters, on fields it answered | ✅ built, **rename from accuracy** |
| `cost_per_1k` | vendor cost per 1,000 lookups | ⬜ new column |
| `score` | `agreement × fill_rate` | ✅ built, to be written into the unified table |

Cost will be **$0.00 for every source currently enabled** — they are all free tier. The only
non-zero figure available is proxycheck at $5.99/month. The column is still worth having: it makes
"free" explicit rather than assumed, and it is where a paid tier would show up.

### Proxy: cost · agreement · bot identification · FPR · precision · recall

| Column | Definition | Status |
|---|---|---|
| `bot_identification_pct` | flagged as bot ÷ answered | ✅ computable |
| `false_positive_rate_pct` | **flagged as bot ÷ pool, where every IP in the pool is a qualified lead** | ✅ computable, and exact |
| `precision_infra_pct` | flags landing on operator-published ranges ÷ all flags | ✅ built |
| `recall_infra_pct` | published-range IPs caught ÷ all published-range IPs | ✅ built |
| `precision_bot_pct` | bots correctly caught ÷ all called bot | 🛑 **not computable — see below** |
| `recall_bot_pct` | bots correctly caught ÷ all actual bots | 🛑 **not computable — see below** |

### 🛑 Why bot precision and recall cannot be computed on this pool

Your definitions are the right ones. The problem is the pool.

**Every IP in it produced a qualified lead** — someone was introduced, spoke to an agent, scheduled
a meeting, listed a property or closed. By construction, **the pool contains no bots.**

That has two consequences:

- **False-positive rate is exact and excellent.** Any bot flag on a qualified-lead IP is definitely
  wrong. Right now FraudLogix flags **332 of the 2,071** as bot family — a **16.0% false-positive
  rate** against confirmed humans. That is a real, defensible, damning number.
- **Recall is undefined.** Recall needs *actual bots*, and there are none here. Dividing by zero
  true positives gives nothing. The same applies to bot precision: with no true positives, precision
  is 0 by construction for every vendor, which measures nothing.

**To get bot precision and recall you need a second pool containing known bots.** Options, roughly
in order of effort:

1. **Sessions with `is_bot_click = true`** in `unified_session_summary` — an incumbent's label, so
   it measures agreement with that incumbent, not truth. Weak but available today.
2. **IPs on operator-published ranges** — Tor exits, cloud egress. Definitely non-human traffic,
   already loaded. Narrow, but it is fact. This is what the current precision/recall measures.
3. **A labelled fraud set** from whoever adjudicates chargebacks or invalid traffic. Strongest, and
   it does not exist yet.

**Recommendation:** ship FPR now against the qualified-lead pool, keep infrastructure precision and
recall as they are, and label the bot precision/recall columns **"needs a bot-labelled pool"**
rather than printing a misleading 0. Add them the moment option 3 exists.

---

## 3. Rename: Accuracy → Agreement

Everywhere — API fields, table columns, UI headers, docs. The reason is already recorded: MaxMind
ranks 1st against Apple's real ground truth but 5th on consensus, because consensus rewards
conformity. Calling that "accuracy" asserts something the data does not support.

Affected: `row_agreement_pct` (already correct), `agreement_pct`, `state_matches_consensus` group,
`row_accuracy_pct` on `ip_intelligence` → `row_agreement_pct`, and every UI label.

The two places that keep the word *accuracy* legitimately: precision/recall against published
ranges, and the 30 Apple-verified IPs. Those are measured against fact.

---

## 4. Ordered next steps

| # | Step | Effort | Blocked by |
|---|---|---|---|
| 1 | Rebuild `lead_truth` from `utm_content` + `furthest_stage` — 2,071 IPs | 30 min | — |
| 2 | Enrich the 2,022 new IPs across all 11 sources | ~1 hr | — |
| 3 | Add `cost_per_1k` to the source registry; seed $0.00 and proxycheck's $5.99/mo | 20 min | — |
| 4 | Rebuild `pairwise_agreement`, `geo_score`, `risk_score` on the new pool | 30 min | 1–2 |
| 5 | Add metric columns to both unified tables, including `score` per row | 45 min | 4 |
| 6 | Add `false_positive_rate_pct` from the qualified-lead pool | 20 min | 1 |
| 7 | Rename accuracy → agreement across API, tables and docs | 30 min | — |
| 8 | New `/raw` endpoint + UI screen showing unfiltered rows with filters and CSV export | 45 min | 5 |
| 9 | One Lovable prompt covering the rename, the new columns and the raw-data screen | — | 7–8 |

Steps 1–7 are backend and need no decisions from you. Step 2 is the long pole and costs nothing —
every source is free tier.

---

## 5. What I need from you

1. **Confirm the pool switch.** 2,071 qualified-lead IPs replacing 511, with only 49 in common.
   Every published figure changes. I think it is clearly right — qualified leads are a better
   population and 4× the size — but it is your call, not mine.
2. **Bot ground truth.** Is there a labelled bot or invalid-traffic set anywhere? Without one, bot
   precision and recall stay uncomputable no matter how many vendors we add.
3. **The 0.27% `utm_content` match rate** — worth asking the lead-pipeline owner whether that is a
   traffic-source limitation or a retention window.
