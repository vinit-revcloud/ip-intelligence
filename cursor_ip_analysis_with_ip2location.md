# IP analysis with ip2location
_Exported on 8/18/2026 at 01:08:58 GMT+5 from Cursor (3.14.7)_

---

**User**

I have placed a 100K sample from raw.raw_tune_clicks table at the root of this project. Out of this sample, we need to check how many IPs are we able to find within the IP ranges of ip2location lite db. Can you perform this analaysis & share the results with me?

---

**Cursor**

I'll locate the 100K sample and the IP2Location Lite data, then check how many sample IPs fall within those ranges.

Next I'll inspect the sample and IP2Location schemas so we can match IPs against the ranges correctly.

Running a Python match: convert sample IPs to integers and binary-search them against the IP2Location ranges.

Full IPv4 coverage explains the 100% hit rate — I'll check how many land in real geo ranges vs the `-` / unknown placeholders.

Creating a canvas with the analysis results.

**100% of sample IPs fall within IP2Location Lite DB11 ranges.** Usable geo is available for **99.983%** of clicks.

Open the full breakdown beside chat: [ip2location-coverage](/Users/ahsanz/.cursor/projects/Users-ahsanz-ahsanz-revcloud-ip-db-api/canvases/ip2location-coverage.canvas.tsx) (a live canvas for this analysis).

| Metric | Result |
|---|---|
| Click rows | 100,000 |
| Unique IPs | 71,718 |
| Matched to a DB range | **100%** (rows & unique) |
| Valid IPv4 / IPv6 / invalid | 100% / 0 / 0 |
| Full geo (country + city + coords) | **99,983** rows (99.983%) |
| In a range but geo = `-` | **17** rows / 17 unique IPs |

**Why 100% range coverage?** DB11 spans the full IPv4 space (`0`–`4294967295`), so every valid IPv4 hits some range. The useful question is whether that range has real location data.

**The 17 no-geo IPs** all sit in `148.178.x.x` (unknown/reserved DB fields). Everything else resolved to real country/city/coords across **150** countries (US ~94.6% of rows).

**Bonus:** sample `country_code` agreed with DB11 on **98.12%** of rows.

---

**User**

Does the ip2location lite db 11 database cover all US IP addresses?

---

**Cursor**

I'll check how US ranges are represented in DB11 and whether that implies full US IPv4 coverage.

**Yes for lookup coverage, no for perfect US labeling/accuracy.**

IP2Location Lite DB11 includes **every IPv4 address** — the ranges run from `0` to `4,294,967,295` with **no gaps**. Any US IP will match a row.

What that does *not* mean:

1. **Not every US-allocated IP is labeled `US`.** In this copy, **911,913** ranges (~**1.49B** addresses, ~34.8% of IPv4) are marked `US`. Other addresses may be other countries or `-` (unknown), even if ARIN considers them US space.
2. **Lite is Class C (/24) only.** Within a `/24`, it keeps the majority location, so city/ZIP can be wrong even when country is right. IP2Location cites ~**98%** country / ~**60%** city accuracy for Lite vs higher for commercial.
3. **`IP2LOCATION-LITE-DB11-us-1000.csv` is just a 1,000-row US sample**, not the full US set (the full DB has ~912K US ranges).

**Bottom line:** You can look up any US IPv4 in Lite DB11. You should not treat it as a complete, perfectly accurate inventory of all US IPs at city level.

---

**User**

How do I format the IPs from these IP ranges?

---

**Cursor**

The ranges in those CSVs are stored as **32-bit integers**, not dotted quads. Checking the sample format so I can show the conversion.

`ip_from` / `ip_to` are **IPv4 addresses as 32-bit integers**. Convert them to dotted quads like this:

**Python**
```python
import ipaddress

ipaddress.IPv4Address(18935296)  # -> 1.32.238.0
ipaddress.IPv4Address(18935551)  # -> 1.32.238.255
```

Or manually:
```python
def int_to_ip(n: int) -> str:
    return ".".join(str((n >> s) & 255) for s in (24, 16, 8, 0))
```

