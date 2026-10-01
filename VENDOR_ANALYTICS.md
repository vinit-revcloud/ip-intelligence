# Vendor Analytics: Location and Risk

18 Sep 2026. It explains **what each vendor gives us, how accurate it is, and why we use what we use**, for the two tables `ip_geo` (location) and `ip_intelligence` (risk: proxy, VPN, Tor, datacenter, bot).

All figures come from our own data (queries in `build/pipeline/sql/checks/`). None come from vendor marketing.

---

## 1. The vendors

| Vendor | Gives | Cost | How we get it |
|---|---|---|---|
| **IP2Location DB11** | Location | Free database | Loaded file, answers every IP |
| **IP2Proxy PX12** | Proxy list | Free database | Loaded file, **answers only IPs on its proxy list** |
| **FraudLogix** | Risk decision per ad click | Already paid (part of TUNE) | From `raw.raw_tune_clicks`, **only IPs that clicked an ad** |
| **proxycheck.io** | Risk + location + ISP + risk score | Paid plan (queries per day) | API, answers any IP we ask |
| **ipinfo.io**, **ipwho.is** | Location | Free with limits | Web API, a few hundred a day, used as tie-breakers |

---

## 2. Fill rate: how many of our 4,960,640 IPs each vendor answers (18 Sep)

### Risk (`ip_intelligence`)

| Vendor | Rows | Proxy / VPN / Tor / datacenter filled | Bot filled | Compromised filled | ISP / ASN filled |
|---|---|---|---|---|---|
| FraudLogix | 91.4% | **89.6%** | 89.6% | never | never |
| IP2Proxy PX12 | 100% | **0.3%** (only listed proxies) | never | never | 0.3% |
| proxycheck.io | 5.7% | 5.7% | never | 5.7% | 5.7% |

### Location (`ip_geo`)

| Vendor | State | City | ZIP | Lat/long | Time zone |
|---|---|---|---|---|---|
| IP2Location DB11 | **100%** | 100% | 99.8% | 100% | 100% |
| proxycheck.io | 5.7% | 5.7% | 4.9% | 5.7% | 5.7% |
| ipinfo.io / ipwho.is | 0.1% | 0.1% | 0.1% | 0.1% | 0.1% |

**What limits each fill rate**, and whether money fixes it:
- **FraudLogix:** only IPs that clicked a TUNE ad. It can't be asked about other IPs. **Its maximum is about 91%, already reached.**
- **IP2Proxy PX12:** a list, so silence is not an answer. **It can't be raised, and it isn't used as an answer.**
- **proxycheck.io:** limited only by our daily query plan. **It can reach 100%.** This is the one lever, and the upgrade below uses it.
- **ipinfo.io / ipwho.is:** free limits of a few thousand a day. Reaching 4.96M would need paid plans, and their accuracy is only slightly better than DB11 (below). **Not worth buying.**
- **Bot:** no vendor except FraudLogix returns a bot flag. See section 5.

**After the upgrade**, the risk table will have one acceptable answer for **100%** of IPs: proxycheck.io at 100%, plus FraudLogix at 89.6%. The location table will have two answers for every IP: DB11 and proxycheck.io.

---

## 3. Location accuracy: which vendor is right about where the customer is

**Truth:** 2,105 customers who gave a full postal address (`qualified_lead_ips`).
**Rules:** state = same state name; city = same city name; ZIP = same first five digits.
**Caveat:** a postal address is where someone lives, not always where their connection is. Use these to **compare vendors**, not as a promise.

### Fair comparison: the 1,049 customers every vendor answered

| Vendor | State | City | ZIP | State + city |
|---|---|---|---|---|
| **ipinfo.io** | **54.2%** | **11.1%** | **4.0%** | **11.1%** |
| ipwho.is | 53.7% | 10.5% | 1.8% | 10.4% |
| proxycheck.io | 51.6% | 7.2% | 2.9% | 7.2% |
| IP2Location DB11 | 47.0% | 9.5% | 2.2% | 9.5% |
| **Our combined answer** | 54.1% | 11.0% | 3.6% | 11.0% |

### Every customer each vendor answered

| Vendor | Tested | State | City | ZIP |
|---|---|---|---|---|
| **Our combined answer** | 2,105 | **62.5%** | **15.3%** | 4.1% |
| proxycheck.io | 2,105 | 59.7% | 11.9% | **5.4%** |
| IP2Location DB11 | 2,105 | 59.0% | 14.5% | 3.4% |
| ipinfo.io | 1,050 | 54.3% | 11.1% | 4.0% |
| ipwho.is | 1,050 | 53.7% | 10.5% | 1.8% |

### What this means
- **State is the only level to rely on.** City is right about 1 time in 10, ZIP about 1 in 25, for **every** vendor. That is a limit of IP geolocation (mobile networks, relays), not of one vendor.
- **No single vendor wins everywhere.** ipinfo.io is best on the fair pool; DB11 and proxycheck.io are close and cover every IP.
- **Our combined answer is the best overall** (62.5% state on all 2,105). It takes the state most vendors agree on, then falls back to the vendor that was right most often on the truth set (priority ipinfo.io → ipwho.is → DB11 → proxycheck.io).
- **Agreement between vendors** (last 30 days): two or more vendors name the same state for **84.6%** of addresses.

**Reference for location:** `ip_resolved` (our combined answer). If one vendor's row is needed, use **IP2Location DB11**: 100% fill, free, within a few points of the best.

---

