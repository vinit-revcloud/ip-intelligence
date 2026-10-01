"""Addresses from the base tables that need proxycheck.io: ipintel_curated.proxycheck_queue.

The rule is the one the lookup API applies (lookup.needs_proxycheck), so an address gets the same treatment
whether it arrives through a new base-table row or a direct API call:

  Never, when proxycheck.io has already answered the address, or it is not a public address.
  Otherwise, in this order:
    new_address          the address was not in ip_geo / ip_intelligence before this run
    no_location          no vendor gave a location
    no_answer            no vendor gave a proxy answer
    vendors_disagree     proxy vendors disagree
    flagged_unconfirmed  flagged, with nothing confirming it
    location_disagree    location vendors disagree

Which addresses are checked: every address whose base-table rows changed since the previous successful run
(its ip_occurrences row was inserted or updated) plus every address IP2Location first answered since then.
The window starts at the previous run's watermark, so a failed run is covered again by the next one.

Job A queues them. Job B sends every waiting address first, the same day, and closes each queue row when the
answer is in the tables (or proxycheck.io had no record for it).
"""
from common import DB, lit, public_ipv4_sql, rows, run, scalar

QUEUE = DB + ".proxycheck_queue"
REASONS = ["new_address", "no_location", "no_answer", "vendors_disagree", "flagged_unconfirmed",
           "location_disagree", "recheck_stale"]
RECHECK = "recheck_stale"
RECHECK_AFTER_DAYS = 30        # owner's rule: a returning address gets a fresh answer when ours is older than this
RECHECK_DAILY_CAP = 20000      # at most this many re-checks queued per run, so new addresses always fit the budget


def reason_sql(r, is_new):
    """Why the resolved row `r` needs proxycheck.io, or NULL. Mirrors lookup.needs_proxycheck."""
    return f"""CASE WHEN {r}.proxy_decided_by = 'proxycheck_io' THEN NULL
       WHEN NOT ({public_ipv4_sql(r + '.ip_address')}) THEN NULL
       WHEN {is_new} THEN 'new_address'
       WHEN {r}.geo_status = 'no_answer' THEN 'no_location'
       WHEN {r}.proxy_status IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed') THEN {r}.proxy_status
       WHEN {r}.geo_status = 'vendors_disagree' THEN 'location_disagree'
  END"""


def candidates_sql(since):
    return f"""
WITH new AS (
  SELECT ip_address FROM {DB}.ip_geo WHERE vendor = 'ip2location_db11' AND created_at >= {lit(since)}),
touched AS (
  SELECT ip_address FROM {DB}.ip_occurrences WHERE updated_at >= {lit(since)}
  UNION SELECT ip_address FROM new)
SELECT r.ip_address, {reason_sql('r', 'n.ip_address IS NOT NULL')} AS reason
FROM touched t
JOIN {DB}.ip_resolved r ON r.ip_address = t.ip_address
LEFT JOIN new n ON n.ip_address = t.ip_address"""


def enqueue(staging, since, queued_at, run_id):
    """Add every base-table address that needs proxycheck.io. Returns (counts by reason, check)."""
    stg = staging.ctas("pc_candidates", "SELECT * FROM (%s) WHERE reason IS NOT NULL" % candidates_sql(since))
    by_reason = {r["reason"]: r["n"] for r in rows("SELECT reason, count(*) AS n FROM %s GROUP BY reason" % stg)}
    if by_reason:
        run(f"""
MERGE INTO {QUEUE} t USING {stg} s ON t.ip_address = s.ip_address
WHEN NOT MATCHED THEN INSERT (ip_address, reason, source, queued_at, queued_by_run, answered_at, outcome)
  VALUES (s.ip_address, s.reason, 'base_tables', {lit(queued_at)}, {lit(run_id)}, CAST(NULL AS varchar), CAST(NULL AS varchar))""")
    missing = scalar(f"SELECT count(*) FROM {stg} s LEFT JOIN {QUEUE} q ON q.ip_address = s.ip_address WHERE q.ip_address IS NULL")
    check = {"name": "Every base-table address that needs proxycheck.io is queued", "passed": not missing,
             "detail": None if not missing else "%d addresses needing proxycheck.io are not in the queue" % missing}
    return by_reason, check


