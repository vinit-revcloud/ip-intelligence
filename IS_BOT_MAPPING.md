# STEP 2 STANDARD (19 Sep 2026, owner decision): `is_bot` = bad signal

**This replaces the narrower "automation only" rules described further down.** The owner's goal is to catch bad clicks and
signals, not only bots, so every reason a vendor flags now counts:

| Vendor | `is_bot` = true (bad) when | `bot_reason` |
|---|---|---|
| FraudLogix | The IP's **latest** decision is FLAGGED, for **any** reason: PROXY, VPN, MOBILE_PROXY_SIGNALS, BOT_GENERATED, NON_HUMAN_SCRIPT, ABNORMAL_TRAFFIC_PATTERNS, BASIC_FRAUD, MASKED_DEVICES, SPOOFED, DATA_CENTER, TOR, TOR_EXIT_NODE, OTHER_REASON, 8, 9, 10, NOT_APPLICABLE | The reason code |
| FraudLogix, no decision (filled from proxycheck.io) | proxycheck.io says bad | `PROXYCHECK_IO:` + its reason |
| proxycheck.io | Proxy, VPN, TOR, datacenter, compromised or scraper; any proxy/threat type (SOCKS, HTTP(S), Shadowsocks, OpenVPN, VPN, Compromised Server, TOR, Hosting, Scraper, Inference Engine); a cloud network (17 ASNs); or risk score 67+ ("very dangerous") | The type, or VPN / PROXY / DATA_CENTER / `CLOUD_ASN:<asn>` / `HIGH_RISK:<score>` |
| IP2Proxy PX12 | Listed (public proxy, VPN or datacenter address) | Its listing, e.g. `PUB/DCH/SPAM` |

- Not bad: `is_bot` = false, `bot_reason` = `NOT_BOT`. Empty only where the vendor gave no answer.
- Under this standard `is_bot` always equals `is_flagged`, and a daily check fails the run if they ever differ.
- **Per IP:** the IP is bad if FraudLogix **or** proxycheck.io says so.
- The old narrow meaning is still recoverable from `bot_reason`: BOT_GENERATED, NON_HUMAN_SCRIPT, SPOOFED, DATA_CENTER, TOR, SOCKS*, HTTP*, COMPROMISED_SERVER, SCRAPER, CLOUD_ASN:*.

**Result (unified, 19 Sep 01:08 IST publish):**

| Vendor | Rows | Bad | Not bad | Empty |
|---|---|---|---|---|
| FraudLogix | 4,533,991 | 612,561 | 3,921,430 | 0 |
| proxycheck.io | 757,199 | 92,212 | 664,987 | 0 |
| IP2Proxy PX12 | 4,989,206 | 16,873 | 0 | 4,972,333 (not listed) |

Public IPs with a FraudLogix or proxycheck.io answer: 4,989,122. Of those, **687,238 are bad**.

**What it means for real customers:**
- **535 of 1,044 paying IPs (51%) are now marked bad.** Almost all of it is VPN (300) and PROXY (185): real customers on iCloud Private Relay, corporate VPNs and mobile proxies. Other reasons: MASKED_DEVICES 23, ABNORMAL_TRAFFIC_PATTERNS 16, MOBILE_PROXY_SIGNALS 5, BASIC_FRAUD 3, BOT_GENERATED 3, SOCKS5 2, NON_HUMAN_SCRIPT 1, DATA_CENTER 1.
- **Known fakes: 24 of 40 (60%) are marked bad.**
- **Use `bot_reason` to choose how strict to be.** Excluding VPN/PROXY/MOBILE_PROXY_SIGNALS brings paying customers wrongly marked down to about 5% at most (49 of 1,044).

**Applied by:** `build/pipeline/step2_apply_standard.py` (all existing rows) and `vendors.py` / `apply.py` (new answers, daily).
**Rollback snapshots:** `ipintel_curated.ip_intelligence` 2239472014142278690; `ip_intelligence_analytics` 1972227255402150572.
**Code backup:** `archive/deployed-code-before-step2-standard-2026-09-19/`.

---

# How every column in `ip_intelligence` is filled, per vendor

Updated 18 Sep 2026. Code: `build/pipeline/src/vendors.py`. Existing rows were brought in line on 18 Sep 11:09 UTC
(rollback point: `ipintel_curated.ip_intelligence` snapshot `4849693903920381688`).

## The rule for empty cells

