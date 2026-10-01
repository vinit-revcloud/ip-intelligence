# Lovable prompt — the six unified tables

Paste everything below the line into Lovable as one message.

---

Rebuild the data layer of this app against six new live tables. Replace whatever table definitions, mock rows and fetch helpers currently exist. Do not invent columns: the lists below are exhaustive and exact.

## API

Base URL: `https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/`

Every request needs the header `Authorization: Bearer xEVWxcFa--qFzYdEqaVNOkDE5R4VG6VMu5se-2WddbA`.

Store the token in a single module (`src/lib/api.ts`) and read the base URL from `VITE_IPINTEL_API_URL`. No component may call `fetch` directly.

Six endpoints:

| Endpoint | Rows |
|---|---|
| `GET /tables/ip-geo` | 14,735 |
| `GET /tables/ip-geo-analytics` | 14,735 |
| `GET /tables/ip-intelligence` | 8,420 |
| `GET /tables/ip-intelligence-analytics` | 8,420 |
| `GET /tables/vendor-overview-geo` | 7 |
| `GET /tables/vendor-overview-proxy` | 4 |

### Pagination contract

All six accept `limit` and `offset` query parameters. Default limit 2000, maximum 5000. The two overview endpoints return every row in one call, so do not paginate those.

Response shape, identical on all six:

```json
{ "count": 14735, "total": 14735, "limit": 2000, "offset": 0,
  "next_offset": 2000, "rows": [] }
```

- `total` is the size of the whole table.
- `count` is how many rows survived the filters.
- `next_offset` is null on the last page. Keep requesting until it is null.

Write one `fetchAll(endpoint, params)` helper that loops on `next_offset` and concatenates. Show a progress indicator while it loops, because the geo analytics table needs eight round trips.

### Filters

The four per-IP endpoints accept `ip` and `vendor` query parameters. Both are exact matches applied on the server before pagination. Use them for the IP drill-down and the vendor detail page instead of downloading everything and filtering in the browser.

## Table 1 — ip_geo (10 columns)

`ip_address`, `vendor`, `state`, `city`, `zip_code`, `latitude`, `longitude`, `timezone`, `created_at`, `updated_at`

This is the raw vendor answer and nothing else. No scores, no agreement, no consensus. One row per IP per vendor across seven vendors, so an IP always has seven rows even when a vendor returned nothing.

Null means that vendor had no answer for that field. Render nulls as an em-dash, never as an empty cell and never as zero. Latitude and longitude are numbers, everything else is a string.

## Table 2 — ip_geo_analytics (23 columns)

Joins to `ip_geo` on `ip_address` plus `vendor`. Same 14,735 rows.

`ip_address`, `vendor`, `has_answer`, `consensus_state`, `consensus_city`, `consensus_zip`, `state_votes`, `city_votes`, `zip_votes`, `state_matches_consensus`, `city_matches_consensus`, `zip_matches_consensus`, `truth_state`, `truth_city`, `truth_zip`, `state_matches_truth`, `city_matches_truth`, `zip_matches_truth`, `fields_answered`, `fields_judged`, `fields_matched`, `row_agreement_pct`, `row_truth_agreement_pct`

The three groups mean different things:

- **Consensus** is what the other vendors said. The vote columns say how many vendors backed the winning value. A field is only judged when at least two vendors voted on it.
- **Truth** is the address on the lead record. Treat it as a weak reference, not ground truth. It describes the property rather than always the person, so city and zip agreement is low for every vendor and that is expected.
- Row agreement is agreement with consensus. Row truth agreement is agreement with the lead address. They are different numbers, so label them differently and never average them together.

The six `matches` columns are tri-state. See the rendering rule below.

## Table 3 — ip_intelligence (14 columns)

`ip_address`, `vendor`, `is_proxy`, `is_vpn`, `is_tor`, `is_datacenter`, `is_bot`, `is_compromised`, `is_scraper`, `is_anonymous`, `isp`, `asn`, `created_at`, `updated_at`

The compromised, scraper and anonymous columns are new. Add three columns to every proxy grid and three toggles to the filter panel. All eight boolean columns are tri-state.

Four vendors here, not seven: proxycheck_io, fraudlogix_tune, ip2proxy_px12, authoritative_lists.

