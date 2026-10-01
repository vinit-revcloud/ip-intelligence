# IP Intelligence Platform — Complete Build Log

**Read this top to bottom and you will understand the whole system.** It is the single record of
what exists, why it was built that way, what was measured, and how to rebuild any of it.


|                    |                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------- |
| **Status**         | Source of truth is a live table · 4 tables served · vendor-comparison scope only |
| **Last updated**   | 2026-09-10 |
| **AWS account**    | 221490242148 · **Region** us-west-2                                                         |
| **Build identity** | `arn:aws:iam::221490242148:user/source_creation_tool_user` (underscores, not hyphens)       |
| **CLI profile**    | `source-creation-tool`                                                                      |


> Every table here can be rebuilt from the SQL in §6 and §7. That is deliberate: the previous
> attempt at this project was lost because its SQL existed only inside a chat session.

---



## 1. What this project is

The business buys IP intelligence from several vendors. Each claims to say **where** an IP is and
**what** it is (clean, proxy, VPN, datacenter, bot). They disagree constantly, they cost money, and
acting on a wrong claim has direct revenue consequences — block a real customer and you lose a sale;
trust a bad IP and you pay for fraudulent traffic.

**This platform is the referee.** It is not a fraud-blocking system. It is a vendor quality
workbench that answers, with evidence: which source is actually right, where they disagree, and what
enforcing each one would cost in real revenue.

Two rules shape everything:

1. **A source is a vendor *product*, not a company.** IP2Location LITE DB11 and IP2Proxy PX12 are
  two separate sources.
2. **Adding a vendor must never require a schema change.** Vendors live in rows; results live in
  tall tables keyed by `vendor_product_id`. There is never a `maxmind_score` column.

**The split:** Lovable owns the UI. AWS owns every number, every credential and every long-running
job. No vendor key and no Athena query ever reaches a browser.

---



## 2. Where things stand


| Phase   | Scope                                                                | Status                   |
| ------- | -------------------------------------------------------------------- | ------------------------ |
| **P0**  | Workgroups, Glue databases, rescue backup                            | ✅ Done                   |
| **P1**  | 4.9M-IP data foundation and enrichment join                          | ✅ Done                   |
| **P2**  | 485-IP vendor benchmark, 11 sources                                  | ✅ Done                   |
| **P3**  | Findings API (Lambda + Function URL)                                 | ✅ Done                   |
| **P4a** | Lovable `/findings` screen                                           | ✅ Live on real data      |
| **P4b** | Overview, Comparison, Jobs, Operations, Sources                      | ✅ Converted to live data |
| **P4c** | Honesty pass: remove inert controls, split truth from scored sources | 🟡 In progress — §9.4    |
| **P5**  | Scheduled re-runs, wider truth pool                                  | ⬜                        |
| **P6**  | Auth, task automation                                                | ⬜                        |


**Total AWS cost to date: roughly $0.02.** No vendor fees — every source in use is free tier.

---



## 3. What was found in the account (the starting point)

The handover documents described a working data layer. It was not working.


| Table in `ip-database`                                                       | Claimed                  | Actual                                          |
| ---------------------------------------------------------------------------- | ------------------------ | ----------------------------------------------- |
| `ip_list`, `ip_flags`, `ip_business_truth`, `db11_bucketed`, `px12_bucketed` | built                    | **0 rows** — data gone                          |
| `ip_dim`, `isp_value_analysis`                                               | built                    | **0 rows** — empty prefix                       |
| `ip_analytics`                                                               | the joined product table | 1,990,844 rows but **every vendor column NULL** |
| `db11_parquet`, `px12_parquet`                                               | reference data           | intact ✅                                        |


**Root cause.** Five tables were created with bare `CREATE TABLE … AS SELECT`, so Athena chose their
storage: `s3://vinit-cdp-experimentation/Unsaved/2026/09/02/tables/…`. Those prefixes are now empty.
There is no lifecycle rule on that bucket, so the data was removed or never durably committed. The
Glue entries survive and still describe columns, so the tables *look* present and silently return
nothing.

`ip_analytics` survived with real business data — 11.33M sessions, $15.94M revenue — but had been
built by joining to the already-empty `ip_dim`, so it was **100% business truth and 0% IP
intelligence**. The enrichment join, which is the actual product, had never successfully run.

The `primary` Athena workgroup had `OutputLocation = null` and
`EnforceWorkGroupConfiguration = false`. Nothing in the account prevented this, and nothing would
have prevented it recurring.

---



## 4. Infrastructure



### Athena workgroups


| Workgroup     | Enforced | Purpose                                                                                             |
| ------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `ipintel`     | **true** | Interactive/ad-hoc only. Enforcement stops a console session writing table data to a scratch bucket |
| `ipintel_etl` | false    | Table builds. Every CTAS **must** declare `external_location`                                       |


Both output to `…/ip-intelligence/athena-results/`, engine v3, CloudWatch metrics on,
`BytesScannedCutoffPerQuery` = 20 GB.

> **Why two workgroups — do not "simplify" this.**
> `EnforceWorkGroupConfiguration=true` makes Athena **reject** any CTAS carrying
> `external_location`. Enforcement therefore forces *all* table data into one prefix — the same
> failure as the original `Unsaved/` incident, at a different path. Enforcement protects interactive
> use; the ETL workgroup allows declared locations. Both are needed.
>
> Note also: the scan cutoff is a **cost** guard. It does not stop a compute-explosion range join,
> which scans little and runs forever. Bucketing is the fix for those.



### Glue databases


| Database            | S3 location                    |
| ------------------- | ------------------------------ |
| `ipintel_reference` | `…/ip-intelligence/reference/` |
| `ipintel_curated`   | `…/ip-intelligence/curated/`   |
| `ipintel_analytics` | `…/ip-intelligence/analytics/` |


Base prefix: `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/`

**Read-only upstream** (never written): `raw.raw_tune_clicks` · `unified.unified_session_summary` ·
`unified.uct_leads` · `ip-database.db11_parquet` · `ip-database.px12_parquet`

### S3 layout

```
ip-intelligence/
  reference/       vendor source files + ZIP centroids
  curated/         typed tables, partitioned by snapshot_date / observed_date
  analytics/       scorecards, partitioned by as_of_date
  serving/         findings.json + console.json — what the API reads
  athena-results/  query output only, never a table location
  _rescue/         backup of the pre-existing ip_analytics
```



### API


| Resource     | Detail                                                                                                 |
| ------------ | ------------------------------------------------------------------------------------------------------ |
| Lambda       | `ipintel-findings-api` · python3.12 · 512 MB · 20 s                                                    |
| Function URL | `https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/`                                |
| Auth         | `Authorization: Bearer <token>`; 401 without                                                           |
| IAM role     | `ipintel-api-role` — `s3:GetObject` on `ip-intelligence/serving/*` and its own log group. Nothing else |




### Nothing pre-existing was touched

`ip-database` unchanged (its newest table predates this work by two hours) · `raw.*` and `unified.*`
read-only throughout · `primary` workgroup untouched · no existing S3 object deleted or overwritten.
Everything created is prefixed `ipintel`: 2 workgroups, 3 databases, 14 tables, 1 IAM role,
1 Lambda. Deleting everything with that prefix returns the account to its prior state.

---



## 5. Two datasets, two purposes

This is the part most easily confused, so it is stated plainly.

**Dataset A — the full universe (4.9M IPs).** Every IP ever seen in TUNE clicks or sessions,
enriched with the two bulk databases we own. Answers *"what do we know about our traffic at scale?"*

**Dataset B — the benchmark (485 IPs).** A small set where we have a location that did **not** come
from an IP lookup, run against every source we can reach. Answers *"which vendor is actually right?"*

You cannot do B at 4.9M scale (no truth, and API limits). You cannot do A on 485 IPs (not
representative). Both exist.

---



## 6. Dataset A — the 4.9M universe



### 6.0 Tables

All at `…/curated/<table>/snapshot_date=2026-09-03/`, Parquet + Snappy.


| Table                 | Rows       | Grain                                                            |
| --------------------- | ---------- | ---------------------------------------------------------------- |
| `ip_list`             | 4,939,775  | one IP — TUNE clicks ∪ session IPs, with `ip_num` and `prefix16` |
| `db11_bucketed`       | 3,012,036  | range × /16                                                      |
| `px12_bucketed`       | 2,690,046  | range × /16                                                      |
| `ip_dim`              | 4,939,775  | one IP — **the enrichment join**                                 |
| `ip_flags`            | 4,531,830  | one IP — FraudLogix verdicts rolled up                           |
| `ip_business_outcome` | 1,990,813  | one IP — sessions, revenue, leads                                |
| `ip_vendor_result`    | 14,411,380 | one (IP, source) — **the tall table**                            |




### Validation — every gate matched the documented figures


| Metric                           | Expected              | Rebuilt   |     |
| -------------------------------- | --------------------- | --------- | --- |
| DB11 state / city / zip fill     | 99.97 / 99.97 / 99.83 | identical | ✅   |
| PX12 hits                        | 16,771 (0.3395%)      | identical | ✅   |
| `db11_bucketed` rows             | 3,012,036             | identical | ✅   |
| Geo gap filled (state/city)      | 644,539               | identical | ✅   |
| Geo gap filled (zip)             | 642,060               | identical | ✅   |
| Total revenue                    | $15,939,329           | identical | ✅   |
| FraudLogix flagged               | ~14.6%                | 14.62%    | ✅   |
| PX12 corroboration of FraudLogix | 0.98%                 | identical | ✅   |


`ip_list` is +52 and `ip_flags` +3,555 versus the profiling run — new traffic since, expected drift.

**Any future run that deviates from these is a defect, not a discovery.**

### Findings from Dataset A