def waiting_sql():
    """Queued addresses still waiting: never answered by proxycheck.io, or queued for a re-check."""
    return f"""SELECT q.ip_address FROM {QUEUE} q
WHERE q.answered_at IS NULL
  AND (q.reason = '{RECHECK}'
       OR NOT EXISTS (SELECT 1 FROM {DB}.ip_intelligence i WHERE i.ip_address = q.ip_address AND i.vendor = 'proxycheck_io'))"""


def enqueue_unresolved(staging, queued_at, run_id):
    """Every public address in the tables with no reliable answer (FraudLogix undecided and no proxycheck.io
    answer; IP2Proxy alone never counts) is queued, whatever its age, so Job B sends it first. Addresses
    proxycheck.io already returned no record for are left out: asking again every day would not change that.
    Returns (addresses queued, check)."""
    stg = staging.ctas("pc_unresolved", f"""
WITH ans AS (SELECT ip_address, count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND has_answer) AS n
             FROM {DB}.ip_intelligence_analytics GROUP BY ip_address)
SELECT g.ip_address FROM (SELECT DISTINCT ip_address FROM {DB}.ip_geo) g
LEFT JOIN ans a ON a.ip_address = g.ip_address
LEFT JOIN {QUEUE} q ON q.ip_address = g.ip_address
WHERE coalesce(a.n, 0) = 0 AND {public_ipv4_sql('g.ip_address')}
  AND NOT (q.ip_address IS NOT NULL AND q.answered_at IS NULL)
  AND coalesce(q.outcome, '') <> 'no_record_from_proxycheck'""")
    n = scalar("SELECT count(*) FROM %s" % stg)
    if n:
        run(f"""
MERGE INTO {QUEUE} t USING {stg} s ON t.ip_address = s.ip_address
WHEN MATCHED AND t.answered_at IS NOT NULL THEN UPDATE SET reason = 'no_answer', source = 'tables',
  queued_at = {lit(queued_at)}, queued_by_run = {lit(run_id)}, answered_at = CAST(NULL AS varchar), outcome = CAST(NULL AS varchar)
WHEN NOT MATCHED THEN INSERT (ip_address, reason, source, queued_at, queued_by_run, answered_at, outcome)
  VALUES (s.ip_address, 'no_answer', 'tables', {lit(queued_at)}, {lit(run_id)}, CAST(NULL AS varchar), CAST(NULL AS varchar))""")
    missing = scalar(f"SELECT count(*) FROM {stg} s LEFT JOIN {QUEUE} q ON q.ip_address = s.ip_address "
                     f"WHERE q.ip_address IS NULL OR q.answered_at IS NOT NULL")
    check = {"name": "Every public address without a reliable answer is queued for proxycheck.io",
             "passed": not missing,
             "detail": None if not missing else "%d unresolved addresses are not waiting in the queue" % missing}
    return n, check


