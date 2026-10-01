# Bot / Not-bot Labels for Every Session IP

One-time analysis, run 17 Sep 2026 10:00 UTC, after the proxycheck.io backfill covered every experiment IP.
- **Script:** `build/pipeline/analysis/session_ip_bot_labels.py`. It only reads data; nothing is written to any table.
- **Outputs:** `analysis/session-ip-bot-labels-2026-09/`.

## Short answer

1. **Is bot / not bot done?** Yes. Every public IP with a website session from 18 Jun to 9 Sep 2026 (133,954 IPs, 350,329 sessions) has a label under the MoM rule, with the evidence behind it. Per-IP file: `session_ip_labels.csv`.
2. **Does every IP have at least one proxy vendor answer?**
   - **Experiment IPs:** yes, all of them.
     - All time: 38,446 of 38,446 have a proxycheck.io answer.
     - In this window: 26,096 of 26,096.
   - **Session IPs from the last 90 days:** 138,359 of 139,418 (99.2%). The 1,047 public addresses still missing are in our tables and are first in line for tomorrow's 07:30 run. The other 12 are IPv6 or private addresses, which no vendor answers.
   - **All 4,960,008 addresses:** 4,504,977 (90.8%) have at least one proxy answer. At 78,000 queries a day, the remaining about 455,000 take about 6 days *(projection)*.
3. **Can vendor flags pick out the bots?** No. Real customers are flagged **more** often than IPs that never produced a lead (32.6% vs 7.2%). A proxy or VPN flag describes the network, not the person. The label below is therefore defined by business outcome (revenue), as the MoM asked, not by vendor flags.

## Method

| Step | Rule |
|---|---|
| Population | `unified.unified_session_summary`, `session_date` 18 Jun to 9 Sep 2026 (up to 90 days back, the last 7 days left out so revenue has time to appear), public IPv4 `session_ip` only |
| Leads | `sampledb.revenue_leads_plus`, joined on `utm_content = session_id`, lead created on or after the session date |
| Revenue | Sum of `expected_revenue` per IP; blank counts as 0 |
| **Real person** | At least one lead with revenue above 0 |
| **Bot** (MoM, strict) | Everything else, reported in two parts: `lead_no_revenue` (a lead, no revenue) and `no_lead` |
| Evidence per IP | Sessions, bot-click sessions (session table), session proxy flag, experiment ids, the FraudLogix / IP2Proxy / proxycheck.io flags, proxycheck.io risk score, our combined proxy answer (`ip_resolved`) |

Vendor "flag" means any of: proxy, VPN, Tor, datacenter, bot, compromised, scraper.

**Checks, all passed:**
- The IP count and the session count equal direct counts on the session table.
- Every IP has exactly one label.
- `real_person` exactly when revenue > 0.
- Every scorecard row adds up to all IPs.

## Labels

| Label | IPs | Share |
|---|---|---|
| Real person | 427 | 0.3% |
| Bot: lead, no revenue | 2,341 | 1.7% |
| Bot: no lead | 131,186 | 97.9% |
| **Total** | **133,954** | |

1,315 of the 2,341 "lead, no revenue" IPs have **blank** revenue, not 0. This is still an open question for the mentor (see `LEAD_IP_VENDOR_ANALYSIS.md`).

## Evidence by label

| | Real person | Lead, no revenue | No lead |
|---|---|---|---|
| IPs | 427 | 2,341 | 131,186 |
| Have a proxy answer | 100% | 100% | 99.2% |
| Flagged by our combined answer | **32.6%** | 16.6% | **7.2%** |
| proxycheck.io risk ≥ 67 | 31.9% | 14.2% | 3.1% |
| At least one bot-click session | 5.2% | 5.0% | 6.7% |
| FraudLogix bot flag | 0.2% | 0.2% | 0.4% |
| In an experiment | 90.6% | 70.2% | 18.3% |

**What this shows:**
- Flags go **up** with customer value.
  - Of the 139 flagged real customers, 137 are flagged as VPN.
  - 136 of them come from Akamai (76), Fastly (36) or Cloudflare (24). These are the networks behind Apple's iCloud Private Relay, which hides a Safari user's real address.
- The session table's bot-click flag hardly separates the groups (5.2% vs 6.7%).
- FraudLogix's bot flag is almost never set, in any group.

## Vendor scorecard on all session IPs

Bot is the positive class. FPR = share of real people the source flagged (lower is better).