- **$7,074,034 — 44% of all attributed revenue — sits on IPs with no geolocation today.** DB11
resolves 99.98% of them. This is the strongest business case in the project.
- `ip_is_vpn` **is NULL on all 11,331,530 session rows.** The console's VPN metric never had a source.
- `ip_is_proxy` **is NULL on 2,653,101 rows (23%)** — the same rows missing geo.
- **127,354 FraudLogix verdicts normalize to** `unknown` — `MASKED_DEVICES`, `BASIC_FRAUD`,
`OTHER_REASON`, `SPOOFED` and undocumented numeric codes. They fail loud by design, never silently
to `clean`.



### DDL

Run in workgroup `ipintel_etl`.
`$B` = `s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence`

**6.1** `ip_business_outcome` — business truth. `has_lead`/`has_revenue` are strings `on`/`off`;
`ip_is_proxy` is `true`/`false`/NULL; `is_bot_click` is a real boolean. Proxy counts are named
`incumbent_*` deliberately — they are an unidentified vendor's opinion, not truth.

```sql
CREATE TABLE ipintel_curated.ip_business_outcome
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='$B/curated/ip_business_outcome/snapshot_date=2026-09-03/') AS
SELECT
  session_ip                                                    AS ip,
  count(*)                                                      AS sessions,
  sum(coalesce(expected_revenue,0))                             AS revenue,
  sum(CASE WHEN has_revenue = 'on' THEN 1 ELSE 0 END)           AS revenue_sessions,
  sum(CASE WHEN has_lead    = 'on' THEN 1 ELSE 0 END)           AS lead_sessions,
  sum(CASE WHEN has_partial_lead = 'on' THEN 1 ELSE 0 END)      AS partial_lead_sessions,
  sum(CASE WHEN is_bot_click THEN 1 ELSE 0 END)                 AS bot_sessions,
  sum(CASE WHEN ip_is_proxy = 'true' THEN 1 ELSE 0 END)         AS incumbent_proxy_sessions,
  sum(CASE WHEN ip_is_proxy IS NULL THEN 1 ELSE 0 END)          AS incumbent_unenriched_sessions,
  min(session_date)                                             AS first_seen,
  max(session_date)                                             AS last_seen,
  max(nullif(nullif(ip_country_code,''),'-'))                   AS truth_country,
  max(nullif(nullif(ip_region_name ,''),'-'))                   AS truth_state,
  max(nullif(nullif(ip_city_name   ,''),'-'))                   AS truth_city,
  max(nullif(nullif(ip_zip_code    ,''),'-'))                   AS truth_zip
FROM unified.unified_session_summary
WHERE session_ip IS NOT NULL
  AND regexp_like(session_ip, '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
GROUP BY session_ip;
```

**6.2 Bucketed range tables.** `prefix16` is the /16 bucket that makes the range join tractable —
without it, matching 4.9M IPs against 3M ranges is a cross join.

```sql
CREATE TABLE ipintel_curated.db11_bucketed
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='$B/curated/db11_bucketed/snapshot_date=2026-09-03/') AS
SELECT ip_from, ip_to, country_code, region_name, city_name,
       latitude, longitude, zip_code, time_zone, b AS prefix16
FROM "ip-database".db11_parquet
CROSS JOIN UNNEST(sequence(ip_from / 65536, ip_to / 65536)) AS t(b);

CREATE TABLE ipintel_curated.px12_bucketed
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='$B/curated/px12_bucketed/snapshot_date=2026-09-03/') AS
SELECT ip_from, ip_to, proxy_type, country_code, region_name, city_name,
       isp, domain, usage_type, asn, as_name, last_seen, threat, provider,
       fraud_score, b AS prefix16
FROM "ip-database".px12_parquet
CROSS JOIN UNNEST(sequence(ip_from / 65536, ip_to / 65536)) AS t(b);
```

**6.3** `ip_list` — the IP universe.

```sql
CREATE TABLE ipintel_curated.ip_list
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='$B/curated/ip_list/snapshot_date=2026-09-03/') AS
WITH all_ips AS (
  SELECT DISTINCT ip FROM raw.raw_tune_clicks
   WHERE ip IS NOT NULL AND regexp_like(ip,'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
  UNION
  SELECT DISTINCT session_ip FROM unified.unified_session_summary
   WHERE session_ip IS NOT NULL AND regexp_like(session_ip,'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
)
SELECT ip,
  cast(split_part(ip,'.',1) AS bigint)*16777216
+ cast(split_part(ip,'.',2) AS bigint)*65536
+ cast(split_part(ip,'.',3) AS bigint)*256
+ cast(split_part(ip,'.',4) AS bigint)                AS ip_num,
 (cast(split_part(ip,'.',1) AS bigint)*16777216
+ cast(split_part(ip,'.',2) AS bigint)*65536
+ cast(split_part(ip,'.',3) AS bigint)*256
+ cast(split_part(ip,'.',4) AS bigint)) / 65536       AS prefix16
FROM all_ips;
```

**6.4** `ip_dim` — the enrichment join that had never run. Missing values are normalised **once,
here**: IP2Location writes `-`, exports write `''`, the session table writes `NULL`.

```sql
CREATE TABLE ipintel_curated.ip_dim
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='$B/curated/ip_dim/snapshot_date=2026-09-03/') AS
SELECT
  i.ip, i.ip_num, i.prefix16,
  nullif(nullif(l.country_code,''),'-')  AS db11_country,
  nullif(nullif(l.region_name ,''),'-')  AS db11_state,
  nullif(nullif(l.city_name   ,''),'-')  AS db11_city,
  nullif(nullif(l.zip_code    ,''),'-')  AS db11_zip,
  l.latitude AS db11_lat, l.longitude AS db11_lon,
  nullif(nullif(l.time_zone,''),'-')     AS db11_timezone,
  (l.ip_from IS NOT NULL)                AS in_db11,
  p.proxy_type AS px12_proxy_type, p.usage_type AS px12_usage_type,
  p.isp AS px12_isp, p.asn AS px12_asn, p.as_name AS px12_as_name,
  p.fraud_score AS px12_fraud_score, p.last_seen AS px12_last_seen,
  p.threat AS px12_threat,
  (p.ip_from IS NOT NULL)                AS in_px12
FROM ipintel_curated.ip_list i
LEFT JOIN ipintel_curated.db11_bucketed l
       ON i.prefix16 = l.prefix16 AND i.ip_num BETWEEN l.ip_from AND l.ip_to
LEFT JOIN ipintel_curated.px12_bucketed p
       ON i.prefix16 = p.prefix16 AND i.ip_num BETWEEN p.ip_from AND p.ip_to;
```

**6.5** `ip_flags` — FraudLogix rollup. The version in `athena_tables_fixes.txt` fails with
`COLUMN_NOT_FOUND: 'created_at'`; that column does not exist. The real ones are `datetime` and
`date_pst`.

```sql
CREATE TABLE ipintel_curated.ip_flags
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='$B/curated/ip_flags/snapshot_date=2026-09-03/') AS
SELECT
  ip,
  count(*)                                                            AS clicks,
  min(date_pst)                                                       AS first_seen,
  max(date_pst)                                                       AS last_seen,
  max(CASE WHEN access_control_decision='FLAGGED' THEN 1 ELSE 0 END)=1 AS ever_flagged,
  sum(CASE WHEN access_control_decision='FLAGGED' THEN 1 ELSE 0 END)   AS flagged_clicks,
  array_agg(DISTINCT access_control_reason_code)
    FILTER (WHERE access_control_decision='FLAGGED')                   AS flag_reasons,
  max(CASE WHEN access_control_reason_code IN
        ('PROXY','VPN','TOR','TOR_EXIT_NODE','DATA_CENTER','MOBILE_PROXY_SIGNALS')
       AND access_control_decision='FLAGGED' THEN 1 ELSE 0 END)=1      AS flagged_proxy_family,
  max(CASE WHEN access_control_reason_code IN
        ('BOT_GENERATED','NON_HUMAN_SCRIPT','ABNORMAL_TRAFFIC_PATTERNS')
       AND access_control_decision='FLAGGED' THEN 1 ELSE 0 END)=1      AS flagged_bot_family,
  max(CASE WHEN coalesce(access_control_decision,'')='' THEN 1 ELSE 0 END)=1 AS has_unenriched_click
FROM raw.raw_tune_clicks
WHERE ip IS NOT NULL AND regexp_like(ip,'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
GROUP BY ip;
```

**6.6** `ip_vendor_result` — the tall table. **Adding a vendor is a new** `UNION ALL` **branch and a new**
`vendor_product_id` **value, never a new column.** `has_answer` is the critical field: absence from
PX12 means *unknown*, never *clean*.

