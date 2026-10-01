# IP Intelligence System: Overview for Presentation

Status as of 17 Sep 2026, 15:15 UTC. AWS account 221490242148, us-west-2.

---

## 1. What the system is

This is the company's source for **where an IP address is** (state, city, ZIP) and **whether it is risky** (proxy, VPN, Tor, datacenter, bot).

- **Updates:** every day, automatically, from two production tables. They are only read, never changed.
- **Lookups:** a live lookup service (the teammate's IP Lookup API), plus an app for the reports.
- **Vendor scoring:** vendors are scored against real business results (revenue and lead stage), not against each other alone.

| | |
|---|---|
| IP addresses in the tables | **4,960,008** |
| Location rows · risk rows | 5,171,012 · 9,699,074 |
| Vendors | FraudLogix, IP2Proxy PX12, proxycheck.io (paid), IP2Location DB11, ipinfo.io, ipwho.is |
| Daily proxycheck.io budget | 80,000 queries: 78,000 for enrichment, 2,000 kept as a safety margin |
| Running cost besides the proxycheck.io plan | Effectively zero (a few cents a day of Athena and S3) |

---

## 2. How it works

```
 raw.raw_tune_clicks ─┐  (production, read only)
 unified.unified_     ├─► 07:30 UTC  Daily load (Job A)
   session_summary  ──┘     new IPs → IP2Location, IP2Proxy, FraudLogix, ipinfo.io, ipwho.is
                            → ipintel_curated tables → combined answer (ip_resolved)
                                   │
                                   ▼
                          proxycheck.io run (Job B), up to 78,000 IPs a day
                            order: queued → new today → EXPERIMENT IPs → last 30 days → last 90 days → rest
                            10:00 fallback · 22:00 top-up
                                   │  every check passed?
                                   ▼
                          Publish: the 6 unified tables are refreshed
                            unified.ip_geo · ip_intelligence · ip_geo_analytics ·
                            ip_intelligence_analytics · vendor_overview_geo · vendor_overview_proxy
                                   │
                    ┌──────────────┴───────────────┐
                    ▼                              ▼
       Teammate's IP Lookup API            App data export (new, 17 Sep)
       GET /v1/ip/{ip}                     9 report files → S3 serving/app/
       (reads unified tables;                        │
        calls proxycheck.io live when needed)        ▼
                    │                       Lovable app report pages
                    └──────────► Lovable app: IP Lookup page
```

**Safety built in:**
- **Permissions:** the pipeline role is not allowed to write to any production table. AWS itself enforces this, and it is checked before every run.
- **Checks:** every run has 10–14 checks (no duplicates, no table shrinks, every address has one answer, and more). The `unified` tables are only refreshed when all of them pass. Before swapping in new files, a rollback copy is kept.
- **Change review:** CloudTrail is reviewed every run; nothing outside the project was touched.
- **Operations:** alarms email the team, there is an emergency pause switch, and half-finished writes are never kept.

---

## 3. What was delivered

| # | Deliverable | Status |
|---|---|---|
| 1 | Daily enrichment pipeline with proxycheck.io backfill and checks | Running daily |
| 2 | The six `unified` tables kept current after every passed run (the teammate API reads them) | Running |
| 3 | Location rules v2: agreed / nearby (≤ 25 km) / same state / states differ, with vendor priorities based on evidence | Live |
| 4 | **One-time lead-IP vendor analysis** (MoM): revenue, lead stage, FPR, accuracy per vendor | Done |
| 5 | **Bot / not bot for every session IP** (MoM rule, plus an evidence-based verdict) | Done |
| 6 | **At least one proxy answer for every IP**, experiment IPs first | Experiment IPs 100%; see section 6 |
| 7 | Lovable app v2: live IP Lookup and 5 report pages, with data uploaded | Live |
| 8 | App report data refreshed in S3 automatically after every run | Live since 17 Sep |
| 9 | Clean-up: our own API retired, 15 unused tables dropped | Done; admin deletions pending |
| 10 | Documentation (manual, system guide, review log, plan) | Done |

---

## 4. Result 1: Lead-IP vendor evaluation (the MoM analysis)

### Method
1. **Sessions:** from `unified.unified_session_summary`, 18 Jun to 9 Sep 2026. That is up to 90 days back, leaving out the last 7 days so revenue has time to appear.
2. **Join to leads:** `sampledb.revenue_leads_plus`, matching `utm_content = session_id`, with the lead created on or after the session.
3. **Label each IP:** total `expected_revenue` above 0 means **real person**; otherwise **bot** (blank revenue counts as 0).
4. **Grade vendors:** compare each vendor's flag for every IP with the label, and break the results down by lead category and furthest stage.

**Population:** 2,768 lead IPs, 3,235 leads, **427 real-person IPs** and 2,341 "bot" IPs.

### Scorecard (any risk flag; bot is the positive class)

| Vendor | Coverage | **FPR** (real people flagged) | Accuracy | Precision | Recall |
|---|---|---|---|---|---|
| FraudLogix | 84% | **22.4%** | 46.7% | 91.5% | 41.4% |
| proxycheck.io | 100% | **32.6%** | 24.5% | 73.7% | 16.6% |
| Session table flag | 100% | **36.1%** | 25.3% | 73.4% | 18.2% |
| IP2Proxy PX12 | 0.5% | too few answers to judge | — | — | — |

**Bot flag only** (not proxy or VPN): FraudLogix flags 5 IPs (FPR 0.3%), and the session bot-click flag 140 (FPR 5.2%). Outright bot flags are rare.

### Which lead stages mean "human"

| Lead category | IPs | With revenue | FraudLogix flags | proxycheck.io flags |
|---|---|---|---|---|
| meeting | 67 | **85%** | 29.8% | 40.3% |
| intro_qualified | 739 | 50% | 22.5% | 28.3% |
| below_intro | 1,960 | **0%** | 44.6% | 14.8% |

- **Human stages:** revenue appears only from **intro_qualified** onwards. `meeting_scheduled` (94%) and `connected` (70%) are the strongest signs of a real person.
- **Non-human side:** the complement is **below_intro**, which never has revenue.
- **FraudLogix** follows the stages best: it flags below-intro IPs most.
- **FraudLogix wrongly flagged 80 real customers**: 77 for `PROXY`, 2 for `MOBILE_PROXY_SIGNALS`, 1 for `NON_HUMAN_SCRIPT`.

---

## 5. Result 2: Bot / not bot for every session IP

**Population:** every public IP with a session from 18 Jun to 9 Sep: **133,954 IPs, 350,329 sessions**.

| Label | IPs | Share |
|---|---|---|
| Real person (revenue > 0) | 427 | 0.3% |
| Bot: lead but no revenue | 2,341 | 1.7% |
| Bot: no lead | 131,186 | 97.9% |

### Key finding: vendor flags cannot identify bots

| | Real person | Lead, no revenue | No lead |
|---|---|---|---|
| Flagged by our combined answer | **32.6%** | 16.6% | **7.2%** |
| proxycheck.io risk ≥ 67 | 31.9% | 14.2% | 3.1% |
| Bot-click session | 5.2% | 5.0% | 6.7% |

- **Paying customers are flagged more often than IPs that never produced a lead.** Of the 139 flagged customers, 137 are flagged as VPN, and 136 come through Akamai, Fastly or Cloudflare, the networks behind **Apple iCloud Private Relay**.
- A proxy or VPN flag describes the network, not the person. **Blocking on these flags would block one in three paying customers.**
- That is why the bot label is based on **revenue**, as the MoM set out, and vendors are judged on **FPR**.

**Per experiment:** 32 experiments are in the window.
- In the largest, experiment 76 (8,908 IPs, 181 real people), 98% of IPs count as bots under the MoM rule.
- Experiments with more real customers also have more flags (64, 65, 62, 75), which again shows flags follow the audience's networks.

## 5b. Result 2b: Evidence-based bot verdict (17 Sep)

proxycheck.io has no bot field, and proxy/VPN flags hit paying customers. So each IP is judged on vendor network signals **plus session behaviour**, and every rule is tested on the 427 paying IPs (`SESSION_IP_BOT_VERDICT.md`).

| Verdict | IPs | Share |
|---|---|---|
| Human (revenue, or intro_qualified and later) | 808 | 0.6% |
| Likely human (real engagement, no bot sign) | 32,602 | 24.3% |
| Unknown (mostly one short visit) | 49,450 | 36.9% |
| Suspicious (only weak signs, such as VPN or repeated bounces) | 49,246 | 36.8% |
| **Bot** (strong sign) | **1,848** | **1.4%** |

- **Strong bot signs:** automation browser, FraudLogix bot reason, datacenter network, compromised host.
- **Accuracy on real customers:** together they wrongly flag **0.23%** of paying customers, against 32.6% for proxy/VPN flags.
- **Takeaway:** "no revenue" is not "bot". Of IPs with no lead, 1.4% show hard bot evidence and 23% behave like people.
- **Experiments to review:** 53, 57 and 58 have the lowest human share; 53 and 47 have a bot share above 2%.

---

## 6. Result 3: Enrichment and proxy coverage

| Group | IPs | At least one proxy answer |
|---|---|---|
| **Experiment IPs** (all time) | 38,446 | **100%**, all from proxycheck.io |
| Session IPs, last 90 days | 139,418 | 99.2% (1,047 queued for the next run; 12 are IPv6 or private and can't be answered) |
| Addresses seen in the last 30 days | 42,786 | **100%** answered by proxycheck.io |
| All addresses | 4,960,008 | 90.8%; about 6 days to 100% at 78,000 a day *(projection)* |

**Location, last 30 days** (42,786 addresses):

| Status | Addresses |
|---|---|
| Two or more vendors agree | 20,248 |
| Within 25 km | 6,656 |
| Same state, cities further apart | 9,307 |
| States differ or no location | 6,572 |

So **84.6% have the state confirmed** by at least two vendors.

**Location accuracy against customers' own postal addresses** (1,049 addresses every vendor answered):

| Vendor | State | City | ZIP |
|---|---|---|---|
| ipinfo.io | **54.2%** | **11.1%** | **4.0%** |
| ipwho.is | 53.7% | 10.5% | 1.8% |
| proxycheck.io | 51.6% | 7.2% | 2.9% |
| IP2Location DB11 | 47.0% | 9.5% | 2.2% |
| Our combined answer | 54.1% | 11.0% | 3.6% |

City and ZIP from IP addresses are unreliable for every vendor; state is the level to trust.

**17 Sep changes:**
- **Budget:** the 30,000 queries a day reserved for our retired API now go to enrichment (78,000 a day).
- **Order:** the backfill now sends experiment IPs first.
- **Today's run:** the rest of the day's quota was spent (27,712 queries), and all checks passed.

---

## 7. The app (Lovable)

| Page | Data | Refresh |
|---|---|---|
| **IP Lookup** (one IP, or up to 200) | Teammate's IP Lookup API | Live |
| **Bot / Not bot** | `session_ip_labels.json` | One-time analysis |
| **Lead-IP Vendor Evaluation** (scorecards, stages, FraudLogix wrong flags, what each vendor said per IP) | `lead_ip_analysis.json`, `lead_ips.json` | One-time analysis |
| **Location Accuracy** | `geo_accuracy.json` | After every run |
| **Enrichment Coverage** | `coverage.json`, `proxy_coverage.json` | After every run |
| **Vendor Scorecards** | `vendor_overview_*.json` | After every run |
| **Data Upload** | Manual backup for the files above | When needed |

**How the data reaches the app:**
- **Automatic part:** after every passed run, the pipeline writes the 9 files to `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/app/`. This has been live since 17 Sep 11:34 UTC.
- **Today:** files are uploaded on the Data Upload page. The current files are as of 17 Sep 11:30 UTC.
- **Next:** once an AWS admin creates a read-only key for that one folder, the app reads S3 directly and no manual step is left (section 9).
- **Secrets:** the IP Lookup token is stored only as a Lovable server secret.

---

## 8. Data and components

| Where | What |
|---|---|
| `unified` (6 project tables) | `ip_geo`, `ip_intelligence`, `ip_geo_analytics`, `ip_intelligence_analytics`, `vendor_overview_geo`, `vendor_overview_proxy`, refreshed after every passed run |
| `ipintel_curated` (12 tables) | Working tables, including `ip_resolved` (one combined answer per IP), `ip_occurrences`, `proxycheck_queue`, `qualified_lead_ips` |
| Lambda | `ipintel-free-daily` (Job A), `ipintel-proxycheck-daily` (Job B, publish, app export) |
| DynamoDB `ipintel-pipeline-state` | Settings, run logs with checks, quota counter, audit items |
| S3 `ip-intelligence/` | Batches, proxycheck.io responses, reports, app files, archives |
| Secrets Manager | `ipintel/proxycheck-paid` (never shown or shared) |
| Production (read only) | `raw.raw_tune_clicks`, `unified.unified_session_summary`, `sampledb.revenue_leads_plus` |

---

## 9. Open items

| Item | Owner |
|---|---|
| Create the read-only S3 key for the app, so report data needs no manual upload | AWS admin (one time) |
| Delete our retired API (Function URL, Lambda, log group, role) and 5 unused benchmark tables (`ADMIN_DELETION_STEPS.md`) | AWS admin |
| Is blank `expected_revenue` 0 or unknown? It affects 1,315 "bot" lead IPs | Mentor / owner |
| Daily version of the vendor evaluation | Later, when asked |
| The teammate API ignores our combined answer (`ip_resolved`) and prefers FraudLogix, which has the 22% FPR | Teammate (recommendation) |
| Delete the data folders of the 15 dropped tables | On or after 23 Sep, with the owner's go-ahead |

---

## 10. Recommendations
1. **Don't block traffic on proxy or VPN flags alone.** They hit a third of paying customers (iCloud Private Relay). Use the evidence-based `bot` verdict instead (0.23% of paying customers affected).
2. **Use FPR on revenue-labelled IPs as the vendor metric.** Of the vendors that cover most IPs, FraudLogix is the best (22.4%) but still high.
3. **Use the lead stage** (below_intro vs intro_qualified and later) as the practical "human" signal.
4. **For location, trust the state; not city or ZIP.** Use ipinfo.io first, or our combined answer.
5. **Point the teammate API at `ip_resolved`,** so lookups return the evidence-based answer.

---

## Documents for detail

| Document | Content |
|---|---|
| `LEAD_IP_VENDOR_ANALYSIS.md` | Full lead-IP analysis and checks |
| `SESSION_IP_BOT_LABELS.md` | Full bot / not-bot analysis (MoM label) |
| `SESSION_IP_BOT_VERDICT.md` | Evidence-based bot verdict and signal test |
| `docs/USER_MANUAL.md` | For analysts: lookups, Athena, reports |
| `docs/SYSTEM_GUIDE.md` | For engineers: jobs, checks, budget, operations |
| `WORK_DONE_REVIEW.md` | Every change with evidence and undo |
| `FINAL_IMPLEMENTATION_PLAN.md` | Step status |
| `LOVABLE_PROMPT_APP_V2.md` | App specification |
| `ADMIN_DELETION_STEPS.md` | Admin commands |