**SQL (Athena / Presto / Trino)**
```sql
format('%s.%s.%s.%s',
  (ip_from / 16777216) % 256,
  (ip_from / 65536) % 256,
  (ip_from / 256) % 256,
  ip_from % 256
)
```

**Example from your file**

| ip_from | ip_to | dotted range |
|---|---|---|
| 18935296 | 18935551 | `1.32.238.0` – `1.32.238.255` |
| 28442624 | 28442879 | `1.178.0.0` – `1.178.0.255` |

Reverse (string → int) when looking up click IPs:
```python
int(ipaddress.IPv4Address("99.69.36.99"))
```

---

**User**

Can you run a 100K ip sample against raw.raw_tune_clicks & determine how many IPs from ip2location db11 lite are present in raw.raw_tune_clicks table. Share the results here.

---

**Cursor**

I'll sample 100K IPs from IP2Location Lite DB11 and check how many appear in `raw.raw_tune_clicks` — first checking what data access we have.

Checking AWS/Athena access to query the full `raw.raw_tune_clicks` table.

Sampling 100K IPs from DB11, uploading them, and joining against the full Athena clicks table.

Athena hit a proxy issue — retrying with a cleaner runner.

Join finished — gathering table size and a country breakdown of the matches.

**214 of 100,000** sampled IP2Location Lite DB11 IPs appear in `raw.raw_tune_clicks` (**0.214%**).

### Method
- Drew **100,000 unique IPs** from DB11 by sampling random ranges, then a random address inside each range (seed `42`)
- Exact-matched those IPs to the full Athena table `raw.raw_tune_clicks`

### Results

| Metric | Value |
|---|---|
| DB11 sample IPs | 100,000 |
| Present in `raw.raw_tune_clicks` | **214** (0.214%) |
| Matching click rows | 711 |
| Clicks table size | 16,302,182 rows · 4,527,008 distinct IPs |

**By DB country (of the 214 hits):**

| Country | Sample IPs | Present in clicks |
|---|---|---|
| US | 30,578 | **210** |
| CA | 2,549 | 2 |
| ZA | 748 | 1 |
| GP | 14 | 1 |
| Others | — | 0 |

Almost all overlap is US traffic, which fits the clicks mix.

**Why so low?** DB11 covers all IPv4; a random IP from a random `/24` is unlikely to be one of the ~4.5M distinct IPs in clicks. This is the reverse of the earlier check (clicks → DB), which was ~100%.

Sample file: `ip2location_db11_100k_ip_sample.csv` (also on S3 as `scratch_ahsan.ip2location_db11_100k_ip_sample`). I can rerun with US-only sampling or range-level overlap (any click IP inside the sampled ranges) if that would be more useful.

---

**User**

<timestamp>Thursday, Aug 13, 2026, 11:47 PM (UTC+5)</timestamp>
<system_notification>
The following task has finished. If you were already aware, ignore this notification and do not restate prior responses.

<task>
kind: shell
status: aborted
task_id: 539518
title: Create Athena external table for 100K IP sample
tool_call_id: call-a4175acf-9a1f-4ed2-9d37-b6876d524a16-28
fc_244c4621-f3af-9948-ab36-1a1469ba533c_0
output_path: /Users/ahsanz/.cursor/projects/Users-ahsanz-ahsanz-revcloud-ip-db-api/terminals/539518.txt
</task>
</system_notification>
<user_query>Briefly inform the user about the task result and perform any follow-up actions (if needed). If there's no follow-ups needed, don't explicitly say that.</user_query>

---

**Cursor**

The earlier Athena setup job was aborted after a proxy connection failure. The analysis was rerun successfully afterward — results are unchanged: **214 / 100,000** sampled DB11 IPs were found in `raw.raw_tune_clicks`.

---

**User**

What are the distinct values for usage_type column in ip2proxy lite database?

---

**Cursor**

I'll check the IP2Proxy Lite schema and pull the distinct `usage_type` values.

