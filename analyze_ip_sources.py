#!/usr/bin/env python3
"""Cross-source IP analysis: Tune clicks x IP2Location DB11 x IP2Proxy PX12."""

from __future__ import annotations

import csv
import ipaddress
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
TUNE_PATH = os.path.join(ROOT, "raw_tune_clicks_100K_sample.csv")
DB11_PATH = os.path.join(ROOT, "IP2LOCATION-LITE-DB11.CSV")
PX12_PATH = os.path.join(ROOT, "IP2PROXY-LITE-PX12.CSV")
SESSION_PATH = os.path.join(ROOT, "session_summary_geo_columns_100K_sample.csv")
OUT_PATH = os.path.join(ROOT, "analysis_results.json")

# CSV field-size safety for wide Tune rows
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def log(msg: str) -> None:
    print(msg, flush=True)


def is_filled(val: str | None) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    return s not in ("", "-", "null", "None", "NULL")


def ip_to_int(ip: str) -> int | None:
    try:
        return int(ipaddress.IPv4Address(ip.strip()))
    except Exception:
        return None


def analyze_tune() -> dict:
    log(f"[1/5] Reading Tune sample: {TUNE_PATH}")
    rows = 0
    unique_ips: dict[str, int] = {}
    invalid_ips = 0
    empty_ips = 0
    ipv6 = 0

    ac_decision = Counter()
    ac_reason = Counter()
    status_vals = Counter()
    country = Counter()

    ac_decision_filled_rows = 0
    ac_reason_filled_rows = 0
    status_filled_rows = 0
    both_ac_filled_rows = 0

    # Per-IP aggregation for access_control completeness
    ip_decisions: dict[str, set[str]] = defaultdict(set)
    ip_reasons: dict[str, set[str]] = defaultdict(set)
    ip_statuses: dict[str, set[str]] = defaultdict(set)
    ip_countries: dict[str, set[str]] = defaultdict(set)

    with open(TUNE_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows += 1
            ip = (row.get("ip") or "").strip()
            dec = (row.get("access_control_decision") or "").strip()
            reason = (row.get("access_control_reason_code") or "").strip()
            st = (row.get("status") or "").strip()
            cc = (row.get("country_code") or "").strip()

            if not ip:
                empty_ips += 1
            else:
                unique_ips[ip] = unique_ips.get(ip, 0) + 1
                ip_int = ip_to_int(ip)
                if ip_int is None:
                    if ":" in ip:
                        ipv6 += 1
                    else:
                        invalid_ips += 1

            if is_filled(dec):
                ac_decision_filled_rows += 1
                ac_decision[dec] += 1
            else:
                ac_decision["<empty>"] += 1
            if is_filled(reason):
                ac_reason_filled_rows += 1
                ac_reason[reason] += 1
            else:
                ac_reason["<empty>"] += 1
            if is_filled(st):
                status_filled_rows += 1
                status_vals[st] += 1
            else:
                status_vals["<empty>"] += 1
            if is_filled(dec) and is_filled(reason):
                both_ac_filled_rows += 1
            if cc:
                country[cc] += 1

            if ip:
                ip_decisions[ip].add(dec if is_filled(dec) else "<empty>")
                ip_reasons[ip].add(reason if is_filled(reason) else "<empty>")
                ip_statuses[ip].add(st if is_filled(st) else "<empty>")
                if cc:
                    ip_countries[ip].add(cc)

    n_unique = len(unique_ips)

    ips_with_decision = sum(
        1 for ip, vals in ip_decisions.items() if any(v != "<empty>" for v in vals)
    )
    ips_with_reason = sum(
        1 for ip, vals in ip_reasons.items() if any(v != "<empty>" for v in vals)
    )
    ips_with_both_ac = sum(
        1
        for ip in unique_ips
        if any(v != "<empty>" for v in ip_decisions[ip])
        and any(v != "<empty>" for v in ip_reasons[ip])
    )
    ips_missing_any_ac = n_unique - ips_with_both_ac

    # Flagged: anything other than ACCEPTED / NOT_APPLICABLE
    flagged_rows = 0
    flagged_ips = set()
    accepted_only_ips = 0
    mixed_decision_ips = 0
    for ip, vals in ip_decisions.items():
        non_empty = {v for v in vals if v != "<empty>"}
        if any(v not in ("ACCEPTED",) for v in non_empty):
            flagged_ips.add(ip)
        if len(non_empty) > 1:
            mixed_decision_ips += 1
        if non_empty == {"ACCEPTED"}:
            accepted_only_ips += 1
    for ip, vals in ip_reasons.items():
        non_empty = {v for v in vals if v != "<empty>"}
        if any(v not in ("NOT_APPLICABLE",) for v in non_empty):
            flagged_ips.add(ip)

    # Row-level flagged
    # recompute from counters
    flagged_decision_rows = rows - ac_decision.get("ACCEPTED", 0) - ac_decision.get("<empty>", 0)
    flagged_reason_rows = rows - ac_reason.get("NOT_APPLICABLE", 0) - ac_reason.get("<empty>", 0)

    us_rows = country.get("US", 0)
    us_unique = sum(1 for ip, ccs in ip_countries.items() if "US" in ccs)

    ip_ints = {}
    for ip in unique_ips:
        n = ip_to_int(ip)
        if n is not None:
            ip_ints[ip] = n

    log(
        f"    rows={rows:,} unique_ips={n_unique:,} valid_ipv4={len(ip_ints):,} "
        f"ac_decision_fill={ac_decision_filled_rows/rows*100:.4f}% "
        f"flagged_ips={len(flagged_ips):,}"
    )

    return {
        "rows": rows,
        "unique_ips": n_unique,
        "valid_ipv4_unique": len(ip_ints),
        "empty_ips": empty_ips,
        "invalid_ips": invalid_ips,
        "ipv6_ips": ipv6,
        "ac_decision_filled_rows": ac_decision_filled_rows,
        "ac_reason_filled_rows": ac_reason_filled_rows,
        "status_filled_rows": status_filled_rows,
        "both_ac_filled_rows": both_ac_filled_rows,
        "ac_decision_fill_pct_rows": round(ac_decision_filled_rows / rows * 100, 6),
        "ac_reason_fill_pct_rows": round(ac_reason_filled_rows / rows * 100, 6),
        "both_ac_fill_pct_rows": round(both_ac_filled_rows / rows * 100, 6),
        "status_fill_pct_rows": round(status_filled_rows / rows * 100, 6),
        "ips_with_decision": ips_with_decision,
        "ips_with_reason": ips_with_reason,
        "ips_with_both_ac": ips_with_both_ac,
        "ips_missing_any_ac": ips_missing_any_ac,
        "ips_with_both_ac_pct": round(ips_with_both_ac / n_unique * 100, 6) if n_unique else 0,
        "ac_decision_dist": dict(ac_decision.most_common()),
        "ac_reason_dist": dict(ac_reason.most_common()),
        "status_dist": dict(status_vals.most_common(30)),
        "country_dist_top": dict(country.most_common(15)),
        "us_rows": us_rows,
        "us_rows_pct": round(us_rows / rows * 100, 4),
        "us_unique_ips": us_unique,
        "us_unique_pct": round(us_unique / n_unique * 100, 4) if n_unique else 0,
        "flagged_unique_ips": len(flagged_ips),
        "flagged_unique_pct": round(len(flagged_ips) / n_unique * 100, 6) if n_unique else 0,
        "accepted_only_ips": accepted_only_ips,
        "mixed_decision_ips": mixed_decision_ips,
        "flagged_decision_rows": flagged_decision_rows,
        "flagged_reason_rows": flagged_reason_rows,
        "_ip_ints": ip_ints,
        "_ip_counts": unique_ips,
        "_flagged_ips": flagged_ips,
        "_ip_countries": {ip: sorted(v) for ip, v in ip_countries.items()},
    }


def load_db11_ranges() -> dict:
    log(f"[2/5] Loading IP2Location DB11 ranges: {DB11_PATH}")
    starts = []
    ends = []
    countries = []
    cities = []
    zips = []
    lats = []
    lons = []
    regions = []

    us_ranges = 0
    us_addrs = 0
    dash_ranges = 0
    dash_addrs = 0
    zip_filled_ranges = 0
    city_filled_ranges = 0
    n = 0
    prev_to = -1
    gaps = 0

    with open(DB11_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for rec in reader:
            if not rec or len(rec) < 10:
                continue
            a = int(rec[0])
            b = int(rec[1])
            cc = rec[2]
            city = rec[5]
            zipc = rec[8]
            width = b - a + 1
            starts.append(a)
            ends.append(b)
            countries.append(cc)
            cities.append(city)
            zips.append(zipc)
            regions.append(rec[4])
            lats.append(rec[6])
            lons.append(rec[7])
            n += 1
            if prev_to >= 0 and a != prev_to + 1:
                gaps += 1
            prev_to = b
            if cc == "US":
                us_ranges += 1
                us_addrs += width
            if cc == "-":
                dash_ranges += 1
                dash_addrs += width
            if is_filled(city):
                city_filled_ranges += 1
            if is_filled(zipc):
                zip_filled_ranges += 1

    log(f"    DB11 ranges={n:,} US_ranges={us_ranges:,} US_addrs={us_addrs:,} gaps={gaps}")
    return {
        "starts": np.array(starts, dtype=np.uint32),
        "ends": np.array(ends, dtype=np.uint32),
        "countries": np.array(countries, dtype=object),
        "cities": np.array(cities, dtype=object),
        "zips": np.array(zips, dtype=object),
        "regions": np.array(regions, dtype=object),
        "lats": np.array(lats, dtype=object),
        "lons": np.array(lons, dtype=object),
        "n_ranges": n,
        "gaps": gaps,
        "us_ranges": us_ranges,
        "us_addrs": us_addrs,
        "dash_ranges": dash_ranges,
        "dash_addrs": dash_addrs,
        "city_filled_ranges": city_filled_ranges,
        "zip_filled_ranges": zip_filled_ranges,
        "min_from": int(starts[0]) if starts else None,
        "max_to": int(ends[-1]) if ends else None,
    }


def load_px12_ranges() -> dict:
    log(f"[3/5] Loading IP2Proxy PX12 ranges: {PX12_PATH}")
    starts = []
    ends = []
    proxy_types = []
    countries = []
    usage_types = []
    threats = []
    providers = []
    scores = []
    isps = []

    n = 0
    addrs = 0
    us_ranges = 0
    us_addrs = 0
    score_dist = Counter()
    proxy_dist = Counter()
    usage_dist = Counter()
    threat_filled = 0
    provider_filled = 0
    score_80 = 0
    score_high = 0  # 91-99
    default_flagged_addrs = 0  # fraud_score == 80
    high_flagged_addrs = 0

    with open(PX12_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for rec in reader:
            if not rec or len(rec) < 16:
                continue
            a = int(rec[0])
            b = int(rec[1])
            width = b - a + 1
            ptype = rec[2]
            cc = rec[3]
            usage = rec[9]
            threat = rec[13]
            provider = rec[14]
            score_s = rec[15]
            try:
                score = int(score_s)
            except Exception:
                score = -1
            starts.append(a)
            ends.append(b)
            proxy_types.append(ptype)
            countries.append(cc)
            usage_types.append(usage)
            threats.append(threat)
            providers.append(provider)
            scores.append(score)
            isps.append(rec[7])
            n += 1
            addrs += width
            proxy_dist[ptype] += 1
            usage_dist[usage] += 1
            score_dist[score] += 1
            if cc == "US":
                us_ranges += 1
                us_addrs += width
            if is_filled(threat):
                threat_filled += 1
            if is_filled(provider):
                provider_filled += 1
            if score == 80:
                score_80 += 1
                default_flagged_addrs += width
            if 91 <= score <= 99:
                score_high += 1
                high_flagged_addrs += width

    log(
        f"    PX12 ranges={n:,} addrs={addrs:,} US_addrs={us_addrs:,} "
        f"score80={score_80:,} high91_99={score_high:,}"
    )
    return {
        "starts": np.array(starts, dtype=np.uint32),
        "ends": np.array(ends, dtype=np.uint32),
        "proxy_types": np.array(proxy_types, dtype=object),
        "countries": np.array(countries, dtype=object),
        "usage_types": np.array(usage_types, dtype=object),
        "threats": np.array(threats, dtype=object),
        "providers": np.array(providers, dtype=object),
        "scores": np.array(scores, dtype=np.int16),
        "isps": np.array(isps, dtype=object),
        "n_ranges": n,
        "addrs": addrs,
        "us_ranges": us_ranges,
        "us_addrs": us_addrs,
        "score_dist": {str(k): v for k, v in sorted(score_dist.items())},
        "proxy_dist": dict(proxy_dist.most_common()),
        "usage_dist": dict(usage_dist.most_common()),
        "threat_filled_ranges": threat_filled,
        "provider_filled_ranges": provider_filled,
        "score_80_ranges": score_80,
        "score_high_ranges": score_high,
        "default_flagged_addrs": default_flagged_addrs,
        "high_flagged_addrs": high_flagged_addrs,
    }


def lookup_indices(ip_ints: np.ndarray, starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(starts, ip_ints, side="right") - 1
    valid = np.zeros(len(ip_ints), dtype=bool)
    ok = idx >= 0
    if ok.any():
        i = idx[ok]
        valid_ok = ip_ints[ok] <= ends[i]
        # also starts[i] <= ip (true by construction of searchsorted if ranges contiguous / sorted)
        valid_ok &= starts[i] <= ip_ints[ok]
        valid[np.where(ok)[0][valid_ok]] = True
    out = idx.astype(np.int64)
    out[~valid] = -1
    return out


def cross_match(tune: dict, db11: dict, px12: dict) -> dict:
    log("[4/5] Cross-matching unique Tune IPs against DB11 and PX12")
    items = list(tune["_ip_ints"].items())
    ips = [ip for ip, _ in items]
    ip_ints = np.array([n for _, n in items], dtype=np.uint32)
    n = len(ips)

    db_idx = lookup_indices(ip_ints, db11["starts"], db11["ends"])
    px_idx = lookup_indices(ip_ints, px12["starts"], px12["ends"])

    db_hit = db_idx >= 0
    px_hit = px_idx >= 0
    n_db = int(db_hit.sum())
    n_px = int(px_hit.sum())
    n_both = int((db_hit & px_hit).sum())
    n_db_only = int((db_hit & ~px_hit).sum())
    n_px_only = int((~db_hit & px_hit).sum())
    n_neither = int((~db_hit & ~px_hit).sum())

    # DB11 quality on matched Tune IPs
    db_cc = Counter()
    db_usable_geo = 0
    db_city_filled = 0
    db_zip_filled = 0
    db_dash = 0
    country_agree = 0
    country_disagree = 0
    country_compared = 0
    mismatch_pairs = Counter()

    ip_countries = tune["_ip_countries"]
    for i, hit in enumerate(db_hit):
        if not hit:
            continue
        j = int(db_idx[i])
        cc = db11["countries"][j]
        city = db11["cities"][j]
        zipc = db11["zips"][j]
        lat = db11["lats"][j]
        lon = db11["lons"][j]
        db_cc[cc] += 1
        if cc == "-":
            db_dash += 1
        if is_filled(city):
            db_city_filled += 1
        if is_filled(zipc):
            db_zip_filled += 1
        if (
            is_filled(cc)
            and is_filled(city)
            and is_filled(lat)
            and is_filled(lon)
            and lat not in ("0.000000", "0", "0.0")
            and lon not in ("0.000000", "0", "0.0")
        ):
            db_usable_geo += 1
        tune_ccs = ip_countries.get(ips[i], [])
        if tune_ccs and is_filled(cc):
            country_compared += 1
            if cc in tune_ccs:
                country_agree += 1
            else:
                country_disagree += 1
                mismatch_pairs[f"{tune_ccs[0]}->{cc}"] += 1

    # PX12 classification on matched Tune IPs
    px_proxy = Counter()
    px_usage = Counter()
    px_score = Counter()
    px_threat = Counter()
    px_cc = Counter()
    px_threat_filled = 0
    px_provider_filled = 0
    px_score_80 = 0
    px_score_high = 0
    px_score_low = 0
    px_dch = 0
    px_non_dch = 0
    px_pub = 0
    flagged_and_px = 0
    flagged_not_px = 0
    accepted_and_px = 0

    flagged = tune["_flagged_ips"]
    ip_counts = tune["_ip_counts"]

    # Fraud workflow buckets
    # A: Tune has both AC fields (all do) AND PX12 hit
    # B: Tune has both AC but no PX12
    # C: Tune missing AC, PX12 hit (fallback)
    # D: Tune missing AC, no PX12 (uncovered)
    missing_ac = set()
    for ip in ips:
        # reconstructed: if both filled on the IP
        pass

    # We stored ips_with_both_ac count but not the set. Recompute from... we didn't keep
    # empty flags. All IPs likely have AC. We'll classify from flagged set + px hit.

    px_match_examples = []
    high_risk_examples = []

    for i, hit in enumerate(px_hit):
        if not hit:
            if ips[i] in flagged:
                flagged_not_px += 1
            continue
        j = int(px_idx[i])
        ptype = px12["proxy_types"][j]
        usage = px12["usage_types"][j]
        score = int(px12["scores"][j])
        threat = px12["threats"][j]
        provider = px12["providers"][j]
        cc = px12["countries"][j]
        isp = px12["isps"][j]
        px_proxy[ptype] += 1
        px_usage[usage] += 1
        px_score[score] += 1
        px_cc[cc] += 1
        if is_filled(threat):
            px_threat_filled += 1
            px_threat[threat] += 1
        else:
            px_threat["<empty>"] += 1
        if is_filled(provider):
            px_provider_filled += 1
        if score == 80:
            px_score_80 += 1
        elif 91 <= score <= 99:
            px_score_high += 1
        elif 0 <= score <= 36:
            px_score_low += 1
        if usage == "DCH":
            px_dch += 1
        else:
            px_non_dch += 1
        if ptype == "PUB":
            px_pub += 1
        if ips[i] in flagged:
            flagged_and_px += 1
        else:
            accepted_and_px += 1

        rec = {
            "ip": ips[i],
            "clicks": ip_counts[ips[i]],
            "proxy_type": ptype,
            "usage_type": usage,
            "fraud_score": score,
            "threat": threat if is_filled(threat) else None,
            "provider": provider if is_filled(provider) else None,
            "px_country": cc,
            "isp": isp,
            "tune_flagged": ips[i] in flagged,
            "db11_country": db11["countries"][int(db_idx[i])] if db_hit[i] else None,
            "db11_city": db11["cities"][int(db_idx[i])] if db_hit[i] else None,
        }
        if len(px_match_examples) < 25:
            px_match_examples.append(rec)
        if (score >= 91 or is_filled(threat)) and len(high_risk_examples) < 25:
            high_risk_examples.append(rec)

    # US-only among Tune unique
    us_mask = np.array(
        ["US" in ip_countries.get(ip, []) for ip in ips], dtype=bool
    )
    n_us = int(us_mask.sum())
    n_us_db = int((us_mask & db_hit).sum())
    n_us_px = int((us_mask & px_hit).sum())

    # DB11 US-labeled among Tune unique (may differ from Tune country)
    db_us = 0
    for i, hit in enumerate(db_hit):
        if hit and db11["countries"][int(db_idx[i])] == "US":
            db_us += 1

    log(
        f"    Tune unique IPv4={n:,} DB11 hit={n_db:,} ({n_db/n*100:.4f}%) "
        f"PX12 hit={n_px:,} ({n_px/n*100:.4f}%) both={n_both:,}"
    )

    # Coverage vs US IPv4 mass (sample vs full-table estimates)
    US_IPV4 = db11["us_addrs"]  # ~1.495B
    FULL_TABLE_DISTINCT_IPS = 4_527_008  # prior Athena measurement
    FULL_TABLE_ROWS = 16_302_182
    SAMPLE_US_UNIQUE = us_unique = n_us

    return {
        "tune_unique_ipv4": n,
        "db11_hit_unique": n_db,
        "db11_hit_pct": round(n_db / n * 100, 6) if n else 0,
        "px12_hit_unique": n_px,
        "px12_hit_pct": round(n_px / n * 100, 6) if n else 0,
        "both_hit_unique": n_both,
        "db11_only_unique": n_db_only,
        "px12_only_unique": n_px_only,
        "neither_unique": n_neither,
        "db11_usable_geo_unique": db_usable_geo,
        "db11_usable_geo_pct": round(db_usable_geo / n * 100, 6) if n else 0,
        "db11_city_filled_unique": db_city_filled,
        "db11_city_fill_pct": round(db_city_filled / n * 100, 6) if n else 0,
        "db11_zip_filled_unique": db_zip_filled,
        "db11_zip_fill_pct": round(db_zip_filled / n * 100, 6) if n else 0,
        "db11_unknown_geo_unique": db_dash,
        "db11_country_dist": dict(db_cc.most_common(20)),
        "country_compared": country_compared,
        "country_agree": country_agree,
        "country_agree_pct": round(country_agree / country_compared * 100, 4) if country_compared else 0,
        "country_mismatch_top": dict(mismatch_pairs.most_common(10)),
        "px_proxy_dist": dict(px_proxy.most_common()),
        "px_usage_dist": dict(px_usage.most_common()),
        "px_score_dist": {str(k): v for k, v in sorted(px_score.items())},
        "px_threat_dist": dict(px_threat.most_common()),
        "px_country_dist": dict(px_cc.most_common(15)),
        "px_threat_filled": px_threat_filled,
        "px_threat_fill_pct_of_hits": round(px_threat_filled / n_px * 100, 4) if n_px else 0,
        "px_provider_filled": px_provider_filled,
        "px_provider_fill_pct_of_hits": round(px_provider_filled / n_px * 100, 4) if n_px else 0,
        "px_score_80": px_score_80,
        "px_score_80_pct_of_hits": round(px_score_80 / n_px * 100, 4) if n_px else 0,
        "px_score_high_91_99": px_score_high,
        "px_score_high_pct_of_hits": round(px_score_high / n_px * 100, 4) if n_px else 0,
        "px_score_low_27_36": px_score_low,
        "px_dch": px_dch,
        "px_non_dch": px_non_dch,
        "px_non_dch_pct_of_hits": round(px_non_dch / n_px * 100, 4) if n_px else 0,
        "px_pub": px_pub,
        "px_pub_pct_of_hits": round(px_pub / n_px * 100, 4) if n_px else 0,
        "flagged_and_px12": flagged_and_px,
        "flagged_not_px12": flagged_not_px,
        "accepted_and_px12": accepted_and_px,
        "tune_us_unique": n_us,
        "tune_us_db11_hit": n_us_db,
        "tune_us_px12_hit": n_us_px,
        "tune_us_px12_pct": round(n_us_px / n_us * 100, 4) if n_us else 0,
        "db11_labeled_us_unique": db_us,
        "px12_as_pct_of_tune_unique": round(n_px / n * 100, 6) if n else 0,
        "px_match_examples": px_match_examples,
        "high_risk_examples": high_risk_examples,
        "coverage_estimates": {
            "db11_us_ipv4_addresses": US_IPV4,
            "full_table_distinct_ips_prior": FULL_TABLE_DISTINCT_IPS,
            "full_table_rows_prior": FULL_TABLE_ROWS,
            "sample_unique_ips": n,
            "sample_us_unique": SAMPLE_US_UNIQUE,
            "sample_us_as_pct_of_db11_us_space": round(SAMPLE_US_UNIQUE / US_IPV4 * 100, 8) if US_IPV4 else 0,
            "full_table_as_pct_of_db11_us_space": round(FULL_TABLE_DISTINCT_IPS / US_IPV4 * 100, 6) if US_IPV4 else 0,
            "full_table_as_pct_of_all_ipv4": round(FULL_TABLE_DISTINCT_IPS / 4_294_967_296 * 100, 6),
            "prior_100k_db11_sample_in_clicks": {"present": 214, "sample": 100_000, "pct": 0.214},
            "prior_1m_db11_sample_in_clicks": {"present": 2327, "sample": 1_000_000, "pct": 0.2327},
            "prior_100k_us_db11_in_clicks": {"present": 210, "us_sampled": 30578, "pct": round(210 / 30578 * 100, 4)},
            "prior_1m_us_db11_in_clicks": {"present": 2264, "us_sampled": 305383, "pct": round(2264 / 305383 * 100, 4)},
        },
    }


def analyze_session() -> dict:
    log(f"[5/5] Inspecting session geo sample: {SESSION_PATH}")
    with open(SESSION_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        n = 0
        lat_filled = 0
        addr_filled = 0
        for row in reader:
            n += 1
            if is_filled(row.get("geo_latitude")):
                lat_filled += 1
            if is_filled(row.get("geo_address")):
                addr_filled += 1
            if n >= 100000:
                break
    has_ip = any(c and "ip" in c.lower() for c in fields)
    return {
        "rows": n,
        "columns": fields,
        "has_ip_column": has_ip,
        "geo_lat_fill_pct": round(lat_filled / n * 100, 4) if n else 0,
        "geo_address_fill_pct": round(addr_filled / n * 100, 4) if n else 0,
        "join_note": "No IP column — cannot cross-match to Tune / IP2Location / IP2Proxy on this sample.",
    }


def main() -> None:
    tune = analyze_tune()
    db11 = load_db11_ranges()
    px12 = load_px12_ranges()
    match = cross_match(tune, db11, px12)
    session = analyze_session()

    # Fraud workflow summary
    n_unique = match["tune_unique_ipv4"]
    tune_ac_complete = tune["ips_with_both_ac"]
    tune_ac_missing = tune["ips_missing_any_ac"]
    px_hits = match["px12_hit_unique"]
    # Fallback universe: IPs without Tune AC go to PX12. In this sample AC is expected ~100%.
    fraud_workflow = {
        "step1_tune_status_complete_unique_ips": tune_ac_complete,
        "step1_tune_status_complete_pct": tune["ips_with_both_ac_pct"],
        "step2_fallback_needed_unique_ips": tune_ac_missing,
        "step3_px12_positive_hits_unique": px_hits,
        "step3_px12_hit_pct_of_tune": match["px12_hit_pct"],
        "geo_map_db11_hit_pct": match["db11_hit_pct"],
        "interpretation": (
            "Fraud: use Tune access_control_* as primary when populated. "
            "If missing, look up IP2Proxy PX12 (positive hit only; miss ≠ clean). "
            "Geo: map every IPv4 directly to IP2Location DB11 ranges."
        ),
    }

    # Drop heavy private keys
    tune_out = {k: v for k, v in tune.items() if not k.startswith("_")}
    db11_out = {
        "n_ranges": db11["n_ranges"],
        "gaps": db11["gaps"],
        "us_ranges": db11["us_ranges"],
        "us_addrs": db11["us_addrs"],
        "us_pct_of_ipv4": round(db11["us_addrs"] / 4_294_967_296 * 100, 4),
        "dash_ranges": db11["dash_ranges"],
        "dash_addrs": db11["dash_addrs"],
        "city_filled_ranges": db11["city_filled_ranges"],
        "zip_filled_ranges": db11["zip_filled_ranges"],
        "min_from": db11["min_from"],
        "max_to": db11["max_to"],
        "full_ipv4_coverage": db11["min_from"] == 0 and db11["max_to"] == 4294967295 and db11["gaps"] == 0,
    }
    px12_out = {k: v for k, v in px12.items() if k not in (
        "starts", "ends", "proxy_types", "countries", "usage_types",
        "threats", "providers", "scores", "isps",
    )}
    px12_out["threat_fill_pct"] = round(px12["threat_filled_ranges"] / px12["n_ranges"] * 100, 4)
    px12_out["provider_fill_pct"] = round(px12["provider_filled_ranges"] / px12["n_ranges"] * 100, 4)
    px12_out["score_80_pct"] = round(px12["score_80_ranges"] / px12["n_ranges"] * 100, 4)
    px12_out["score_high_pct"] = round(px12["score_high_ranges"] / px12["n_ranges"] * 100, 4)
    px12_out["us_addrs_pct_of_px12"] = round(px12["us_addrs"] / px12["addrs"] * 100, 4) if px12["addrs"] else 0
    px12_out["px12_addrs_as_pct_of_ipv4"] = round(px12["addrs"] / 4_294_967_296 * 100, 6)
    px12_out["px12_us_as_pct_of_db11_us"] = round(px12["us_addrs"] / db11["us_addrs"] * 100, 6) if db11["us_addrs"] else 0
    px12_out["default_flagged_score80_addrs"] = px12["default_flagged_addrs"]
    px12_out["default_flagged_score80_pct_of_px12_addrs"] = round(
        px12["default_flagged_addrs"] / px12["addrs"] * 100, 4
    ) if px12["addrs"] else 0

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "tune": "raw_tune_clicks_100K_sample.csv (100K rows from raw.raw_tune_clicks)",
            "db11": "IP2LOCATION-LITE-DB11.CSV (full)",
            "px12": "IP2PROXY-LITE-PX12.CSV (full)",
            "session": "session_summary_geo_columns_100K_sample.csv",
            "full_table_prior_athena": {
                "rows": 16_302_182,
                "distinct_ips": 4_527_008,
            },
        },
        "tune": tune_out,
        "db11": db11_out,
        "px12": px12_out,
        "cross_match": match,
        "session_geo": session,
        "fraud_workflow": fraud_workflow,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    log(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
