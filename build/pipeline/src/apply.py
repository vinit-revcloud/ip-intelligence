"""Writing vendor answers into the six ipintel_curated tables, and proving it was done right.

Rules, from the plan:
  * one row per address per vendor
  * a new pair is inserted; an existing pair is updated only when its answer changed, and keeps
    its created_at
  * the working-out is recalculated only for addresses whose answers changed
  * a scorecard is scored only over addresses every vendor on it was asked about
"""
from common import BUCKET, DB, PREFIX, lit, rows, run, s3_put_json, scalar

MIN_SCORECARD_POOL = 1000

GEO_FIELDS = ["state", "city", "zip_code", "latitude", "longitude", "timezone"]
INTEL_FIELDS = ["is_proxy", "is_vpn", "is_tor", "is_datacenter", "is_bot", "is_compromised",
                "is_scraper", "is_anonymous", "isp", "asn"]
FOUR_TABLES = ["ip_geo", "ip_intelligence", "ip_geo_analytics", "ip_intelligence_analytics"]


def latest_snapshot(table):
    return scalar('SELECT CAST(snapshot_id AS varchar) FROM "%s"."%s$snapshots" '
                  'ORDER BY committed_at DESC LIMIT 1' % (DB, table))


def table_counts():
    return {t: scalar("SELECT count(*) FROM %s.%s" % (DB, t)) for t in FOUR_TABLES}


def _differs(fields):
    return " OR ".join("t.%s IS DISTINCT FROM s.%s" % (f, f) for f in fields)


# Columns FraudLogix never supplies. On a FraudLogix row they hold proxycheck.io's values (owner's rule: a partial
# answer is combined with proxycheck.io's). Re-reading FraudLogix's latest decision must not empty them again.
FRAUDLOGIX_NEVER_SUPPLIES = ["is_compromised", "is_scraper", "is_anonymous", "isp", "asn"]


def intel_source(stg):
    """The staged ip_intelligence rows as they should be merged: FraudLogix rows keep the existing values of the
    columns FraudLogix never supplies; every other vendor's answer is taken exactly as staged."""
    cols = ", ".join(
        ("CASE WHEN s.vendor = 'fraudlogix_tune' THEN coalesce(s.{f}, e.{f}) ELSE s.{f} END AS {f}"
         if f in FRAUDLOGIX_NEVER_SUPPLIES else "s.{f}").format(f=f) for f in INTEL_FIELDS)
    return (f"(SELECT s.ip_address, s.vendor, {cols}, s.seen_at FROM {stg} s "
            f"LEFT JOIN {DB}.ip_intelligence e ON e.ip_address = s.ip_address AND e.vendor = s.vendor)")


def plan_changes(stg, target, fields):
    """Count what the upsert is about to do, before it does it."""
    if target == "ip_intelligence":
        stg = intel_source(stg)
    r = rows(f"""
SELECT
  count_if(t.ip_address IS NULL AND e.ip_address IS NULL) AS inserted,
  count_if(t.ip_address IS NULL AND e.ip_address IS NOT NULL) AS added,
  count_if(t.ip_address IS NOT NULL AND ({_differs(fields)})) AS updated,
  count_if(t.ip_address IS NOT NULL AND NOT ({_differs(fields)})) AS unchanged
FROM {stg} s
LEFT JOIN {DB}.{target} t ON t.ip_address = s.ip_address AND t.vendor = s.vendor
LEFT JOIN (SELECT DISTINCT ip_address FROM {DB}.{target}
           WHERE ip_address IN (SELECT ip_address FROM {stg})) e ON e.ip_address = s.ip_address""")[0]
    return r


def merge_geo(stg):
    cols = ", ".join(GEO_FIELDS)
    run(f"""
MERGE INTO {DB}.ip_geo t
USING {stg} s
ON t.ip_address = s.ip_address AND t.vendor = s.vendor
WHEN MATCHED AND ({_differs(GEO_FIELDS)}) THEN UPDATE SET
  {", ".join("%s = s.%s" % (f, f) for f in GEO_FIELDS)}, updated_at = s.seen_at
WHEN NOT MATCHED THEN INSERT (ip_address, vendor, {cols}, created_at, updated_at)
  VALUES (s.ip_address, s.vendor, {", ".join("s." + f for f in GEO_FIELDS)}, s.seen_at, s.seen_at)""")


def merge_intel(stg):
    cols = ", ".join(INTEL_FIELDS)
    run(f"""
MERGE INTO {DB}.ip_intelligence t
USING {intel_source(stg)} s
ON t.ip_address = s.ip_address AND t.vendor = s.vendor
WHEN MATCHED AND ({_differs(INTEL_FIELDS)}) THEN UPDATE SET
  {", ".join("%s = s.%s" % (f, f) for f in INTEL_FIELDS)}, updated_at = s.seen_at
WHEN NOT MATCHED THEN INSERT (ip_address, vendor, {cols}, created_at, updated_at)
  VALUES (s.ip_address, s.vendor, {", ".join("s." + f for f in INTEL_FIELDS)}, s.seen_at, s.seen_at)""")


