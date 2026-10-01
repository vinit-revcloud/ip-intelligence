"""Enrichment coverage for the last 30 days, exported for the app after every daily run.

serving/ipintel_curated/enrichment_coverage.json, read by the API's GET /coverage:
  inserted_by_day  rows added to ip_geo and ip_intelligence per day (created_at) and new addresses per day
                   (first day an address was seen in any base table)
  window           every address seen in the base tables in the last 30 days, by the day it was last seen:
                   how many have a proxycheck.io answer, a proxy conclusion, and an agreed location
  totals           the same for the whole window and for every address in the tables
"""
import datetime

import common as c

KEY = "%s/serving/ipintel_curated/enrichment_coverage.json" % c.PREFIX
WINDOW_DAYS = 30
NO_CONCLUSION = "('no_answer', 'vendors_disagree', 'flagged_unconfirmed')"


def build():
    today = datetime.datetime.utcnow().date()
    start = today - datetime.timedelta(days=WINDOW_DAYS)
    s = c.lit(start.isoformat())
    inserted = c.rows(f"""
SELECT d, sum(geo) AS geo_rows, sum(intel) AS intel_rows, sum(new_ips) AS new_addresses FROM (
  SELECT substr(created_at, 1, 10) AS d, count(*) AS geo, 0 AS intel, 0 AS new_ips FROM {c.DB}.ip_geo
   WHERE created_at >= {s} GROUP BY 1
  UNION ALL SELECT substr(created_at, 1, 10), 0, count(*), 0 FROM {c.DB}.ip_intelligence WHERE created_at >= {s} GROUP BY 1
  UNION ALL SELECT d, 0, 0, count(*) FROM (SELECT ip_address, cast(min(first_seen) AS varchar) AS d
    FROM {c.DB}.ip_occurrences GROUP BY ip_address) WHERE d >= {s} GROUP BY 1)
GROUP BY d ORDER BY d""", timeout_s=300)
    per_day = f"""
WITH occ AS (SELECT ip_address, max(last_seen) AS last_seen FROM {c.DB}.ip_occurrences GROUP BY ip_address)
SELECT {{key}} AS d, count(*) AS addresses,
  count_if(r.proxy_decided_by LIKE '%proxycheck%') AS proxycheck_answered,
  count_if(r.proxy_status NOT IN {NO_CONCLUSION}) AS proxy_concluded,
  count_if(r.proxy_status IN {NO_CONCLUSION}) AS proxy_no_conclusion,
  count_if(r.geo_status = 'agreed') AS geo_agreed,
  count_if(r.geo_status = 'single_source') AS geo_single_source,
  count_if(r.geo_status = 'nearby') AS geo_nearby,
  count_if(r.geo_status = 'same_state') AS geo_same_state,
  count_if(r.geo_status NOT IN ('agreed', 'single_source', 'nearby', 'same_state')) AS geo_disagree_or_missing
FROM {c.DB}.ip_resolved r LEFT JOIN occ o ON o.ip_address = r.ip_address
{{where}} GROUP BY 1 ORDER BY 1"""
    window = c.rows(per_day.format(key="cast(o.last_seen AS varchar)", where="WHERE o.last_seen >= date " + s), timeout_s=300)
    whole = c.rows(per_day.format(key="CASE WHEN o.last_seen >= date %s THEN 'last_30_days' ELSE 'all_addresses' END" % s,
                                  where=""), timeout_s=300)
    fields = ["addresses", "proxycheck_answered", "proxy_concluded", "proxy_no_conclusion", "geo_agreed",
              "geo_single_source", "geo_nearby", "geo_same_state", "geo_disagree_or_missing"]
    totals = {"last_30_days": {f: 0 for f in fields}, "all_addresses": {f: 0 for f in fields}}
    for r in whole:                       # "all_addresses" row holds the older ones: add both into the total
        for f in fields:
            totals["all_addresses"][f] += r[f] or 0
            if r["d"] == "last_30_days":
                totals["last_30_days"][f] += r[f] or 0
    for t in totals.values():
        n = t["addresses"] or 0
        t.update(proxycheck_pct=round(100.0 * t["proxycheck_answered"] / n, 1) if n else None,
                 proxy_concluded_pct=round(100.0 * t["proxy_concluded"] / n, 1) if n else None,
                 geo_agreed_pct=round(100.0 * t["geo_agreed"] / n, 1) if n else None,
                 geo_state_agreed_pct=round(100.0 * (t["geo_agreed"] + t["geo_nearby"] + t["geo_same_state"]) / n, 1) if n else None)
    return {"as_of": c.now_iso(), "window_days": WINDOW_DAYS, "window_start": start.isoformat(),
            "totals": totals, "inserted_by_day": inserted, "window_by_last_seen_day": window,
            "definitions": {
                "proxycheck_answered": "proxycheck.io answered this address",
                "proxy_concluded": "the proxy answer is decided (confirmed by proxycheck.io, or every vendor says clean)",
                "proxy_no_conclusion": "no vendor answered, vendors disagree, or a flag nobody confirmed",
                "geo_agreed": "at least two location vendors agree on state and city",
                "geo_single_source": "only one location vendor answered",
                "geo_nearby": "two or more location vendors name the same state and two of them are within 25 km",
                "geo_same_state": "two or more location vendors name the same state, cities more than 25 km apart",
                "geo_disagree_or_missing": "no two location vendors name the same state, or no location at all"}}


def export():
    try:
        doc = build()
        c.s3_put_json(KEY, doc)
        t = doc["totals"]["last_30_days"]
        return {"name": "Enrichment coverage exported", "passed": True,
                "detail": "last 30 days: %d addresses, %s%% answered by proxycheck.io" % (t["addresses"], t["proxycheck_pct"])}
    except Exception as e:
        return {"name": "Enrichment coverage exported", "passed": False, "detail": ("%s: %s" % (type(e).__name__, e))[:300]}