A cell is empty (NULL) **only** when the vendor gave no answer for that IP, or never supplies that column at all.
Wherever a vendor answered, every column it can support is true or false.

**Checked after the update:** rows where the vendor answered but `is_bot` is still empty = **0** for every vendor.

## `is_bot`: which vendor answers mean bot

No vendor except FraudLogix has a bot field, so `is_bot` is built from each vendor's own answer, using only signals
that are **automated traffic, not people**. Each rule was tested on the 427 IPs that produced revenue (known humans)
before it was used:

| Vendor | `is_bot` = true when | `is_bot` = false when | Empty when | Paying customers wrongly flagged |
|---|---|---|---|---|
| **FraudLogix** | Reason `BOT_GENERATED`, `NON_HUMAN_SCRIPT`, `DATA_CENTER`, `SPOOFED`, `TOR`, `TOR_EXIT_NODE` | Accepted, or flagged for another reason (proxy, VPN, mobile proxy…) | FraudLogix saw the click but never decided | 1 of 427 (0.23%) |
| **proxycheck.io** | Type SOCKS4, SOCKS5, HTTP, HTTPS (open proxies), Compromised Server, **Scraper** (added 18 Sep; 0 of 757,199 answers carry it so far), TOR, Hosting, **or the IP is on a cloud / server-hosting network** (AWS, Google Cloud, Azure, DigitalOcean, Hetzner, OVH, Linode, Vultr, Alibaba, Oracle, Leaseweb, Contabo, Aruba, DataCamp, M247, UK-2) | Business, Residential, Wireless, or no type, on an ordinary network | Never: every answered row is filled | 2 of 427 (0.47%); the cloud rule alone hit 0 |
| **IP2Proxy PX12** | Listed with usage datacenter (DCH), CDN or search-engine spider (SES), **or** threat BOTNET, SCANNER, SPAM | Listed for another use (education, ISP, mobile…) with no threat | The IP is **not on its list**: absence from a proxy list is not an answer | 0 of 427 |

**Why the cloud rule was added (18 Sep 11:20 UTC):** proxycheck.io labels AWS and other cloud servers "Business" or VPN, never "Hosting". In your sample, `3.142.51.77` and `18.225.175.238` (Amazon) had `is_bot` false. A person does not browse from a cloud server. The rule uses proxycheck.io's ASN, flagged 0 of 427 paying customers, and added 11,105 bot rows.

- **Deliberately excluded:** Akamai, Cloudflare and Fastly (they carry iCloud Private Relay, which paying customers use), Google AS15169, and general carriers such as Cogent AS174 (both carry ordinary customer traffic).

**Rejected on the evidence:**
- **proxycheck.io "Business":** it would flag 90 of 427 paying customers (21%). It is ordinary office and home broadband.
- **VPN or proxy on its own** (any vendor): it flags about half of paying customers, mostly iCloud Private Relay users.

## Result (18 Sep, all rows)

| Vendor | Rows | `is_bot` true | `is_bot` false | Empty | Why the empty ones are empty |
|---|---|---|---|---|---|
| FraudLogix | 4,533,979 | 84,137 | 4,363,058 | 86,784 | Click seen, no FraudLogix decision |
| proxycheck.io | 282,506 | **13,449** | 269,057 | **0** | — |
| IP2Proxy PX12 | 4,989,117 | 16,348 | 525 | 4,972,244 | Not on IP2Proxy's list |

**After tonight's proxycheck.io upgrade,** every IP gets a proxycheck.io row, and with it a filled `is_bot`. That gives
every IP at least one reasonable source.

## Every other column

| Column | FraudLogix | proxycheck.io | IP2Proxy PX12 |
|---|---|---|---|
| `is_proxy` | Reason PROXY or MOBILE_PROXY_SIGNALS | `proxy` = yes | Listed (always true) |
| `is_vpn` | Reason VPN | `vpn` = yes | Proxy type VPN |
| `is_tor` | Reason TOR / TOR_EXIT_NODE | Type TOR | Proxy type TOR |
| `is_datacenter` | Reason DATA_CENTER | Type Hosting (not Business: a 400-address test showed Business is broadband) | Usage DCH or CDN |
| `is_bot` | See above | See above | See above |
| `is_compromised` | Never supplied (empty) | Type Compromised Server | Never supplied (empty) |
| `is_scraper` | Never supplied (empty) | Type Scraper | Never supplied (empty) |
| `is_anonymous` | Never supplied (empty) | Proxy or VPN, or an anonymity operator | Never supplied (empty) |
| `isp`, `asn` | Never supplied (empty) | Provider and ASN | Its ISP and ASN (listed IPs only) |

