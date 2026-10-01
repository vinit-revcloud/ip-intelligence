"""Job A: ipintel-free-daily.

Finds addresses that are new in the base tables, or whose FraudLogix decision may have changed,
asks every free vendor about them, and upserts the answers into the ipintel_curated tables.
Then hands over to Job B.

Also answers {"action": "validate", "id": ...} for the Base Tables page, because that check has to
run as this role to prove this role can actually read the table.
"""
import json
import re
import time
import traceback

import accuracy
import apply
import completeness
import coverage
import pcqueue
import resolved
import common as c
import vendors as v

JOB = "free-daily"
FUNCTION_NAMES = ["ipintel-free-daily", "ipintel-proxycheck-daily"]
SAFETY_MARGIN_S = 150
WEB_VENDOR_CAP = 500


def _version_clause(bt, snapshots):
    sid = snapshots.get(bt["sk"])
    return "FOR VERSION AS OF %s" % sid if sid else ""


def _source_select(bt, snapshots):
    db, table = c.ident(bt["database"]), c.ident(bt["table"])
    ipc, seen = c.ident(bt["ip_column"]), c.ident(bt["seen_at_column"])
    return ("SELECT CAST(%s AS varchar) AS ip, try_cast(%s AS date) AS d FROM %s.%s %s"
            % (ipc, seen, db, table, _version_clause(bt, snapshots)))


def _snapshot(bt):
    try:
        r = c.rows('SELECT CAST(snapshot_id AS varchar) AS sid, CAST(committed_at AS varchar) AS at '
                   'FROM %s."%s$snapshots" ORDER BY committed_at DESC LIMIT 1'
                   % (c.ident(bt["database"]), bt["table"]))
        return (r[0]["sid"], r[0]["at"]) if r else (None, None)
    except c.QueryFailed:
        return (None, None)          # not an Iceberg table: no write log, so always treat as changed


def _enabled_vendors(capability):
    items = c.boto3.resource("dynamodb", region_name=c.REGION).Table("ipintel-sources").scan().get("Items", [])
    return sorted(i["id"] for i in c.to_plain(items)
                  if i.get("enabled") and capability in (i.get("capabilities") or []))


# ---------------------------------------------------------------- validate a base table

VALID_IPV4 = re.compile(r"^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$")


