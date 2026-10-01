# IP Intelligence: final project summary

**Status:** complete and running on its own (verified 21 Sep 2026).
**Owner's requirements:** `CLAUDE.md` (the master copy).

Each section below is one presentation slide. Every number is from a verified check on the live tables, with its date.

---

## 1. The goal

Make the company's two IP tables a **reliable, fully enriched source**, so that:
- every IP that visits us has location and a proxy / VPN / bot answer;
- the tables grow and stay correct on their own, every day;
- they can power reporting today and a SaaS product later.

**The two tables:**
- `unified.ip_geo`: location;
- `unified.ip_intelligence`: risk, one row per IP per source.

---

## 2. What was delivered

| Area | Result |
|---|---|
| **Coverage** | Every public IP from our 3 traffic sources is in both tables: **4,989,853 IPs** (19 Sep) |
| **Reliable answer for every IP** | **0 public IPs unresolved**: each has a FraudLogix decision or a proxycheck.io answer (IP2Proxy alone never counts) |
| **proxycheck.io for every IP** | **4,989,792 of 4,989,853** after the step 3 backfill (up from 757k). The rest were new arrivals, answered at the next daily load |
| **Every column filled** | 0 empty core flags, 0 empty `is_bot`, 0 empty flag or reason columns on answered rows |
| **Bad-signal standard (step 2)** | `is_bot` = any bad signal, with the reason in `bot_reason`: **854,527 bad IPs** (19 Sep) |
| **New columns** | `is_flagged`, `flagged_reason`, `bot_reason` in `unified.ip_intelligence` |
| **Runs by itself** | New and returning IPs are added and updated daily, checked, then published |
| **Size** | 14,513,895 intelligence rows · 9,990,828 location rows (19 Sep) |

---

## 3. Where the data comes from

**Traffic sources** (all read only; IPs as of 21 Sep):

| Source | Table | IPs |
|---|---|---|
| TUNE clicks | `raw.raw_tune_clicks` | 4,534,331 |
| Website sessions | `unified.unified_session_summary` | 2,015,840 |
| Experiment router | `experimentation_tools.experiment_router_events` (added 18 Sep) | 129,643 |

**IP-intelligence vendors:**

| Vendor | Gives | Role |
|---|---|---|
| **FraudLogix** (via TUNE) | Decision + reason per click | Reliable, stand-alone. Its decisions are never overwritten |
| **proxycheck.io** | Proxy / VPN / type, ISP, ASN, risk, location | Reliable. Answers every IP and fills gaps |
| **IP2Location DB11** | Location | Downloaded database |
| **IP2Proxy PX12** | Known-proxy list | Supporting evidence only |

---

## 4. How it works every day (IST)

| Time | Step |
|---|---|
| **13:00** | **Daily load:** reads everything new in the 3 sources. New IPs are **appended**; returning IPs are **updated** (latest answer wins) |
| **~13:15** | **proxycheck.io:** answers every new or unresolved IP. Partial answers are combined, and proxycheck.io's own row is kept for vendor comparison |
| **~13:30–14:00** | **Checks, then publish:** about 19 automatic checks. Only a run whose checks all pass refreshes the unified tables and the app's data files |
| **05:45** | Second proxycheck.io run (after the 05:30 IST quota reset) |

**The rules applied to every IP:**
1. **Latest timestamp wins.** For FraudLogix clicks at the exact same second, FLAGGED wins, and the pick is the same every run.
2. **Complete answer** from its source: stored as is.
3. **Partial answer:** gaps are filled from proxycheck.io; FraudLogix's own values always stay.
4. **No answer:** proxycheck.io resolves it.
5. **Unresolved IPs of any age** are queued and resolved automatically.
6. **proxycheck.io answers older than 30 days** are re-checked when the IP returns.

**Proof it works:**

| Day | Daily load | New IPs | proxycheck.io | Unified refresh |
|---|---|---|---|---|
| 20 Sep | 19/19 checks | 526 | all answered the same day | every run 7/7 |
| 21 Sep | 19/19 checks | 416 | all answered the same day | every run 7/7 |

---

## 5. The bad-signal standard (step 2)

An IP is **bad** when **FraudLogix's latest decision is FLAGGED for any reason**, or **proxycheck.io reports a bad signal**:
- **FraudLogix reasons:** proxy, VPN, abnormal traffic, basic fraud, masked devices, bots, scripts, spoofing, datacenter, TOR…;
- **proxycheck.io signals:** proxy, VPN, TOR, datacenter, compromised server, scraper, cloud network, or risk 67+.

It is **clean** when a source answered and neither says bad. There is no "suspicious" tier.

Each bad row says **why** (`bot_reason`), e.g. `BOT_GENERATED`, `SOCKS5`, `CLOUD_ASN:AS16509`.

**Checked against real customers** (1,044 paying IPs, 40 known fake-lead IPs):

| Measure | Result |
|---|---|
| Paying IPs marked bad (all reasons) | 535 (51%): mostly VPN / proxy users, e.g. iCloud Private Relay |
| Paying IPs marked bad, excluding VPN/proxy-only | at most 49 (≈5%) |
| Fake-lead IPs marked bad | 24 of 40 (60%) |

