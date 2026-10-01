# Bot Verdict for Every Session IP

One-time analysis, run 17 Sep 2026 15:00 UTC.
- **Script:** `build/pipeline/analysis/session_ip_bot_verdict.py`. It only reads data; nothing is written to any table.
- **Outputs:** `analysis/session-ip-bot-verdict-2026-09/`.

## Why this was needed
- **proxycheck.io has no bot field.** It answers proxy, VPN, network type and risk, so its bot flag is always empty.
- **FraudLogix rarely says "bot",** and it is the only vendor with a bot flag at all.
- **Proxy and VPN flags describe the network, not the person.** They hit 32.6% of paying customers (see `SESSION_IP_BOT_LABELS.md`).

So the verdict combines vendor network signals with **how the IP's sessions behaved**, and every rule is **tested against known humans**: the 427 IPs that produced revenue.

## Method
**Population:** the same as the MoM analysis. Every public IP with a website session from 18 Jun to 9 Sep 2026: 133,954 IPs, 350,329 sessions. Leads are joined on `utm_content = session_id`.

**Proof of a human** (from the leads table): revenue > 0, or a lead that reached **intro_qualified or later**. No IP below that stage ever produced revenue.

**Rules for a bot signal to count as "strong":**
1. It flags **at most 2%** of paying IPs.
2. It fires **more often on no-lead IPs than on paying IPs**, so it points away from humans rather than just at shared networks.
3. It **can be tested**. A rule defined by "no engagement" can never match a paying IP, so it can't be proven and stays weak.

**Verdict for each IP** (first rule that matches):

| Verdict | Rule |
|---|---|
| **human** | Proof of a human |
| **bot** | At least one strong signal |
| **likely_human** | Engaged (a partial lead, or 3+ events over 5+ seconds), with no weak signal other than VPN/proxy or time-zone mismatch |
| **suspicious** | Only weak signals |
| **unknown** | Nothing either way, mostly a single short visit from a clean network |

### What was found in the session data and handled
- **Funnel fields are inflated.** `journey_stage = Revenue` appears on 113,102 sessions, but only 427 IPs have revenue in the leads table. Human proof therefore comes from the leads table.
- **Consent is recorded on page load.** 40,771 consent sessions lasted 0 seconds with 1 event. Quiz start on its own looks the same, so neither counts as engagement. A partial lead does (median 19 seconds, 5 events).
- **`screen_width` is always empty**, so it isn't used.
- **Time zones:** browser time zones such as `America/New_York` are converted to an offset before comparing with the IP's `UTC-04:00`. Names that can't be converted, such as `Etc/Unknown`, are skipped.
- **Shared networks:** some paying IPs have up to 121 sessions a day (mobile carriers, relays). Session volume is therefore not a bot sign.

## Signal test against known humans

