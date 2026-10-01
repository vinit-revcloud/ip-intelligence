# Bot Detection — Making This a Real Source of Truth

**Date:** 2026-09-11
**Question:** can these tables be trusted to say whether traffic hitting the website is a bot?
**Today: no.** This is the plan that makes the answer yes, and it starts with being precise about
why not.

---

## 1. Two problems, and only one of them is about missing data

### Problem A — we have no confirmed bots

Everything measured so far rests on **2,105 qualified-lead IPs**, which are confirmed *humans*.
There is not a single confirmed bot in the benchmark. That is why `precision_bot` and `recall_bot`
are NULL: with no positives there is no denominator, and a detector cannot be validated against a
set that contains none of what it detects.

### Problem B — a bot is not a property of an IP

This one matters more, and no amount of extra vendors fixes it.

> An IP address describes a **network**. A bot is a **behaviour**.

A residential Comcast IP serves a real customer at 9am and a scraper running on the same household's
compromised device at 3am. iCloud Private Relay — **25% of our qualified-lead traffic** — puts
thousands of unrelated people behind one address. Asking "is this IP a bot" is the wrong question;
the answerable one is:

> **"Given everything we know about this IP, how much does it raise or lower the odds that this
> particular session is automated?"**

That is **IP reputation** — a strong input to a bot decision, not the decision itself. The final
call needs session signals too: user agent, dwell time, request pattern, conversion behaviour.

**The product should be repositioned accordingly.** These tables become the *IP reputation layer*
of bot detection, with a validated, measurable contribution — rather than claiming to be the whole
answer, which would be wrong and would eventually be caught being wrong.

---

## 2. What labels we can actually build — measured over 90 days

396,225 sessions · 150,331 distinct IPs.

| Label | IPs | Quality | Source |
|---|---:|---|---|
| **Confirmed human** | **2,105** | ★★★ strongest | Qualified leads — a person was introduced, met an agent, listed or closed |
| **Confirmed bot (self-declared)** | **484** | ★★★ strongest | `browser_agent` contains bot/crawler/spider — these announce themselves |
| Suspected bot (incumbent) | 9,954 | ★☆☆ circular | `is_bot_click = true` — another vendor's opinion, useful as a comparator only |
| Known infrastructure | ~540 | ★★★ fact | Tor exits, AWS, GCP, Cloudflare, Fastly, iCloud Relay |

**2,105 humans + 484 self-declared bots is a real labelled set** — the first one this project has
had. Small, but every row is genuine, and precision/recall become computable immediately.

**One measurement not to trust:** `duration_seconds = 0` on 322,080 of 396,225 sessions (81%). That
is a data-collection artefact, not 81% bot traffic. Do not use dwell time as a bot signal until
someone explains why four in five sessions record zero.

---

## 3. Sources to add — the bot equivalent of the Tor list

The authoritative lists work because operators publish their own ranges — fact, not opinion. The
same exists for bots and we are not using it.

| Source | What it gives | Cost |
|---|---|---|
| **Googlebot / Bingbot / other verified crawler ranges** | Published by the operator. Definitive **bot positives** | free |
| **Verified-crawler reverse DNS** (`crawl-*.googlebot.com`) | Confirms a self-declared crawler is genuine, not a spoofer claiming to be Google | free |
| **Cloud/hosting ranges** *(already loaded)* | Residential traffic from a datacenter is a strong automation signal | free |
| **AbuseIPDB** | Community abuse reports, 1,000/day free | free tier |
| **IPQualityScore** | Purpose-built bot/fraud scoring, 5,000/month free | free tier |
| **proxycheck `type = "Scraper"`** *(paid plan)* | Already in the schema once step 2 of the implementation plan lands | included |

The first two are the important ones. They turn "we have 484 self-declared bots" into a properly
sized positive class, and they let us catch the spoofing case — traffic *claiming* to be Googlebot
from an IP Google does not own is a much stronger fraud signal than either fact alone.

---

## 4. Revised minimal schema

Three tables replace the current sprawl. Everything else is derived.

### 4.1 `unified.ip_reputation` — the source of truth people query

**One row per IP.** Not per IP × vendor — that is the analytics grain, and it is the reason the
current tables cannot answer a simple question simply.

| Column | Meaning |
|---|---|
| `ip_address` | the key |
| `reputation_score` | **0–100.** 0 = certainly automated, 100 = certainly human |
| `confidence` | 0–100, how much evidence backs the score |
| `recommendation` | `allow` · `review` · `block` |
| `is_proxy` · `is_vpn` · `is_tor` · `is_datacenter` · `is_bot` · `is_compromised` · `is_scraper` · `is_anonymous` | consensus verdict across vendors, three-state |
| `vendors_answered` | how many had an opinion |
| `vendors_agreeing` | how many agreed with the consensus |
| `is_shared_infrastructure` | relay, CDN or CGNAT — the score means something different here |
| `country` · `state` · `city` · `zip_code` · `latitude` · `longitude` | consensus location |
| `first_seen` · `last_seen` · `times_seen` | **from our own traffic**, not a vendor |
| `created_at` · `updated_at` |

One row, one lookup, a usable answer. This is what an API serves.

### 4.2 `unified.ip_vendor_claims` — one row per IP × vendor

Exactly the columns Ahsan specified, geo and risk merged into one table since both are "what this
vendor said about this IP":

