# IP2Location Lite DB11 and PX12 on TUNE and session IPs

We looked up every unique IP from TUNE clicks and from sessions in the two free IP2Location files. Country is almost always US, so geo here means state, city, and ZIP. FraudLogix tags on TUNE clicks are the bot labels we compared against.

## Data we used

| Source | IP column | Unique IPs |
|---|---|---|
| `raw.raw_tune_clicks` (all history) | `ip` | 4,528,275 |
| `unified.unified_session_summary` (all history) | `session_ip` | 1,990,844 |
| Combined, counting each IP once | IPv4 (30 IPv6 session IPs left out of lookups) | 4,936,386 |

Athena through 18 Aug 2026. Lookups against IP2Location LITE DB11 and IP2Proxy LITE PX12. TUNE bot tags: `access_control_decision`, `access_control_reason_code`.

## What sessions already have on each IP

Every row in `unified_session_summary` has IP fields. Below is whether those fields are actually filled, for all 1,990,844 session IPs. Empty and `-` count as not filled. `ip_is_vpn` is never filled.

| Column | Session IPs filled | Share of session IPs | Rows filled |
|---|---|---|---|
| `ip_region_name` (state) | 1,347,491 | 67.7% | 76.6% |
| `ip_city_name` | 1,347,491 | 67.7% | 76.6% |
| `ip_zip_code` | 1,346,120 | 67.6% | 76.6% |
| `ip_latitude` / `ip_longitude` | 1,347,518 | 67.7% | 76.6% |
| `ip_time_zone` | 1,347,523 | 67.7% | 76.6% |
| `ip_area_code` | 1,347,048 | 67.7% | 76.6% |
| `ip_district` | 1,339,799 | 67.3% | 76.4% |
| `ip_country_code` | 1,347,518 | 67.7% | 76.6% |
| `ip_is_proxy` | 1,347,523 | 67.7% | 76.6% |
| `ip_is_vpn` | 0 | 0% | 0% |

| State + city + ZIP together | Session IPs | Share |
|---|---|---|
| All three filled | 1,346,120 | 67.6% |
| Missing state, city, or ZIP | 644,724 | 32.4% |

TUNE clicks only store `country_code` on the click. They do not store state, city, or ZIP today, so those 4.5 million TUNE IPs have no state/city/ZIP on the click row.

## State, city, ZIP from Lite DB11

DB11 columns we used: country, region (state), city, latitude, longitude, ZIP, time zone. We looked up every IPv4 from TUNE and sessions.

| Field from DB11 | TUNE IPs | Session IPs | All unique IPs |
|---|---|---|---|
| Looked up (IPv4) | 100% | 100% | 100% |
| State filled | 99.97% | 99.97% | 99.97% |
| City filled | 99.97% | 99.97% | 99.97% |
| ZIP filled | 99.92% | 99.81% | 99.83% |

Of the 644,724 session IPs that are missing state, city, or ZIP on the session table, DB11 still returns state and city for 99.98% of them, and ZIP for 99.7%.

## What is in Lite PX12, and how often our IPs hit it

PX12 is a list of proxy ranges, not a row for every IP. Columns in the file:

| Column | What it is |
|---|---|
| `ip_from`, `ip_to` | The IP range |
| `proxy_type` | Type of proxy. In this Lite file the only value is PUB (public proxy). |
| `country_code`, `country_name`, `region_name`, `city_name` | Location of the proxy |
| `isp`, `domain` | ISP and domain |
| `usage_type` | How the range is used (DCH = data center, ISP, EDU, etc.) |
| `asn`, `as` | Network number and name |
| `last_seen` | How recently it was seen as a proxy |
| `threat` | Threat label, often empty |
| `provider` | Proxy provider, often empty |
| `fraud_score` | 0–100 score |

Lite PX12 does not include VPN, TOR, or residential proxies. Those types are not in this file.

| Check | Result |
|---|---|
| Our unique IPs that fall in a PX12 range | 16,751 of 4.9 million (0.34%) |
| `proxy_type` on those hits | PUB only |
| `usage_type` on those hits | 96.5% DCH (data center) |
| `fraud_score` on those hits | Almost all 80 or higher |
| `isp` / `asn` filled on those hits | Yes |
| `threat` / `provider` filled on those hits | Rarely |

## A brand-new IP

Say we see an IPv4 we have never stored. We only have these two free files.

| What we want to know | Can we get it from the free files? |
|---|---|
| State | Yes (DB11, ~100% of IPv4) |
| City | Yes (DB11, ~100% of IPv4) |
| ZIP | Yes (DB11, ~99.8% of IPv4) |
| Public proxy / data-center on the Lite list | Only if it is in that 0.34% |
| VPN or TOR | No. Not in Lite PX12. |
| Bot | No. FraudLogix is not coming from this file. |

## FraudLogix tags vs Lite PX12

On TUNE, about 15% of unique IPs are FLAGGED at least once. The same IP can be ACCEPTED on one click and FLAGGED on another.

| | Count | Share |
|---|---|---|
| Distinct TUNE IPs | 4,528,275 | 100% |
| Ever FLAGGED | 661,316 | 14.6% |
| Ever FLAGGED **and** in Lite PX12 | 6,457 | 0.98% of flagged IPs (0.14% of all TUNE IPs) |
| Ever FLAGGED, **not** in Lite PX12 | 654,859 | 99.0% of flagged IPs |

Almost all FraudLogix-flagged IPs are missing from the free proxy file.

We also asked: for IPs with each FraudLogix reason, how many are also in Lite PX12? If Tune were using this free list, PROXY and DATA_CENTER would mostly match. They do not.

| FraudLogix reason | TUNE IPs with this tag | Also in Lite PX12 |
|---|---|---|
| PROXY | 336,011 | 0.6% |
| NON_HUMAN_SCRIPT | 179,013 | 0.7% |
| ABNORMAL_TRAFFIC_PATTERNS | 105,199 | 0.4% |
| MASKED_DEVICES | 89,409 | 1.3% |
| 10 (undocumented code) | 82,092 | 0.9% |
| BASIC_FRAUD | 77,599 | 1.0% |
| BOT_GENERATED | 22,432 | 0.5% |
| VPN | 4,004 | 1.8% |
| DATA_CENTER | 2,666 | 5.9% |
| TOR | 29 | 3 IPs |

Tune’s PROXY tag covers hundreds of thousands of IPs. Lite PX12 only has a couple of thousand of those. So we cannot read Tune’s bot/proxy rules off this free file, and we cannot tag a new IP as bot/not-bot from PX12 the way FraudLogix does.

## What this means

| Need | Free files |
|---|---|
| State, city, ZIP for new IPv4s (TUNE and sessions) | Use DB11. It fills these fields for essentially every IPv4, including the 32% of session IPs that have no state/city/ZIP on the session table today. |
| Proxy / bot / VPN / TOR on a new IP | Lite PX12 is too small and PUB-only. Keep FraudLogix on TUNE clicks. Do not build bot detection on Lite PX12. |
