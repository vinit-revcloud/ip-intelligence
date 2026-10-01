"""One resolved answer per address: ipintel_curated.ip_resolved.

The same rules as resolve_geo and resolve_proxy in the API's lookup.py, so a query in Athena and a lookup
in the app give the same answer. Vendor rows are never changed; this only reads them.

Location: vendors that answered (state, city or coordinates) vote, except geojs_io, which repeats
MaxMind. The group agreeing on normalised state and city with the most vendors wins, then the group
holding the best location scorecard score, then the group whose first vendor id sorts first. The
best-scoring vendor in that group, ties by vendor id, supplies the fields.

Proxy: proxycheck.io decides once it has answered. Without it, clean when every answering vendor says
clean, confirmed when a published range confirms a flag, otherwise no conclusion.
"""
from common import DB, lit, run, scalar

RESOLVED_COLS = ["ip_address", "geo_status", "state", "city", "zip_code", "latitude", "longitude", "timezone",
                 "geo_decided_by", "geo_agreeing_vendors", "geo_vendors_answered",
                 "proxy_status", "flagged", "is_proxy", "is_vpn", "is_tor", "is_datacenter", "is_bot",
                 "is_compromised", "is_scraper", "is_anonymous", "proxy_decided_by", "proxy_agreeing_vendors",
                 "proxy_vendors_answered", "isp", "asn", "proxycheck_risk_score",
                 "seen_in_base_tables", "first_seen", "last_seen"]
FLAG_COLS = ["is_proxy", "is_vpn", "is_tor", "is_datacenter", "is_bot", "is_compromised", "is_scraper"]

_FLAG_TEMPLATE = ("CASE WHEN pc.ip_address IS NOT NULL THEN pc.{f} "
                  "WHEN o.n IS NOT NULL AND o.nf = 0 THEN false "
                  "WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN l.{f} END AS {f}")