def refresh_intel_analytics(stg):
    run(f"""
MERGE INTO {DB}.ip_intelligence_analytics t
USING (
  WITH lists AS (
    SELECT i.ip_address,
           (coalesce(i.is_proxy, false) OR coalesce(i.is_datacenter, false)) AS known_infrastructure,
           a.fraud_reason AS infrastructure_list
    FROM {DB}.ip_intelligence i
    LEFT JOIN {DB}.ip_intelligence_analytics a ON a.ip_address = i.ip_address AND a.vendor = i.vendor
    WHERE i.vendor = 'authoritative_lists' AND i.ip_address IN (SELECT ip_address FROM {stg})
  ),
  x AS (
    SELECT s.ip_address, s.vendor, s.has_answer,
      (coalesce(s.is_proxy, false) OR coalesce(s.is_vpn, false) OR coalesce(s.is_tor, false)
       OR coalesce(s.is_datacenter, false) OR coalesce(s.is_bot, false)
       OR coalesce(s.is_compromised, false) OR coalesce(s.is_scraper, false)) AS flagged,
      s.fraud_reason, s.is_masked_device, s.risk_score,
      coalesce(CASE WHEN s.vendor = 'authoritative_lists'
                    THEN coalesce(s.is_proxy, false) OR coalesce(s.is_datacenter, false) END,
               l.known_infrastructure, false) AS known_infrastructure,
      coalesce(CASE WHEN s.vendor = 'authoritative_lists' THEN s.fraud_reason END, l.infrastructure_list) AS infrastructure_list
    FROM {stg} s LEFT JOIN lists l ON l.ip_address = s.ip_address
  )
  SELECT x.*,
    CASE WHEN NOT has_answer THEN 'no_answer'
         WHEN flagged AND known_infrastructure THEN 'confirmed_by_published_range'
         WHEN flagged THEN 'unconfirmed_flag'
         WHEN known_infrastructure THEN 'missed_known_infrastructure'
         ELSE 'agreed_not_flagged' END AS verdict_class
  FROM x
) s
ON t.ip_address = s.ip_address AND t.vendor = s.vendor
WHEN MATCHED THEN UPDATE SET has_answer = s.has_answer, flagged = s.flagged, fraud_reason = s.fraud_reason,
  is_masked_device = s.is_masked_device, risk_score = s.risk_score,
  known_infrastructure = s.known_infrastructure, infrastructure_list = s.infrastructure_list,
  verdict_class = s.verdict_class
WHEN NOT MATCHED THEN INSERT (ip_address, vendor, has_answer, flagged, fraud_reason, is_masked_device,
  risk_score, known_infrastructure, infrastructure_list, verdict_class)
  VALUES (s.ip_address, s.vendor, s.has_answer, s.flagged, s.fraud_reason, s.is_masked_device,
  s.risk_score, s.known_infrastructure, s.infrastructure_list, s.verdict_class)""")