`ip_address` · `vendor` · `state` · `city` · `zip_code` · `latitude` · `longitude` · `timezone` ·
`is_proxy` · `is_vpn` · `is_tor` · `is_datacenter` · `is_bot` · `is_compromised` · `is_scraper` ·
`is_anonymous` · `isp` · `asn` · `created_at` · `updated_at`

### 4.3 `unified.vendor_accuracy` — one row per vendor, finally real

With a labelled set this stops being agreement and becomes **accuracy**:

| Column | Meaning |
|---|---|
| `vendor` · `capability` (geo / risk) |
| `fill_rate_pct` | how often it answers |
| **`precision_pct`** | of the IPs it called bot, how many *are* bots |
| **`recall_pct`** | of the actual bots, how many it caught |
| **`f1`** | the two combined |
| **`false_positive_rate_pct`** | of confirmed humans, how many it wrongly flagged |
| `geo_state_pct` · `geo_city_pct` · `geo_zip_pct` | against the lead's own address |
| `cost_per_1k` · `score` |
| `labelled_humans` · `labelled_bots` | the denominators, always visible |

**The denominators ship with the metrics.** A precision figure computed on 484 bots means something
different from one computed on 50,000, and the reader must be able to see which they are looking at.

### What happens to the analytics tables

`ip_geo_analytics` and `ip_intelligence_analytics` stay, unchanged in purpose — consensus votes,
match flags, working. They feed §4.3 and are never the thing an API serves.

---

## 5. How the reputation score is built

Weighted, transparent, and every input auditable:

| Signal | Weight | Direction |
|---|---:|---|
| On a published crawler range | high | → bot |
| Self-declared crawler UA, **verified** by reverse DNS | high | → bot |
| Self-declared crawler UA, **not** verified | very high | → bot *and* spoofing |
| On cloud/hosting ranges | medium | → bot |
| Tor exit | high | → bot |
| proxycheck `scraper` / `compromised` | high | → bot |
| proxycheck `risk` score | medium | proportional |
| Multiple vendors agree it is a proxy | medium | → bot |
| **Produced a qualified lead** | **very high** | **→ human, overrides most flags** |
| iCloud Relay / CDN egress | — | **suppresses the score**; shared infrastructure is not evidence about any one visitor |

Two rules that keep it honest:

1. **A qualified lead outranks a vendor flag.** If someone was introduced, met an agent and listed a
   property, they are not a bot regardless of what an IP database says.
2. **Shared infrastructure caps confidence, it does not raise the score.** 25% of qualified traffic
   is behind iCloud Relay. Scoring those as risky would block a quarter of real customers.

**Validation:** run the finished score against the labelled set. If it does not cleanly separate
2,105 humans from 484 bots, it is not ready — and that test is now possible for the first time.

---

## 6. Steps

| # | Step | Output | Time |
|---|---|---|---|
| 1 | Build the labelled set — `ipintel_curated.ip_labels` | 2,105 humans + 484 bots, one row per IP with `label` and `label_source` | 1 hr |
| 2 | Load published crawler ranges + reverse-DNS verification | a properly sized bot positive class | 2 hrs |
| 3 | Add AbuseIPDB + IPQualityScore | two purpose-built bot sources | 2 hrs |
| 4 | Collapse to `ip_vendor_claims` | the per-vendor grain, Ahsan's columns exactly | 1 hr |
| 5 | Build `vendor_accuracy` against the labels | **real precision, recall, F1, FPR** | 1 hr |
| 6 | Build `ip_reputation` with the weighted score | the one-row-per-IP source of truth | 3 hrs |
| 7 | Validate the score against the labelled set | proof it separates humans from bots | 1 hr |
| 8 | Daily job refreshes all three | stays current | 2 hrs |

Steps 1 and 2 are the unlock — everything downstream depends on having real labels. Both can start
immediately and need no new credentials.

---

## 7. What this will and will not deliver

**Will:**
- One row per IP with a score, a confidence and a recommendation — directly consumable by the
  website and other traffic segments
- Genuine per-vendor precision and recall, because there is finally something to be right or wrong
  about
- An auditable answer: every score traces to the signals that produced it

**Will not:**
- Decide whether a *session* is a bot. IP reputation is one input; the session's own behaviour is
  the other, and that lives in your analytics cycle, not here
- Work well on shared infrastructure. A quarter of qualified traffic sits behind iCloud Relay, and
  no IP-level system can separate the people behind one address

**The honest framing for downstream consumers:** *"this IP's reputation, with the evidence and the
confidence"* — not *"this visitor is a bot"*. The first is defensible and useful. The second would
be overclaiming, and the 25% relay share is exactly where it would be caught.

---

## 8. Decisions needed

1. **Reposition as the IP reputation layer?** It is what the data can honestly support, and it is
   genuinely valuable. The alternative is a bot verdict that will be wrong on shared infrastructure.
2. **Add AbuseIPDB and IPQualityScore?** Both free tier, both purpose-built for this. Current risk
   sources detect *infrastructure*, not automation.
3. **Collapse to the three-table schema**, or keep the six from the previous plan? The three answer
   the question directly; the six describe the workings.
4. **Is there a labelled fraud or invalid-traffic set anywhere in the business?** It would be worth
   more than every vendor on this list combined, and it is the one thing I cannot derive.