```sql
CREATE TABLE ipintel_curated.ip_vendor_result
WITH (format='PARQUET', write_compression='SNAPPY',
      external_location='$B/curated/ip_vendor_result/snapshot_date=2026-09-03/') AS
SELECT ip, 'ip2location_db11' AS vendor_product_id,
       (db11_state IS NOT NULL) AS has_answer,
       db11_country AS geo_country, db11_state AS geo_state,
       db11_city AS geo_city, db11_zip AS geo_zip,
       db11_lat AS geo_lat, db11_lon AS geo_lon,
       CAST(NULL AS varchar) AS risk_category, CAST(NULL AS integer) AS risk_score,
       CAST(NULL AS varchar) AS vendor_verdict_raw,
       CAST(NULL AS varchar) AS isp, CAST(NULL AS varchar) AS asn,
       CAST(NULL AS varchar) AS shared_infrastructure
FROM ipintel_curated.ip_dim
UNION ALL
SELECT ip, 'ip2proxy_px12', in_px12, NULL, NULL, NULL, NULL, NULL, NULL,
       CASE WHEN NOT in_px12 THEN NULL
            WHEN px12_usage_type IN ('DCH','CDN','EDU','GOV','ORG','COM') THEN 'datacenter'
            WHEN px12_usage_type IN ('ISP','MOB','ISP/MOB') THEN 'residential_proxy'
            ELSE 'unknown' END,
       px12_fraud_score, px12_proxy_type, px12_isp, px12_asn,
       CASE WHEN px12_usage_type='CDN' THEN 'cdn'
            WHEN px12_usage_type='DCH' THEN 'datacenter' ELSE NULL END
FROM ipintel_curated.ip_dim
UNION ALL
SELECT f.ip, 'fraudlogix_tune', true, NULL, NULL, NULL, NULL, NULL, NULL,
       CASE WHEN NOT f.ever_flagged THEN 'clean'
            WHEN contains(f.flag_reasons,'TOR') OR contains(f.flag_reasons,'TOR_EXIT_NODE') THEN 'tor'
            WHEN contains(f.flag_reasons,'VPN') THEN 'vpn'
            WHEN contains(f.flag_reasons,'DATA_CENTER') THEN 'datacenter'
            WHEN contains(f.flag_reasons,'PROXY')
              OR contains(f.flag_reasons,'MOBILE_PROXY_SIGNALS') THEN 'residential_proxy'
            WHEN contains(f.flag_reasons,'BOT_GENERATED')
              OR contains(f.flag_reasons,'NON_HUMAN_SCRIPT')
              OR contains(f.flag_reasons,'ABNORMAL_TRAFFIC_PATTERNS') THEN 'bot'
            ELSE 'unknown' END,
       NULL, CASE WHEN f.ever_flagged THEN 'FLAGGED' ELSE 'ACCEPTED' END, NULL, NULL, NULL
FROM ipintel_curated.ip_flags f;
```



**6.7 Validation queries** — expected values in the comments.

```sql
-- Must return 99.97 / 99.97 / 99.83 / 16771 / 0.3395
SELECT count(*) total_ips,
  round(100.0*count(db11_state)/count(*),2) db11_state_pct,
  round(100.0*count(db11_city )/count(*),2) db11_city_pct,
  round(100.0*count(db11_zip  )/count(*),2) db11_zip_pct,
  sum(CASE WHEN in_px12 THEN 1 ELSE 0 END) px12_hits,
  round(100.0*sum(CASE WHEN in_px12 THEN 1 ELSE 0 END)/count(*),4) px12_pct
FROM ipintel_curated.ip_dim;

-- Must return gap_filled_state_city = 644539, revenue_on_gap_ips = 7074034
SELECT count(*) session_ips,
  sum(CASE WHEN NOT (b.truth_state IS NOT NULL AND b.truth_city IS NOT NULL
            AND b.truth_zip IS NOT NULL) AND d.db11_state IS NOT NULL
           THEN 1 ELSE 0 END) gap_filled_state_city,
  round(sum(CASE WHEN NOT (b.truth_state IS NOT NULL AND b.truth_city IS NOT NULL
            AND b.truth_zip IS NOT NULL) THEN b.revenue ELSE 0 END),0) revenue_on_gap_ips
FROM ipintel_curated.ip_business_outcome b
LEFT JOIN ipintel_curated.ip_dim d ON b.ip = d.ip;
```

---



## 7. Dataset B — the 485-IP benchmark



### 7.1 How the sample was chosen

Location accuracy needs a location that did **not** come from an IP lookup. The only one in the
warehouse is an address a lead typed themselves, in `unified.uct_leads`, reachable to an IP via
`alyson_session_id → unified.unified_session_summary.session_id → session_ip`.


|                                       | Count                                   |
| ------------------------------------- | --------------------------------------- |
| `uct_leads` rows                      | 134,096                                 |
| …with a session id                    | 10,329 (only **632 distinct** sessions) |
| Distinct IPs with truth               | 552                                     |
| **…with a lead-supplied state + ZIP** | **485** — the benchmark pool            |
| …FraudLogix flagged                   | 100                                     |
| Revenue on the pool                   | $346,515                                |


`uct_leads` **stores empty strings, not NULL.** An `IS NOT NULL` test passes blanks, which
overstated the pool at first. Real counts: `truth_state` 485 · `truth_zip` 485 · `truth_address` 552
· `truth_city` **only 54** · `county` and `phone_number` **0**.

ZIP is therefore the anchor — it derives city, county, metro and a lat/long centroid, and avoids
city-name normalisation entirely.

**All 485 were run, not a 200 sample.** Nothing is rate-limited at this scale, and 485 gives ±4.4%
at 95% confidence versus ±6.9% at 200.

### 7.2 The eleven sources

**Bulk databases (free download).** IP2Location LITE DB11 · IP2Proxy LITE PX12 ·
MaxMind GeoLite2 City · DB-IP City Lite.

**APIs (free tier).** proxycheck.io (1,000/day) · ipwho.is · ipinfo.io · geojs.io.

**Authoritative range lists (free, unlimited, definitive for their class).** Tor exit list ·
Apple iCloud Private Relay · AWS · Google Cloud · Cloudflare · Fastly.

**Internal.** FraudLogix via TUNE.

**Excluded: ip-api.com.** Works and returns good data, but its free tier is licensed
**non-commercial only**. Do not wire it in.

> **Access gotchas**
>
> - MaxMind: the account-ID basic-auth endpoint returns **401**. The working form is
> `https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City-CSV&license_key=<KEY>&suffix=zip`
> - geojs.io and ipwho.is return nothing without a `User-Agent` header.
> - proxycheck batch POST accepts 100 IPs per request and barely touches the daily quota.
> - Matching 485 IPs against a 4M-row range file needs `bisect` on sorted integers. A nested loop
> is 2 billion comparisons and will time out.



### 7.3 Tables


| Table                                   | Rows   | Contents                                              |
| --------------------------------------- | ------ | ----------------------------------------------------- |
| `ipintel_curated.lead_truth`            | 552    | IP ↔ lead-supplied address                            |
| `ipintel_curated.ip_geo_observations`   | 2,938  | location claims (CSV / OpenCSVSerde)                  |
| `ipintel_curated.ip_intel_observations` | 970    | raw risk claims                                       |
| `ipintel_curated.ip_proxy_check`        | 1,692  | **unified risk table**, 4 sources                     |
| `ipintel_reference.zip_centroid`        | 33,791 | Census 2024 gazetteer, ZIP → lat/long (public domain) |
| `ipintel_analytics.geo_accuracy`        | 8      | the location scorecard                                |




### 7.4 Location scorecard


| Source               | IPs | Answered | State     | ZIPs supplied | ZIP match | Median err  | P90 err  |
| -------------------- | --- | -------- | --------- | ------------- | --------- | ----------- | -------- |
| **MaxMind GeoLite2** | 485 | 99.2%    | **59.5%** | 465           | **17.8%** | **49.3 mi** | 783.7 mi |
| geojs.io             | 485 | 99.2%    | 59.5%     | 0             | —         | 49.3 mi     | 783.7 mi |
| ipinfo.io            | 485 | 100%     | 58.8%     | 485           | 11.5%     | 59.3 mi     | 810.9 mi |
| ipwho.is             | 485 | 100%     | 58.4%     | 485           | 9.3%      | 59.5 mi     | 834.5 mi |
| IP2Location DB11     | 485 | 100%     | 54.8%     | 485           | 7.0%      | 74.4 mi     | 972.2 mi |
| proxycheck.io        | 485 | 100%     | 54.2%     | 441           | 7.9%      | 84.1 mi     | —        |
| DB-IP City Lite      | 485 | 100%     | 52.8%     | 0             | —         | 88.1 mi     | 981.3 mi |


**Apple / iCloud Private Relay is deliberately absent from this table.** It is the ground truth for 28 of the 485 IPs, not a competitor. It was originally listed here and scored 0.0% state match, which read as Apple being the worst source when it is in fact the yardstick. It now lives in a separate `truth_sources` block — see §8.7.

**ZIP match must distinguish "not supplied" from "wrong".** DB-IP and geojs return no postal code at
all, so their ZIP match is NULL, not 0%. The `zips_supplied` column exists for exactly this.

### 7.5 Risk scorecard


| Source              | Coverage    | Answer rate | Proxy | VPN | Tor | Datacenter | Bot |
| ------------------- | ----------- | ----------- | ----- | --- | --- | ---------- | --- |
| proxycheck.io       | 485 / 485   | 100%        | 31    | 30  | 0   | 1          | 0   |
| Authoritative lists | 485 / 485   | 100%        | 28    | 28  | 0   | 0          | 0   |
| FraudLogix (TUNE)   | 237 / 485   | 48.9%       | 47    | 0   | 0   | 0          | 67  |
| **IP2Proxy PX12**   | **1 / 485** | **0.2%**    | 1     | 0   | 0   | 1          | 0   |


Coverage denominators are the **pool size (485)**, never the row count a source produced —
otherwise FraudLogix reads as 237/237 = 100%, the opposite of the truth.

---



## 8. Findings and conclusions



### 8.1 🛑 The location percentages are disagreement, not accuracy

**Two independent vendors agree with *each other* on state 93.2% of the time, but with the lead
address only ~59%.** That cannot happen if the address were where the person was sitting.

It is not a mobile artefact — the pool is mostly fixed residential broadband (Charter 39,
Comcast 26, Verizon 24, AT&T 22; T-Mobile only 12).

Most likely `uct_leads.address_line_1` is the **property being enquired about**, not the customer's
own location. `revenue_leads_plus` carrying `property_uuid` supports this. These are real-estate /
home-offer leads; someone in Florida can request an offer on a house in Missouri.

**Consequence:** do not publish 55% as a vendor's accuracy. Until the business confirms what that
address represents, the location table is **vendor disagreement**. Median error and everything in
§8.2–8.6 are unaffected.

### 8.2 geojs.io is not an independent source

It returns byte-identical state, city **and lat/long** to MaxMind GeoLite2 on all 485 IPs — 100.0%
on all three. It is a wrapper over GeoLite2. Counting both overstates how many independent opinions
exist. This is precisely the class of finding the console exists to produce.

### 8.3 IP2Proxy PX12 answered 1 of 485

