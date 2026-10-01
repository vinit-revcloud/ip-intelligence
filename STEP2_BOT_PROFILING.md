# Step 2 (bot standard): profiling of the source tables

Profiled 18 Sep 2026, read only, Athena workgroup `ipintel_etl`. Queries and raw outputs: `build/pipeline/sql/profile_step2/`.

## 1. What each source table actually contains

### `raw.raw_tune_clicks` (FraudLogix via TUNE)
| Fact | Value |
|---|---|
| Span | Jan 2023 to today |
| Decisions | `ACCEPTED`, `FLAGGED`, `IGNORED` (522 old rows); **empty only for Jan 2023** (213,683 clicks) |
| Revenue | `revenue_cents` is **never > 0**. This table cannot tell us who paid |
| Volume | Falling fast: 1.16M clicks in Nov 2025, 34,738 in Aug 2026, 5,334 so far in Sep 2026 |

**FraudLogix changed its reason codes on 3–4 Sep 2025:**

| Reason | IPs | In use |
|---|---|---|
| `NON_HUMAN_SCRIPT` | 179,013 | until 4 Sep 2025 (retired) |
| `BASIC_FRAUD` | 77,599 | until 4 Sep 2025 (retired) |
| `SPOOFED` | 2,685 | until 4 Sep 2025 (retired) |
| codes `10`, `9`, `8` (no name) | 82,092 / 27,165 / 110 | until 3 Sep 2025 (retired; meaning unknown) |
| `BOT_GENERATED` | 22,434 | Jan 2023 to now |
| `ABNORMAL_TRAFFIC_PATTERNS` | 105,321 | since 4 Sep 2025 (new) |
| `MASKED_DEVICES` | 89,655 | since 4 Sep 2025 (new) |
| `DATA_CENTER` | 2,739 | since 3 Sep 2025 (new) |
| `PROXY` / `VPN` / `MOBILE_PROXY_SIGNALS` | 338,213 / 4,010 / 3,941 | proxy family |
| `TOR` / `TOR_EXIT_NODE` | 29 / 1 | rare |
| `OTHER_REASON` | 15,072 | until Jan 2026 |

So for traffic from the last 12 months, the current bot rule effectively rests on only `BOT_GENERATED` and `DATA_CENTER`. `ABNORMAL_TRAFFIC_PATTERNS` (105k IPs) is not counted as bot today.

**The same IP gets different answers over time:**
- 4,447,207 IPs were decided.
- 289,304 of them had **both** ACCEPTED and FLAGGED.
- 200,091 were given a bot reason at least once.
- 115,951 of those have a **latest** decision that is not bot. Under the "latest timestamp wins" rule, these read as not bot today.

### `unified.unified_session_summary`
| Fact | Value |
|---|---|
| Size | 11,442,523 sessions, 2,014,277 IPs, Aug 2022 to 17 Sep 2026 |
| `is_bot_click` | Always filled. **true on 2,237,493 sessions (19.6%)**, which is 122,711 IPs. The source of this flag is unknown to us |
| `has_revenue` | 'on' for 1,154,539 sessions, but only **1,190** of those link to a lead with revenue. **Not real revenue**; do not use it |
| `has_lead` | 'on' for 305,949 sessions; only 2,897 link to a lead in the leads table |
| `ip_is_proxy` | Filled on 8.7M sessions (3.98M true); source unknown. `ip_is_vpn` is always empty |
| Behaviour | Median duration **0 s** and median **1 event**: 73% of sessions last 0 s and 68% have 1 event. Duration and events cannot separate bots from people who leave straight away |
| User agent | 32,368 sessions have a bot-like agent (crawler, headless, script) |

### `experimentation_tools.experiment_router_events`
| Fact | Value |
|---|---|
| Size | 172,317 events, about 129,200 distinct IPs, 7 Apr to 18 Sep 2026 |
| `is_bot` | 1 on **7,170 events / 1,040 IPs**; 0 on the rest; never empty |
| What it catches | Top hit is Google Read-Aloud (a Google fetcher). Many hits are ordinary Chrome agents that are also `is_bot = 0` on other events, so it is not a user-agent list. The rule behind it is unknown to us |
| IPv6 / bad values | 180 non-IPv4 values |

### `sampledb.revenue_leads_plus` (the only real truth)
| Fact | Value |
|---|---|
| Size | 15,010,820 leads, 2012 to today |
| `fake` | true on 664,022 leads; otherwise empty (never false) |
| `phone_verified` | true 1,013,141 / false 334,734 |
| Revenue | 395,359 leads with `expected_revenue > 0` |
| **Link to sessions** | Only **12,345 leads** match a session (`utm_content = session_id`); 1,222 of them have revenue. So a known human/fake label exists for only a few thousand IPs |

