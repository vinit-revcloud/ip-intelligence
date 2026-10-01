# Context: IP Geolocation / Proxy Coverage Analysis

> LLM-oriented project brief. Companion file: [`database.md`](./database.md) (schemas, enums, measured stats).  
> Last updated from chat analysis sessions: **2026-08-13 → 2026-08-14** (follow-up fraud_score deep-dive; docs written 2026-08-18).

---

## 1. Purpose

Evaluate whether **IP2Location Lite DB11** (geo) and **IP2Proxy Lite PX12** (proxy/fraud) are usable enrichment sources for click traffic in **`raw.raw_tune_clicks`** (Tune / affiliate click stream in the RevCloud datalake).

Core questions answered so far:

1. Of click IPs, how many fall inside IP2Location Lite DB11 ranges?
2. Does DB11 cover all US (or all IPv4) addresses?
3. How are DB integer IP ranges converted to dotted-quad IPs?
4. Of randomly sampled IPs *from* DB11, how many appear in `raw.raw_tune_clicks`? (100K and 1M samples)
5. What are IP2Proxy Lite `usage_type` values, and how complete are `threat` / `provider` / `fraud_score`?

---

## 2. Project layout (local workspace)

**Workspace root:** `/Users/ahsanz/ahsanz-revcloud/ip-db-api`

| File | Role | Approx size |
|------|------|-------------|
| `IP2LOCATION-LITE-DB11.CSV` | Full IP2Location Lite DB11 (no header) | ~331 MB, **2,984,119** ranges |
| `IP2LOCATION-LITE-DB11-us-1000.csv` | US-only **sample** of DB11 (**not** full US set); has header | ~117 KB, 1,000 data rows |
| `IP2PROXY-LITE-PX12.CSV` | Full IP2Proxy Lite PX12 (no header) | ~449 MB, **2,690,046** ranges |
| `IP2PROXY-LITE-PX12-us-1000.csv` | US-only **sample** of PX12; has header | ~164 KB, 1,000 data rows |
| `raw_tune_clicks_100K_sample.csv` | Local export of 100K rows from `raw.raw_tune_clicks`; has header | ~97 MB, 100,000 data rows |
| `ip2location_db11_100k_ip_sample.csv` | Generated: 100K random IPs drawn from DB11 ranges | ~4.8 MB |
| `ip2location_db11_1m_ip_sample.csv` | Generated: 1M random IPs drawn from DB11 ranges | ~48 MB |
| `context.md` | This file | — |
| `database.md` | Data models + analysis metrics | — |

**Important:** `*-us-1000.csv` files are convenience samples (~1K US rows). Full US coverage in DB11 is ~**911,913** US-labeled ranges, not 1,000.

---

## 3. Environment & data access

### 3.1 AWS / Athena

| Item | Value |
|------|--------|
| AWS account | `221490242148` |
| Default region | `us-west-2` |
| Athena workgroup used | `primary` (Athena engine v3) |
| Scratch / results bucket | `s3://ahsan-athena-scratch-221490242148-us-west-2/` |
| Athena results prefix | `s3://ahsan-athena-scratch-221490242148-us-west-2/athena-results/` |
| Sample IP upload prefix | `s3://ahsan-athena-scratch-221490242148-us-west-2/ip2location_coverage/` |
| Glue / Athena DB for temp tables | `scratch_ahsan` |
| Clicks database.table | `raw.raw_tune_clicks` |
| Clicks S3 location (Glue) | `s3://datalake-raw-221490242148-us-west-2/tune/raw_tune_clicks_3` |
| Related raw prefix (source files seen in sample) | `s3://datalake-raw-221490242148-us-west-2/tune/HL_tune_clicks_files/...` |

**Ops note:** Athena CLI calls in this environment sometimes fail if HTTP(S)_PROXY points at a local dead proxy. Unset proxy env vars before `aws athena ...` if queries hang or return empty QueryExecutionId.

### 3.2 Athena objects created during analysis

- `scratch_ahsan.ip2location_db11_100k_ip_sample` — created for 100K run; later **dropped** when folder was reused for 1M sample.
- `scratch_ahsan.ip2location_db11_1m_ip_sample` — external CSV table over the 1M sample location (header skipped).

Schema of sample tables:

```text
ip string
ip_int bigint
range_from bigint
range_to bigint
db_country string
```

### 3.3 Observed clicks table scale (Athena, full table scan)

At analysis time (`raw.raw_tune_clicks`):

| Metric | Value |
|--------|--------|
| Click rows | **16,302,182** |
| Distinct `ip` | **4,527,008** |
| Approx data scanned for IP-focused queries | ~87–184 MB (table appears relatively compact on S3 at that time) |
| Partition keys | **None** (unpartitioned external table) |

---

## 4. Domain concepts

### 4.1 IP2Location Lite DB11 (geo)