def refresh_geo_analytics(stg):
    """Consensus for every address whose location answers changed. Same normalisation as the
    benchmark: state lower-cased, city reduced to its first word of letters, zip as given, and
    geojs.io never votes because it repeats MaxMind. Rows are written only where at least two
    voting vendors answered, since one answer cannot be compared with anything."""
    city_key = "split(regexp_replace(lower({c}), '[^a-z ]', ''), ' ')[1]"
    judged = " + ".join("(CASE WHEN %s_matches_consensus IS NOT NULL THEN 1 ELSE 0 END)" % f for f in ("state", "city", "zip"))
    matched = " + ".join("(CASE WHEN %s_matches_consensus THEN 1 ELSE 0 END)" % f for f in ("state", "city", "zip"))
    tjudged = " + ".join("(CASE WHEN %s_matches_truth IS NOT NULL THEN 1 ELSE 0 END)" % f for f in ("state", "city", "zip"))
    tmatched = " + ".join("(CASE WHEN %s_matches_truth THEN 1 ELSE 0 END)" % f for f in ("state", "city", "zip"))
    cols = ["ip_address", "vendor", "has_answer", "consensus_state", "consensus_city", "consensus_zip",
            "state_votes", "city_votes", "zip_votes", "state_matches_consensus", "city_matches_consensus",
            "zip_matches_consensus", "truth_state", "truth_city", "truth_zip", "state_matches_truth",
            "city_matches_truth", "zip_matches_truth", "row_agreement_pct", "row_truth_agreement_pct"]
    run(f"""
MERGE INTO {DB}.ip_geo_analytics t
USING (
  WITH aff AS (SELECT DISTINCT ip_address FROM {stg}),
  norm AS (
    SELECT g.ip_address, g.vendor, g.state, g.city, g.zip_code,
           lower(g.state) AS st_k, {city_key.format(c="g.city")} AS ct_k, g.zip_code AS zp_k
    FROM {DB}.ip_geo g JOIN aff a ON a.ip_address = g.ip_address
  ),
  voters AS (SELECT * FROM norm WHERE vendor <> 'geojs_io'),
  enough AS (
    SELECT ip_address FROM voters WHERE st_k IS NOT NULL OR ct_k IS NOT NULL OR zp_k IS NOT NULL
    GROUP BY ip_address HAVING count(DISTINCT vendor) >= 2
  ),
  cs AS (SELECT ip_address, max_by(st_k, c) AS v, max(c) AS votes FROM
         (SELECT ip_address, st_k, count(*) AS c FROM voters WHERE st_k IS NOT NULL GROUP BY 1, 2) GROUP BY 1),
  cc AS (SELECT ip_address, max_by(ct_k, c) AS v, max(c) AS votes FROM
         (SELECT ip_address, ct_k, count(*) AS c FROM voters WHERE ct_k IS NOT NULL GROUP BY 1, 2) GROUP BY 1),
  cz AS (SELECT ip_address, max_by(zp_k, c) AS v, max(c) AS votes FROM
         (SELECT ip_address, zp_k, count(*) AS c FROM voters WHERE zp_k IS NOT NULL GROUP BY 1, 2) GROUP BY 1),
  lead AS (SELECT ip_address, max(lead_state) AS lead_state, max(lead_city) AS lead_city, max(lead_zip) AS lead_zip
           FROM {DB}.qualified_lead_ips WHERE has_full_address GROUP BY ip_address),
  j AS (
    SELECT n.ip_address, n.vendor,
      (n.state IS NOT NULL OR n.city IS NOT NULL OR n.zip_code IS NOT NULL) AS has_answer,
      cs.v AS consensus_state, cc.v AS consensus_city, cz.v AS consensus_zip,
      cs.votes AS state_votes, cc.votes AS city_votes, cz.votes AS zip_votes,
      CASE WHEN n.st_k IS NOT NULL AND cs.votes >= 2 THEN n.st_k = cs.v END AS state_matches_consensus,
      CASE WHEN n.ct_k IS NOT NULL AND cc.votes >= 2 THEN n.ct_k = cc.v END AS city_matches_consensus,
      CASE WHEN n.zp_k IS NOT NULL AND cz.votes >= 2 THEN n.zp_k = cz.v END AS zip_matches_consensus,
      l.lead_state AS truth_state, l.lead_city AS truth_city, l.lead_zip AS truth_zip,
      CASE WHEN n.st_k IS NOT NULL AND l.lead_state IS NOT NULL THEN n.st_k = lower(l.lead_state) END AS state_matches_truth,
      CASE WHEN n.ct_k IS NOT NULL AND l.lead_city IS NOT NULL THEN n.ct_k = {city_key.format(c="l.lead_city")} END AS city_matches_truth,
      CASE WHEN n.zp_k IS NOT NULL AND l.lead_zip IS NOT NULL THEN n.zp_k = l.lead_zip END AS zip_matches_truth
    FROM norm n JOIN enough e ON e.ip_address = n.ip_address
    LEFT JOIN cs ON cs.ip_address = n.ip_address
    LEFT JOIN cc ON cc.ip_address = n.ip_address
    LEFT JOIN cz ON cz.ip_address = n.ip_address
    LEFT JOIN lead l ON l.ip_address = n.ip_address
  )
  SELECT j.*,
    round(100.0 * ({matched}) / nullif({judged}, 0), 1) AS row_agreement_pct,
    round(100.0 * ({tmatched}) / nullif({tjudged}, 0), 1) AS row_truth_agreement_pct
  FROM j
) s
ON t.ip_address = s.ip_address AND t.vendor = s.vendor
WHEN MATCHED THEN UPDATE SET {", ".join("%s = s.%s" % (c, c) for c in cols[2:])}
WHEN NOT MATCHED THEN INSERT ({", ".join(cols)}) VALUES ({", ".join("s." + c for c in cols)})""")


# ---------------------------------------------------------------- scorecards

def _in_list(vendors):
    return ", ".join(lit(v) for v in vendors)