**Takeaway:** the standard catches bad signals broadly. Filter on `bot_reason` (e.g. exclude VPN/proxy-only) to decide what to act on.

---

## 6. What our traffic looks like (last 30 days: 20 Aug – 18 Sep)

| Metric | Value |
|---|---|
| Visits | 188,676 (sessions 103k · router 74k · clicks 11k) |
| Unique IPs | 81,910 (42,756 new) |
| Bad | 37.7%. By signal: automation 3.5% · behaviour 16.7% · VPN/proxy 17.5% |
| Bad excluding VPN/proxy-only | 20.2% |
| Worst source | TUNE clicks: 55.8% bad |
| Network | 35% mobile · 20% proxy · 7.5% VPN · 1.7% cloud |

**Honest finding:**
- **Bad-flagged sessions converted better, not worse:** 1.89% lead rate vs 0.98% for clean, and $79.50 vs $24.73 revenue per 1,000 visits.
- **What it means:** these flags mark *infrastructure* (VPNs, mobile carriers, proxies) that many real customers use. They are not a measure of whether a visitor converts.

---

## 7. Reliability and safety

**Guarantees:**
- **Checks before publish:** no duplicates, no unanswered IPs, every bad row has a reason, and `is_bot` = `is_flagged`.
- **Failures are contained:** a failed run never replaces good data. The previous version keeps serving.
- **Rollback:** snapshots for every table change, and a code backup before every deploy (`archive/`).
- **Production untouched:**
  - source tables are read only;
  - Athena runs only in the `ipintel_etl` workgroup;
  - AWS access only through the `ipintel-builder` role;
  - keys stay in Secrets Manager.
- **Audit:** every job run checks AWS activity; any write outside the project is flagged (none so far).
- **Full mapping check** (21 Sep): every source IP is mapped, first/last seen are correct, FraudLogix rows match the latest click, and every public IP is in both tables with a reliable verdict. **0 exceptions.**

**Problems found and fixed on the way:**

| Problem | Fix |
|---|---|
| Backfill merge ran out of memory (500k answers at once) | Processes one batch at a time (135 MB instead of 1 GB+) |
| Daily load timed out on a long audit | Audit is incremental, oldest first, and saves progress |
| Same-second FraudLogix clicks gave a random answer (182 IPs) | Fixed tie-break (FLAGGED first); 84 rows corrected |
| IP2Proxy multi-value types misread | Each part is matched; 2 rows corrected |
| Re-reading FraudLogix emptied filled columns | Filled columns are kept |
| Old unresolved IPs could slip through | Queued every day; the check covers all IPs |

---

## 8. Cost and budget

| Item | Now | Next |
|---|---|---|
| proxycheck.io plan | $199.99/month, 5.12M queries/day (this month) | Owner switches to the **$10 plan** next month |
| Enrichment budget | No cap this month; **30,000/day reserved** for the owner | Needs the owner's split before the switch, **or enrichment stops** (the 30k reserve comes first) |
| Daily use after the backfill | ~420–530 queries/day (new IPs only) | Fits a small plan |

---

## 9. Product and app

| Deliverable | File |
|---|---|
| SaaS blueprint: architecture, analytics catalogue, API, pricing proposal, roadmap, risks | `SAAS_PRODUCT_BLUEPRINT.md` |
| App prompts: Knowledge + 7 prompts (Alyson brand, dashboards, lookup, trust pages, SaaS shell) | `LOVABLE_PROMPT_SAAS.md` |
| Landing-page prompts and assets (`landing-assets/`) | `LOVABLE_PROMPT_LANDING.md` |
| Daily app data, including `traffic_analytics.json` and `bad_signals.json` | S3 `ip-intelligence/serving/app/`, and `app-data/` locally |

**Before any external sale:** vendor-licence check (resale of vendor data) and privacy (policy, DPA).

---

## 10. Open items (handover)

| # | Item | Owner |
|---|---|---|
| 1 | Tell us the $10 plan's daily limit and the split **before switching** | Owner |
| 2 | Admin requests in `ADMIN_DELETION_STEPS.md`: delete the retired API / role / 5 benchmark tables; create the app's read-only S3 key | Owner → AWS admin |
| 3 | Build the Lovable app and landing page from the prompt files | Owner |
| 4 | Optional: remove the 15 dropped legacy tables' S3 folders (after 23 Sep, with go-ahead) | Owner |
| 5 | Optional: a faster than daily load (needs an admin to add a schedule) | Owner |

---

## 11. Where to find everything

| Need | File |
|---|---|
| All requirements (master) | `CLAUDE.md` |
| How the system works, daily flow, adding a source | `docs/SYSTEM_GUIDE.md` |
| Rules and every column's meaning | `IS_BOT_MAPPING.md` |
| Step 2 research (source profiling) | `STEP2_BOT_PROFILING.md` |
| Checks to re-run any time | `build/pipeline/sql/checks/final_verification.sql`, `source_mapping_verification.sql` |
| Pipeline code | `build/pipeline/src/` |