## Table 4 — ip_intelligence_analytics (17 columns)

Joins to `ip_intelligence` on `ip_address` plus `vendor`. Same 8,420 rows.

`ip_address`, `vendor`, `has_answer`, `flagged`, `fraud_reason`, `is_masked_device`, `risk_score`, `known_infrastructure`, `infrastructure_list`, `verdict_class`, `bot_false_positive`, `row_agreement_pct`, `confidence`, `first_seen`, `last_seen`, `times_seen`, `observed_at`

The verdict column has exactly five values. Render each as a coloured pill:

| Value | Label | Colour |
|---|---|---|
| `confirmed_by_published_range` | Confirmed | green |
| `agreed_not_flagged` | Clean | grey |
| `unconfirmed_flag` | Unconfirmed flag | amber |
| `missed_known_infrastructure` | Missed | red |
| `no_answer` | No answer | outline only |

The masked-device column is a device-fingerprint signal, not a bot signal. Show it in its own column with a neutral icon. Never fold it into the bot count and never let it drive a flagged verdict.

Confidence, first seen and times seen are null on every row today. Keep the columns defined but hide them behind the column picker, off by default.

## Table 5 — vendor_overview_geo (7 rows, 11 columns)

`vendor`, `ips_tested`, `fill_rate_pct`, `agreement_pct`, `state_truth_pct`, `city_truth_pct`, `zip_truth_pct`, `cost_per_1k`, `score`, `excluded_from_voting`, `as_of_date`

Sort by score descending. This is the geo leaderboard.

Score is agreement multiplied by fill rate, so a vendor that answers half the time cannot win on agreement alone. Put that sentence in a tooltip on the score header.

The exclusion flag is true for exactly one vendor, geojs_io. It returns values identical to maxmind_geolite2 on every field, so counting both would double one opinion. Show the row with a small "not a voter" badge and a tooltip saying it mirrors MaxMind. Do not hide the row.

## Table 6 — vendor_overview_proxy (4 rows, 19 columns)

`vendor`, `ips_tested`, `answered`, `fill_rate_pct`, `flagged`, `bot_flagged`, `bot_identification_pct`, `false_positive_rate_pct`, `compromised_flagged`, `scraper_flagged`, `anonymous_flagged`, `precision_infra_pct`, `recall_infra_pct`, `precision_bot_pct`, `recall_bot_pct`, `bot_metric_status`, `cost_per_1k`, `score`, `as_of_date`

Sort by score descending.

Bot precision and bot recall are null on every row. Do not render a zero and do not render an empty cell. Render the text of the bot metric status column instead, in muted type. It currently reads "needs a bot-labelled pool". The infrastructure precision and recall columns are real numbers and display normally.

## Tri-state rule, applies to every boolean column

A boolean here has three states and the third one is not "no".

| Value | Cell | Meaning |
|---|---|---|
| `true` | "Yes", solid pill | the vendor affirmed it |
| `false` | "No", outline pill | the vendor explicitly denied it |
| `null` | em-dash, muted | the vendor never answered |

Never coerce null to false. Never count null rows in a denominator. When you compute any percentage in the UI, divide by the number of rows where `has_answer` is true, not by the row count.

Add a legend showing the three states once per page that contains a boolean grid.

## Naming

The word is **Agreement**, never Accuracy. Check headers, tooltips, chart axes, CSV export headers and empty-state copy. Nothing in this app compares a vendor against verified ground truth, so "accuracy" would be a false claim.

## Scope

There is no revenue in this product. If any revenue field, chart, filter, route or API call still exists, delete it. This app compares vendors and nothing else.

## Pages to build or update

1. **Geo leaderboard** — table 5, sorted by score, with the score tooltip and the geojs badge.
2. **Proxy leaderboard** — table 6, sorted by score, with the bot metric status text where the two bot columns are null.
3. **IP explorer** — search an IP, then call all four per-IP endpoints with the `ip` filter. Show the seven geo rows and the four intelligence rows side by side, each with its analytics twin joined on `ip_address` plus `vendor`.
4. **Vendor detail** — pick a vendor, call the per-IP endpoints with the `vendor` filter, show its own rows plus its leaderboard line.

Keep the existing visual style. Do not restyle anything that is not listed here.