def refresh_geo_scorecard(staging, vendors):
    """vendors: the enabled location vendors. Returns (pool_size, recalculated)."""
    pool_sql = f"""SELECT ip_address FROM {DB}.ip_geo_analytics WHERE vendor IN ({_in_list(vendors)})
                   GROUP BY ip_address HAVING count(DISTINCT vendor) = {len(vendors)}"""
    pool = scalar("SELECT count(*) FROM (%s)" % pool_sql)
    if pool < MIN_SCORECARD_POOL:
        return pool, False
    ans = " + ".join("(CASE WHEN g.%s IS NOT NULL THEN 1 ELSE 0 END)" % f for f in ("state", "city", "zip_code"))
    jud = " + ".join("(CASE WHEN a.%s_matches_consensus IS NOT NULL THEN 1 ELSE 0 END)" % f for f in ("state", "city", "zip"))
    mat = " + ".join("(CASE WHEN a.%s_matches_consensus THEN 1 ELSE 0 END)" % f for f in ("state", "city", "zip"))
    stg = staging.ctas("scorecard_geo", f"""
WITH pool AS ({pool_sql}),
f AS (
  SELECT a.vendor, ({ans}) AS fields_answered, ({jud}) AS fields_judged, ({mat}) AS fields_matched,
         a.state_matches_truth, a.city_matches_truth, a.zip_matches_truth
  FROM {DB}.ip_geo_analytics a
  JOIN pool p ON p.ip_address = a.ip_address
  JOIN {DB}.ip_geo g ON g.ip_address = a.ip_address AND g.vendor = a.vendor
  WHERE a.vendor IN ({_in_list(vendors)})
)
SELECT vendor, count(*) AS ips_tested,
  round(100.0 * sum(fields_answered) / (3.0 * count(*)), 1) AS fill_rate_pct,
  round(100.0 * sum(fields_matched) / nullif(sum(fields_judged), 0), 1) AS agreement_pct,
  round(100.0 * sum(CASE WHEN state_matches_truth THEN 1 ELSE 0 END)
        / nullif(sum(CASE WHEN state_matches_truth IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS state_truth_pct,
  round(100.0 * sum(CASE WHEN city_matches_truth THEN 1 ELSE 0 END)
        / nullif(sum(CASE WHEN city_matches_truth IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS city_truth_pct,
  round(100.0 * sum(CASE WHEN zip_matches_truth THEN 1 ELSE 0 END)
        / nullif(sum(CASE WHEN zip_matches_truth IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS zip_truth_pct,
  CAST('0.00' AS varchar) AS cost_per_1k,
  round((100.0 * sum(fields_matched) / nullif(sum(fields_judged), 0)) * (sum(fields_answered) / (3.0 * count(*))), 1) AS score,
  (vendor = 'geojs_io') AS excluded_from_voting,
  CAST(current_date AS varchar) AS as_of_date
FROM f GROUP BY vendor""")
    cols = ["vendor", "ips_tested", "fill_rate_pct", "agreement_pct", "state_truth_pct", "city_truth_pct",
            "zip_truth_pct", "cost_per_1k", "score", "excluded_from_voting", "as_of_date"]
    run(f"""MERGE INTO {DB}.vendor_overview_geo t USING {stg} s ON t.vendor = s.vendor
WHEN MATCHED THEN UPDATE SET {", ".join("%s = s.%s" % (c, c) for c in cols[1:])}
WHEN NOT MATCHED THEN INSERT ({", ".join(cols)}) VALUES ({", ".join("s." + c for c in cols)})""")
    return pool, True