## 2. How the bot fields agree (per IP)

| Session says | Router says | IPs | FraudLogix bot | proxycheck.io bot |
|---|---|---|---|---|
| not bot | (no router row) | 1,826,899 | 25,889 | 40,871 |
| **bot** | (no router row) | 112,960 | **4,062** | **1,006** |
| not bot | not bot | 64,387 | 319 | 577 |
| (no session) | not bot | 54,795 | 189 | 806 |
| **bot** | **not bot** | 9,189 | 38 | 18 |
| bot | bot | 562 | 37 | 93 |
| not bot | bot | 280 | 30 | 53 |
| (no session) | bot | 198 | 26 | 55 |

- The three bot sources barely agree.
- Of the 122k IPs the session table calls bot, FraudLogix agrees on about 3.4% and proxycheck.io on about 1%.
- Where both router and session saw an IP, they agree on "bot" for only 562 IPs and disagree on 9,469.

## 3. Signals against the truth (leads table)

**Truth** is the leads table joined to sessions (`utm_content = session_id`):
- **1,044 paying IPs:** a linked lead with `expected_revenue > 0`, treated as known humans.
- **40 fake IPs:** a linked lead with `fake = true`. That is too few to measure how many bots a signal catches.

Script: `x2_run.py` (it uses a temporary `stg_` table, dropped afterwards).

| Signal | Paying IPs wrongly hit | Fake IPs hit | Verdict |
|---|---|---|---|
| **Router `is_bot`** | 3 of 613 with router data (0.5%) | 0 of 40 | Safe; small coverage |
| **FraudLogix latest decision, current bot rule** | 5 (0.48%) | 1 | Safe |
| **proxycheck.io `is_bot`, current rule** | 5 (0.48%) | 0 | Safe |
| FraudLogix ever `DATA_CENTER` | 1 (0.1%) | 0 | Safe |
| FraudLogix ever `SPOOFED` | 2 (0.19%) | 0 | Safe |
| FraudLogix ever code 9 | 4 (0.38%) | 1 | Safe, but meaning unknown |
| FraudLogix ever `BOT_GENERATED` | 23 (2.2%) | 3 | Borderline if counted "ever"; safe when latest |
| FraudLogix ever code 10 | 58 (5.6%) | 2 | Too noisy |
| **Session `is_bot_click`** | **68 (6.5%)** | 2 | **Too noisy for bot on its own** |
| FraudLogix ever `BASIC_FRAUD` | 72 (6.9%) | 5 | Too noisy |
| FraudLogix ever `ABNORMAL_TRAFFIC_PATTERNS` | 104 (10.0%) | 7 | Too noisy |
| FraudLogix ever `MASKED_DEVICES` | 122 (11.7%) | 10 | Too noisy |
| FraudLogix ever `NON_HUMAN_SCRIPT` | 132 (12.6%) | 4 | Too noisy "ever"; safe as latest |
| proxycheck.io proxy or VPN | 302 (28.9%) | 14 | Not a bot signal |

**What this proves:**
1. **"Latest decision" beats "ever flagged":** the same reasons counted "ever" hit 12.6% of paying customers, but only 0.48% as the latest decision.
2. **Safe today:** the router's own `is_bot` and our current FraudLogix and proxycheck.io rules, each at 0.5% or less.
3. **Not safe on their own:** session `is_bot_click` and FraudLogix's newer reasons (`ABNORMAL_TRAFFIC_PATTERNS`, `MASKED_DEVICES`).

## 4. Misconceptions this profiling rules out
1. **"Session `has_revenue` = paying customer."** False: 1.15M 'on' sessions, about 1.2k real revenue leads.
2. **"FraudLogix reasons are stable."** False: the code set changed on 4 Sep 2025, and old codes 8/9/10 have no name.
3. **"TUNE clicks will keep covering new IPs."** False: volume has fallen to about 5k clicks a month, so FraudLogix covers little new traffic.
4. **"`is_bot_click` / router `is_bot` are vendor answers."** Unknown: both come from internal logic we have not seen, and they disagree with each other and with the vendors.
5. **"Short sessions mean bots."** Not provable: most real sessions also last 0 s with 1 event.

## 5. Decision (19 Sep 2026)
The owner chose the **bad-signal** standard: every FraudLogix FLAGGED reason, every proxycheck.io proxy, VPN, threat or cloud signal (plus risk 67+), and every IP2Proxy listing counts as `is_bot` = true. The rules and results are in `IS_BOT_MAPPING.md`, top section.
