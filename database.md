# Database & Data Models: IP DBs + Tune Clicks

> LLM-oriented schema + measured statistics companion to [`context.md`](./context.md).  
> Sources: local CSV dumps in `/Users/ahsanz/ahsanz-revcloud/ip-db-api` and Athena table `raw.raw_tune_clicks` (account `221490242148`, region `us-west-2`).

---

## 1. Inventory of datasets

| Logical name | Physical source | Format | Header? | Row count (data) | Notes |
|--------------|-----------------|--------|---------|------------------|-------|
| IP2Location Lite DB11 (full) | `IP2LOCATION-LITE-DB11.CSV` | CSV, quoted fields | **No** | 2,984,119 | Full IPv4 span |
| IP2Location Lite DB11 (US sample) | `IP2LOCATION-LITE-DB11-us-1000.csv` | CSV | **Yes** | 1,000 | Convenience sample only |
| IP2Proxy Lite PX12 (full) | `IP2PROXY-LITE-PX12.CSV` | CSV, quoted fields | **No** | 2,690,046 | Proxy/risk ranges only |
| IP2Proxy Lite PX12 (US sample) | `IP2PROXY-LITE-PX12-us-1000.csv` | CSV | **Yes** | 1,000 | Convenience sample only |
| Tune clicks (local sample) | `raw_tune_clicks_100K_sample.csv` | CSV | **Yes** | 100,000 | Export of `raw.raw_tune_clicks` |
| Tune clicks (warehouse) | Athena/`Glue` `raw.raw_tune_clicks` | External table on S3 | N/A | 16,302,182 rows @ analysis time | `s3://datalake-raw-221490242148-us-west-2/tune/raw_tune_clicks_3` |
| Generated DB11 100K IP sample | `ip2location_db11_100k_ip_sample.csv` | CSV | Yes | 100,000 | seed 42 |
| Generated DB11 1M IP sample | `ip2location_db11_1m_ip_sample.csv` | CSV | Yes | 1,000,000 | seed 42 |

---

## 2. IP2Location Lite DB11

### 2.1 Schema

Full file has **no header**. Column order (aligned with the US sample header):

| # | Column | Type (logical) | Description |
|---|--------|----------------|-------------|
| 0 | `ip_from` | uint32 as decimal string | Inclusive start of IPv4 range (integer form) |
| 1 | `ip_to` | uint32 as decimal string | Inclusive end of IPv4 range |
| 2 | `country_code` | string | ISO-like country code, or `-` |
| 3 | `country_name` | string | Country name, or `-` |
| 4 | `region_name` | string | Region/state, or `-` |
| 5 | `city_name` | string | City, or `-` |
| 6 | `latitude` | float string | e.g. `37.323000`; unknown often `0.000000` |
| 7 | `longitude` | float string | e.g. `-122.032180`; unknown often `0.000000` |
| 8 | `zip_code` | string | Postal code, or `-` |
| 9 | `time_zone` | string | Offset like `-07:00` / `+08:00`, or `-` |

Example row (full file, first data-ish rows):

```text
"0","16777215","-","-","-","-","0.000000","0.000000","-","-"
"16777216","16777471","AU","Australia","Queensland","Brisbane","-27.467540","153.028090","4000","+10:00"
```

US sample header line:

```text
ip_from,ip_to,country_code,country_name,region_name,city_name,latitude,longitude,zip_code,time_zone
```

### 2.2 Keys & join semantics

- **Grain:** one row = one contiguous IPv4 inclusive range.
- **Lookup key:** convert subject IPv4 → uint32 `ip_int`; find row where `ip_from <= ip_int <= ip_to`.
- Ranges are sorted by `ip_from` and are **contiguous with no gaps** in this dump:
  - `min(ip_from) = 0`
  - `max(ip_to) = 4294967295` (`2^32 - 1`)
  - Sum of `(ip_to - ip_from + 1)` = **4,294,967,296** (100% of IPv4)
  - Gaps between consecutive ranges = **0**

### 2.3 Sentinel / missing values

| Pattern | Meaning used in analysis |
|---------|--------------------------|
| `country_code = '-'` (and usually city/region/tz `-`, lat/lon `0.000000`) | No usable geo |
| Non-`-` country + city + nonzero coords | “Full / usable geo” |

