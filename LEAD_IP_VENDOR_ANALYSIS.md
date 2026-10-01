# Lead-IP Vendor Analysis

One-time analysis, 16 Sep 2026. Read only: no table was changed.

## What was measured
- **Sessions:** `unified.unified_session_summary`, session dates 18 Jun – 9 Sep 2026. That is 90 to 7 days ago; the last 7 days are left out so revenue has time to appear. Private and reserved IPs are excluded.
- **Leads:** `sampledb.revenue_leads_plus`, joined on `utm_content = session_id`, with the lead created on or after the session date.
- **Lead IPs:** every IP with at least one such lead, **2,768 IPs and 3,235 leads**.
- **Label per IP:**
  - `expected_revenue` summed over its leads above 0 → **real person** (427 IPs).
  - Otherwise → **bot** (2,341 IPs), as in the MoM.
- **Vendors graded:**
  - FraudLogix, IP2Proxy and proxycheck.io (their answers in `ipintel_curated.ip_intelligence`).
  - The session table's own `ip_is_proxy` and `is_bot_click` fields.
  - Before running, the 834 lead IPs without a proxycheck.io answer were sent to proxycheck.io (834 queries), so it covers all of them.
- **Flagged** means any of proxy, VPN, Tor, datacenter, bot, compromised or scraper. "Bot" is the positive class.

## Vendor scorecard (any flag)

| Vendor | Answered | Flagged | TP | FP | TN | FN | **FPR** | **Accuracy** | Precision | Recall |
|---|---|---|---|---|---|---|---|---|---|---|
| FraudLogix | 2,326 (84%) | 898 | 822 | 76 | 264 | 1,164 | **22.4%** | **46.7%** | 91.5% | 41.4% |
| proxycheck.io | 2,768 (100%) | 528 | 389 | 139 | 288 | 1,952 | **32.6%** | **24.5%** | 73.7% | 16.6% |
| Session table | 2,768 (100%) | 580 | 426 | 154 | 273 | 1,915 | **36.1%** | **25.3%** | 73.4% | 18.2% |
| IP2Proxy | 14 (0.5%) | 14 | 14 | 0 | 0 | 0 | — | 100% (14 IPs) | 100% | 100% |

How to read the columns:
- **FPR:** of the real-person IPs a vendor answered, the share it flagged. Lower is better.
- **Accuracy:** the share of answered IPs where the flag matched the label.
- **IP2Proxy:** it only answers for proxies on its list, so it can't be judged on this sample.

## Bot flag only

| Vendor | Bot-flagged | FP | FPR | Precision | Recall |
|---|---|---|---|---|---|
| FraudLogix | 5 | 1 | 0.3% | 80.0% | 0.2% |
| Session table (`is_bot_click`) | 140 | 22 | 5.2% | 84.3% | 5.0% |

Almost nothing is flagged as a bot outright. Nearly all flags are proxy or VPN.

## Which lead stages decide it

| Lead category | IPs | With revenue | FraudLogix flags | proxycheck.io flags | Session table flags |
|---|---|---|---|---|---|
| listing | 2 | 1 (50%) | 0% | 50% | 50% |
| meeting | 67 | 57 (85%) | 29.8% | 40.3% | 44.8% |
| intro_qualified | 739 | 369 (50%) | 22.5% | 28.3% | 31.4% |
| below_intro | 1,960 | 0 (0%) | 44.6% | 14.8% | 16.2% |

Detail by furthest stage is in `lead_stage_signal.csv`.
- **Revenue only appears from intro_qualified onwards.** No below_intro IP had revenue. `connected` (70%) and `meeting_scheduled` (94%) are the strongest real-person stages.
- **FraudLogix tracks the stage best.** It flags 44.6% of below_intro IPs but 22–30% of intro_qualified and meeting IPs.
- **proxycheck.io and the session table flag the opposite way:** meeting IPs (40–45%) more than below_intro IPs (15–16%).
- **proxycheck.io's 139 false positives are almost all VPN (137).** They sit on Akamai (76), Fastly (36) and Cloudflare (24), which carry Apple iCloud Private Relay traffic. These are real customers using a privacy relay.

## FraudLogix flags on real people
**80 IPs** were flagged by FraudLogix although their lead earned revenue or reached a meeting or later (`fraudlogix_wrong_flags.csv`).

| FraudLogix reason | IPs |
|---|---|
| `PROXY` | 77 |
| `MOBILE_PROXY_SIGNALS` | 2 |
| `NON_HUMAN_SCRIPT` | 1 |

So FraudLogix's false positives are almost all `PROXY`.

## Cautions
- **Blank revenue:** 1,315 of the 2,341 "bot" IPs have `expected_revenue` blank rather than 0. Under the strict MoM rule they count as bots. Treating blank as "unknown" would change accuracy and recall a lot, but not FPR.
- **"Bot" here means "earned nothing".** A below_intro lead is still usually a person, so accuracy and recall under this label are low for every vendor. **FPR is the reliable comparison.**
- **Sample size:** 427 real-person IPs. The FPR values are ±4–5 points at 95% confidence.

## Checks (all passed)
- Lead IPs (2,768) and leads (3,235) equal a direct join count for the same dates.
- Every IP has exactly one label and one row per vendor. Every revenue IP is labelled real person.
- For each vendor, TP + FP + TN + FN + not answered = 2,768.
- A separate SQL recount of proxycheck.io gives the same TP/FP/TN/FN (389/139/288/1,952).
- Every IP on the FraudLogix list is flagged and has revenue or a meeting stage or later.

## Files
- **Data (`analysis/lead-ip-vendor-2026-09/`):**
  - `ips_<vendor>.csv`: one row per lead IP with label, revenue, lead category, furthest stage, the vendor's flags and the outcome.
  - `ip_labels.csv`
  - `scorecard_any_flag.csv`, `scorecard_bot_flag_only.csv`
  - `lead_category_signal.csv`, `lead_stage_signal.csv`
  - `fraudlogix_wrong_flags.csv`
  - `summary.json`
- **Code:** `build/pipeline/analysis/lead_ip_vendor.py`, which can be re-run and changes nothing.
- **Queries:** `build/pipeline/sql/analysis/`.