def enqueue_rechecks(staging, since, queued_at, run_id, max_age_days=RECHECK_AFTER_DAYS, cap=RECHECK_DAILY_CAP):
    """Owner's rule: when an address shows up again in a base table and proxycheck.io's answer for it is older
    than max_age_days, ask again, so the latest answer wins. 'Seen again' = its ip_occurrences row changed since
    the previous successful run. The age of the answer is the last time it was asked through the queue, else
    when the proxycheck.io row was created. Most recently seen first, at most `cap` per run.
    Returns (addresses queued, check)."""
    stg = staging.ctas("pc_recheck", f"""
WITH touched AS (SELECT ip_address, max(last_seen) AS last_seen FROM {DB}.ip_occurrences
                 WHERE updated_at >= {lit(since)} GROUP BY ip_address),
pc AS (SELECT ip_address, created_at FROM {DB}.ip_intelligence WHERE vendor = 'proxycheck_io')
SELECT t.ip_address FROM touched t
JOIN pc ON pc.ip_address = t.ip_address
LEFT JOIN {QUEUE} q ON q.ip_address = t.ip_address
WHERE {public_ipv4_sql('t.ip_address')}
  AND NOT (q.ip_address IS NOT NULL AND q.answered_at IS NULL)
  AND substr(coalesce(q.answered_at, pc.created_at), 1, 10)
      < CAST(date_add('day', -{int(max_age_days)}, date(substr({lit(queued_at)}, 1, 10))) AS varchar)
ORDER BY t.last_seen DESC, t.ip_address
LIMIT {int(cap)}""")
    n = scalar("SELECT count(*) FROM %s" % stg)
    if n:
        run(f"""
MERGE INTO {QUEUE} t USING {stg} s ON t.ip_address = s.ip_address
WHEN MATCHED AND t.answered_at IS NOT NULL THEN UPDATE SET reason = '{RECHECK}', source = 'base_tables',
  queued_at = {lit(queued_at)}, queued_by_run = {lit(run_id)}, answered_at = CAST(NULL AS varchar), outcome = CAST(NULL AS varchar)
WHEN NOT MATCHED THEN INSERT (ip_address, reason, source, queued_at, queued_by_run, answered_at, outcome)
  VALUES (s.ip_address, '{RECHECK}', 'base_tables', {lit(queued_at)}, {lit(run_id)}, CAST(NULL AS varchar), CAST(NULL AS varchar))""")
    missing = scalar(f"SELECT count(*) FROM {stg} s LEFT JOIN {QUEUE} q ON q.ip_address = s.ip_address "
                     f"WHERE q.ip_address IS NULL OR q.answered_at IS NOT NULL")
    check = {"name": "Every returning address with an answer older than %d days is queued for a re-check" % max_age_days,
             "passed": not missing,
             "detail": None if not missing else "%d re-check addresses are not waiting in the queue" % missing}
    return n, check


def close(staging, closed_at, no_record_ips, sent_ips=()):
    """Mark queue rows answered once proxycheck.io's answer is in ip_intelligence, and rows proxycheck.io
    returned no record for. A re-check row is closed only when this run actually sent the address (the old
    answer is already in the table, so its presence proves nothing). Returns how many are still waiting."""
    run(f"""
MERGE INTO {QUEUE} t
USING (SELECT DISTINCT ip_address FROM {DB}.ip_intelligence WHERE vendor = 'proxycheck_io') s
ON t.ip_address = s.ip_address
WHEN MATCHED AND t.answered_at IS NULL AND t.reason <> '{RECHECK}' THEN UPDATE SET answered_at = {lit(closed_at)}, outcome = 'answered'""")
    if sent_ips:
        staging.put_ndjson("sent", [{"ip_address": ip} for ip in sent_ips])
        st = staging.json_table("sent", "ip_address string")
        run(f"""
MERGE INTO {QUEUE} t USING (SELECT DISTINCT ip_address FROM {st}) s ON t.ip_address = s.ip_address
WHEN MATCHED AND t.answered_at IS NULL AND t.reason = '{RECHECK}' THEN UPDATE SET answered_at = {lit(closed_at)}, outcome = 'rechecked'""")
    if no_record_ips:
        staging.put_ndjson("no_record", [{"ip_address": ip} for ip in no_record_ips])
        nr = staging.json_table("no_record", "ip_address string")
        run(f"""
MERGE INTO {QUEUE} t USING (SELECT DISTINCT ip_address FROM {nr}) s ON t.ip_address = s.ip_address
WHEN MATCHED AND t.answered_at IS NULL THEN UPDATE SET answered_at = {lit(closed_at)}, outcome = 'no_record_from_proxycheck'""")
    return scalar("SELECT count(*) FROM %s WHERE answered_at IS NULL" % QUEUE)