### 2.4 Measured coverage (full DB11 dump)

| Metric | Value |
|--------|--------|
| Ranges | 2,984,119 |
| IPv4 addresses covered | 4,294,967,296 (100%) |
| US ranges (`country_code='US'`) | 911,913 |
| US address count | 1,494,722,560 (~34.8017% of IPv4) |
| Ranges with `country_code='-'` | 7,658 |
| Addresses with `country_code='-'` | 616,359,168 (~14.3507% of IPv4) |

**Top countries by address mass (approx):**

| country_code | Addresses | % of IPv4 |
|--------------|-----------|-----------|
| US | 1,494,722,560 | 34.8017% |
| `-` | 616,359,168 | 14.3507% |
| CN | 350,573,056 | 8.1624% |
| JP | 191,341,312 | 4.4550% |
| DE | 140,457,984 | 3.2703% |
| GB | 135,351,808 | 3.1514% |
| KR | 116,172,800 | 2.7049% |
| BR | 85,046,528 | 1.9801% |
| FR | 83,393,024 | 1.9416% |
| CA | 73,615,616 | 1.7140% |

### 2.5 Lite product caveats (vendor + analysis)

- Lite resolves at **Class C (/24)** majority location when a /24 spans multiple places.
- Vendor ballpark accuracy: ~**98%** country, ~**60%** city (Lite); commercial higher.
- Therefore: “covered” ≠ “city-accurate,” especially for ARIN/US traffic.

---

## 3. IP2Proxy Lite PX12

### 3.1 Schema

Full file has **no header**. Column order (aligned with US sample header):

| # | Column | Type (logical) | Description |
|---|--------|----------------|-------------|
| 0 | `ip_from` | uint32 string | Range start (often equal to `ip_to` for single-IP rows) |
| 1 | `ip_to` | uint32 string | Range end |
| 2 | `proxy_type` | string | Proxy classification (e.g. `PUB` in samples) |
| 3 | `country_code` | string | Country code |
| 4 | `country_name` | string | Country name |
| 5 | `region_name` | string | Region |
| 6 | `city_name` | string | City |
| 7 | `isp` | string | ISP / org |
| 8 | `domain` | string | Domain |
| 9 | `usage_type` | string | Network usage category (see enum below) |
| 10 | `asn` | string | ASN number or `-` |
| 11 | `as` | string | AS name (column name is `as` in sample header) |
| 12 | `last_seen` | string | Days-since / last-seen style field (sample values like `30`) |
| 13 | `threat` | string | Threat tags or `-` |
| 14 | `provider` | string | VPN/proxy provider name or `-` |
| 15 | `fraud_score` | string/int | Risk score (always populated in this dump) |

US sample header:

```text
ip_from,ip_to,proxy_type,country_code,country_name,region_name,city_name,isp,domain,usage_type,asn,as,last_seen,threat,provider,fraud_score
```

Example:

```text
"18935707","18935707","PUB","US","United States of America","California","El Segundo","RackIP Consultancy Pte. Ltd.","rackip.com","DCH","64050","BGP Network Limited","30","-","-","80"
```

### 3.2 Keys & join semantics

- **Grain:** proxy/risk IP range (sometimes a single IP where `ip_from == ip_to`).
- **Lookup:** same uint32 between-bounds join as DB11.
- **Universe:** only listed proxy-related ranges — **not** full IPv4. Non-match means “not in PX12 Lite,” not “not a proxy.”

### 3.3 `usage_type` enum (measured distinct values)

Measured on full `IP2PROXY-LITE-PX12.CSV` (**2,690,046** rows), 11 distinct values:

| usage_type | Meaning (IP2Location convention) | Rows | % of PX12 rows |
|------------|----------------------------------|------|----------------|
| `DCH` | Data Center / Web Hosting / Transit | 2,639,857 | ~98.13% |
| `ISP` | Fixed Line ISP | 20,131 | ~0.75% |
| `EDU` | University / College / School | 19,355 | ~0.72% |
| `ISP/MOB` | Fixed + Mobile ISP | 7,435 | ~0.28% |
| `COM` | Commercial | 1,712 | ~0.06% |
| `MOB` | Mobile ISP | 878 | ~0.03% |
| `GOV` | Government | 342 | ~0.01% |
| `CDN` | Content Delivery Network | 294 | ~0.01% |
| `MIL` | Military | 20 | ~0.0007% |
| `ORG` | Organization | 20 | ~0.0007% |
| `LIB` | Library | 2 | ~0.00007% |