- Free/open “LITE” geolocation DB: country, region, city, lat/lon, ZIP, timezone.
- Rows are **IP ranges** `[ip_from, ip_to]` stored as **32-bit unsigned integers**, not dotted quads.
- Official Lite limitation: resolution is effectively **Class C (/24)** majority location. Country accuracy claimed ~98%; city ~60%. Commercial DB is finer-grained and more accurate.
- This copy **covers the entire IPv4 address space** (`ip_from` min `0` … `ip_to` max `4294967295`) with **zero gaps** between consecutive ranges. Therefore **every valid IPv4 looks up to some row**.
- Some rows have country/region/city = `-` and lat/lon `0.000000` (unknown / unallocated / no usable geo). In this DB copy: **7,658** such ranges; **~616M** addresses labeled country `-` (~14.35% of IPv4).
- US-labeled address mass in this copy: **~1.495B** addresses (~34.8% of IPv4) across **911,913** US ranges.

### 4.2 IP2Proxy Lite PX12 (proxy / risk)

- Lite proxy/VPN/threat-oriented DB; also range-based integer IPs.
- Includes `proxy_type`, geo-ish fields, ISP/domain, `usage_type`, ASN, `last_seen`, `threat`, `provider`, `fraud_score`.
- **Does not cover all IPv4** the way DB11 does — only listed proxy/suspicious ranges (2.69M rows). Absence from PX12 ≠ “clean”; it only means “not in this proxy DB.”
- Placeholder for missing string fields is typically `-`.

### 4.3 Tune clicks (`raw.raw_tune_clicks`)

- Affiliate / offer click stream (Tune). Key field for this work: **`ip`** (dotted IPv4 strings in samples, e.g. `99.69.36.99`).
- Also carries `country_code` from upstream (useful to compare vs DB11 country).
- Local 100K CSV was exported from this table for offline analysis; full-table joins used Athena.

---

## 5. IP encoding & lookup methods

### 5.1 Integer ↔ dotted quad

DB files store:

```text
ip_from, ip_to  ∈  [0, 4294967295]
```

Convert:

```python
import ipaddress
ipaddress.IPv4Address(18935296)           # -> IPv4Address('1.32.238.0')
int(ipaddress.IPv4Address("99.69.36.99")) # -> 1665281123
```

Manual:

```python
def int_to_ip(n: int) -> str:
    return ".".join(str((n >> s) & 255) for s in (24, 16, 8, 0))
```

Athena / Presto-style:

```sql
format('%s.%s.%s.%s',
  (ip_from / 16777216) % 256,
  (ip_from / 65536) % 256,
  (ip_from / 256) % 256,
  ip_from % 256)
```

Example from DB11 US sample:

| ip_from | ip_to | Dotted range |
|---------|-------|--------------|
| 18935296 | 18935551 | `1.32.238.0` – `1.32.238.255` |
| 28442624 | 28442879 | `1.178.0.0` – `1.178.0.255` |

### 5.2 Range membership (local analysis)

For click → DB11:

1. Parse click `ip` as IPv4 → `ip_int`.
2. Load DB11 ranges sorted by `ip_from`.
3. `idx = bisect_right(starts, ip_int) - 1`.
4. Hit iff `idx >= 0` and `starts[idx] <= ip_int <= ends[idx]`.

### 5.3 Sampling IPs *from* DB11 (for reverse overlap)

Used for “how many DB IPs appear in clicks?”:

1. Load all DB11 ranges.
2. `random.sample` N distinct ranges (seed **42**).
3. For each range, `random.randint(ip_from, ip_to)` → unique dotted IP.
4. Upload CSV → Athena external table → `JOIN raw.raw_tune_clicks ON ip`.

This measures **exact IP string equality**, not “any IP in the same /24 as a click.” Exact match rates are therefore expected to be low (~0.2%).

---

## 6. Analyses performed (chronological)

### A. Click sample → DB11 coverage (local)

**Input:** `raw_tune_clicks_100K_sample.csv` (100,000 rows).  
**DB:** `IP2LOCATION-LITE-DB11.CSV`.

| Metric | Result |
|--------|--------|
| Rows | 100,000 |
| Unique IPs | 71,718 |
| All IPs valid IPv4 | Yes (0 IPv6 / invalid / empty) |
| Rows matching a DB11 range | **100,000 (100%)** |
| Unique IPs matching a range | **71,718 (100%)** |
| Rows with usable geo (country + city + coords) | **99,983 (99.983%)** |
| Rows in range but geo = `-` | **17 (0.017%)** — all `148.178.x.x`, same unknown range |
| Distinct DB countries on unique IPs (excl `-`) | 150 |
| Sample `country_code` == DB11 country | **98.12%** of rows |

**Interpretation:** Because DB11 spans all IPv4, range hit rate for valid IPv4 is trivially 100%. The useful KPI is **usable geo fill**, not mere range membership.

Canvas artifact (optional UI):  
`/Users/ahsanz/.cursor/projects/Users-ahsanz-ahsanz-revcloud-ip-db-api/canvases/ip2location-coverage.canvas.tsx`

### B. “Does Lite DB11 cover all US IPs?”

**Answer (precise):**