The free proxy database is effectively empty for this traffic. It is **not** saying those IPs are
clean — it has no opinion. Recorded as `has_answer = false`, never as a clean verdict.

### 8.4 Shared infrastructure distorts every revenue figure

**28 of 485 IPs (5.8%) are iCloud Private Relay**, holding **$346,245 of the pool's $346,515 —
99.9%.** They are Apple's egress points via Fastly and Cloudflare. `146.75.164.0` alone has 53,967
sessions and 7 leads, so the revenue attributed to it is thousands of different people summed
together, not one customer.

So every revenue-at-risk figure is reported twice. FraudLogix appears to put **$305,758** at risk;
excluding shared infrastructure the real figure is **$2,193**.

### 8.5 A genuinely valid truth source

Apple publishes the city for every relay egress range — the operator's own statement, not an
inference. For `146.75.164.0`:


| Source                         | Says                    |               |
| ------------------------------ | ----------------------- | ------------- |
| **Apple (authoritative)**      | **Dallas, TX**          | ground truth  |
| ipwho.is · ipinfo.io · MaxMind | Dallas, TX              | correct       |
| **IP2Location DB11**           | **Mexico City, Mexico** | wrong country |


Provable without touching the disputed lead address. This is the headline demo.

### 8.7 A ground-truth source must never sit in a ranked table

Apple was initially included in the location scorecard alongside the seven vendors, where it scored **0.0% state match** — because its rows carry Apple's own city for relay ranges, which the scoring query was comparing against the disputed lead address rather than treating as the reference.

The table shape implied a comparison that was not valid. This is the same category error as PX12's silence reading as a *clean* verdict: the presentation asserted something the data did not support. Fixed at the source in `run-2026-09-03-05` — Apple moved to a `truth_sources` block, and the source counts corrected from a contradictory 7 / 8 / 12 to a single **7 geo + 4 risk + 1 truth**.

**Rule:** a source under test and the yardstick it is measured against never appear in the same ranked table.

### 8.6 MaxMind is the best free geo source

Best ZIP match at 17.8% — more than double IP2Location's 7.0% — and the lowest median error at
49 miles. On this sample it beats every other free option.

---



## 9. The API and the UI



### 9.1 Endpoints

Base URL: `https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/`
Header: `Authorization: Bearer <token>`


| Route       | Size    | Serves                                                             |
| ----------- | ------- | ------------------------------------------------------------------ |
| `/health`   | tiny    | run id + timestamp; the "data is live" indicator                   |
| `/summary`  | ~5 KB   | sample stats, both scorecards, source independence, truth caveat   |
| `/findings` | ~866 KB | everything, including all 485 IPs of evidence                      |
| `/ip/{ip}`  | small   | one IP's full evidence trail                                       |
| `/console`  | ~8 KB   | issue list (6), run history (4), plan totals |
| `/recommendations` | ~9 KB | which source to use for which job, with method and caveats — see section 18 |
| `/sources`  | live    | writable registry in DynamoDB — see section 17 |


Live payload: `run-2026-09-03-05`. `/summary` and `/findings` carry a `truth_sources` array and `sample.truth_sources`, kept separate from `geo_scorecard` so a reference source is never ranked against the vendors it verifies (§8.7). `sample.geo_sources` = 7 and `sample.risk_sources` = 4; the UI must render these two separately and never sum them.

Two files back these: `serving/findings.json` (benchmark) and `serving/console.json` (registry,
issues, runs). **Refreshing is one** `aws s3 cp` — no redeploy, no schema change.

`risk_scorecard` rows carry `run_complete` and `coverage_note` so the UI can distinguish *"the
vendor had no opinion"* from *"we failed to query it fully"* — a distinction a percentage alone
cannot express.