"Never supplied" means the vendor does not return that information. It is not missing data, and it cannot be filled
without inventing it.

## How to use it
- **Proxy / VPN for any IP:** FraudLogix where it decided, which is its standalone strength (lowest wrong-flag rate on paying customers, 22.4%); otherwise proxycheck.io.
- **Bot for any IP:** `is_bot` = true on **any** vendor row is a strong sign. Together these rules flag well under 1% of paying customers.
- **For a decision per IP,** use the evidence-based verdict (`SESSION_IP_BOT_VERDICT.md`), which adds session behaviour.

## Check it yourself

```sql
SELECT vendor, count(*) AS rows_, count_if(is_bot) AS bot_true, count_if(NOT is_bot) AS bot_false,
       count_if(is_bot IS NULL) AS bot_empty,
       count_if(is_bot IS NULL AND is_proxy IS NOT NULL) AS empty_but_answered   -- must be 0
FROM unified.ip_intelligence GROUP BY vendor;
```

## FraudLogix "no decision" rows are resolved through proxycheck.io

FraudLogix only decides on some clicks. **86,784 IPs** have a FraudLogix row with no decision (every column empty).

- **Queued:** on 18 Sep, the 86,330 of them that are public and had no proxycheck.io answer were queued (reason `fraudlogix_undecided`). The other 423 already had one; 31 are private addresses that no vendor can answer.
- **First in line:** the queue is always sent first. So they are answered in the first chunk after tonight's plan upgrade, or over the next 2–3 mornings at 50,000 a day.
- **When answered,** each gets a proxycheck.io row with every column filled, `is_bot` included. The FraudLogix row stays as it is: it is FraudLogix's record, and inventing a decision FraudLogix never made would be false data.
- **To answer "is this IP a bot or proxy?":** for **bot**, an IP is a bot if FraudLogix **or** proxycheck.io says so. A cloud server FraudLogix accepted is still a cloud server. For **proxy/VPN**, read FraudLogix when it decided, otherwise proxycheck.io. After the backfill, every IP has at least one of the two.

```sql
-- One answer per IP.
-- Bot: true if FraudLogix OR proxycheck.io says bot (either vendor's bot sign is strong: under 1% of paying customers).
-- Proxy/VPN: FraudLogix when it decided (lowest wrong-flag rate), otherwise proxycheck.io.
SELECT ip_address,
       CASE WHEN count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND is_bot IS NOT NULL) = 0 THEN NULL
            ELSE bool_or(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND coalesce(is_bot, false)) END AS is_bot,
       coalesce(max(CASE WHEN vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL THEN vendor END),
                max(CASE WHEN vendor = 'proxycheck_io' THEN vendor END)) AS proxy_source,
       coalesce(max(CASE WHEN vendor = 'fraudlogix_tune' AND is_proxy IS NOT NULL THEN CAST(is_proxy OR is_vpn AS integer) END),
                max(CASE WHEN vendor = 'proxycheck_io' THEN CAST(is_proxy OR is_vpn AS integer) END)) = 1 AS is_proxy_or_vpn
FROM unified.ip_intelligence
GROUP BY ip_address;
```

## Accuracy overview (how much to trust each answer)

Truth: the 2,768 IPs that produced a lead from 18 Jun to 9 Sep 2026, labelled by revenue (427 real people). Full detail: `VENDOR_ANALYTICS.md`, `SESSION_IP_BOT_VERDICT.md`.

| Signal | Real people wrongly flagged | Use it for |
|---|---|---|
| **`is_bot` = true** (any vendor, rules above) | **under 1%** | **Bot decisions.** Safe to exclude or block |
| FraudLogix proxy/VPN flag | 22.4% | Proxy/VPN reporting; not blocking on its own |
| proxycheck.io proxy/VPN flag | 32.6% (mostly iCloud Private Relay) | Proxy/VPN reporting; not blocking on its own |
| IP2Proxy listing | too few answers to judge | Supporting evidence only |

**Limit:** `is_bot` catches **infrastructure** bots: cloud servers, open proxies, compromised hosts and FraudLogix's bot reasons. A bot on a home network with a normal browser still reads as false. Those need session behaviour (the evidence-based verdict), which no IP vendor can see.