### 3.4 Column fill rates (`threat`, `provider`, `fraud_score`)

Definition used: **filled** = value is not empty and not `-`.

| Column | Filled rows | Fill % | Dash `-` % | Blank % |
|--------|-------------|--------|------------|---------|
| `threat` | 51,002 | **1.8960%** | 98.1040% | 0% |
| `provider` | 26,278 | **0.9769%** | 99.0231% | 0% |
| `fraud_score` | 2,690,046 | **100.0000%** | 0% | 0% |

#### `threat` when filled (top values)

| Value | Rows | % of all PX12 rows |
|-------|------|--------------------|
| `-` | 2,639,044 | 98.1040% |
| `SCANNER` | 18,040 | 0.6706% |
| `BOTNET` | 14,976 | 0.5567% |
| `SPAM` | 13,721 | 0.5101% |
| `SPAM/SCANNER` | 2,500 | 0.0929% |
| `SPAM/BOTNET` | 928 | 0.0345% |
| `SPAM/SCANNER/BOTNET` | 491 | 0.0183% |
| `SCANNER/BOTNET` | 346 | 0.0129% |

#### `provider` when filled (examples)

Mostly `-`. Top named providers include: `24Shells`, `Blazing SEO`, `code200`, `ExpressVPN`, `UnitVpn`, `WisdomISP`, `Mysterium VPN`, `NordVPN`, etc. (each ≪ 0.3% of rows).

### 3.5 `fraud_score` value domain & distribution

| Property | Value |
|----------|--------|
| Distinct values | 20 |
| Min | **27** |
| Max | **99** |
| Always populated | Yes |

Full histogram (all PX12 rows):

| fraud_score | Rows | % |
|-------------|------|---|
| 27 | 3 | 0.0001% |
| 28 | 9 | 0.0003% |
| 29 | 5 | 0.0002% |
| 30 | 5 | 0.0002% |
| 31 | 13 | 0.0005% |
| 32 | 5 | 0.0002% |
| 33 | 5 | 0.0002% |
| 34 | 7 | 0.0003% |
| 35 | 29 | 0.0011% |
| 36 | 28,363 | 1.0544% |
| **80** | **2,309,652** | **85.8592%** |
| 91 | 47,311 | 1.7587% |
| 92 | 39,070 | 1.4524% |
| 93 | 34,135 | 1.2689% |
| 94 | 32,835 | 1.2206% |
| 95 | 33,955 | 1.2622% |
| 96 | 20,484 | 0.7615% |
| 97 | 17,890 | 0.6650% |
| 98 | 17,632 | 0.6555% |
| 99 | 108,638 | 4.0385% |

**Clusters (approx):**

- Default-ish: `80` ≈ **85.86%**
- High band `91–99` ≈ **12.83%**
- Low band `27–36` ≈ **1.06%**

---

## 4. `raw.raw_tune_clicks` (Tune clicks)

### 4.1 Warehouse table

| Property | Value |
|----------|--------|
| Glue/Athena | `raw.raw_tune_clicks` |
| S3 location | `s3://datalake-raw-221490242148-us-west-2/tune/raw_tune_clicks_3` |
| Partitions | None |
| Rows @ analysis | 16,302,182 |
| Distinct `ip` @ analysis | 4,527,008 |

### 4.2 Column list (Glue `StorageDescriptor`)

All typed as strings unless noted:

`transaction_id`, `affiliate_id`, `affiliate_manager_id`, `advertiser_id`, `advertiser_manager_id`, `offer_id`, `creative_url_id`, `affiliate_click_id`, `affiliate_source`, `affiliate_sub1`…`affiliate_sub5`, `affiliate_unique_1`…`affiliate_unique_5`,  
`datetime` (**timestamp**), `date_pst` (**date**),  
`revenue_cents`, `payout_cents`, `refer`, `url`, `pixel_refer`,  
**`ip`**, `user_agent`, **`country_code`**, `browser_id`, `is_click_unique`,  
`ad_campaign_id`, `ad_campaign_creative_id`, `offer_file_id`, `status`, `offer_file_size`,  
`currency`, `payout_type`, `revenue_type`,  
`device_brand`, `device_model`, `device_os`, `device_os_version`,  
`device_id`, `device_id_md5`, `device_id_sha1`,  
`android_id`, `android_id_md5`, `android_id_sha1`,  
`mac_address`, `mac_address_md5`, `mac_address_sha1`,  
`odin`, `open_udid`, `ios_ifa`, `ios_ifa_md5`, `ios_ifa_sha1`, `ios_ifv`,  
`user_id`, `unknown_id`, `payout_group_id`, `revenue_group_id`,  
`req_connection_speed`, `google_aid`,  
`access_control_decision`, `access_control_reason_code`,  
`s3_file_path`, `source_file`, `processing_timestamp` (**timestamp**)

### 4.3 Fields most relevant to IP enrichment

| Column | Role |
|--------|------|
| `ip` | Primary join/lookup key (dotted IPv4 in analyzed samples) |
| `country_code` | Upstream country; compared to DB11 country (98.12% agree on 100K sample) |
| `datetime` / `date_pst` | Event time |
| `user_agent` / device_* | Device context (not used in IP DB analyses yet) |
| `access_control_decision` | e.g. `ACCEPTED` in sample rows |

### 4.4 Local sample file

`raw_tune_clicks_100K_sample.csv` — same columns as warehouse export; 100,000 data rows + header.

Observed in that sample:

- 100% rows had parseable IPv4 in `ip`
- 71,718 distinct IPs
- Top sample `country_code` values skewed heavily to `US` (~95K rows)

---

## 5. Generated analysis tables / files

### 5.1 DB11 random IP samples

**Files:**

- `ip2location_db11_100k_ip_sample.csv`
- `ip2location_db11_1m_ip_sample.csv`

**Schema:**

| Column | Type | Description |
|--------|------|-------------|
| `ip` | string | Dotted IPv4 sampled from a DB11 range |
| `ip_int` | int | Integer form of `ip` |
| `range_from` | int | Source DB11 `ip_from` |
| `range_to` | int | Source DB11 `ip_to` |
| `db_country` | string | Source DB11 `country_code` |

**Generation algorithm:**

1. Load all DB11 ranges.
2. `random.seed(42)`.
3. Sample N distinct range indices without replacement (`random.sample`).
4. For each range, pick `ip_int = random.randint(range_from, range_to)` with light dedupe.
5. Emit CSV; upload to S3 for Athena.

**Athena external table (1M run):** `scratch_ahsan.ip2location_db11_1m_ip_sample`  
**Location:** `s3://ahsan-athena-scratch-221490242148-us-west-2/ip2location_coverage/`  
**SerDe:** OpenCSVSerde, skip header line.

Country mix in 1M sample (range-uniform, not address-weighted), top codes:

| db_country | Sample IPs (approx) |
|------------|---------------------|
| US | 305,383 |
| FR | 45,392 |
| GB | 44,096 |
| JP | 40,478 |
| BR | 36,467 |
| DE | 33,895 |
| IT | 31,680 |
| CA | 25,808 |

---

## 6. Analysis results (structured for retrieval)

### 6.1 Clicks → DB11 (local 100K click sample)

| Metric | Value |
|--------|--------|
| Click rows | 100,000 |
| Unique IPs | 71,718 |
| Range match rate (rows) | 100% |
| Range match rate (unique IPs) | 100% |
| Usable geo rows | 99,983 (99.983%) |
| No-geo rows (country `-`) | 17 (0.017%) |
| No-geo unique IPs | 17 — all in `148.178.x.x` / range ints `2494693376`–`2494758911` |
| `country_code` agreement vs DB11 | 98.12% |
| Top mismatch examples | BR→US (303), US→JM (198), US→SE (138) |

Top DB11 countries by click rows (after lookup): US 94,623; BD 520; PK 453; NG 394; IN 325; …

### 6.2 DB11 → clicks exact overlap (Athena)

| Sample size | IPs present in `raw.raw_tune_clicks` | Rate | Matching click rows |
|-------------|--------------------------------------|------|---------------------|
| 100,000 | 214 | 0.2140% | 711 |
| 1,000,000 | 2,327 | 0.2327% | 5,872 |