_SELECT = """
WITH scores AS (SELECT vendor, coalesce(max(score), 0) AS score FROM {db}.vendor_overview_geo GROUP BY vendor),
ga AS (
  SELECT g.ip_address, g.vendor, g.state, g.city, g.zip_code, g.latitude, g.longitude, g.timezone,
         coalesce(s.score, 0) AS score, g.vendor <> 'geojs_io' AS votes,
         nullif(lower(trim(g.state)), '') AS nstate,
         regexp_extract(regexp_replace(lower(coalesce(g.city, '')), '[^a-z ]', ''), '[a-z]+') AS ncity
  FROM {db}.ip_geo g LEFT JOIN scores s ON s.vendor = g.vendor
  WHERE nullif(trim(g.state), '') IS NOT NULL OR nullif(trim(g.city), '') IS NOT NULL OR g.latitude IS NOT NULL),
voters AS (SELECT ip_address, count_if(votes) AS nvoters, count(*) AS nanswered FROM ga GROUP BY ip_address),
pool AS (SELECT ga.* FROM ga JOIN voters v ON v.ip_address = ga.ip_address WHERE ga.votes OR v.nvoters = 0),
grp AS (
  SELECT ip_address, nstate, ncity, count(*) AS n, max(score) AS best, min(vendor) AS first_vendor,
         array_sort(array_agg(vendor)) AS vendors
  FROM pool GROUP BY ip_address, nstate, ncity),
bestgrp AS (
  SELECT * FROM (SELECT grp.*, row_number() OVER (PARTITION BY ip_address ORDER BY n DESC, best DESC, first_vendor) AS rn
                 FROM grp) WHERE rn = 1),
pick AS (
  SELECT * FROM (
    SELECT p.*, b.n, b.vendors,
           row_number() OVER (PARTITION BY p.ip_address ORDER BY p.score DESC, p.vendor) AS rn
    FROM pool p JOIN bestgrp b ON b.ip_address = p.ip_address
     AND p.nstate IS NOT DISTINCT FROM b.nstate AND p.ncity IS NOT DISTINCT FROM b.ncity) WHERE rn = 1),
geo_res AS (
  SELECT k.ip_address, k.state, k.city, k.zip_code, k.latitude, k.longitude, k.timezone,
         k.vendor AS geo_decided_by, array_join(k.vendors, ',') AS geo_agreeing_vendors,
         v.nanswered AS geo_vendors_answered,
         CASE WHEN k.n >= 2 THEN 'agreed' WHEN v.nvoters <= 1 THEN 'single_source' ELSE 'vendors_disagree' END AS geo_status
  FROM pick k JOIN voters v ON v.ip_address = k.ip_address),
ia AS (SELECT i.*, ({flag_any}) AS flagged FROM {db}.ip_intelligence i WHERE i.is_proxy IS NOT NULL),
pc AS (SELECT * FROM ia WHERE vendor = 'proxycheck_io'),
o AS (
  SELECT ip_address, count(*) AS n, count_if(flagged) AS nf,
         array_join(array_sort(array_agg(vendor)), ',') AS all_v,
         array_join(array_sort(filter(array_agg(CASE WHEN flagged THEN vendor END), x -> x IS NOT NULL)), ',') AS flagged_v,
         array_join(array_sort(filter(array_agg(CASE WHEN NOT flagged THEN vendor END), x -> x IS NOT NULL)), ',') AS clean_v
  FROM ia WHERE vendor <> 'proxycheck_io' GROUP BY ip_address),
l AS (SELECT * FROM ia WHERE vendor = 'authoritative_lists' AND flagged),
isp AS (
  SELECT ip_address,
         min_by(isp, CASE WHEN vendor = 'proxycheck_io' THEN '' ELSE vendor END) AS isp,
         min_by(asn, CASE WHEN vendor = 'proxycheck_io' THEN '' ELSE vendor END) AS asn
  FROM ia WHERE nullif(isp, '') IS NOT NULL GROUP BY ip_address),
risk AS (SELECT ip_address, max(risk_score) AS risk_score FROM {db}.ip_intelligence_analytics
         WHERE vendor = 'proxycheck_io' GROUP BY ip_address),
occ AS (
  SELECT ip_address, min(first_seen) AS first_seen, max(last_seen) AS last_seen,
         array_join(array_sort(array_agg(DISTINCT source_table)), ',') AS seen_in
  FROM {db}.ip_occurrences GROUP BY ip_address),
ips AS (SELECT ip_address FROM {db}.ip_geo UNION SELECT ip_address FROM {db}.ip_intelligence)
SELECT ips.ip_address,
  coalesce(gr.geo_status, 'no_answer') AS geo_status,
  gr.state, gr.city, gr.zip_code, gr.latitude, gr.longitude, gr.timezone,
  gr.geo_decided_by, coalesce(gr.geo_agreeing_vendors, '') AS geo_agreeing_vendors,
  coalesce(gr.geo_vendors_answered, 0) AS geo_vendors_answered,
  CASE WHEN pc.ip_address IS NOT NULL THEN
         CASE WHEN o.n IS NULL THEN 'proxycheck_only'
              WHEN (pc.flagged AND o.nf > 0) OR (NOT pc.flagged AND o.nf < o.n) THEN 'confirmed'
              ELSE 'proxycheck_overrides' END
       WHEN o.n IS NULL THEN 'no_answer'
       WHEN o.nf = 0 THEN 'clean_by_vendors'
       WHEN o.nf < o.n THEN 'vendors_disagree'
       WHEN l.ip_address IS NOT NULL THEN 'confirmed_by_published_range'
       ELSE 'flagged_unconfirmed' END AS proxy_status,
  CASE WHEN pc.ip_address IS NOT NULL THEN pc.flagged WHEN o.n IS NOT NULL AND o.nf = 0 THEN false
       WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN true END AS flagged,
  {flags},
  CASE WHEN pc.ip_address IS NOT NULL THEN 'proxycheck_io' WHEN o.n IS NOT NULL AND o.nf = 0 THEN 'all answering vendors'
       WHEN o.n IS NOT NULL AND o.nf = o.n AND l.ip_address IS NOT NULL THEN 'authoritative_lists' END AS proxy_decided_by,
  coalesce(CASE WHEN pc.ip_address IS NOT NULL THEN (CASE WHEN pc.flagged THEN o.flagged_v ELSE o.clean_v END)
                WHEN o.n IS NOT NULL AND o.nf = 0 THEN o.all_v
                WHEN o.n IS NOT NULL AND o.nf = o.n THEN o.flagged_v END, '') AS proxy_agreeing_vendors,
  coalesce(o.n, 0) + CASE WHEN pc.ip_address IS NOT NULL THEN 1 ELSE 0 END AS proxy_vendors_answered,
  isp.isp, isp.asn, risk.risk_score AS proxycheck_risk_score,
  coalesce(occ.seen_in, '') AS seen_in_base_tables, occ.first_seen, occ.last_seen
FROM ips
LEFT JOIN geo_res gr ON gr.ip_address = ips.ip_address
LEFT JOIN pc ON pc.ip_address = ips.ip_address
LEFT JOIN o ON o.ip_address = ips.ip_address
LEFT JOIN l ON l.ip_address = ips.ip_address
LEFT JOIN isp ON isp.ip_address = ips.ip_address
LEFT JOIN risk ON risk.ip_address = ips.ip_address
LEFT JOIN occ ON occ.ip_address = ips.ip_address"""