## Step 1 complete: no unresolved public IP (18 Sep 13:25 UTC)

**Fill rules for FraudLogix rows** (`apply.fill_fraudlogix_from_proxycheck`, run after every proxycheck.io merge):

| FraudLogix row | Filled from proxycheck.io | `is_bot` | Marked |
|---|---|---|---|
| Empty (FraudLogix never decided) | Every data column: proxy, vpn, tor, datacenter, compromised, scraper, anonymous, isp, asn | **Left empty** until the bot standard (step 2) is agreed | `fraud_reason` = `FILLED_FROM_PROXYCHECK_IO` in `ip_intelligence_analytics` |
| Decided by FraudLogix | Only the columns FraudLogix never supplies: compromised, scraper, anonymous, isp, asn | FraudLogix's own value kept | Not marked (FraudLogix's decision stands) |

A later real FraudLogix decision replaces the filled values in the daily load. Accuracy work uses real decisions only
(exclude `FILLED_FROM_PROXYCHECK_IO`).

**Result on `unified.ip_intelligence`:**

| Check | Value |
|---|---|
| Public IPs with no FraudLogix decision and no proxycheck.io answer | **0** (the 90 left are private 10.x / 172.16.x addresses; no vendor can answer them) |
| Empty FraudLogix rows | **0** (86,784 filled and marked) |
| proxycheck.io rows | 757,084, none empty |
| Public IPs complete (risk and location) | 4,989,020 of 4,989,024; the other 4 have no location from any vendor |

**How it got there** (18 Sep, after the plan upgrade to 5.12M/day):
- **12:24 UTC:** a chunk sent 373,482 queries (the queue first); 746,529 rows added; 13 of 13 checks passed.
- **12:49:** 100,029 queries for every remaining unresolved IP; 199,998 rows added; 13 of 13 checks passed.
- **13:14:** 1,209 IPs with no location sent.
- **Code fixes made on the way:** backfill runs now send the day's queued batches from the upgraded headroom; batches already planned count towards a chunk's size; unresolved IPs are selected first.
- **Next:** step 2 (the bot standard), then step 3 (proxycheck.io for the about 4.23M decided IPs, which also fills ISP and ASN on their FraudLogix rows).

## `is_flagged`, `flagged_reason`, `bot_reason` (added 18 Sep 2026)

These three columns live in `ip_intelligence` and are kept current by both daily jobs (`apply.refresh_flag_columns`).
- **Empty (NULL)** only where the vendor gave no answer.
- **Answered but not flagged** reads `NOT_FLAGGED`.
- **Answered but not bot** reads `NOT_BOT`.

| Vendor | `is_flagged` | `flagged_reason` | `bot_reason` (when `is_bot` = true) |
|---|---|---|---|
| FraudLogix | Latest decision is FLAGGED | FraudLogix reason code: PROXY, BOT_GENERATED, ABNORMAL_TRAFFIC_PATTERNS, MASKED_DEVICES, 10… | The same reason code |
| FraudLogix, filled from proxycheck.io | proxycheck.io's flag | `PROXYCHECK_IO:` + proxycheck.io's reason, e.g. `PROXYCHECK_IO:VPN` | Empty (is_bot waits for step 2) |
| proxycheck.io | Any of proxy, vpn, tor, datacenter, bot, compromised, scraper | Its proxy/threat type (SOCKS5, COMPROMISED_SERVER, TOR, SCRAPER…), else VPN / PROXY / DATA_CENTER / CLOUD_ASN | Its type, or `CLOUD_ASN:<asn>` |
| IP2Proxy PX12 | Listed | proxy/usage/threat, e.g. `PUB/DCH/SPAM` | The same |

**First fill (18 Sep 16:40 UTC):**
- **Rows filled:** 5,308,063, which is every answered row.
- **Checks passed:** every answered row has `is_flagged` and `flagged_reason`, and `bot_reason` is filled exactly when `is_bot` is.
- **Rollback point:** snapshot `7634772127020019789`.

**Fixed the same day:** the IP2Proxy rule now reads usage and threat values made of several parts (e.g. `ISP/MOB` with `BOTNET`). This corrected 2 rows to bot.

**`unified.ip_intelligence`:** the owner added the columns on 18 Sep. They have been filled since the 19:01 UTC publish and match `ipintel_curated` row for row.