def validate(bt_id):
    bt = c.get_item("base_table", bt_id)
    if not bt:
        return {"status": "invalid", "problems": ["No base table named %s" % bt_id]}
    problems, out = [], {"checked_at": c.now_iso(), "table_format": "unknown", "write_pattern": "unknown",
                         "last_write_at": None, "rows_estimate": None, "valid_ipv4_pct": None,
                         "scan_gb_per_run": None}
    try:
        for k in ("database", "table", "ip_column", "seen_at_column"):
            c.ident(bt.get(k))
    except ValueError as e:
        problems.append(str(e))
    if not problems:
        try:
            t = c.glue.get_table(DatabaseName=bt["database"], Name=bt["table"])["Table"]
            cols = {col["Name"]: col["Type"] for col in t["StorageDescriptor"]["Columns"]}
            out["table_format"] = "iceberg" if (t.get("Parameters") or {}).get("table_type", "").upper() == "ICEBERG" else "hive"
            if bt["ip_column"] not in cols:
                problems.append("Column %s does not exist" % bt["ip_column"])
            elif not re.match(r"^(string|varchar)", cols[bt["ip_column"]]):
                problems.append("Column %s is %s, not text" % (bt["ip_column"], cols[bt["ip_column"]]))
            if bt["seen_at_column"] not in cols:
                problems.append("Column %s does not exist" % bt["seen_at_column"])
            elif not re.match(r"^(date|timestamp|string|varchar)", cols[bt["seen_at_column"]]):
                problems.append("Column %s is %s, not a date" % (bt["seen_at_column"], cols[bt["seen_at_column"]]))
        except c.glue.exceptions.EntityNotFoundException:
            problems.append("Table %s.%s does not exist" % (bt["database"], bt["table"]))
    if not problems:
        try:
            sample = c.rows("SELECT CAST(%s AS varchar) AS ip FROM %s.%s WHERE %s IS NOT NULL LIMIT 2000"
                            % (c.ident(bt["ip_column"]), c.ident(bt["database"]), c.ident(bt["table"]),
                               c.ident(bt["ip_column"])), timeout_s=120)
            good = sum(1 for r in sample if r["ip"] and VALID_IPV4.match(r["ip"]))
            out["valid_ipv4_pct"] = round(100.0 * good / len(sample), 1) if sample else 0.0
            if not sample:
                problems.append("The address column has no values")
            elif out["valid_ipv4_pct"] < 50:
                problems.append("Only %.1f%% of sampled values are IPv4 addresses. Is this the right column?"
                                % out["valid_ipv4_pct"])
        except c.QueryFailed as e:
            problems.append("The pipeline could not read this table: %s" % str(e)[:200])
    if not problems and out["table_format"] == "iceberg":
        try:
            r = c.rows('SELECT operation, CAST(committed_at AS varchar) AS at, summary FROM %s."%s$snapshots" '
                       'ORDER BY committed_at DESC LIMIT 20' % (c.ident(bt["database"]), bt["table"]), timeout_s=120)
            if r:
                ops = {x["operation"] for x in r}
                out["write_pattern"] = "append" if ops == {"append"} else "overwrite"
                out["last_write_at"] = r[0]["at"]
                summ = r[0]["summary"] or ""
                m = re.search(r"total-records=(\d+)", summ)
                f = re.search(r"total-files-size=(\d+)", summ)
                if m:
                    out["rows_estimate"] = int(m.group(1))
                if f:
                    ncols = max(len(cols), 1)
                    out["scan_gb_per_run"] = round(int(f.group(1)) * 2.0 / ncols / 1e9, 2)
        except c.QueryFailed:
            pass
    out["status"] = "invalid" if problems else "valid"
    out["problems"] = problems
    c.update_item("base_table", bt_id, validation=out, updated_at=c.now_iso())
    return out


# ---------------------------------------------------------------- the daily run

MAINTAINED_TABLES = ["ip_geo", "ip_intelligence", "ip_geo_analytics", "ip_intelligence_analytics",
                     "vendor_overview_geo", "vendor_overview_proxy", "ip_occurrences", "ip_resolved"]


def maintain(event, context):
    """Weekly: merge the small files every daily upsert leaves, then drop table versions older than the
    Iceberg default of 5 days. Only the project's own tables in ipintel_curated. Runs in this function so
    it can never overlap a daily run (reserved concurrency 1)."""
    # Only the fixed list, never a name from the event on its own: OPTIMIZE and VACUUM do not accept a
    # quoted identifier, so the name goes in bare and must be one of ours.
    tables = [t for t in (event.get("tables") or MAINTAINED_TABLES) if t in MAINTAINED_TABLES]
    log = c.start_run("maintenance", event.get("run_id") or c.new_run_id("maintenance"),
                      {"trigger": event.get("trigger", "manual"), "tables": tables})
    done, results = [], []
    try:
        if c.is_paused()[0]:
            return c.finish_run(log, "skipped", "The pipeline is paused.")
        for t in tables:
            if context and context.get_remaining_time_in_millis() < 240000:
                rest = [x for x in tables if x not in done]
                c.lam.invoke(FunctionName=context.function_name, InvocationType="Event",
                             Payload=json.dumps({"action": "maintain", "tables": rest, "trigger": "hand-over"}).encode())
                return c.finish_run(log, "succeeded", "Handed over %d tables to a fresh copy" % len(rest),
                                    done=done, results=results)
            for stmt in ("OPTIMIZE %s.%s REWRITE DATA USING BIN_PACK" % (c.DB, t),
                         "VACUUM %s.%s" % (c.DB, t)):
                try:
                    c.run(stmt, timeout_s=600)
                    results.append({"statement": stmt, "ok": True})
                except Exception as e:
                    results.append({"statement": stmt, "ok": False, "error": ("%s: %s" % (type(e).__name__, e))[:300]})
            done.append(t)
        failed = [r for r in results if not r["ok"]]
        return c.finish_run(log, "failed" if failed else "succeeded",
                            ("%d of %d statements failed" % (len(failed), len(results))) if failed else None,
                            done=done, results=results)
    except Exception as e:
        traceback.print_exc()
        return c.finish_run(log, "failed", "%s: %s" % (type(e).__name__, str(e)[:900]), done=done)