| Signal | IPs hit | Paying IPs hit (FPR) | No-lead IPs hit | Result |
|---|---|---|---|---|
| Automation or crawler browser | 573 | 0 (0%) | 0.44% | **strong** |
| FraudLogix bot reason | 549 | 1 (0.23%) | 0.41% | **strong** |
| Datacenter / hosting network | 723 | 0 (0%) | 0.54% | **strong** |
| Compromised host | 28 | 0 (0%) | 0.02% | **strong** |
| Tor | 0 | 0 | 0% | weak (never seen) |
| 100+ sessions in a day | 14 | 2 (0.47%) | 0.01% | weak (shared networks) |
| All sessions are bot clicks (session table) | 8,881 | 22 (5.15%) | 6.66% | weak (FPR above 2%) |
| 3+ sessions, all instant bounces | 14,942 | 0 | 11.39% | weak (can't be tested) |
| Browser time zone ≠ IP time zone | 28,308 | 145 (34%) | 21.0% | weak |
| VPN or proxy (any vendor) | 45,266 | 213 (50%) | 33.5% | weak |

**All four strong signals together flag 1 of 427 paying IPs (0.23%).** For comparison, vendor proxy/VPN flags hit 32.6%.

## Results

| Verdict | IPs | Share | Sessions |
|---|---|---|---|
| human | 808 | 0.6% | 25,981 |
| likely_human | 32,602 | 24.3% | 68,654 |
| unknown | 49,450 | 36.9% | 55,995 |
| suspicious | 49,246 | 36.8% | 189,877 |
| **bot** | **1,848** | **1.4%** | 9,822 |

**Why IPs are called bot** (an IP can have more than one reason; 22 do):
- datacenter network: 722
- automation browser: 573
- FraudLogix bot reason: 548
- compromised host: 28

**Why IPs are suspicious** (most common combinations):
- only VPN/proxy: 15,729
- only repeated instant bounces: 10,648
- time-zone mismatch + VPN/proxy: 6,056
- all bot clicks + time-zone mismatch + VPN/proxy: 5,267

**Unknown:** 44,347 of the 49,450 had a single session. One visit isn't enough evidence either way.

### Compared with the MoM label

| MoM label | IPs | human | likely_human | unknown | suspicious | bot |
|---|---|---|---|---|---|---|
| Real person (revenue > 0) | 427 | 100% | 0 | 0 | 0 | 0 |
| Lead, no revenue | 2,341 | 16.3% | 78.6% | 0.3% | 4.0% | 0.8% |
| No lead | 131,186 | 0 | 23.4% | 37.7% | 37.5% | 1.4% |

**What this means:** "no revenue" is not the same as "bot".
- **Lead without revenue:** 95% of these IPs look human by evidence.
- **No lead at all:** under the MoM rule every one counts as a bot, but only **1.4%** show hard bot evidence; 23% behave like people, and the rest can't be decided from an IP.

### Per experiment (the 12 largest; all 32 in `verdict_per_experiment.csv`)

| Experiment | IPs | Human + likely | Unknown | Suspicious | Bot | Bot % |
|---|---|---|---|---|---|---|
| 76 | 8,908 | 49.2% | 2,237 | 2,212 | 73 | 0.82 |
| 68 | 4,871 | 63.8% | 705 | 1,042 | 18 | 0.37 |
| 66 | 3,163 | 55.6% | 661 | 725 | 20 | 0.63 |
| 72 | 2,794 | 54.4% | 584 | 669 | 21 | 0.75 |
| 60 | 2,765 | 54.5% | 640 | 593 | 25 | 0.90 |
| 58 | 1,837 | 24.4% | 713 | 651 | 25 | 1.36 |
| 57 | 895 | 23.6% | 361 | 307 | 16 | 1.79 |
| 75 | 705 | 59.7% | 130 | 148 | 6 | 0.85 |
| 53 | 668 | 20.1% | 248 | 269 | 17 | **2.54** |
| 65 | 642 | 57.0% | 147 | 120 | 9 | 1.40 |
| 47 | 626 | 62.5% | 40 | 182 | 13 | **2.08** |
| 64 | 531 | 70.1% | 72 | 83 | 4 | 0.75 |

Experiments 53, 57 and 58 have the lowest human share and the highest bot share, so they are worth a traffic-quality review.

## Checks (all passed)
- IP and session counts equal direct counts on the session table.
- Every IP has exactly one verdict.
- No paying IP is called bot.
- Every strong signal stays within 2% FPR on paying IPs.
- All strong rules together stay within 5% of paying IPs (actual: 0.23%).

## Limits
- **Bot verdicts undercount.** Bots on home or mobile networks with normal browsers and no FraudLogix flag look like real traffic; this is why "suspicious" and "unknown" are large.
- **Known humans are few:** 427 paying IPs. A 0% FPR means "0 of 427" (within about 1% at 95% confidence).
- **FraudLogix's bot flag** reflects only its latest decided click per IP.
- **One IP can be many people** (carrier networks, iCloud Private Relay). The verdict is about the IP, not a person.

## What this enables next
1. **Use `bot` as a block or exclude list with little risk to revenue** (0.23% FPR). Treat `suspicious` as "review" or "don't pay for", not as "block".
2. **Report experiments by `human + likely_human` share** instead of the MoM rule, which calls 98% of traffic bots.
3. **After the mentor approves:** a daily version stored in `ipintel_curated`, and a behavioural bot-detection tool on the website to shrink "suspicious" and "unknown".

## Files

| File | Content |
|---|---|
| `ip_bot_verdict.csv` | One row per IP: verdict, strong and weak signals, revenue, leads, stage, session behaviour, risk, experiments |
| `signal_test.csv` | The signal test above |
| `verdict_by_mom_label.csv` | Verdict against the MoM label |
| `bot_reasons.csv` | Why IPs are called bot |
| `verdict_per_experiment.csv` | All 32 experiments |
| `summary.json` | Totals and check results |

**In the app:** the data is included in `session_ip_labels.json` under `verdict`. See the addendum in `LOVABLE_PROMPT_APP_V2.md` for the page section.

**Re-run:** `cd build/pipeline`, then `python analysis/session_ip_bot_verdict.py`, then `python analysis/export_app_data.py`.