## 4. Risk accuracy: which vendor is right about bots and proxies

**Truth:** revenue. Every IP with a lead from 18 Jun to 9 Sep 2026 (2,768 IPs), joined on `utm_content = session_id`. **Real person** = revenue above 0 (427 IPs). Bot is the positive class.

| Vendor | Answered | **FPR** (real people flagged) | Accuracy | Precision | Recall |
|---|---|---|---|---|---|
| **FraudLogix** | 84% | **22.4%** | **46.7%** | **91.5%** | **41.4%** |
| proxycheck.io | 100% | 32.6% | 24.5% | 73.7% | 16.6% |
| Session table flag | 100% | 36.1% | 25.3% | 73.4% | 18.2% |
| IP2Proxy PX12 | 0.5% | — (too few) | — | — | — |

**Bot flag only:** FraudLogix flags 5 of these IPs (FPR 0.3%), and the session bot-click flag 140 (FPR 5.2%).

### What this means
- **FraudLogix is the best risk vendor where it has an answer:** lowest FPR, highest precision and recall. It also follows the lead stage: it flags 44.6% of below-intro IPs, which never produce revenue, and only 22–30% of qualified ones.
- **proxycheck.io is the coverage vendor.** It answers any IP, but flags more real customers. 137 of its 139 wrong flags are VPN flags on **iCloud Private Relay** (Akamai, Fastly, Cloudflare), which paying Safari users go through.
- **No vendor's proxy/VPN flag should block traffic on its own.** Even the best one flags 1 paying customer in 5.

**Reference for risk:** **FraudLogix first, proxycheck.io when FraudLogix has no answer.** That is also the order your teammate's API uses. For a yes/no bot decision, use the verdict below, not a raw flag.

---

## 5. Bot: how we answer it, since proxycheck.io has no bot field

Only FraudLogix returns a bot flag, and it rarely uses it. So bot is decided from **evidence tested against paying customers** (`SESSION_IP_BOT_VERDICT.md`). A signal counts only if it flags at most 2% of paying IPs and appears more often on IPs with no lead:

| Signal | Source | Paying IPs wrongly flagged | Counts as |
|---|---|---|---|
| Datacenter / hosting network | proxycheck.io type "Hosting", FraudLogix, IP2Proxy | 0% | **Bot** |
| Compromised host | proxycheck.io | 0% | **Bot** |
| FraudLogix bot reason | FraudLogix | 0.23% | **Bot** |
| Automation or crawler browser | session table | 0% | **Bot** |
| VPN or proxy | any vendor | 49.9% | only "suspicious" |
| All sessions are bot clicks | session table | 5.2% | only "suspicious" |

**All four strong signals together wrongly flag 0.23% of paying customers,** compared with 32.6% for proxy/VPN flags.

**Why the upgrade matters for bot:** two of the four strong signals (datacenter, compromised) come from proxycheck.io. Once proxycheck.io answers every IP, **every IP gets a network-based bot check**, not just the 5.7% answered today.

---

## 6. The choice, in one table

| Question | Use | Why |
|---|---|---|
| Where is this IP? | `ip_resolved` state (or IP2Location DB11) | Best combined accuracy (62.5% state); DB11 fills 100% for free |
| Is it a proxy or VPN? | FraudLogix, else proxycheck.io | FraudLogix has the lowest FPR (22.4%); proxycheck.io covers everything else |
| Is it a bot? | Bot verdict (strong signals) | 0.23% of paying customers wrongly flagged; raw flags hit 22–33% |
| Should we block it? | Only on a strong bot signal | VPN/proxy alone blocks iCloud Private Relay customers |
| Which vendor to pay for more? | proxycheck.io | The only vendor whose fill rate money can raise; it also gives datacenter and compromised for the bot check |

---

## 7. proxycheck.io plan: what to buy to finish today

| | Queries |
|---|---|
| IPs without a proxycheck.io answer (18 Sep) | 4,678,134 |
| About 1% extra (IPs that are both proxy and VPN are charged twice) | ~47,000 |
| Already used today | ~77,300 |
| **Needed today** | **about 4.80 million** |

| Plan | Daily queries | Price / month | Done in |
|---|---|---|---|
| $49.99 | 1.28M | $49.99 | 4 days |
| $99.99 | 2.56M | $99.99 | 2 days |
| **$199.99** | **5.12M** | **$199.99** | **today** (about 320k spare, enough for the router-table IPs) |

**Recommendation: $199.99 (5.12M daily queries).** It's the smallest plan that finishes in one day. The plan is monthly: after the backfill, day-to-day needs are about 2,500 new IPs a day, so you can move back down to the $9.99 plan next cycle.

**Upgrade early in the UTC day.** proxycheck.io resets daily limits at midnight UTC, and running about 4.7M queries takes several hours.

## 8. How the backfill will run (ready now)

`build/pipeline/backfill_chunks.py` runs it in chunks. Each chunk is sent, merged into the tables and checked before the next one starts, and the runner stops at the first failed check. The `unified` tables are refreshed every second chunk and at the end.

```bash
cd build/pipeline
python backfill_chunks.py --chunk 250000 --max-chunks 1   # test chunk: timing and checks
python backfill_chunks.py --chunk 1000000                 # the rest, about 5 chunks
```

**Afterwards:** `python run_sql.py sql/checks/vendor_fill_rates.sql --show` should show proxycheck.io at about 100% for every column it supplies, and `sql/checks/table_completeness.sql` should show every public IP as complete.