- **Lookup coverage:** Yes — every IPv4, including every US address, maps to some DB11 row (full space, no gaps).
- **Correct US labeling / city accuracy:** No guarantee. Lite is /24-majority; ~98% country / ~60% city per vendor. Not every ARIN-US address is necessarily labeled `US` in Lite.
- **`IP2LOCATION-LITE-DB11-us-1000.csv`:** sample only, not exhaustive US inventory.

### C. DB11 IP sample → clicks overlap (Athena) — 100K

**Input:** 100,000 random IPs from DB11 (seed 42).  
**Target:** full `raw.raw_tune_clicks`.

| Metric | Result |
|--------|--------|
| Sample IPs | 100,000 |
| Present in clicks (exact `ip`) | **214 (0.214%)** |
| Matching click rows | 711 |
| Of hits by DB country | US 210, CA 2, ZA 1, GP 1 |

### D. DB11 IP sample → clicks overlap (Athena) — 1M

Same method, N=1,000,000, seed 42.

| Metric | Result |
|--------|--------|
| Sample IPs | 1,000,000 |
| Present in clicks | **2,327 (0.2327%)** |
| Matching click rows | 5,872 |
| US among hits | 2,264 (~97% of hits) |

**Interpretation:** Reverse overlap is small because ~4.5M distinct click IPs ≪ IPv4 space; random addresses from random DB ranges rarely equal an observed click IP. This is the **inverse** of analysis A (clicks→DB ≈ 100%).

Rough consistency: 100K → 0.214%; 1M → 0.233%.

### E. IP2Proxy Lite field inventory

- Distinct `usage_type` values and counts (see `database.md`).
- Fill rates: `threat` ~1.90%, `provider` ~0.98%, `fraud_score` **100%**.
- `fraud_score` range **27–99**; dominant value **80** (~85.86%). Full histogram in `database.md`.

---

## 7. Key takeaways for future LLM / engineering work

1. **Enriching clicks with DB11 geo is feasible for IPv4:** expect near-universal range hits; watch for `-` geo rows (~0.017% in the 100K click sample).
2. **Do not confuse “in DB11” with “accurately geolocated.”** Lite = coarser /24 majority logic.
3. **PX12 is a sparse proxy list**, not a full IP universe. Use for positive proxy/risk signals; missing ≠ safe.
4. **`fraud_score` is always present** in this PX12 dump but heavily skewed to `80` — treat as a coarse score, validate before using as a hard threshold.
5. **`threat` / `provider` are rarely filled** in Lite PX12 (~1–2%); do not design features that assume dense fill.
6. **Direction of overlap matters:**
   - clicks ⊂ DB11 ranges ≈ 100% (IPv4)
   - random DB11 IPs ⊂ clicks ≈ 0.2%
7. Prefer **integer range join** (`ip_int BETWEEN ip_from AND ip_to`) for production enrichment; exact IP equality against sampled DB IPs is the wrong join shape for geo coverage.
8. US sample CSVs are **not** production datasets.

---

## 8. Suggested next analyses (not done yet)

- Range-level overlap: what % of sampled DB11 **/24 ranges** contain ≥1 click IP (vs exact IP match).
- US-only DB11 sample vs clicks.
- Join clicks to **PX12** (proxy_type, fraud_score, usage_type) and measure match rate / score distribution on real traffic.
- Compare Lite vs commercial DB if licensed.
- IPv6: not present in the 100K click sample; confirm whether Tune emits IPv6 elsewhere.

---

## 9. Reproducibility notes

| Item | Value |
|------|--------|
| Random seed for DB11 IP samples | `42` |
| Local range lookup | Python `bisect` on sorted `ip_from` |
| Athena join pattern | `sample.ip = raw.raw_tune_clicks.ip` |
| Generated sample columns | `ip, ip_int, range_from, range_to, db_country` |

Example Athena overlap query pattern:

```sql
SELECT
  (SELECT COUNT(*) FROM scratch_ahsan.ip2location_db11_1m_ip_sample) AS sample_ips,
  COUNT(DISTINCT s.ip) AS sample_ips_present_in_clicks,
  COUNT(*) AS matching_click_rows
FROM scratch_ahsan.ip2location_db11_1m_ip_sample s
JOIN raw.raw_tune_clicks c
  ON c.ip = s.ip;
```

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| DB11 | IP2Location Lite database edition with city/ZIP/timezone fields |
| PX12 | IP2Proxy Lite database edition used in this repo |
| Lite | Free IP2Location/IP2Proxy tier; Class-C oriented, fewer fields / lower accuracy than commercial |
| `ip_from` / `ip_to` | Inclusive integer bounds of an IPv4 range |
| `-` | Sentinel for missing / unknown string geo or proxy attributes |
| Tune clicks | Affiliate click events landed in `raw.raw_tune_clicks` |
| Exact IP overlap | String/IPv4 equality between a sampled DB IP and a click `ip` |
| Usable geo | Country code present (not `-`) plus city and non-zero coordinates |
