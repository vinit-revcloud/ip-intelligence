# Lovable Prompt — Four Tables, Source of Truth, Agreement Rename

The benchmark now runs off a **source-of-truth table** rather than a fixed IP list, and four tables
are served. No env changes. Paste everything below as one message.

---

> Rewire the console around four tables served by the API. There is no fixed IP list any more — the
> population is whatever the qualified-lead source-of-truth table contains, currently 2,105 IPs.
>
> ## Endpoints
>
> ```
> GET /tables/vendor-overview-geo     7 rows  · one per geo vendor
> GET /tables/vendor-overview-proxy   4 rows  · one per risk vendor
> GET /tables/ip-geo                  14,735 rows · one per IP per geo vendor
> GET /tables/ip-proxy                8,420 rows  · one per IP per risk vendor
> ```
>
> Each returns `{ count, rows: [...] }`. Add a `createServerFn` per endpoint reading
> `IPINTEL_API_URL` / `IPINTEL_API_TOKEN` inside `.handler()`.
>
> ## Rename: Accuracy → Agreement
>
> Every label, header, tooltip and type. The word *accuracy* survives only where we measure against
> fact: **precision/recall against operator-published ranges**, and the Apple-verified ground truth.
> Everywhere else it is agreement with a majority, and calling that accuracy overstates it.
>
> ## 1. `/vendors` — two overview tables
>
> **Vendor Overview — Geo** (`minWidth={1180}`), sorted by `score` desc:
> Vendor · Fill Rate % · State Fill % · City Fill % · ZIP Fill % · State Agreement % ·
> City Agreement % · ZIP Agreement % · **Agreement %** · State Truth % · City Truth % ·
> ZIP Truth % · **Cost / 1k** · **Score**
>
> **Vendor Overview — Proxy** (`minWidth={1280}`), sorted by `score` desc:
> Vendor · Answered · Fill Rate % · Flagged · Detection % · Bot Flagged · Bot Identification % ·
> **False-Positive Rate %** · Precision (infra) % · Recall (infra) % · Masked-Device Flags ·
> **Cost / 1k** · **Score**
>
> - Two column groups on the geo table under shared headers: **Agreement** (vs other vendors) and
>   **Truth** (vs the qualified lead's own address). They answer different questions and must not
>   be read as one number.
> - `null` renders as an em-dash plus a neutral `Pill` "not supplied" — never 0%. DB-IP and geojs
>   publish no postal code.
> - `excluded_from_voting === true` gets a `Pill tone="warn"` "mirror — not a voter" and 85% opacity.
> - **`precision_bot_pct` and `recall_bot_pct` are always null.** Render an em-dash plus a pill
>   showing `bot_metric_status`, with a header tooltip: *"Every IP in this pool produced a qualified
>   lead, so it is a confirmed human. That makes the false-positive rate exact — any bot flag here
>   is definitively wrong. It also means there are no true bots to catch, so bot precision and
>   recall have no denominator."*
> - **False-Positive Rate is the headline column**: bold, right-aligned, `tone="bad"` above 5%.
>
> ## 2. `/raw` — the two per-IP tables
>
> A `Tabs` control, **IP Geo** and **IP Proxy**. Show **only these columns** — the rest exist for
> analytics and must not appear:
>
> **IP Geo:** `ip_address` · `vendor` · `state` · `city` · `zip_code` · `latitude` · `longitude` ·
> `timezone` · `created_at` · `updated_at`
>
> **IP Proxy:** `ip_address` · `vendor` · `is_proxy` · `is_vpn` · `is_tor` · `is_datacenter` ·
> `is_bot` · `isp` · `asn` · `created_at` · `updated_at`
>
> There is no `country_code` or `country_name` — those were removed from the table.
>
> Per tab: an IP search box, a vendor `Select`, a row counter reading
> `Showing {filtered} of {count}`, client-side pagination at 100/page, and a **Download CSV** button
> exporting the filtered rows.
>
> **Tri-state booleans render three ways: `true` → "yes", `false` → "no", `null` → em-dash with a
> neutral "no opinion" pill.** This is the most important rule on the proxy tab. A FraudLogix row
> reading all-`false` means the vendor explicitly accepted that IP; a PX12 row of all-`null` means
> it had no opinion. Those are different facts and must not look the same.
>
> ## 3. Population header
>
> On every data screen, under the subtitle, one muted line:
> `Source of truth: qualified leads · {ips} IPs · {vendors} vendors · updated {as_of_date}`
> Take the values from the overview payloads. **Do not hardcode an IP count** — the pool grows as
> new qualified leads arrive.
>
> ## Constraints
>
> Existing primitives only; semantic tokens only; no hardcoded colours, vendor names, counts or
> metric values. No router changes, no `src/routeTree.gen.ts` edits. Explicit `minWidth` on every
> table; no horizontal page overflow at 390px. Strict TypeScript, no `any`. Build must pass.
>
> **Verify:** grep for `accuracy`, `country_code`, `country_name`, and any hardcoded `511` or
> `2,071` — none should remain outside the two permitted accuracy usages.

---

## What was built in AWS

### `ipintel_curated.qualified_lead_ips` — the source of truth

Built from your query, partitioned by `ingest_date` so refreshes are incremental:

```sql
FROM sampledb.revenue_leads_plus r
JOIN unified.unified_session_summary s ON s.session_id = trim(r.utm_content)
WHERE r.furthest_stage IN ('introduced','agent_left_vm','connected','meeting_scheduled',
      'met_in_person','coming_soon','listing','in_escrow','closed','closed_booked','closed_paid')
```

**2,109 IPs · 2,579 qualified leads · 2,105 with state + ZIP · 1,855 with city · 1,699
phone-verified.** Lead dates span 2021-05-26 to 2026-09-09. Every row is a **confirmed human**,
which is what makes false-positive rate exact rather than estimated.

The pipeline now reads this table instead of a fixed IP list. A new qualified lead appears in the
next run automatically.

### Vendor Overview — Geo

| Vendor | Fill | Agreement | State Truth | City Truth | ZIP Truth | Cost/1k | **Score** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **proxycheck.io** | 95.6% | 80.5% | 59.7% | 13.0% | 5.4% | $0.00 | **77.0** |
| IP2Location DB11 | 94.9% | 71.7% | 58.1% | 14.6% | 3.4% | $0.00 | **68.0** |
| MaxMind GeoLite2 | 95.9% | 69.8% | **64.3%** | **20.4%** | **10.3%** | $0.00 | **66.9** |
| DB-IP combined | 66.7% | 75.3% | 56.5% | 11.9% | — | $0.00 | **50.2** |
| geojs.io *(mirror)* | 64.5% | 75.2% | 64.3% | 20.6% | — | $0.00 | **48.5** |
| ipinfo.io | **49.9%** | **85.8%** | 54.3% | 11.9% | 4.0% | $0.00 | **42.8** |
| ipwho.is | **49.9%** | 78.3% | 53.7% | 11.1% | 1.8% | $0.00 | **39.1** |

**ipinfo.io has the highest agreement but the lowest score**, because its free tier capped at 1,050
of 2,105 IPs — a 49.9% fill rate. It is the most consistent source and the least available one, and
the multiplicative score is what surfaces that trade-off.

**MaxMind leads on every truth column** — the comparison against the lead's own address — while
ranking 3rd on agreement. Same inversion as before: agreeing with the crowd and being right are
different things.

### Vendor Overview — Proxy

| Vendor | Answered | Flagged | Bot Flags | **FPR** | Precision | Recall | Masked-Device | **Score** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Authoritative lists | 2,105 | 540 | 0 | 0.0% | 100% | 100% | 0 | **100.0** |
| **proxycheck.io** | 2,105 | 556 | 0 | **0.0%** | **97.1%** | **100%** | 0 | **99.2** |
| FraudLogix (TUNE) | 1,686 | 392 | 10 | **0.6%** | 0.5% | 0.4% | 52 | **46.9** |
| IP2Proxy PX12 | 5 | 5 | 0 | 0.0% | 0.0% | 0.0% | 0 | **0.0** |

### Your "latest decision" rule changed the FraudLogix verdict substantially

Using the **latest** `access_control_decision` per IP instead of "ever flagged across all history"
moved FraudLogix's false-positive rate from **19.9% to 0.6%** — bot flags fell from 329 to 10.

Most of those historical bot flags were superseded by a later ACCEPTED decision on the same IP.
Judging a vendor on its full flag history rather than its current verdict was making it look far
worse than it is. Your instinct on this was right and it materially changes the recommendation.

### ACCEPTED and MASKED_DEVICES, as implemented

| `fraud_reason` | Rows | is_proxy | is_bot | is_masked_device |
|---|---:|---:|---:|---:|
| ACCEPTED | 1,196 | 0 | 0 | 0 |
| *(no answer)* | 419 | — | — | — |
| PROXY | 371 | 371 | 0 | 0 |
| MASKED_DEVICES | 52 | 0 | **0** | **52** |
| NON_HUMAN_SCRIPT | 5 | 0 | **5** | 0 |

**ACCEPTED sets every boolean to `false` explicitly** — a real negative, not a null.

**MASKED_DEVICES sets none of the five booleans.** It means the *device fingerprint* was obscured —
user-agent spoofing, canvas/WebGL blocking, anti-fingerprinting browsers, privacy extensions. That
is a device signal, not a network or automation one. Evidence: **195 confirmed humans in this pool
carry it**, and 25% of the pool is on iCloud Private Relay, so masking mostly tracks Apple privacy
features used by real customers. It gets its own `is_masked_device` column instead.

Only `BOT_GENERATED` and `NON_HUMAN_SCRIPT` set `is_bot`.