def refresh_proxy_scorecard(staging, vendors):
    pool_sql = f"""SELECT ip_address FROM {DB}.ip_intelligence_analytics WHERE vendor IN ({_in_list(vendors)})
                   GROUP BY ip_address HAVING count(DISTINCT vendor) = {len(vendors)}"""
    pool = scalar("SELECT count(*) FROM (%s)" % pool_sql)
    if pool < MIN_SCORECARD_POOL:
        return pool, False
    stg = staging.ctas("scorecard_proxy", f"""
WITH pool AS ({pool_sql})
SELECT a.vendor, count(*) AS ips_tested,
  sum(CASE WHEN a.has_answer THEN 1 ELSE 0 END) AS answered,
  round(100.0 * sum(CASE WHEN a.has_answer THEN 1 ELSE 0 END) / count(*), 1) AS fill_rate_pct,
  sum(CASE WHEN a.flagged THEN 1 ELSE 0 END) AS flagged,
  sum(CASE WHEN i.is_bot THEN 1 ELSE 0 END) AS bot_flagged,
  round(100.0 * sum(CASE WHEN i.is_bot THEN 1 ELSE 0 END)
        / nullif(sum(CASE WHEN a.has_answer THEN 1 ELSE 0 END), 0), 1) AS bot_identification_pct,
  -- The approved definition: of the confirmed humans (qualified_lead_ips.confirmed_human) in the pool that
  -- this vendor gave a bot answer for, the share it flagged as bot. Every such flag is wrong. NULL when the
  -- vendor gives no bot answers at all. (Until 15 Sep this column divided by the whole pool, which is not
  -- all humans, so it repeated bot_identification_pct.)
  round(100.0 * sum(CASE WHEN hu.ip_address IS NOT NULL AND i.is_bot THEN 1 ELSE 0 END)
        / nullif(sum(CASE WHEN hu.ip_address IS NOT NULL AND i.is_bot IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS false_positive_rate_pct,
  sum(CASE WHEN i.is_compromised THEN 1 ELSE 0 END) AS compromised_flagged,
  sum(CASE WHEN i.is_scraper THEN 1 ELSE 0 END) AS scraper_flagged,
  sum(CASE WHEN i.is_anonymous THEN 1 ELSE 0 END) AS anonymous_flagged,
  -- NULL, not 0, when the pool holds no published-range address: there is nothing to measure against.
  CASE WHEN sum(CASE WHEN a.known_infrastructure THEN 1 ELSE 0 END) = 0 THEN CAST(NULL AS double) ELSE
  round(100.0 * sum(CASE WHEN a.flagged AND a.known_infrastructure THEN 1 ELSE 0 END)
        / nullif(sum(CASE WHEN a.flagged THEN 1 ELSE 0 END), 0), 1) END AS precision_infra_pct,
  round(100.0 * sum(CASE WHEN a.flagged AND a.known_infrastructure THEN 1 ELSE 0 END)
        / nullif(sum(CASE WHEN a.known_infrastructure THEN 1 ELSE 0 END), 0), 1) AS recall_infra_pct,
  CAST(NULL AS double) AS precision_bot_pct, CAST(NULL AS double) AS recall_bot_pct,
  CAST('false_positive_rate_pct measured on ' || CAST(sum(CASE WHEN hu.ip_address IS NOT NULL AND i.is_bot IS NOT NULL THEN 1 ELSE 0 END) AS varchar)
       || ' confirmed humans; precision and recall need a bot-labelled pool' AS varchar) AS bot_metric_status,
  CAST('0.00' AS varchar) AS cost_per_1k,
  round(avg(CASE WHEN NOT a.has_answer THEN NULL
                 WHEN a.verdict_class IN ('confirmed_by_published_range', 'agreed_not_flagged') THEN 100.0
                 ELSE 0.0 END), 1) AS score,
  CAST(current_date AS varchar) AS as_of_date
FROM {DB}.ip_intelligence_analytics a
JOIN pool p ON p.ip_address = a.ip_address
JOIN {DB}.ip_intelligence i ON i.ip_address = a.ip_address AND i.vendor = a.vendor
LEFT JOIN (SELECT DISTINCT ip_address FROM {DB}.qualified_lead_ips WHERE confirmed_human) hu ON hu.ip_address = a.ip_address
WHERE a.vendor IN ({_in_list(vendors)})
GROUP BY a.vendor""")
    cols = ["vendor", "ips_tested", "answered", "fill_rate_pct", "flagged", "bot_flagged", "bot_identification_pct",
            "false_positive_rate_pct", "compromised_flagged", "scraper_flagged", "anonymous_flagged",
            "precision_infra_pct", "recall_infra_pct", "precision_bot_pct", "recall_bot_pct", "bot_metric_status",
            "cost_per_1k", "score", "as_of_date"]
    run(f"""MERGE INTO {DB}.vendor_overview_proxy t USING {stg} s ON t.vendor = s.vendor
WHEN MATCHED THEN UPDATE SET {", ".join("%s = s.%s" % (c, c) for c in cols[1:])}
WHEN NOT MATCHED THEN INSERT ({", ".join(cols)}) VALUES ({", ".join("s." + c for c in cols)})""")
    return pool, True


def export_scorecards():
    """The dashboard reads these files. They sit beside the existing ones, under their own folder,
    so the app keeps showing today's files until it is switched to these."""
    for t in ("vendor_overview_geo", "vendor_overview_proxy"):
        data = rows("SELECT * FROM %s.%s ORDER BY score DESC" % (DB, t))
        s3_put_json("%s/serving/ipintel_curated/tbl_%s.json" % (PREFIX, t), {"count": len(data), "rows": data})


# ---------------------------------------------------------------- assertions

