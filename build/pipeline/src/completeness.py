"""Is every IP in our data lake usable in the two tables? Exported after every daily run.

serving/ipintel_curated/table_completeness.json:
  states     one entry per completeness state, for every address the pipeline has ever seen in a base table
  window     the same for addresses seen in the last 90 days, which is what reporting uses
  gaps       what is still missing and how long it should take

An address is COMPLETE when both are true:
  risk      at least one row in ip_intelligence from FraudLogix or proxycheck.io with is_proxy filled.
            IP2Proxy PX12 only lists known proxies, so a missing PX12 row is not an answer.
  location  at least one row in ip_geo with a state or a city.
Private and reserved addresses are excluded everywhere: no vendor can answer them.
"""
import common as c

KEY = "%s/serving/ipintel_curated/table_completeness.json" % c.PREFIX
DAILY_BUDGET = 78000

SQL = f"""
WITH base AS (SELECT ip_address, max(last_seen) AS last_seen FROM {c.DB}.ip_occurrences
              WHERE {c.public_ipv4_sql('ip_address')} GROUP BY ip_address),
risk AS (
  SELECT ip_address, count(*) AS rows_any,
         count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND is_proxy IS NOT NULL) AS acceptable,
         count_if(vendor = 'ip2proxy_px12' AND is_proxy IS NOT NULL) AS px12,
         count_if(vendor = 'proxycheck_io') AS pc_rows
  FROM {c.DB}.ip_intelligence GROUP BY ip_address),
geo AS (
  SELECT ip_address, count(*) AS rows_any,
         count_if(nullif(state, '') IS NOT NULL OR nullif(city, '') IS NOT NULL) AS filled
  FROM {c.DB}.ip_geo GROUP BY ip_address),
q AS (SELECT DISTINCT ip_address FROM {c.DB}.proxycheck_queue WHERE answered_at IS NULL),
j AS (
  SELECT b.ip_address, b.last_seen, (q.ip_address IS NOT NULL) AS queued,
         coalesce(r.rows_any, 0) AS risk_rows, coalesce(r.acceptable, 0) AS acceptable,
         coalesce(r.px12, 0) AS px12, coalesce(r.pc_rows, 0) AS pc_rows,
         coalesce(g.rows_any, 0) AS geo_rows, coalesce(g.filled, 0) AS geo_filled
  FROM base b
  LEFT JOIN risk r ON r.ip_address = b.ip_address
  LEFT JOIN geo g ON g.ip_address = b.ip_address
  LEFT JOIN q ON q.ip_address = b.ip_address),
st AS (
  SELECT *,
    CASE WHEN risk_rows = 0 AND geo_rows = 0 THEN 'no_row_in_either_table'
         WHEN risk_rows = 0 THEN 'no_risk_row'
         WHEN acceptable = 0 AND px12 > 0 THEN 'only_ip2proxy_answered'
         WHEN acceptable = 0 THEN 'no_acceptable_risk_answer'
         WHEN geo_filled = 0 THEN 'risk_only_no_location'
         ELSE 'complete' END AS state
  FROM j)
SELECT state, count(*) AS ips,
       count_if(last_seen >= date_add('day', -90, current_date)) AS seen_90d,
       count_if(last_seen >= date_add('day', -30, current_date)) AS seen_30d,
       count_if(queued) AS queued,
       count_if(pc_rows = 0) AS still_to_ask_proxycheck,
       CAST(max(last_seen) AS varchar) AS newest_last_seen
FROM st GROUP BY state ORDER BY state
"""


def build():
    rows = c.rows(SQL, timeout_s=600)
    by = {r["state"]: r for r in rows}
    total = sum(r["ips"] for r in rows)
    window = sum(r["seen_90d"] for r in rows)
    complete = by.get("complete", {})
    incomplete = [r for r in rows if r["state"] != "complete"]
    missing = sum(r["ips"] for r in incomplete)
    missing_90d = sum(r["seen_90d"] for r in incomplete)
    to_ask = sum(r["still_to_ask_proxycheck"] for r in incomplete)
    return {
        "as_of": c.now_iso(),
        "rule": {"risk": "a FraudLogix or proxycheck.io row with is_proxy filled; IP2Proxy PX12 does not count",
                 "location": "a row in ip_geo with a state or a city",
                 "excluded": "private and reserved addresses, which no vendor can answer"},
        "addresses": total,
        "complete": complete.get("ips", 0),
        "complete_pct": round(100.0 * complete.get("ips", 0) / total, 2) if total else None,
        "incomplete": missing,
        "window_90d": {"addresses": window, "complete": complete.get("seen_90d", 0), "incomplete": missing_90d},
        "states": rows,
        "gaps": {"still_to_ask_proxycheck": to_ask,
                 "days_left_at_daily_budget": round(to_ask / float(DAILY_BUDGET), 1) if to_ask else 0,
                 "daily_budget": DAILY_BUDGET},
    }


def export():
    """Writes the report and returns two checks: the 90-day window must be complete; the rest is progress."""
    try:
        doc = build()
        c.s3_put_json(KEY, doc)
        w = doc["window_90d"]
        open_gap = w["incomplete"] - sum(r["queued"] for r in doc["states"] if r["state"] != "complete")
        return [
            {"name": "Every address seen in the last 90 days is complete in both tables",
             "passed": open_gap <= 0,
             "detail": "%d of %d addresses incomplete" % (w["incomplete"], w["addresses"]) if w["incomplete"]
                       else "%d addresses, all complete" % w["addresses"]},
            {"name": "Table completeness exported", "passed": True,
             "detail": "%s%% of %d addresses complete; %d still to ask proxycheck.io (about %s days)" % (
                 doc["complete_pct"], doc["addresses"], doc["gaps"]["still_to_ask_proxycheck"],
                 doc["gaps"]["days_left_at_daily_budget"])},
        ]
    except Exception as e:
        return [{"name": "Table completeness exported", "passed": False,
                 "detail": ("%s: %s" % (type(e).__name__, e))[:300]}]