def refresh_resolved(event, context):
    """Recompute ip_resolved for every address, rebuild the report files, then refresh the unified tables.
    For when the resolution rules change; the daily runs do the same as part of their work."""
    run_id = event.get("run_id") or c.new_run_id("resolved-refresh")
    log = c.start_run("resolved-refresh", run_id, {"trigger": event.get("trigger", "manual"),
                                                   "reason": event.get("reason")})
    staging = c.Staging(run_id)
    try:
        if c.is_paused()[0]:
            return c.finish_run(log, "skipped", "The pipeline is paused.")
        perm = c.permission_check()
        if not c.record_safety([perm]):
            return c.finish_run(log, "failed", "Safety check failed before any work was done: " + (perm["detail"] or ""))
        changed, total = resolved.refresh(staging, c.now_iso())
        checks = [perm] + resolved.checks() + [accuracy.export(), coverage.export()]
        failed = [x for x in checks if not x["passed"]]
        if not failed and event.get("publish", True):
            c.lam.invoke(FunctionName="ipintel-proxycheck-daily", InvocationType="Event",
                         Payload=json.dumps({"action": "publish", "trigger": "after-resolved-refresh",
                                             "source_run": run_id}).encode())
        return c.finish_run(log, "failed" if failed else "succeeded",
                            ("%d check(s) failed" % len(failed)) if failed else None,
                            resolved_changed=changed, resolved_rows=total, checks=checks)
    except Exception as e:
        traceback.print_exc()
        return c.finish_run(log, "failed", "%s: %s" % (type(e).__name__, str(e)[:900]))
    finally:
        staging.cleanup()