def assertions(before, new_ips_table, stg_geo, stg_intel, pre_geo_snap, pre_intel_snap, file_vendors):
    checks = []

    def add(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": None if passed else detail})

    dup = rows(f"""
SELECT 'ip_geo' AS t, count_if(n > 1) AS d FROM (SELECT count(*) n FROM {DB}.ip_geo GROUP BY ip_address, vendor)
UNION ALL SELECT 'ip_intelligence', count_if(n > 1) FROM (SELECT count(*) n FROM {DB}.ip_intelligence GROUP BY ip_address, vendor)
UNION ALL SELECT 'ip_geo_analytics', count_if(n > 1) FROM (SELECT count(*) n FROM {DB}.ip_geo_analytics GROUP BY ip_address, vendor)
UNION ALL SELECT 'ip_intelligence_analytics', count_if(n > 1) FROM (SELECT count(*) n FROM {DB}.ip_intelligence_analytics GROUP BY ip_address, vendor)""")
    bad = {r["t"]: r["d"] for r in dup if r["d"]}
    add("No address appears twice for the same vendor", not bad, "duplicate pairs: %s" % bad)

    after = table_counts()
    shrank = {t: (before[t], after[t]) for t in FOUR_TABLES if after[t] < before[t]}
    add("No table has fewer rows than before", not shrank, "before and after: %s" % shrank)

    if new_ips_table:
        missing = scalar(f"""SELECT count(*) FROM {new_ips_table} n
                             WHERE NOT EXISTS (SELECT 1 FROM {DB}.ip_geo g WHERE g.ip_address = n.ip_address)""")
        add("Every new address is in ip_geo", missing == 0, "%s new addresses are missing" % missing)
        for vendor, table in file_vendors:
            gap = scalar(f"""SELECT count(*) FROM {new_ips_table} n WHERE NOT EXISTS
                             (SELECT 1 FROM {DB}.{table} x WHERE x.ip_address = n.ip_address AND x.vendor = {lit(vendor)})""")
            add("%s has a row for every new address" % vendor, gap == 0,
                "%s new addresses have no %s row" % (gap, vendor))

    for stg, table, snap in ((stg_geo, "ip_geo", pre_geo_snap), (stg_intel, "ip_intelligence", pre_intel_snap)):
        if not stg or not snap:
            continue
        moved = scalar(f"""
SELECT count(*) FROM {stg} s
JOIN {DB}.{table} FOR VERSION AS OF {snap} o ON o.ip_address = s.ip_address AND o.vendor = s.vendor
JOIN {DB}.{table} n ON n.ip_address = s.ip_address AND n.vendor = s.vendor
WHERE o.created_at IS DISTINCT FROM n.created_at""")
        add("Updated %s rows kept their original created_at" % table, moved == 0,
            "%s rows had created_at changed" % moved)
    return checks, after

FILLED_MARK = "FILLED_FROM_PROXYCHECK_IO"


def fill_fraudlogix_from_proxycheck():
    """Owner's rules (18 Sep), using proxycheck.io's answer for the same IP:
      1. An (IP, fraudlogix_tune) row with no FraudLogix decision gets every data column from proxycheck.io
         (proxy, vpn, tor, datacenter, compromised, scraper, anonymous, isp, asn) and, since the step 2 standard
         (19 Sep), is_bot too. The row is marked in ip_intelligence_analytics (fraud_reason = FILLED_MARK), so
         real FraudLogix decisions can always be told apart; accuracy work uses real decisions only.
      2. A row FraudLogix did decide keeps FraudLogix's values; only the columns FraudLogix never supplies
         (compromised, scraper, anonymous, isp, asn) are taken from proxycheck.io.
    A later real FraudLogix decision replaces rule-1 values in the daily load. Returns rows filled by rule 1."""
    pc = f"""SELECT ip_address, is_proxy, is_vpn, is_tor, is_datacenter, is_bot, is_compromised, is_scraper, is_anonymous,
                   isp, asn, updated_at
            FROM {DB}.ip_intelligence WHERE vendor = 'proxycheck_io' AND is_proxy IS NOT NULL"""
    filled = f"""SELECT ip_address FROM {DB}.ip_intelligence_analytics
                 WHERE vendor = 'fraudlogix_tune' AND fraud_reason = '{FILLED_MARK}'"""
    n = scalar(f"""SELECT count(*) FROM {DB}.ip_intelligence f JOIN ({pc}) p ON p.ip_address = f.ip_address
                   WHERE f.vendor = 'fraudlogix_tune' AND f.is_proxy IS NULL""")
    # rule 1: empty (or previously filled) rows take every data column; is_bot left empty
    run(f"""
MERGE INTO {DB}.ip_intelligence t
USING (SELECT p.* FROM ({pc}) p JOIN {DB}.ip_intelligence f ON f.ip_address = p.ip_address AND f.vendor = 'fraudlogix_tune'
       LEFT JOIN ({filled}) m ON m.ip_address = p.ip_address
       WHERE f.is_proxy IS NULL OR m.ip_address IS NOT NULL) s
ON t.ip_address = s.ip_address AND t.vendor = 'fraudlogix_tune'
WHEN MATCHED THEN UPDATE SET is_proxy = s.is_proxy, is_vpn = s.is_vpn, is_tor = s.is_tor,
  is_datacenter = s.is_datacenter, is_bot = s.is_bot, is_compromised = s.is_compromised,
  is_scraper = s.is_scraper, is_anonymous = s.is_anonymous, isp = s.isp, asn = s.asn, updated_at = s.updated_at""")
    # rule 2: decided rows keep FraudLogix's values; only the columns FraudLogix never supplies are added
    run(f"""
MERGE INTO {DB}.ip_intelligence t
USING (SELECT p.* FROM ({pc}) p JOIN {DB}.ip_intelligence f ON f.ip_address = p.ip_address AND f.vendor = 'fraudlogix_tune'
       LEFT JOIN ({filled}) m ON m.ip_address = p.ip_address
       WHERE f.is_proxy IS NOT NULL AND m.ip_address IS NULL
         AND (f.is_compromised IS NULL OR f.is_scraper IS NULL OR f.is_anonymous IS NULL OR f.isp IS NULL OR f.asn IS NULL)) s
ON t.ip_address = s.ip_address AND t.vendor = 'fraudlogix_tune'
WHEN MATCHED THEN UPDATE SET is_compromised = coalesce(t.is_compromised, s.is_compromised),
  is_scraper = coalesce(t.is_scraper, s.is_scraper), is_anonymous = coalesce(t.is_anonymous, s.is_anonymous),
  isp = coalesce(t.isp, s.isp), asn = coalesce(t.asn, s.asn)""")
    # mark rule-1 rows in the analytics table
    run(f"""
MERGE INTO {DB}.ip_intelligence_analytics t
USING (SELECT pa.ip_address, pa.flagged, pa.risk_score, pa.known_infrastructure, pa.infrastructure_list, pa.verdict_class
       FROM {DB}.ip_intelligence_analytics pa
       JOIN {DB}.ip_intelligence_analytics fa ON fa.ip_address = pa.ip_address AND fa.vendor = 'fraudlogix_tune'
       WHERE pa.vendor = 'proxycheck_io' AND pa.has_answer
         AND (NOT fa.has_answer OR coalesce(fa.fraud_reason, '') = '{FILLED_MARK}')) s
ON t.ip_address = s.ip_address AND t.vendor = 'fraudlogix_tune'
WHEN MATCHED THEN UPDATE SET has_answer = true, flagged = s.flagged, fraud_reason = '{FILLED_MARK}',
  risk_score = s.risk_score, known_infrastructure = s.known_infrastructure,
  infrastructure_list = s.infrastructure_list, verdict_class = s.verdict_class""")
    return n


# ---------------------------------------------------------------- is_flagged / flagged_reason / bot_reason

FLAG_COLUMNS = ["is_flagged", "flagged_reason", "bot_reason"]
NOT_FLAGGED, NOT_BOT = "NOT_FLAGGED", "NOT_BOT"
_PC_NETWORK_TYPES = ("business", "residential", "wireless", "")


def _code(expr):
    """A vendor type as a reason code: 'Compromised Server' -> 'COMPROMISED_SERVER'."""
    return "upper(replace(trim(%s), ' ', '_'))" % expr


def flag_columns_sql():
    """The three explanation columns of ip_intelligence, from each row's own answer. NULL only where the vendor gave
    no answer; answered and not flagged / not bot says NOT_FLAGGED / NOT_BOT.

    Step 2 standard (owner, 19 Sep): is_bot means "bad signal", so for every vendor is_bot = is_flagged and
    bot_reason = flagged_reason whenever is_bot is true.
      fraudlogix_tune  FraudLogix's latest decision is FLAGGED; reason = its reason code (PROXY, VPN, BOT_GENERATED,
                       ABNORMAL_TRAFFIC_PATTERNS, BASIC_FRAUD, MASKED_DEVICES, 10, ...).
                       Rows filled from proxycheck.io (FILLED_MARK) take proxycheck.io's values, reason prefixed
                       'PROXYCHECK_IO:'.
      proxycheck_io    any of proxy, vpn, tor, datacenter, compromised, scraper, a bad type, a cloud network or
                       risk 67+; reason = the type (SOCKS5, COMPROMISED_SERVER, ...) else VPN / PROXY / TOR /
                       DATA_CENTER / SCRAPER / CLOUD_ASN:<asn> / HIGH_RISK (risk 67+) / VPN / PROXY,
                       strongest first.
      ip2proxy_px12    listed; reason = proxy type / usage / threat, e.g. PUB/DCH/SPAM.
    """
    import vendors
    net_types = ", ".join(lit(t) for t in _PC_NETWORK_TYPES)
    clouds = ", ".join(lit(a) for a in sorted(vendors.CLOUD_ASNS))
    flagged = ("(coalesce({p}.is_proxy, false) OR coalesce({p}.is_vpn, false) OR coalesce({p}.is_tor, false) "
               "OR coalesce({p}.is_datacenter, false) OR coalesce({p}.is_bot, false) "
               "OR coalesce({p}.is_compromised, false) OR coalesce({p}.is_scraper, false))")
    reason = ("coalesce(CASE WHEN lower(trim(coalesce({a}.fraud_reason, ''))) NOT IN ({net}) THEN {code} END, "
              # strongest signal first; plain VPN / PROXY last, since real customers use them too
              "CASE WHEN {p}.is_tor THEN 'TOR' "
              "WHEN {p}.is_datacenter THEN 'DATA_CENTER' WHEN {p}.is_compromised THEN 'COMPROMISED_SERVER' "
              "WHEN {p}.is_scraper THEN 'SCRAPER' "
              "WHEN upper(coalesce({p}.asn, '')) IN ({clouds}) THEN 'CLOUD_ASN:' || upper({p}.asn) "
              "WHEN {a}.risk_score >= {risk} THEN 'HIGH_RISK' "
              "WHEN {p}.is_vpn THEN 'VPN' WHEN {p}.is_proxy THEN 'PROXY' "
              "WHEN {p}.is_bot THEN 'BAD_SIGNAL' END)")
    kw = dict(net=net_types, clouds=clouds, risk=vendors.HIGH_RISK)
    fp, fr = flagged.format(p="i"), reason.format(p="i", a="a", code=_code("a.fraud_reason"), **kw)
    pp, pr = flagged.format(p="pi"), reason.format(p="pi", a="pa", code=_code("pa.fraud_reason"), **kw)
    return f"""
WITH x AS (
SELECT i.ip_address, i.vendor, i.is_bot,
  CASE WHEN NOT coalesce(a.has_answer, false) THEN CAST(NULL AS boolean)
       WHEN i.vendor = 'fraudlogix_tune' AND a.fraud_reason = '{FILLED_MARK}' THEN {pp}
       WHEN i.vendor = 'fraudlogix_tune' THEN coalesce(a.fraud_reason, 'ACCEPTED') <> 'ACCEPTED'
       WHEN i.vendor = 'proxycheck_io' THEN {fp}
       ELSE coalesce(a.flagged, false) END AS is_flagged,
  CASE WHEN NOT coalesce(a.has_answer, false) THEN CAST(NULL AS varchar)
       WHEN i.vendor = 'fraudlogix_tune' AND a.fraud_reason = '{FILLED_MARK}'
            THEN CASE WHEN {pp} THEN 'PROXYCHECK_IO:' || {pr} ELSE '{NOT_FLAGGED}' END
       WHEN i.vendor = 'fraudlogix_tune'
            THEN CASE WHEN coalesce(a.fraud_reason, 'ACCEPTED') = 'ACCEPTED' THEN '{NOT_FLAGGED}' ELSE a.fraud_reason END
       WHEN i.vendor = 'proxycheck_io' THEN CASE WHEN {fp} THEN {fr} ELSE '{NOT_FLAGGED}' END
       ELSE CASE WHEN a.flagged THEN coalesce(a.fraud_reason, 'FLAGGED') ELSE '{NOT_FLAGGED}' END END AS flagged_reason
FROM {DB}.ip_intelligence i
LEFT JOIN {DB}.ip_intelligence_analytics a ON a.ip_address = i.ip_address AND a.vendor = i.vendor
LEFT JOIN {DB}.ip_intelligence pi ON pi.ip_address = i.ip_address AND pi.vendor = 'proxycheck_io' AND i.vendor = 'fraudlogix_tune'
LEFT JOIN {DB}.ip_intelligence_analytics pa ON pa.ip_address = i.ip_address AND pa.vendor = 'proxycheck_io' AND i.vendor = 'fraudlogix_tune')
SELECT ip_address, vendor, is_flagged, flagged_reason,
  CASE WHEN is_bot IS NULL THEN CAST(NULL AS varchar) WHEN NOT is_bot THEN '{NOT_BOT}'
       ELSE coalesce(nullif(flagged_reason, '{NOT_FLAGGED}'), 'BAD_SIGNAL') END AS bot_reason
FROM x"""


def refresh_flag_columns():
    """Bring is_flagged / flagged_reason / bot_reason in line with each row's answer. Only rows whose values
    change are written; updated_at is left alone (these columns explain the answer, they are not a new one).
    Returns the number of rows changed."""
    diff = " OR ".join("t.%s IS DISTINCT FROM s.%s" % (f, f) for f in FLAG_COLUMNS)
    n = scalar(f"""SELECT count(*) FROM {DB}.ip_intelligence t JOIN ({flag_columns_sql()}) s
                   ON s.ip_address = t.ip_address AND s.vendor = t.vendor WHERE {diff}""")
    if n:
        run(f"""
MERGE INTO {DB}.ip_intelligence t
USING ({flag_columns_sql()}) s
ON t.ip_address = s.ip_address AND t.vendor = s.vendor
WHEN MATCHED AND ({diff}) THEN UPDATE SET is_flagged = s.is_flagged, flagged_reason = s.flagged_reason,
  bot_reason = s.bot_reason""", timeout_s=840)
    return n


def flag_column_checks():
    """Every answered row has is_flagged and flagged_reason; bot_reason is filled exactly when is_bot is; and under the
    step 2 standard (is_bot = bad signal) is_bot equals is_flagged."""
    r = rows(f"""
SELECT count_if(a.has_answer AND (i.is_flagged IS NULL OR i.flagged_reason IS NULL)) AS answered_empty,
       count_if(NOT coalesce(a.has_answer, false) AND (i.is_flagged IS NOT NULL OR i.flagged_reason IS NOT NULL)) AS unanswered_filled,
       count_if((i.is_bot IS NULL) <> (i.bot_reason IS NULL)) AS bot_mismatch,
       count_if(i.is_bot AND i.bot_reason = '{NOT_BOT}') + count_if(NOT i.is_bot AND i.bot_reason <> '{NOT_BOT}') AS bot_wrong,
       count_if(i.is_flagged AND i.flagged_reason = '{NOT_FLAGGED}') + count_if(NOT i.is_flagged AND i.flagged_reason <> '{NOT_FLAGGED}') AS flag_wrong,
       count_if(i.is_bot IS NOT NULL AND i.is_bot IS DISTINCT FROM i.is_flagged) AS bad_signal_not_flagged
FROM {DB}.ip_intelligence i
LEFT JOIN {DB}.ip_intelligence_analytics a ON a.ip_address = i.ip_address AND a.vendor = i.vendor""", timeout_s=600)[0]
    bad = {k: v for k, v in r.items() if v}
    return [{"name": "is_flagged / flagged_reason / bot_reason match every row's answer", "passed": not bad,
             "detail": None if not bad else "; ".join("%s: %s rows" % kv for kv in bad.items())}]