There are **11** distinct `usage_type` values in IP2Proxy Lite PX12:

| usage_type | Meaning | Rows |
|---|---|---|
| `DCH` | Data Center/Web Hosting/Transit | 2,639,857 |
| `ISP` | Fixed Line ISP | 20,131 |
| `EDU` | University/College/School | 19,355 |
| `ISP/MOB` | Fixed + Mobile ISP | 7,435 |
| `COM` | Commercial | 1,712 |
| `MOB` | Mobile ISP | 878 |
| `GOV` | Government | 342 |
| `CDN` | Content Delivery Network | 294 |
| `MIL` | Military | 20 |
| `ORG` | Organization | 20 |
| `LIB` | Library | 2 |

`DCH` dominates (~98% of ranges).

---

**User**

Can you run a 1 million ip sample against raw.raw_tune_clicks & determine how many IPs from ip2location db11 lite are present in raw.raw_tune_clicks table. Share the results here.

---

**Cursor**

I'll sample 1M IPs from DB11 Lite, upload them, and join against `raw.raw_tune_clicks` the same way as the 100K run.

**2,327 of 1,000,000** sampled IP2Location Lite DB11 IPs appear in `raw.raw_tune_clicks` (**0.2327%**).

### Method
- Sampled **1,000,000 unique IPs** from DB11 (random range → random IP in range, seed `42`)
- Exact-matched to full Athena table `raw.raw_tune_clicks`

### Results

| Metric | Value |
|---|---|
| DB11 sample IPs | 1,000,000 |
| Present in `raw.raw_tune_clicks` | **2,327** (0.2327%) |
| Matching click rows | 5,872 |

**Top countries among hits:**

| Country | Sample IPs | Present in clicks |
|---|---|---|
| US | 305,383 | **2,264** |
| GB | 44,096 | 9 |
| CA | 25,808 | 5 |
| MX | 13,422 | 5 |
| DE | 33,895 | 4 |
| IN | 23,182 | 4 |

~97% of matches are US (2,264 / 2,327). Hit rate is in line with the earlier 100K run (0.214% → 0.233%).

---

**User**

on the proxy db, can you tell how % are the threat, fraud_score & provider columns are filled?

---

**Cursor**

I'll measure fill rates for `threat`, `fraud_score`, and `provider` in the IP2Proxy Lite DB.

In **IP2Proxy Lite PX12** (2,690,046 rows), treating `-` as empty:

| Column | Filled | Fill % |
|---|---|---|
| `threat` | 51,002 | **1.90%** |
| `provider` | 26,278 | **0.98%** |
| `fraud_score` | 2,690,046 | **100%** |

`threat` and `provider` are almost always `-`. `fraud_score` is always populated (mostly `80` — ~86% of rows).

---

**User**

What's value range for fraud score, what % have what values?

---

**Cursor**

**Range:** `27`–`99` (20 distinct values) across 2,690,046 rows.

| fraud_score | Rows | % |
|---|---|---|
| 27 | 3 | 0.0001% |
| 28 | 9 | 0.0003% |
| 29 | 5 | 0.0002% |
| 30 | 5 | 0.0002% |
| 31 | 13 | 0.0005% |
| 32 | 5 | 0.0002% |
| 33 | 5 | 0.0002% |
| 34 | 7 | 0.0003% |
| 35 | 29 | 0.0011% |
| 36 | 28,363 | 1.05% |
| **80** | **2,309,652** | **85.86%** |
| 91 | 47,311 | 1.76% |
| 92 | 39,070 | 1.45% |
| 93 | 34,135 | 1.27% |
| 94 | 32,835 | 1.22% |
| 95 | 33,955 | 1.26% |
| 96 | 20,484 | 0.76% |
| 97 | 17,890 | 0.67% |
| 98 | 17,632 | 0.66% |
| 99 | 108,638 | 4.04% |

Most rows are **80** (~86%). High-risk cluster **91–99** is ~12.8%; low scores **27–36** are ~1.1%.