def handler(event, context):
    event = event or {}
    if event.get("action") == "validate":
        return validate(event["id"])
    if event.get("action") == "maintain":
        return maintain(event, context)
    if event.get("action") == "refresh_resolved":
        return refresh_resolved(event, context)

    run_id = event.get("run_id") or c.new_run_id(JOB)
    deadline = time.time() + (context.get_remaining_time_in_millis() / 1000.0 if context else 840) - SAFETY_MARGIN_S
    log = c.start_run(JOB, run_id, {"trigger": event.get("trigger", "manual")})
    staging = c.Staging(run_id)
    try:
        paused, _ = c.is_paused()
        if paused:
            return c.finish_run(log, "skipped", "The pipeline is paused. Resume it on the Safety page.")
        if not (c.get_item("job", JOB) or {}).get("enabled") and event.get("trigger") != "manual":
            return c.finish_run(log, "skipped", "This job is switched off.")

        swept = c.sweep_staging()
        if swept:
            log["swept_staging_tables"] = swept

        perm = c.permission_check()
        log["checks"] = [perm]
        if not c.record_safety([perm]):
            return c.finish_run(log, "failed", "Safety check failed before any work was done: " + (perm["detail"] or ""))

        # 1. base tables that passed their last check
        bts = [b for b in c.query("base_table") if b.get("enabled")]
        usable = [b for b in bts if (b.get("validation") or {}).get("status") == "valid"]
        skipped = [b["sk"] for b in bts if b not in usable]
        if not usable:
            return c.finish_run(log, "failed", "No enabled base table has passed its check.")

        # 2. what changed since the last successful run, pinned to one version each
        snapshots, changed, quiet = {}, [], []
        for b in usable:
            sid, at = _snapshot(b)
            snapshots[b["sk"]] = sid
            if sid is None or sid != b.get("watermark_snapshot_id"):
                changed.append(b["sk"])
            if at:
                age_h = (time.time() - time.mktime(time.strptime(at[:19], "%Y-%m-%d %H:%M:%S"))) / 3600
                if age_h > 30:
                    quiet.append("%s (%.0f hours)" % (b["sk"], age_h))
        if quiet:
            c.alert("IP pipeline: a base table has not been written recently", "No write for over 30 hours: " + ", ".join(quiet))
        force = event.get("force") is True
        if not changed and not force:
            return c.finish_run(log, "skipped", "No base table has changed since the last successful run.",
                                new_ips=0, rows_inserted=0, rows_added=0, rows_updated=0, quiet_tables=quiet)

        seen_at = c.now_iso()
        before = apply.table_counts()
        pre_geo, pre_intel = apply.latest_snapshot("ip_geo"), apply.latest_snapshot("ip_intelligence")

        # 3. new addresses: in any base table, not yet in ipintel_curated.ip_geo
        union = "\n  UNION ALL\n  ".join(_source_select(b, snapshots) for b in usable)
        new_ips = staging.ctas("new_ips", f"""
WITH src AS (
  {union}
),
agg AS (SELECT ip, min(d) AS first_seen, max(d) AS last_seen FROM src
        WHERE ip IS NOT NULL AND length(ip) BETWEEN 7 AND 15 GROUP BY ip),
num AS (
  SELECT ip, first_seen, last_seen,
         try_cast(split_part(ip, '.', 1) AS bigint) AS o1, try_cast(split_part(ip, '.', 2) AS bigint) AS o2,
         try_cast(split_part(ip, '.', 3) AS bigint) AS o3, try_cast(split_part(ip, '.', 4) AS bigint) AS o4
  FROM agg WHERE cardinality(split(ip, '.')) = 4
)
SELECT ip AS ip_address, o1 * 16777216 + o2 * 65536 + o3 * 256 + o4 AS ip_num, o1 * 256 + o2 AS prefix16,
       first_seen, last_seen
FROM num n
WHERE o1 BETWEEN 0 AND 255 AND o2 BETWEEN 0 AND 255 AND o3 BETWEEN 0 AND 255 AND o4 BETWEEN 0 AND 255
  AND NOT EXISTS (SELECT 1 FROM {c.DB}.ip_geo g WHERE g.ip_address = n.ip AND g.vendor = 'ip2location_db11')""")
        # "New" means IP2Location has no row yet, not "no row at all": a live lookup can add proxycheck's
        # answer for an address before it ever reaches a base table, and that address still needs every
        # other vendor once it does.
        n_new = c.scalar("SELECT count(*) FROM %s" % new_ips)

        # 4. addresses whose FraudLogix decision may have changed: clicks in the last three days
        tune = next((b for b in usable if b["database"] == "raw" and b["table"] == "raw_tune_clicks"), None)
        tune_clause = _version_clause(tune, snapshots) if tune else ""
        fl_targets = staging.ctas("fraudlogix_targets", f"""
SELECT ip_address FROM {new_ips}
UNION
SELECT DISTINCT t.ip AS ip_address FROM raw.raw_tune_clicks {tune_clause} t
WHERE t.ip IS NOT NULL AND try_cast(t.datetime AS date) >= current_date - interval '3' day
  AND t.ip IN (SELECT ip_address FROM {c.DB}.ip_geo WHERE vendor = 'ip2location_db11')""")

        # 5. ask the downloaded databases and FraudLogix
        notes = []
        switched_on = set(_enabled_vendors("geo")) | set(_enabled_vendors("risk")) | set(_enabled_vendors("validator"))
        geo_parts = [v.db11_geo_sql(new_ips, seen_at)]
        for vendor, table in v.OPTIONAL_GEO_DATABASES.items():
            if vendor not in switched_on:
                continue
            if c.table_exists(table):
                geo_parts.append(v.range_geo_sql(vendor, table, new_ips, seen_at))
            else:
                notes.append("%s is switched on but its database is not loaded" % vendor)
        intel_parts = [v.px12_intel_sql(new_ips, seen_at), v.fraudlogix_intel_sql(fl_targets, tune_clause)]
        for vendor, table in v.OPTIONAL_INTEL_DATABASES.items():
            if vendor not in switched_on:
                continue
            if c.table_exists(table):
                intel_parts.append(v.range_lists_intel_sql(table, new_ips, seen_at))
            else:
                notes.append("%s is switched on but its database is not loaded" % vendor)

        # 6. the free web APIs, within their limits. They are the tie-breakers for location: first addresses
        # seen in the last 30 days whose location vendors name different states, then the same state but
        # far-apart cities, each vendor on different addresses so more conflicts get a third vote; then new
        # addresses, which every web vendor is asked about.
        enabled_geo = _enabled_vendors("geo")
        web_rows, web_notes = [], []
        web_vendors = [x for x in enabled_geo if x in v.WEB_GEO_VENDORS]
        if web_vendors:
            start = (c.get_item("job", JOB) or {}).get("web_vendors_since", "2026-09-14")
            has_cols = ", ".join("coalesce(contains(h.vs, %s), false) AS has_%d" % (c.lit(x), i)
                                 for i, x in enumerate(web_vendors))
            cand = c.rows(f"""
WITH occ AS (SELECT ip_address, max(last_seen) AS ls FROM {c.DB}.ip_occurrences GROUP BY ip_address),
cand AS (
  SELECT r.ip_address, CASE r.geo_status WHEN 'vendors_disagree' THEN 1 ELSE 2 END AS pri, o.ls
  FROM {c.DB}.ip_resolved r JOIN occ o ON o.ip_address = r.ip_address
  WHERE r.geo_status IN ('vendors_disagree', 'same_state') AND o.ls >= date_add('day', -30, current_date)
    AND {c.public_ipv4_sql('r.ip_address')}
  UNION ALL
  SELECT g.ip_address, 3, CAST(NULL AS date) FROM {c.DB}.ip_geo g
  WHERE g.vendor = 'ip2location_db11' AND substr(g.created_at, 1, 10) >= {c.lit(start)}
  UNION ALL
  SELECT ip_address, 3, CAST(NULL AS date) FROM {new_ips}),
best AS (SELECT ip_address, min(pri) AS pri, max(ls) AS ls FROM cand GROUP BY ip_address),
have AS (SELECT ip_address, array_agg(vendor) AS vs FROM {c.DB}.ip_geo
         WHERE vendor IN ({", ".join(c.lit(x) for x in web_vendors)}) GROUP BY ip_address),
x AS (SELECT b.ip_address, b.pri, b.ls, {has_cols} FROM best b LEFT JOIN have h ON h.ip_address = b.ip_address)
SELECT * FROM x WHERE NOT ({" AND ".join("has_%d" % i for i in range(len(web_vendors)))})
ORDER BY pri, ls DESC NULLS LAST, ip_address
LIMIT {WEB_VENDOR_CAP * len(web_vendors) * 3}""", timeout_s=300)
            assigned = set()
            for i, vendor in enumerate(web_vendors):
                if time.time() > deadline - 300:
                    web_notes.append("%s: skipped, not enough time left" % vendor)
                    continue
                ips, tie = [], 0
                for r in cand:
                    if len(ips) >= WEB_VENDOR_CAP:
                        break
                    if r["has_%d" % i] or (r["pri"] < 3 and r["ip_address"] in assigned):
                        continue
                    ips.append(r["ip_address"])
                    if r["pri"] < 3:
                        tie += 1
                        assigned.add(r["ip_address"])
                got, asked, stopped = v.ask_web_vendor(vendor, ips, seen_at, deadline - 240)
                web_rows += got
                web_notes.append("%s: asked %d of %d (%d location tie-breaks)%s" % (
                    vendor, asked, len(ips), tie, ("; stopped: " + stopped) if stopped else ""))
        if web_rows:
            staging.put_ndjson("web_geo", web_rows)
            web_tbl = staging.json_table("web_geo", v.GEO_JSON_DDL)
            geo_parts.append("SELECT %s FROM %s" % (v.GEO_COLS, web_tbl))

        dedupe = "SELECT %s FROM (SELECT x.*, row_number() OVER (PARTITION BY ip_address, vendor ORDER BY seen_at DESC) AS rn FROM (%s) x) WHERE rn = 1"
        # Each lookup sits in its own subquery: Athena does not allow a WITH clause directly inside
        # UNION ALL, and the FraudLogix lookup starts with one.
        wrap = lambda parts: "\nUNION ALL\n".join("SELECT * FROM (%s)" % p for p in parts)
        stg_geo = staging.ctas("geo", dedupe % (v.GEO_COLS, wrap(geo_parts)))
        stg_intel = staging.ctas("intel", dedupe % (v.INTEL_COLS, wrap(intel_parts)))

        # 7. upsert, counting first so the run log says exactly what happened
        geo_plan = apply.plan_changes(stg_geo, "ip_geo", apply.GEO_FIELDS)
        intel_plan = apply.plan_changes(stg_intel, "ip_intelligence", apply.INTEL_FIELDS)
        apply.merge_geo(stg_geo)
        apply.merge_intel(stg_intel)

        # 8. the working-out, for affected addresses only
        apply.refresh_intel_analytics(stg_intel)
        apply.refresh_geo_analytics(stg_geo)
        apply.refresh_flag_columns()                       # is_flagged / flagged_reason / bot_reason

        # 8b. where every address occurs: one row per address and base table, from the pinned versions.
        # Recomputed in full because session summary is rewritten, then merged so history is kept:
        # first_seen only moves earlier and last_seen only later.
        occ_parts = ["SELECT %s AS base_table, %s AS source_table, ip, d FROM (%s)"
                     % (c.lit(b["sk"]), c.lit("%s.%s" % (b["database"], b["table"])), _source_select(b, snapshots))
                     for b in usable]
        stg_occ = staging.ctas("occurrences", """
SELECT ip AS ip_address, base_table, source_table, min(d) AS first_seen, max(d) AS last_seen,
       count(DISTINCT d) AS days_seen, count(*) AS rows_seen
FROM (%s)
WHERE regexp_like(ip, '^[0-9]{1,3}(\\.[0-9]{1,3}){3}$')
GROUP BY 1, 2, 3""" % "\nUNION ALL\n".join(occ_parts))
        c.run(f"""
MERGE INTO {c.DB}.ip_occurrences t
USING {stg_occ} s
ON t.ip_address = s.ip_address AND t.base_table = s.base_table
WHEN MATCHED AND (t.first_seen IS DISTINCT FROM least(coalesce(t.first_seen, s.first_seen), coalesce(s.first_seen, t.first_seen))
               OR t.last_seen IS DISTINCT FROM greatest(coalesce(t.last_seen, s.last_seen), coalesce(s.last_seen, t.last_seen))
               OR t.days_seen < s.days_seen OR t.rows_seen < s.rows_seen OR t.source_table <> s.source_table)
  THEN UPDATE SET first_seen = least(coalesce(t.first_seen, s.first_seen), coalesce(s.first_seen, t.first_seen)),
                  last_seen = greatest(coalesce(t.last_seen, s.last_seen), coalesce(s.last_seen, t.last_seen)),
                  days_seen = greatest(t.days_seen, s.days_seen), rows_seen = greatest(t.rows_seen, s.rows_seen),
                  source_table = s.source_table, updated_at = {c.lit(seen_at)}
WHEN NOT MATCHED THEN INSERT (ip_address, base_table, source_table, first_seen, last_seen, days_seen, rows_seen, updated_at)
  VALUES (s.ip_address, s.base_table, s.source_table, s.first_seen, s.last_seen, s.days_seen, s.rows_seen, {c.lit(seen_at)})""",
              timeout_s=600)
        occ_missing = c.scalar(f"SELECT count(*) FROM {new_ips} n WHERE NOT EXISTS "
                               f"(SELECT 1 FROM {c.DB}.ip_occurrences o WHERE o.ip_address = n.ip_address)")

        # 9. scorecards
        geo_pool, geo_done = apply.refresh_geo_scorecard(staging, v.scoreable(enabled_geo))
        proxy_pool, proxy_done = apply.refresh_proxy_scorecard(staging, _enabled_vendors("risk"))
        for label, pool, done in (("location", geo_pool, geo_done), ("proxy", proxy_pool, proxy_done)):
            if not done:
                notes.append("%s scorecard kept as it was: only %d addresses were asked of every vendor on it, below %d"
                             % (label, pool, apply.MIN_SCORECARD_POOL))
        apply.export_scorecards()

        # 9b. one resolved answer per address, the same rules as the lookup API
        resolved_changed, resolved_rows = resolved.refresh(staging, seen_at)

        # 9c. base-table addresses that need proxycheck.io, by the same rule as the lookup API. The window
        # starts at the previous successful run, so a failed run's addresses are covered by the next one.
        since = event.get("queue_since") or min([b["watermark_at"] for b in usable if b.get("watermark_at")] or [seen_at])
        queued_by_reason, queue_check = pcqueue.enqueue(staging, since, seen_at, run_id)
        # 9c2. any address in the tables still without a reliable answer, whatever its age
        unresolved, unresolved_check = pcqueue.enqueue_unresolved(staging, seen_at, run_id)
        if unresolved:
            queued_by_reason["no_answer_any_age"] = unresolved
        # 9d. returning addresses whose proxycheck.io answer is old get a fresh one (latest answer wins)
        rechecks, recheck_check = pcqueue.enqueue_rechecks(staging, since, seen_at, run_id)
        if rechecks:
            queued_by_reason[pcqueue.RECHECK] = rechecks

        # 10. assertions
        checks, after = apply.assertions(before, new_ips, stg_geo, stg_intel, pre_geo, pre_intel,
                                         [("ip2location_db11", "ip_geo"), ("ip2proxy_px12", "ip_intelligence")])
        checks += resolved.checks()
        checks.append(accuracy.export())
        checks.append(coverage.export())
        checks += completeness.export()
        checks += apply.flag_column_checks()
        checks.append(queue_check)
        checks.append(recheck_check)
        checks.append(unresolved_check)
        checks.append({"name": "Every new address has a row saying where it was seen", "passed": not occ_missing,
                       "detail": ("%d new addresses have no ip_occurrences row" % occ_missing) if occ_missing else None})
        seen, findings, partial = c.activity_review(FUNCTION_NAMES, deadline=deadline - 60)
        checks = [perm] + checks + [{"name": "Nothing outside the project was touched in the last 24 hours",
                                     "passed": not findings,
                                     "detail": "; ".join(findings[:5]) or ("review partial (%d events); the next run continues it" % seen if partial else None)}]
        c.record_safety([perm], seen, findings, partial)
        failed = [x for x in checks if not x["passed"]]

        summary = dict(new_ips=n_new,
                       rows_inserted=geo_plan["inserted"] + intel_plan["inserted"],
                       rows_added=geo_plan["added"] + intel_plan["added"],
                       rows_updated=geo_plan["updated"] + intel_plan["updated"],
                       geo_changes=geo_plan, intel_changes=intel_plan, rows_after=after,
                       snapshots=snapshots, changed_tables=changed, skipped_tables=skipped,
                       resolved_changed=resolved_changed, resolved_rows=resolved_rows,
                       queued_for_proxycheck=queued_by_reason, queue_window_start=since,
                       notes=notes + web_notes, scorecard_pools={"location": geo_pool, "proxy": proxy_pool},
                       audit_events=seen, checks=checks)
        if failed:
            return c.finish_run(log, "failed", "%d assertion(s) failed; progress was not recorded" % len(failed), **summary)

        # 11. record progress only now, then start Job B
        for b in usable:
            if snapshots.get(b["sk"]):
                c.update_item("base_table", b["sk"], watermark_snapshot_id=snapshots[b["sk"]],
                              watermark_at=c.now_iso())
        result = c.finish_run(log, "succeeded", None, **summary)
        if event.get("start_proxycheck", True):
            c.lam.invoke(FunctionName="ipintel-proxycheck-daily", InvocationType="Event",
                         Payload=json.dumps({"trigger": "after free-daily"}).encode())
        return result
    except Exception as e:
        traceback.print_exc()
        return c.finish_run(log, "failed", "%s: %s" % (type(e).__name__, str(e)[:900]))
    finally:
        staging.cleanup()