def resolved_select():
    flag_any = " OR ".join("coalesce(i.%s, false)" % f for f in FLAG_COLS)
    flags = ",\n  ".join(_FLAG_TEMPLATE.format(f=f) for f in FLAG_COLS + ["is_anonymous"])
    return _SELECT.format(db=DB, flag_any=flag_any, flags=flags)


def _differs(cols):
    return " OR ".join("t.%s IS DISTINCT FROM s.%s" % (c, c) for c in cols)


def refresh(staging, updated_at):
    """Recompute every address and merge only what changed. Full, not incremental: a scorecard change can
    change which vendor wins for addresses nobody touched today. Returns (changed_rows, total_rows)."""
    stg = staging.ctas("resolved", resolved_select())
    cols = RESOLVED_COLS[1:]
    changed = scalar(f"""SELECT count(*) FROM {stg} s LEFT JOIN {DB}.ip_resolved t ON t.ip_address = s.ip_address
                         WHERE t.ip_address IS NULL OR {_differs(cols)}""")
    if changed:
        run(f"""
MERGE INTO {DB}.ip_resolved t USING {stg} s ON t.ip_address = s.ip_address
WHEN MATCHED AND ({_differs(cols)}) THEN UPDATE SET {", ".join("%s = s.%s" % (c, c) for c in cols)}, updated_at = {lit(updated_at)}
WHEN NOT MATCHED THEN INSERT ({", ".join(RESOLVED_COLS)}, updated_at)
  VALUES ({", ".join("s." + c for c in RESOLVED_COLS)}, {lit(updated_at)})""", timeout_s=800)
    return changed, scalar(f"SELECT count(*) FROM {DB}.ip_resolved")


def checks():
    """Every address in ip_geo or ip_intelligence has exactly one resolved row."""
    r = scalar(f"""SELECT count(*) FROM (SELECT ip_address FROM {DB}.ip_geo UNION SELECT ip_address FROM {DB}.ip_intelligence) a
                   LEFT JOIN {DB}.ip_resolved r ON r.ip_address = a.ip_address WHERE r.ip_address IS NULL""")
    d = scalar(f"SELECT count(*) FROM (SELECT ip_address FROM {DB}.ip_resolved GROUP BY 1 HAVING count(*) > 1)")
    return [{"name": "Every address has exactly one resolved answer", "passed": not r and not d,
             "detail": None if not r and not d else "%s addresses without a resolved row, %s with more than one" % (r, d)}]