1M hits by DB country (top): US 2,264; GB 9; CA 5; MX 5; DE 4; IN 4; …

Clicks table denominators at same time: **16,302,182** rows, **4,527,008** distinct IPs.

### 6.3 PX12 quality fields (summary)

| Field | Fill % | Notes |
|-------|--------|------|
| `usage_type` | 100% (always one of 11 codes) | Dominated by `DCH` |
| `threat` | 1.90% | Mostly `-` |
| `provider` | 0.98% | Mostly `-` |
| `fraud_score` | 100% | Range 27–99; mode 80 (~85.86%) |

---

## 7. Recommended physical data model (if loading to warehouse)

Suggested normalized enrichment tables (not yet created in Glue beyond scratch samples):

### 7.1 `ip2location_lite_db11`

```text
ip_from       bigint  not null  -- PK part
ip_to         bigint  not null  -- PK part / check ip_to >= ip_from
country_code  string
country_name  string
region_name   string
city_name     string
latitude      double
longitude     double
zip_code      string
time_zone     string
```

**Serving pattern:** sort by `ip_from`; binary search or Athena `ip_int BETWEEN ip_from AND ip_to` (broadcast small side / range join carefully).

### 7.2 `ip2proxy_lite_px12`

```text
ip_from       bigint
ip_to         bigint
proxy_type    string
country_code  string
country_name  string
region_name   string
city_name     string
isp           string
domain        string
usage_type    string
asn           string
as_name       string   -- rename from `as`
last_seen     string   -- or int if cleaned
threat        string   -- nullable / '-'
provider      string   -- nullable / '-'
fraud_score   int
```

### 7.3 Enrichment output grain (suggested)

One row per click (or per distinct click IP):

```text
ip
ip_int
db11_country_code
db11_region_name
db11_city_name
db11_latitude
db11_longitude
db11_zip_code
db11_time_zone
db11_geo_usable          boolean  -- false if country_code = '-'
px12_matched             boolean
px12_proxy_type
px12_usage_type
px12_threat              -- null if '-'
px12_provider            -- null if '-'
px12_fraud_score         -- null if unmatched
```

---

## 8. Validation rules / gotchas for LLMs & pipelines

1. Full DB11/PX12 CSVs have **no header** — do not use first row as schema.
2. Sample `*-us-1000.csv` files **do** have headers and are **not** complete US extracts.
3. Integer IPs are **strings in CSV** — cast to bigint/uint32 before range compares.
4. Treat `-` as NULL for geo/proxy string fields when computing fill rates.
5. `fraud_score` being non-null does **not** imply high information content (mode 80).
6. Exact equality joins of randomly sampled DB IPs to clicks understate range-level traffic overlap.
7. DB11 full-space coverage makes “% of click IPs found in DB” a weak KPI; prefer usable-geo % and accuracy audits.
8. PX12 non-match ≠ clean IP.
9. Column named `as` in PX12 sample header is awkward in SQL — alias to `as_name`.
10. Athena proxy env: unset `HTTP(S)_PROXY` if CLI query start fails in this laptop environment.

---

## 9. Quick reference formulas

```text
ip_int = (((a*256 + b)*256 + c)*256 + d)   for IPv4 a.b.c.d

match_db11(ip) := exists range where ip_from <= ip_int <= ip_to

usable_geo := country_code not in ('','-')
              AND city_name not in ('','-')
              AND latitude not in ('','-','0.000000')
              AND longitude not in ('','-','0.000000')

px12_filled(col) := col is not null AND trim(col) <> '' AND col <> '-'
```

---

## 10. File ↔ Athena map

| Local / logical | Athena / S3 |
|-----------------|-------------|
| Clicks warehouse | `raw.raw_tune_clicks` |
| 1M DB11 IP sample | `scratch_ahsan.ip2location_db11_1m_ip_sample` → `s3://ahsan-athena-scratch-221490242148-us-west-2/ip2location_coverage/` |
| Athena results | `s3://ahsan-athena-scratch-221490242148-us-west-2/athena-results/` |
| Datalake raw root | `s3://datalake-raw-221490242148-us-west-2/` |

---

*End of database.md — see context.md for narrative, methods, and decision takeaways.*