`/console` **contents.** 11 sources with plan, limit, capabilities, coverage and health; 6 issues
(2 critical: the truth-validity question and PX12's coverage); 4 runs showing the benchmark evolving
from 6 sources to 11; and plan totals — **$0 committed, 0 paid plans.**

### 9.2 Lovable prompts


| File                          | Covers                                                            | Status         |
| ----------------------------- | ----------------------------------------------------------------- | -------------- |
| `LOVABLE_PROMPT_FINAL.md`     | `/findings` — scorecards, independence, worked example, IP lookup | ✅ Shipped      |
| `LOVABLE_PROMPT_REAL_DATA.md` | Overview, Comparison, Jobs, Operations, Sources                   | ✅ Shipped      |
| (in chat)                     | Honesty pass — inert controls, source counts, ground-truth card   | 🟡 In progress |


Add these as **server-side** secrets in Lovable (never public, never `VITE_`):

```
IPINTEL_API_URL   = https://h25l6d2efgqnxqjrt6xpzjzbdq0hceyr.lambda-url.us-west-2.on.aws/
IPINTEL_API_TOKEN = xEVWxcFa--qFzYdEqaVNOkDE5R4VG6VMu5se-2WddbA
```

Keep the trailing slash — paths are built as `${IPINTEL_API_URL}summary`.

### 9.3 Mock data still to remove

`/findings` is live on real data. Five pages still show invented figures:


| Page              | Shows                                              | Reality                                       |
| ----------------- | -------------------------------------------------- | --------------------------------------------- |
| Overview          | 28,442 comparable IPs · "MaxMind Anonymous failed" | 485 benchmarked · MaxMind is healthy and best |
| Vendor Comparison | $918K · Location score 91                          | Duplicates `/findings`; never computed        |
| Jobs & Sampling   | ProxyCheck 80K/day                                 | Free tier is **1,000/day**                    |
| Operations        | OPS-1048 "credential 401"                          | Six real issues, two critical                 |
| Sources & Plans   | $2,510 annual committed                            | **$0** — every source is free tier            |


There is no "MaxMind Anonymous" product in this project and no expired credential. That entire
storyline is demo fiction from `console-data.ts`. The verification step in
`LOVABLE_PROMPT_REAL_DATA.md` greps for `28,442`, `918K`, `80K/day`, `2,510` and
`MaxMind Anonymous` — if any survive, the conversion is not done.

---



### 9.4 UI honesty rules

Three defects found once the screens were live, all the same underlying mistake: **the interface described capabilities the system does not have.** They are listed together because the next person will be tempted to reintroduce all three.


| Defect                                                           | Why it was wrong                                                                                             | Fix                                                                                                        |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Banner reading *"Use the filters to change the reporting view"*  | The filters were never wired. The sentence was simply false                                                  | Replaced with a static line stating run id, timestamp and population                                       |
| Global filter bar — period, All Sites, All Publishers, Search IP | The benchmark is one fixed run over one population. There is no period, site or publisher dimension to slice | Removed. Only **Refresh** remains, because the payload really does change between runs                     |
| Jobs page checkboxes and a permanently disabled *Run job* button | Ticking a box did nothing; the button could never fire                                                       | Converted to a read-only table; button replaced with a callout explaining that runs come from the pipeline |


**The rule: if a control cannot change anything, it must not look like a control.**

This is the same failure mode as two data defects already recorded — PX12's silence rendering as a *clean* verdict (§8.3), and Apple appearing in a ranked table it was the yardstick for (§8.7). In each case the presentation asserted something the data did not support. When reviewing this console, that is the first thing to look for.

---



## 10. Design decisions and why


| Decision                                     | Reason                                                                                                                                            |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Keep the existing `ip-intelligence/` prefix  | The three-layer shape was already right; the failure was tables bypassing it, not the bucket                                                      |
| Two Athena workgroups                        | Enforcement and `external_location` are mutually exclusive — see §4                                                                               |
| **No RDS**                                   | Every screen is a precomputed aggregate of a few hundred KB. S3 JSON avoids VPC, NAT, pooling and migrations — days faster and ~$70/month cheaper |
| Athena never on the request path             | 2–20 s per query, billed per TB. Athena computes on a schedule; the API reads precomputed JSON                                                    |
| Precomputed JSON + one Lambda                | Smallest thing that works, touches nothing existing, refresh is one `s3 cp`                                                                       |
| Rename proxy counts `incumbent_*`            | They are a vendor's opinion sitting in a table called business truth                                                                              |
| Unmapped verdicts → `unknown`, never `clean` | A silent fallthrough turns a proxy into a customer                                                                                                |
| `snapshot_date` on every table               | Rollback is repointing at the previous snapshot, not restoring from backup                                                                        |
| Run all 485, not a 200 sample                | Same cost, ±4.4% instead of ±6.9%                                                                                                                 |
| Report revenue twice                         | One number cannot answer both "what would we lose" and "what should we block"                                                                     |
| Ground truth kept out of ranked tables       | A yardstick scored against itself reads as the worst source — see §8.7                                                                            |
| No inert controls in the UI                  | A dead select or disabled button claims a capability that does not exist — see §9.4                                                               |


---



## 11. Credentials


| Credential                        | State                                                                                                                                        |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| proxycheck.io key #1 (64-hex)     | **Invalid.** With-key and without-key responses byte-identical; an all-zeros fake key returned the same dashboard response. Never registered |
| proxycheck.io key #2 (`vn6788-…`) | **Working.** `Daily Limit: 1000`, `Plan Tier: Free`. Completed 485/485                                                                       |
| MaxMind licence key               | **Working**, via the permalink form only                                                                                                     |
| Findings API token                | Generated at deploy, stored in the Lambda `API_TOKEN` env var                                                                                |


All four have appeared in chat transcripts. **Rotate the proxycheck and MaxMind keys**, and move all
of them into Secrets Manager under `ipintel/*` before production.

---



## 12. How to re-run everything

1. **Dataset A** — run §6.1 through §6.6 in workgroup `ipintel_etl`, then §6.7 to validate.
  Roughly 1.2 GB scanned, about $0.006.
2. **Dataset B** — rebuild `lead_truth`, export the IP list, run the vendor fan-out (bulk files by
  `bisect` range match, APIs by batched HTTP), normalise to `ip_geo.csv` / `ip_intel.csv`, upload,
   rebuild `geo_accuracy` and `ip_proxy_check`.
3. **Refresh the API** — rebuild `findings.json` and `console.json`, then:

```bash
aws s3 cp findings.json s3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/findings.json
```

The UI picks it up automatically. No redeploy.

Adding a source means new rows in the observation tables and a new row in each scorecard. The tables
grow a row; no component changes.

---



## 13. Open questions and next steps

**Business — these gate interpretation, not the pipeline.**

1. **Is** `uct_leads.address_line_1` **the customer's address or the property they are asking about?**
  One conversation. It decides whether location accuracy is measurable at all from this source.
2. **What produces** `ip_is_proxy` **/** `ip_is_vpn` **on the session table?** An unidentified vendor is
  currently sitting inside a table called business truth.
3. **How should revenue on shared infrastructure be counted?** iCloud Private Relay is $154K on a
  single IP.
4. **Mapping for the 127,354 unmapped FraudLogix codes**, including the undocumented numerics.

**Engineering.**

1. Ship `LOVABLE_PROMPT_REAL_DATA.md` — five pages still on mock data.
2. **Widen the truth pool.** 552 of 4.9M is **0.011% coverage** and caps everything. Another lead
  source with addresses is worth more than any additional vendor.
3. Schedule the benchmark (EventBridge → fan-out → refresh the JSON).
4. Add AbuseIPDB and IPQualityScore — both free tier with signup.
5. Decide IPv6: currently invisible rather than counted as uncovered.

---



## 14. Session log


| Date       | Change                                                                                                                                                     |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-09-03 | Read-only audit: 5 tables empty on `Unsaved/` paths, `ip_analytics` with null vendor columns, unenforced `primary` workgroup                               |
| 2026-09-03 | P0: `ipintel` + `ipintel_etl` workgroups, 3 Glue databases, `_rescue/` backup                                                                              |
| 2026-09-03 | P1: 7 curated tables. All 13 validation gates matched. Enrichment join populated for the first time                                                        |
| 2026-09-03 | P2: `lead_truth` (485 IPs), 11 sources run, scorecards built. Found the truth-validity problem, the geojs↔MaxMind duplication, and PX12 answering 1 of 485 |
| 2026-09-03 | P3: `ipintel-findings-api` Lambda + Function URL. Four refresh runs; live payload `run-2026-09-03-04`                                                      |
| 2026-09-03 | proxycheck key #1 proven invalid; key #2 working; full 485 coverage achieved                                                                               |
| 2026-09-03 | MaxMind GeoLite2 and DB-IP added; MaxMind is the best free geo source                                                                                      |
| 2026-09-03 | `/console` endpoint added — source registry, 6 issues, 4 runs, plan totals                                                                                 |
| 2026-09-03 | `/findings` shipped in Lovable on live data                                                                                                                |
| 2026-09-03 | Build log restructured end-to-end                                                                                                                          |
| 2026-09-03 | P4b shipped: Overview, Comparison, Jobs, Operations and Sources converted to live `/console` data                                                          |
| 2026-09-03 | Honesty pass: removed the false filter banner, the inert global filter bar and the dead Jobs controls                                                      |
| 2026-09-03 | `run-2026-09-03-05`: Apple moved out of `geo_scorecard` into `truth_sources`; source counts corrected to 7 geo + 4 risk + 1 truth                          |
| 2026-09-04 | Truth source corrected to `sampledb.revenue_leads_plus`; pool 485 to 511, city truth 54 to 284, 140 phone-verified. Property-vs-person question settled (section 15) |
| 2026-09-04 | Consensus scoring, brute-force pairwise matrix, precision/recall risk scoring; DB-IP three files merged (section 16) |
| 2026-09-05 | Source Manager: DynamoDB registry, CRUD plus live diagnose, 12 sources seeded (section 17) |
| 2026-09-05 | `/recommendations` endpoint added — 4 picks, 3 avoid, 7 method steps, 5 caveats (section 18) |
| 2026-09-07 | `unified.ip_geo` (3,577 rows) and `unified.ip_intelligence` (2,044 rows) created with per-row accuracy; endpoints and CSVs added (section 19) |
| 2026-09-07 | Revenue and business-outcome analysis removed from every payload and screen; `scope_note` added (section 19.1) |
| 2026-09-08 | Pool switched to `utm_content` + `furthest_stage` qualified leads: 511 to 2,071 IPs, only 49 in common (section 20.1) |
| 2026-09-08 | Free API daily caps measured: ipwho.is and ipinfo.io stop at 1,000; file sources cover all 2,055 (section 20.2) |
| 2026-09-08 | iCloud Private Relay is 25.4% of qualified traffic; Apple ground truth grew from 30 to 523 IPs (section 20.3) |
| 2026-09-08 | Metric columns added (fill, agreement, cost, bot ID, FPR, precision, recall); accuracy renamed to agreement (sections 20.4-20.8) |
| 2026-09-10 | Source of truth became a table: `ipintel_curated.qualified_lead_ips`, 2,109 IPs, incremental by `ingest_date` (section 21.1) |
| 2026-09-10 | Four tables built and served: vendor_overview_geo/proxy, ip_geo, ip_intelligence; country_code and country_name removed (section 21.2) |
| 2026-09-10 | Latest-decision rule moved FraudLogix FPR from 19.9% to 0.6% (section 21.3); ACCEPTED and MASKED_DEVICES mapping fixed (section 21.4) |



---

## 15. Truth source correction (2026-09-04)

The benchmark originally used `unified.uct_leads`. The correct table is
**`sampledb.revenue_leads_plus`** (14,966,619 leads). Dataset A was untouched — only the benchmark
truth changed.

### The join path — measured, not assumed

`revenue_leads_plus` has **no session id and no IP column**. Every candidate was tested:

| Path | Result |
|---|---|
| `revenue_leads_plus.user_id` ↔ `unified_session_summary.user_id` | ❌ 2,862 vs 49 distinct, **0 overlap** |
| `raw_tune_clicks` → leads | ❌ no email or lead identifier on the clicks table |
| **`revenue_leads_plus.email` ↔ `uct_leads.email` → `alyson_session_id` → session → IP** | ✅ 1,556 of 2,394 emails match |

So `uct_leads` remains as the **bridge to an IP**; `revenue_leads_plus` replaces it as the **source
of truth values**.

### What improved

| Truth field | uct_leads | revenue_leads_plus |
|---|---:|---:|
| IPs with state + ZIP | 485 | **511** |
| IPs with city | 54 | **284** |
| IPs with metro (MSA) | 0 | **313** |
| Phone-verified | 0 | **140** |
| Intro-qualified / deals | — | 137 / 137 |

### The question is settled: the address is the property

`revenue_leads_plus` carries `property_type`, `property_use`, `sell_reason`, `already_has_agent`
and `property_uuid`. It is a property record.

**The decisive test:** the scorecard was run twice — on all 511, and on the 140 phone-verified leads
where a human confirmed the record by phone.

| Segment | n | MaxMind state match |
|---|---:|---:|
| All leads | 511 | 64.3% |
| **Phone-verified** | **140** | **64.0%** |

Identical. Cleaner records do not close the gap, so the ~64% is **not a data-quality artefact** —
the address was never measuring the person's location.

**Consequence:** the metric is renamed, not fixed. It is now **IP-to-property distance**, a
lead-quality and fraud signal. No lead table can measure vendor geolocation accuracy. The only valid
vendor-accuracy anchor remains Apple's published relay city, on 30 IPs.

---

## 16. Consensus scoring (2026-09-04)

With no location ground truth, sources are scored against **each other**, plus the small amount of
real truth available.

### 16.1 Location — consensus method

| Step | Table | What it does |
|---|---|---|
| 1 | `ipintel_analytics.pairwise_agreement` | brute force: all 21 source pairs × state/city/ZIP/lat-lon |
| 2 | *(derived)* | any pair agreeing ≥99.5% on lat/lon collapses to **one voter** |
| 3 | *(in `geo_score`)* | consensus = majority answer per IP per field, requires ≥2 votes |
| 4 | `ipintel_analytics.geo_score` | fill rate, agreement, composite |

```
fill_rate   = (state_filled + city_filled + zip_filled) / (3 × ips)
agreement   = (state_hit + city_hit + zip_hit) / (state_judged + city_judged + zip_judged)
score       = agreement × fill_rate
```

Multiplicative on purpose: a source must be **both present and consistent** to rank well. A field a
source never supplies (DB-IP has no ZIP) counts as unfilled, never as wrong.

**The collapse is mandatory.** geojs.io returns byte-identical state, city and lat/lon to MaxMind on
all 511 IPs. Without collapsing, MaxMind votes twice and "consensus" becomes "whoever has the most
mirrors". geojs is scored but excluded from voting — 6 voters from 7 sources.

| Source | Fill | Agreement | **Score** |
|---|---:|---:|---:|
| **ipinfo.io** | 100% | 84.8% | **84.8** |
| ipwho.is | 100% | 79.7% | **79.7** |
| IP2Location DB11 | 100% | 72.2% | **72.2** |
| proxycheck.io | 97.0% | 70.3% | **68.2** |
| MaxMind GeoLite2 | 96.9% | 61.8% | **59.9** |
| DB-IP combined | 66.7% | 74.8% | **49.9** |
| geojs.io *(mirror)* | 65.0% | 71.7% | **46.6** |

### 16.2 ⚠️ Agreement is not accuracy — the inversion

**MaxMind ranks 1st against Apple's real ground truth but 5th on consensus.**

Consensus rewards conformity. MaxMind disagrees with the crowd more often — and on the 30 IPs where
operator-published truth exists, MaxMind is right while IP2Location places a Dallas address in
Mexico City. If several sources license the same upstream data, the consensus is that upstream's
opinion, not the truth.

The column header must read **Agreement**. This caveat ships in the API as
`scoring_explanation.location_caveat` so it can never be dropped from the UI.

### 16.3 Risk — precision method

Detection rate is not accuracy: a source flagging everything scores 100% and is useless. Each flag
is instead checked against **operator-published ranges** — Tor exits, AWS, GCP, Cloudflare, Fastly,
Apple iCloud Relay — which are facts, not opinions.

```
precision = flagged ∩ known_infrastructure / flagged
recall    = flagged ∩ known_infrastructure / known_infrastructure
f1        = 2·precision·recall / (precision + recall)
score     = f1 × fill_rate
```

| Source | Coverage | Flagged | Precision | Recall | F1 | **Score** |
|---|---:|---:|---:|---:|---:|---:|
| **proxycheck.io** | 511/511 | 33 | **90.9%** | **100%** | **95.2** | **95.2** |
| FraudLogix (TUNE) | 249/511 | 84 | 9.5% | 27.6% | 14.2 | **6.9** |
| IP2Proxy PX12 | 1/511 | 1 | 0% | 0% | — | — |

**Caveat that must ship with this table:** it validates **infrastructure** claims only. FraudLogix
largely detects *behavioural* fraud — bots, abnormal traffic patterns — which by definition never
appears on an infrastructure list. Its low precision here means **unverifiable by this method**, not
wrong. Shipped as `scoring_explanation.risk_caveat`.

### 16.4 Correlated-source findings

- **geojs.io ≡ MaxMind GeoLite2** — 100.0% on state, city *and* lat/lon. One database, two names.
- **DB-IP ↔ proxycheck.io** — 88.6% lat/lon agreement, suggesting shared upstream data. Below the
  99.5% collapse threshold, so both still vote, but worth watching.
- **DB-IP Lite publishes no postal code** — its ZIP renders "not supplied", never 0%.

---

## 17. Source Manager — writable registry (2026-09-05)

Sources moved from a static JSON file to **DynamoDB table `ipintel-sources`**, managed entirely
from the UI.

### Endpoints

```
GET    /sources                 list
POST   /sources                 create (409 on duplicate id)
GET    /sources/{id}            read one
PATCH  /sources/{id}            partial update
DELETE /sources/{id}            remove registry entry (observations retained)
POST   /sources/{id}/diagnose   probe one source live
POST   /diagnose                probe every enabled source
```

### Diagnose is a real probe, not a stored flag

| `probe_type` | Check |
|---|---|
| `http` | live request, returns status code, latency and a response sample |
| `file` | S3 prefix object count |
| `athena` | names the table of record |

**Modifying `probe_target`, `probe_type`, `credential_ref` or `enabled` automatically sets
`diagnosis_status = 'stale'`.** A diagnosis describes a configuration; change the configuration and
the diagnosis is a claim about something that no longer exists.

### Guardrails in the API

- Unknown fields are **rejected**, so the UI cannot invent a column that the pipeline never reads.
- `credential_ref` must start with `ipintel/` — the registry stores secret **names**, never secrets.
- `kind` and `capabilities` are validated against fixed vocabularies.

### Two false-alarm fixes made while wiring this

1. **The Lambda role could not list the reference prefix**, so IP2Location and IP2Proxy reported
   `AccessDenied` — they looked broken when they were fine. Added a scoped `s3:ListBucket` on
   `ip-intelligence/*`.
2. **MaxMind reported `failed`** on its 401. A source needing a key is *unconfigured*, not broken.
   It now returns **`needs_credential`** and names the secret it wants. Otherwise every run cries
   wolf and people stop reading the status column.

### Registry contents — 12 sources, all free

**Enabled (9):** ipinfo.io · ipwho.is · proxycheck.io · MaxMind GeoLite2 · DB-IP combined ·
IP2Location DB11 · IP2Proxy PX12 · FraudLogix via TUNE · Authoritative lists (validator).

**Disabled deliberately (3):**

| Source | Why |
|---|---|
| geojs.io | Byte-identical to MaxMind — enabling it gives MaxMind two votes |
| vpnapi.io | Needs a free API key; would add a third independent risk voter |
| ip-api.com | Free tier is **non-commercial only** |

Live diagnose: **8 healthy · 1 needs_credential · 0 failed.**

To enable vpnapi.io: create the secret `ipintel/vpnapi`, then edit the row in the UI and hit
Diagnose. No code change, no redeploy — that is the point of the registry.

---

## 18. Recommendations endpoint (2026-09-05)

`GET /recommendations` serves the source-selection verdict as **structured data**, so the UI renders
it from the payload and never hardcodes a vendor name, score or caveat. Backed by
`serving/recommendations.json`; refreshing is one `aws s3 cp`.

### Payload shape

| Key | Contents |
|---|---|
| `picks[]` | rank, need, source, verdict, headline, why, `evidence[]`, **`weakness`** |
| `avoid[]` | source, severity, headline, why |
| `fair_warnings[]` | sources whose low score would otherwise be misread |
| `method[]` | 7 steps, each with formula and explanation |
| `caveats[]` | 5 statements that must travel with any report |
| `next_steps[]` | priority, action, why |

### The recommendations

| # | Need | Source | Verdict |
|---|---|---|---|
| 1 | Geolocation — bulk, millions of IPs | **IP2Location LITE DB11** | primary |
| 2 | Geolocation — per-lookup accuracy | **ipinfo.io** | primary |
| 3 | Geolocation — hardest cases | **MaxMind GeoLite2** | specialist |
| 4 | Proxy, VPN and bot detection | **proxycheck.io** | primary |

**Why DB11 leads despite ranking 3rd on consensus:** ipinfo's free tier is 50,000 lookups a month,
so enriching 4.9M IPs once would take eight years. DB11 is a local file — no limit, no per-call
cost, 100% fill — and it already fills geolocation for **644,539 session IPs that have none today,
carrying $7,074,034 (44% of attributed revenue)**. Scale decides this, not the scorecard.

**Avoid:** IP2Proxy PX12 (answered 1 of 511, and silence is not a clean verdict) · geojs.io (MaxMind
mirror) · ip-api.com (free tier is non-commercial only).

**Fair warning:** FraudLogix — 9.5% precision means *unverifiable by this method*, not wrong. It
detects behaviour; the validator lists contain infrastructure.

### Why every pick carries a `weakness`

The field is mandatory in the payload and mandatory to render. A recommendation shown without its
limitation is a sales pitch, and each of these has a real one — DB11 placed a Dallas relay IP in
Mexico City; ipinfo wins on agreement, which is not accuracy.

This is the same principle already recorded in sections 8.3, 8.7 and 9.4: the presentation must
never assert more than the data supports.

### The caveat that leads the list

> **Agreement is not accuracy.** Without it, a reader sees "ipinfo 84.8, MaxMind 59.9" and concludes
> MaxMind is worse — when MaxMind is the only source correct against Apple's real ground truth, and
> ranks low precisely because it disagrees with the crowd.

---

## 19. Unified tables and the removal of revenue (2026-09-07)

### 19.1 Scope narrowed to vendor comparison only

Every revenue and business-outcome figure was removed from the served payloads and the console.
Per-IP revenue attribution was never sound — a shared egress IP sums thousands of different
people, so `146.75.164.0` appeared to carry $90,697 across 53,967 sessions and 7 leads — and it
distracted from the one question this product answers well: **which vendor is right about an IP.**

Removed from `findings.json`, `console.json` and `recommendations.json`:

```
sample.revenue                           sample.revenue_on_shared_infrastructure
sample.deal_ips                          console.overview.total_revenue
console.overview.revenue_on_geo_gap      console.plans (whole object)
risk_scorecard[].revenue_on_flagged_all  risk_scorecard[].revenue_on_flagged_excl_shared
risk_scorecard[].leads_on_flagged        risk_score_v2[].flagged_qualified
risk_score_v2[].false_positive_pct       per_ip[].business
per_ip[].lead.is_deal                    2 revenue-framed issues
```

A new **`scope_note`** field is served on `/summary`, `/console` and `/recommendations` and rendered
by the UI, so the boundary is stated rather than assumed:

> This console compares IP intelligence vendors on a fixed set of 511 test IPs. It does not model
> revenue, fraud loss or business outcomes — those were removed because per-IP revenue attribution
> is unsound on shared infrastructure and distracted from the vendor question.

**Vendor pricing stays.** `cost_model`, `plan` and `limit` are part of comparing vendors; modelled
business revenue is not.

### 19.2 `unified.ip_geo` — 3,577 rows

511 IPs × 7 geo sources, one row per (IP, vendor). Both table names were free in `unified`, so
nothing existing was touched, and data is stored under **our own** `ip-intelligence/unified/`
prefix rather than another team's S3 space.

| Group | Columns |
|---|---|
| Key | `ip_address`, `vendor` |
| Vendor claim | `country_code`, `country_name`, `state`, `city`, `zip_code`, `latitude`, `longitude`, `timezone` |
| Answered | `has_answer` |
| Consensus | `consensus_state`, `consensus_city`, `consensus_zip`, `state_votes`, `city_votes`, `zip_votes` |
| Accuracy | `state_matches_consensus`, `city_matches_consensus`, `zip_matches_consensus`, `fields_answered`, `fields_judged`, `fields_matched`, `row_agreement_pct` |
| Property (not the person) | `property_state`, `property_city`, `property_zip`, `state_matches_property` |
| SCD2 | `observed_at`, `valid_from`, `valid_to` |

| Vendor | Answered | Fields judged | Matched | Avg row agreement |
|---|---:|---:|---:|---:|
| ipinfo.io | 511 | 1,430 | 1,209 | **83.3%** |
| ipwho.is | 511 | 1,430 | 1,150 | 80.1% |
| DB-IP combined | 511 | 1,019 | 756 | 74.3% |
| IP2Location DB11 | 511 | 1,430 | 1,049 | 72.6% |
| geojs.io | 507 | 995 | 707 | 70.4% |
| proxycheck.io | 511 | 1,401 | 973 | 68.6% |
| MaxMind GeoLite2 | 507 | 1,396 | 858 | 60.6% |

**One IP, all seven sources** — the view the table exists to produce:

| Vendor | State | City | ZIP | Agreement |
|---|---|---|---|---:|
| geojs.io · ipwho.is · MaxMind | Maryland | Waldorf | 20602 | 100% |
| ipinfo.io · IP2Location DB11 | Maryland | Waldorf | 20603 | 66.7% |
| DB-IP · proxycheck.io | District of Columbia | Washington D.C. | — | 0% |

Five say Maryland, two say DC — about 30 miles apart, on a single IP.

### 19.3 `unified.ip_intelligence` — 2,044 rows

511 IPs × 4 risk sources.

| Group | Columns |
|---|---|
| Key | `ip_address`, `vendor` |
| Vendor claim | `is_proxy`, `is_vpn`, `is_tor`, `is_datacenter`, `is_bot`, `fraud_reason`, `risk_score`, `isp`, `asn` |
| Answered | `has_answer`, `flagged` |
| Accuracy | `known_infrastructure`, `infrastructure_list`, `verdict_class`, `verdict_correct`, `row_accuracy_pct` |
| SCD2 | `observed_at`, `valid_from`, `valid_to` |

| Vendor | Answered | Flagged | Confirmed | Unconfirmed | Missed | No answer | Avg accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Authoritative lists | 511 | 30 | 30 | 0 | 0 | 0 | 100.0% |
| **proxycheck.io** | 511 | 33 | 30 | 3 | 0 | 0 | **99.4%** |
| FraudLogix (TUNE) | 249 | 84 | 8 | 76 | **21** | 262 | 61.0% |
| IP2Proxy PX12 | 1 | 1 | 0 | 1 | 0 | **510** | 0.0% |

`verdict_class` surfaced something no aggregate had shown: **FraudLogix missed 21 IPs that sit on
published infrastructure ranges.** That was previously buried inside a 27.6% recall figure.

### 19.4 Two schema decisions worth keeping

**The cross join is deliberate, and `has_answer` is why it is safe.** The tables hold every
(IP, vendor) pair, so the grid is complete and easy to read. A row with `has_answer = false` means
*we asked and got nothing* — which is different from *no row*, meaning we never asked. Without that
column the cross join would silently contradict the semantic rule.

**Every classification boolean is nullable, on purpose.** `TRUE` = affirmed, `FALSE` = the vendor
explicitly said no, `NULL` = the vendor said nothing. PX12 is NULL across 510 of 511 rows. Treating
that NULL as `FALSE` is exactly how a proxy becomes a customer.

### 19.5 SCD2 status

`valid_from = observed_at` and `valid_to = NULL` on every row, because this is the first observation
of each (IP, vendor). On the next run, close the prior row by setting its `valid_to` to the new
`observed_at`, then insert the new row with `valid_to` NULL. The columns exist now so history works
without a schema change.

### 19.6 Serving

Two endpoints expose the tables: **`GET /unified/geo`** (3,577 rows, 31 columns) and
**`GET /unified/intelligence`** (2,044 rows, 21 columns). Backed by `serving/unified_geo.json` and
`serving/unified_intel.json`; refreshing is one `aws s3 cp`.

CSV exports: `unified_ip_geo_511.csv` and `unified_ip_intelligence_511.csv`.

### 19.7 Reading queries

The consensus columns cannot simply be renamed to `state` / `city` / `zip_code` — those names are
already taken by each vendor's own answer. Alias the vendor's claim instead:

```sql
SELECT ip_address, vendor, country_code, country_name,
       state    AS vendor_state,
       city     AS vendor_city,
       zip_code AS vendor_zip,
       latitude, longitude, timezone,
       consensus_state AS state,
       consensus_city  AS city,
       consensus_zip   AS zip_code,
       state_matches_consensus, city_matches_consensus, zip_matches_consensus,
       row_agreement_pct,
       observed_at AS created_at,
       valid_from  AS updated_at,
       valid_to
FROM unified.ip_geo
ORDER BY ip_address, vendor;
```

```sql
SELECT ip_address, vendor,
       is_proxy, is_vpn, is_tor, is_datacenter, is_bot,
       isp, asn,
       observed_at AS created_at,
       valid_from  AS updated_at,
       valid_to
FROM unified.ip_intelligence
ORDER BY ip_address, vendor;
```

> **Caution on the second query.** Once `has_answer` is out of the projection, all-NULL booleans are
> the only remaining signal that a vendor had no opinion. If this feeds anything automated, keep
> `has_answer` in the SELECT.

---

## 20. Qualified-lead pool and vendor metrics (2026-09-08)

### 20.1 The pool changed — and it is a different population

The benchmark moved from the email bridge to **`utm_content` joined on `session_id`**, restricted to
qualified leads:

```sql
JOIN unified.unified_session_summary s ON s.session_id = trim(r.utm_content)
WHERE r.furthest_stage IN ('introduced','agent_left_vm','connected','meeting_scheduled',
      'met_in_person','coming_soon','listing','in_escrow','closed','closed_booked','closed_paid')
```

New table: **`ipintel_curated.lead_truth_v2`**.

| | Old (email via `uct_leads`) | New (`utm_content` + `furthest_stage`) |
|---|---:|---:|
| IPs | 511 | **2,071** |
| with state + ZIP | 511 | 2,055 |
| with city | 284 | **1,812** |
| **phone-verified** | 140 (27%) | **1,660 (80%)** |
| Qualified leads behind it | — | 1,579,163 → 2,530 matched |

> **Only 49 IPs overlap with the old pool.** This is different traffic, not an extension. Every
> figure published before 2026-09-08 refers to a population that is no longer in use.

**Caveat on the join.** Only 2,442 of 911,053 distinct `utm_content` values match a `session_id` —
a 0.27% match rate. Either `utm_content` carries a session id for only some traffic sources, or
`unified_session_summary` retains less history than the lead table. Worth one question to the lead
pipeline owner; if it is retention, a wider window could grow this pool substantially.

### 20.2 Free API tiers do not scale — measured, not assumed

Enriching 2,055 IPs exposed hard daily caps that were invisible at 511:

| Source | Returned | Note |
|---|---:|---|
| proxycheck.io | **2,055** | batch POST of 100/request — barely touched its 1,000/day cap |
| DB11 · PX12 · MaxMind · DB-IP | **2,055** | local files, no cap |
| ipwho.is | **1,000** | undocumented daily cap; "fair use" is literally 1,000 |
| ipinfo.io | **1,000** | free-tier cap |
| geojs.io | timed out | rate-limited. Dropped from the run — it is a MaxMind mirror and does not vote, so it contributes no information |

**At 2,055 IPs the free API tiers cover half the pool; the file-based sources cover all of it.**
This is the strongest evidence yet for IP2Location DB11 as the bulk primary, and it explains why
proxycheck's batch endpoint matters so much — it is the only API that keeps up.

Their ~49% fill rate is the **vendor's cap, not our failure**, and the registry coverage note says so.

### 20.3 A quarter of qualified traffic is iCloud Private Relay

**523 of 2,055 IPs (25.4%)** are on Apple's published relay ranges — up from 5.8% in the old pool.

Two consequences:

1. **Blocking relay traffic would reject a quarter of your qualified leads.**
2. **Real ground truth grew 17×.** Apple publishes the city for every relay egress range, so those
   523 IPs carry operator-stated truth rather than consensus. That is now a large enough set to
   measure genuine vendor *accuracy* alongside agreement — and it remains the only place in this
   product where the word "accuracy" is earned.

### 20.4 Metric columns added

**Geo** — `fill_rate_pct`, `state/city/zip_agreement_pct`, `agreement_pct`, `cost_per_1k`, `score`.

**Risk** — `fill_rate_pct`, `detection_rate_pct`, `bot_identification_pct`,
`false_positive_rate_pct`, `precision_infra_pct`, `recall_infra_pct`, `f1_infra`, `cost_per_1k`,
`score`, plus `precision_bot_pct` / `recall_bot_pct` / `bot_metric_status`.

`cost_per_1k` was added to all 12 registry entries — **$0.00 everywhere**, with `paid_tier` noting
proxycheck's $5.99/mo. The column exists so "free" is stated rather than assumed, and so a paid tier
has somewhere to land.

### 20.5 🛑 Bot precision and recall are NULL by design

**Every IP in this pool produced a qualified lead**, so it is a confirmed human. That has two
opposite consequences:

- **False-positive rate is exact.** Any bot flag here is definitively wrong, so FPR needs no
  estimation.
- **Bot precision and recall are undefined.** The pool contains no true bots, so recall has no
  denominator and precision computes to 0 for every vendor — a number that measures nothing.

They are stored as NULL with `bot_metric_status = 'needs a bot-labelled pool'`. **Rendering 0% there
would look like vendor failure when it is a measurement gap.** To fill them, a pool containing known
bots is required: `is_bot_click` sessions are cheapest but measure agreement with an incumbent
rather than truth; a labelled fraud set would be authoritative and does not yet exist.

### 20.6 Geolocation scorecard — 2,055 IPs, 5 voters

| Source | Fill | State | City | ZIP | Agreement | Cost/1k | **Score** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **ipinfo.io** | 100% | **98.3%** | **94.6%** | 49.0% | 84.5% | $0.00 | **84.5** |
| ipwho.is | 100% | 97.8% | 83.9% | 45.0% | 79.3% | $0.00 | **79.3** |
| proxycheck.io | 95.6% | 90.9% | 77.7% | **69.8%** | 81.8% | $0.00 | **78.2** |
| IP2Location DB11 | 99.9% | 83.4% | 64.1% | 56.9% | 70.6% | $0.00 | **70.6** |
| MaxMind GeoLite2 | 95.8% | 88.7% | 59.6% | 48.2% | 69.7% | $0.00 | **66.8** |
| DB-IP combined | 66.7% | 82.3% | 69.9% | — | 76.2% | $0.00 | **50.8** |

Agreement is far higher than on the old pool — 98.3% state versus 64% — because qualified-lead
traffic is much cleaner than the previous population. **proxycheck.io leads on ZIP at 69.8%**, well
ahead of the field.

### 20.7 Risk scorecard — FPR is the headline

| Source | Coverage | Flagged | Bot ID % | **FPR** | Precision | Recall | F1 | **Score** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **proxycheck.io** | 2,055 | 541 | 0.0% | **0.0%** | **97.0%** | **100%** | 98.5 | **98.5** |
| FraudLogix (TUNE) | 1,651 | 539 | 19.9% | **19.9%** | 8.2% | 8.9% | 8.5 | **6.8** |
| IP2Proxy PX12 | 5 | 5 | 0.0% | 0.0% | 0.0% | 0.0% | — | — |

**FraudLogix raised 329 bot flags on confirmed-human traffic — a 19.9% false-positive rate.** That
is the clearest measured cost of its behavioural detection on this population.

proxycheck flags 541 IPs but none as bots, so its FPR is 0.0% while still reaching 97% precision and
100% recall against operator-published ranges.

**IP2Proxy PX12 answered 5 of 2,055 (0.2%).** It should come out of the roster.

### 20.8 Rename: Accuracy → Agreement

Applied across API fields, table columns and UI labels: `*_agree_pct` → `*_agreement_pct`,
`row_accuracy_pct` → `row_agreement_pct`.

The word *accuracy* survives in exactly two places, because both measure against fact rather than
conformity: **precision/recall against operator-published ranges**, and the **Apple-verified ground
truth** (now 523 IPs). Everywhere else, consensus measures agreement with a majority — and §16.2
records why that is not the same thing.

---

## 21. Source-of-truth table and the four-table model (2026-09-10)

### 21.1 The population is now a table, not a list

The benchmark no longer runs against a fixed set of IPs. It reads
**`ipintel_curated.qualified_lead_ips`**, built from the qualified-lead join and partitioned by
`ingest_date` so refreshes are incremental:

```sql
FROM sampledb.revenue_leads_plus r
JOIN unified.unified_session_summary s ON s.session_id = trim(r.utm_content)
WHERE r.furthest_stage IN ('introduced','agent_left_vm','connected','meeting_scheduled',
      'met_in_person','coming_soon','listing','in_escrow','closed','closed_booked','closed_paid')
GROUP BY s.session_ip
```

| | Value |
|---|---:|
| IPs | **2,109** |
| Qualified leads behind them | 2,579 |
| with state + ZIP | 2,105 |
| with city | 1,855 |
| phone-verified | 1,699 |
| Lead date range | 2021-05-26 → 2026-09-09 |

Every row carries `confirmed_human = true`, because reaching one of the eleven progressed stages
means a person was introduced, spoke to an agent, met, listed or closed. **That is what makes the
false-positive rate exact rather than estimated.**

A new qualified lead now enters the next run automatically. No IP list to maintain.

### 21.2 Four tables

| Table | Rows | Grain |
|---|---:|---|
| `unified.vendor_overview_geo` | 7 | one per geo vendor |
| `unified.vendor_overview_proxy` | 4 | one per risk vendor |
| `unified.ip_geo` | 14,735 | one per (IP, geo vendor) |
| `unified.ip_intelligence` | 8,420 | one per (IP, risk vendor) |

`country_code` and `country_name` were removed from `ip_geo`. The UI shows a restricted projection;
the remaining columns exist for analytics.

Served at `/tables/vendor-overview-geo`, `/tables/vendor-overview-proxy`, `/tables/ip-geo` and
`/tables/ip-proxy`.

### 21.3 ⭐ The "latest decision" rule changed the FraudLogix verdict

An IP can have many TUNE clicks with different `access_control_decision` values. Taking the
**latest** decision per IP instead of "ever flagged across all history":

| | Ever-flagged | Latest decision |
|---|---:|---:|
| Bot flags | 329 | **10** |
| False-positive rate | **19.9%** | **0.6%** |

Most historical bot flags had been superseded by a later ACCEPTED on the same IP. Judging a vendor
on its full flag history rather than its current verdict was making FraudLogix look far worse than
it is. **This materially changes the recommendation**, and every future comparison must use the
latest decision.

### 21.4 ACCEPTED and MASKED_DEVICES — the mapping, and why

| `fraud_reason` | Rows | `is_proxy` | `is_bot` | `is_masked_device` |
|---|---:|---:|---:|---:|
| ACCEPTED | 1,196 | 0 | 0 | 0 |
| *(no answer)* | 419 | — | — | — |
| PROXY | 371 | 371 | 0 | 0 |
| MASKED_DEVICES | 52 | 0 | **0** | **52** |
| NON_HUMAN_SCRIPT | 5 | 0 | **5** | 0 |

**ACCEPTED writes explicit `false` to all five booleans**, with `fraud_reason = 'ACCEPTED'`. That is
a real negative, distinct from NULL, which means the vendor said nothing.

**MASKED_DEVICES sets none of the five booleans** and gets its own `is_masked_device` column.

It means the *device fingerprint* was obscured — user-agent spoofing, canvas/WebGL blocking,
anti-fingerprinting browsers (Brave, Firefox strict, Safari with Private Relay), privacy extensions.
That is a **device** signal, not a network or automation one, so it is not proxy, VPN, Tor or
datacenter. And it is not a bot:

> **195 confirmed humans in this pool carry MASKED_DEVICES**, and 25% of the pool is on iCloud
> Private Relay. Masking mostly tracks Apple privacy features used by real customers. Folding it
> into `is_bot` would mislabel the best customers and inflate the false-positive rate.

Only `BOT_GENERATED` and `NON_HUMAN_SCRIPT` set `is_bot`. Measured on confirmed humans, both are
noisy: 234 and 35 confirmed humans respectively carried them across the full history.

### 21.5 Vendor Overview — Geo

Two column groups, kept deliberately separate: **Agreement** (versus other vendors) and **Truth**
(versus the qualified lead's own address). They answer different questions.

| Vendor | Fill | Agreement | State Truth | City Truth | ZIP Truth | Cost/1k | **Score** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **proxycheck.io** | 95.6% | 80.5% | 59.7% | 13.0% | 5.4% | $0.00 | **77.0** |
| IP2Location DB11 | 94.9% | 71.7% | 58.1% | 14.6% | 3.4% | $0.00 | **68.0** |
| MaxMind GeoLite2 | 95.9% | 69.8% | **64.3%** | **20.4%** | **10.3%** | $0.00 | **66.9** |
| DB-IP combined | 66.7% | 75.3% | 56.5% | 11.9% | — | $0.00 | **50.2** |
| geojs.io *(mirror)* | 64.5% | 75.2% | 64.3% | 20.6% | — | $0.00 | **48.5** |
| ipinfo.io | **49.9%** | **85.8%** | 54.3% | 11.9% | 4.0% | $0.00 | **42.8** |
| ipwho.is | **49.9%** | 78.3% | 53.7% | 11.1% | 1.8% | $0.00 | **39.1** |

**ipinfo.io has the highest agreement and the lowest score.** Its free tier capped at 1,050 of
2,105 IPs — the most consistent source is also the least available one, and the multiplicative
score is what makes that trade-off visible rather than hidden.

**MaxMind leads every Truth column while ranking 3rd on Agreement** — the same inversion recorded
in §16.2. Agreeing with the crowd and being right are different things.

### 21.6 Vendor Overview — Proxy

| Vendor | Answered | Flagged | Bot flags | **FPR** | Precision | Recall | Masked-device | **Score** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Authoritative lists | 2,105 | 540 | 0 | 0.0% | 100% | 100% | 0 | **100.0** |
| **proxycheck.io** | 2,105 | 556 | 0 | **0.0%** | **97.1%** | **100%** | 0 | **99.2** |
| FraudLogix (TUNE) | 1,686 | 392 | 10 | **0.6%** | 0.5% | 0.4% | 52 | **46.9** |
| IP2Proxy PX12 | **5** | 5 | 0 | 0.0% | 0.0% | 0.0% | 0 | **0.0** |

`precision_bot_pct` and `recall_bot_pct` remain NULL with
`bot_metric_status = 'needs a bot-labelled pool'` — the pool is 100% confirmed humans, so there are
no true bots to catch and recall has no denominator. Rendering 0% there would read as vendor
failure when it is a measurement gap.

**IP2Proxy PX12 answered 5 of 2,105.** It should come out of the roster.

### 21.7 UI decision: one scorecard home

The scorecards stay on **Findings**, repointed at the two overview tables. No separate `/vendors`
page.

Vendor scores in two places is the duplication already fixed once, when Vendor Comparison was
turned into a pointer to Findings (§9.3). Findings also already carries the scoring explanation
boxes, the truth caveat and the ground-truth card, all of which apply unchanged to the new tables —
moving the scorecards elsewhere would either duplicate that context or strand the numbers without
it.

### 21.8 The disagreements filter stays — computed, not stored

The UI projection for `/tables/ip-geo` deliberately serves only ten columns, so `row_agreement_pct`
is not in the payload. The first plan therefore proposed dropping the "disagreements only" filter.

**It stays, computed client-side instead.** Group the loaded rows by `ip_address`; an IP is in
disagreement when the non-null `state`, `city` or `zip_code` values are not all identical across
the vendors that answered. When the filter is on, keep **every row of those IPs**, so the user sees
the full side-by-side comparison rather than orphaned rows. Compare case-insensitively, trim
whitespace, and ignore nulls — a vendor that gave no answer is not a disagreement.

**Why this matters enough to keep:** *show me the IPs where vendors disagree* is the question this
console exists to answer. Everything needed is already in the payload, so the filter costs nothing
and the restricted column list stays intact. Adding `row_agreement_pct` back to the projection
would have solved it too, but at the cost of the rule that the UI shows only the ten agreed columns.

The equivalent Athena query is in `ATHENA_QUERIES.sql` §7.