| Source | Coverage | Flagged | FPR | Precision | Recall |
|---|---|---|---|---|---|
| FraudLogix | 60.5% | 37,653 | 22.4% | 99.8% | 46.6% |
| IP2Proxy PX12 | 0.5% | 687 | — (no real person answered) | 100% | 100% |
| proxycheck.io | 85.5% | 9,956 | 32.6% | 98.6% | 8.6% |
| Session bot-click | 100% | 8,881 | 5.2% | 99.8% | 6.6% |
| Our combined answer | 99.2% | 9,956 | 32.6% | 98.6% | 7.4% |

**How to read it:**
- Precision near 99% says little: 99.7% of all IPs are "bot" under the MoM rule, so almost any flag is "right".
- **FPR** is what matters: flagging on FraudLogix would block about 1 in 5 paying customers, and on proxycheck.io about 1 in 3.
- **Recall** is low everywhere, because most no-lead traffic comes from ordinary home and mobile networks.
- FraudLogix's higher recall comes from its PROXY flag on mobile carriers, not from real bot detection.

The lead-IP-only scorecard (2,768 IPs) is in `LEAD_IP_VENDOR_ANALYSIS.md`; its FPR numbers match these.

## Per experiment (32 experiments in the window)

The 15 largest. The full list is in `per_experiment.csv`.

| Experiment | IPs | Real person | Lead, no revenue | No lead | Bot % (MoM) | Flagged % | Bot-click IPs |
|---|---|---|---|---|---|---|---|
| 76 | 8,908 | 181 | 395 | 8,332 | 98.0 | 20.4 | 896 |
| 68 | 4,871 | 182 | 619 | 4,070 | 96.3 | 22.7 | 400 |
| 66 | 3,163 | 107 | 244 | 2,812 | 96.6 | 28.9 | 275 |
| 72 | 2,794 | 87 | 165 | 2,542 | 96.9 | 28.3 | 223 |
| 60 | 2,765 | 91 | 207 | 2,467 | 96.7 | 31.2 | 225 |
| 58 | 1,837 | 38 | 143 | 1,656 | 97.9 | 8.4 | 120 |
| 57 | 895 | 22 | 28 | 845 | 97.5 | 9.7 | 62 |
| 75 | 705 | 45 | 49 | 611 | 93.6 | 36.5 | 51 |
| 53 | 668 | 12 | 54 | 602 | 98.2 | 7.8 | 45 |
| 65 | 642 | 51 | 47 | 544 | 92.1 | 40.8 | 41 |
| 47 | 626 | 24 | 127 | 475 | 96.2 | 14.2 | 27 |
| 64 | 531 | 51 | 77 | 403 | 90.4 | 48.0 | 27 |
| 50 | 440 | 11 | 64 | 365 | 97.5 | 10.2 | 39 |
| 62 | 434 | 44 | 54 | 336 | 89.9 | 40.6 | 37 |
| 49 | 424 | 11 | 52 | 361 | 97.4 | 9.2 | 33 |

Every experiment IP has a proxy answer (100% in every row).
- **Pattern:** experiments with a higher real-person share also have a higher flagged share (64, 65, 62, 75). The flag follows the audience's networks, not bot traffic.
- **Note:** an IP can belong to more than one experiment, so the rows add up to 30,522 while there are 26,096 distinct IPs.

## How proxy coverage was completed (17 Sep)

1. **Budget:** the 30,000 daily queries reserved for our retired API moved to enrichment. The job now spends 78,000 a day and keeps 2,000. The teammate API does not use our key: proxycheck.io counted 50,354 queries on 16 Sep, below our own 50,859 reservations.
2. **Order:** the backfill now sends experiment IPs first, then IPs seen in the last 30 days, then IPs seen in the last 90 days, then the rest.
3. **Deploy and run:** the new code was deployed at 09:47 UTC. A manual top-up spent the rest of 17 Sep's quota: 27,712 queries, 55,158 rows added, 10 of 10 checks passed. The six `unified` tables were then refreshed (09:55, passed).

## Files

| File | Content |
|---|---|
| `session_ip_labels.csv` | One row per IP: label, revenue, leads, stage, experiments, every vendor flag, risk, combined answer |
| `label_evidence.csv` | The evidence table above |
| `vendor_scorecard_all_session_ips.csv` | The scorecard above, with TP / FP / TN / FN |
| `per_experiment.csv` | All 32 experiments |
| `summary.json` | Totals and check results |

In the app, these numbers are on the **Bot / Not bot** page (`app-data/session_ip_labels.json`, see `LOVABLE_PROMPT_APP_V2.md`).

## Re-run

```bash
cd build/pipeline
python analysis/session_ip_bot_labels.py
python analysis/export_app_data.py
```

Change `START`/`END` at the top of the script to use a different window.
