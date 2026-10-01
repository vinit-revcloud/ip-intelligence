"""Publish the enriched tables to the six unified tables this project created on 11 September.

unified.ip_geo, ip_intelligence, ip_geo_analytics, ip_intelligence_analytics, vendor_overview_geo and
vendor_overview_proxy keep their data files in this project's own S3 folder
(ip-intelligence/unified/<table>/d=2026-09-11/), so they can be refreshed without any change to the Glue
catalog: the table definition, columns, bucketing and location stay exactly as they are, and only the
parquet files inside that folder are replaced.

Each unified table is refreshed in its own existing shape: the two main tables and ip_intelligence_analytics
are bucketed (64 buckets on ip_address); ip_geo_analytics and the two scorecards are plain parquet. Where the
unified definition declares a varchar(n) column, values are cut to n characters, which is what unified can
show anyway (only vendor_overview_proxy.bot_metric_status is longer today).

Order of work, per table. Nothing in unified changes until every check on the new copy has passed.
  1. The unified table still has the definition this code expects. Otherwise stop.
  2. The 11 September files are copied once to archive/ and never removed.
  3. A copy of ipintel_curated.<table> in the unified table's shape is written to a staging folder.
  4. The copy is checked: row count, no duplicate keys, bucket files where bucketed, and identical rows
     (sample addresses for the address tables, every row for the scorecards).
  5. The current files are copied to publish-previous/ (the rollback copy), then the new files are
     copied in, then the old files are removed. Readers see old + new rows for a few seconds, never
     an empty table.
  6. unified.<table> is checked the same way. On any failure the previous files are put back.
"""
import json
import re
import traceback

import app_export
import common as c

UNIFIED_DB = "unified"
BUCKETS = 64
# table -> (key columns, bucketed on ip_address)
SPECS = {
    "ip_geo": (["ip_address", "vendor"], True),
    "ip_intelligence": (["ip_address", "vendor"], True),
    "ip_intelligence_analytics": (["ip_address", "vendor"], True),
    "ip_geo_analytics": (["ip_address", "vendor"], False),
    "vendor_overview_geo": (["vendor"], False),
    "vendor_overview_proxy": (["vendor"], False),
}
TABLES = list(SPECS)
# Columns added to ipintel_curated after unified was created; published once an admin adds them to unified.
ADDED_LATER = {"ip_intelligence": ("is_flagged", "flagged_reason", "bot_reason")}
LIVE_DIR = {t: "%s/unified/%s/d=2026-09-11/" % (c.PREFIX, t) for t in TABLES}
ARCHIVE_DIR = {t: "%s/archive/unified-2026-09-11/%s/" % (c.PREFIX, t) for t in TABLES}
PREVIOUS_DIR = {t: "%s/publish-previous/%s/" % (c.PREFIX, t) for t in TABLES}
_BUCKET_FILE = re.compile(r"^(\d{6})_")
_VARCHAR = re.compile(r"^varchar\((\d+)\)$")


def _keys(prefix):
    out, token = [], None
    while True:
        kw = {"Bucket": c.BUCKET, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        page = c.s3.list_objects_v2(**kw)
        out += [o["Key"] for o in page.get("Contents", []) if not o["Key"].endswith("/")]
        if not page.get("IsTruncated"):
            return out
        token = page["NextContinuationToken"]


def _copy(keys, src_prefix, dst_prefix):
    for k in keys:
        c.s3.copy_object(Bucket=c.BUCKET, Key=dst_prefix + k[len(src_prefix):],
                         CopySource={"Bucket": c.BUCKET, "Key": k})


def _delete(keys):
    for i in range(0, len(keys), 1000):
        c.s3.delete_objects(Bucket=c.BUCKET, Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True})


def _columns(db, table):
    sd = c.glue.get_table(DatabaseName=db, Name=table)["Table"]["StorageDescriptor"]
    return [(x["Name"], x["Type"]) for x in sd["Columns"]], sd


def _base(t):
    return "string" if _VARCHAR.match(t) else t


def _guard(table):
    """The unified table must still be the one this project created; never write under anything else.
    Returns the unified columns and the select list that produces them from ipintel_curated."""
    cols, sd = _columns(UNIFIED_DB, table)
    curated, _ = _columns(c.DB, table)
    _, bucketed = SPECS[table]
    problems = []
    if sd.get("Location", "").rstrip("/") != "s3://%s/%s" % (c.BUCKET, LIVE_DIR[table].rstrip("/")):
        problems.append("location is %s" % sd.get("Location"))
    ucols = [(n, _base(t)) for n, t in cols]
    # unified may lag behind by columns added to ipintel_curated at the end (only an admin can change the unified
    # definition): those are left out until the admin adds them. Anything else is a mismatch.
    extra = curated[len(ucols):]
    if curated[:len(ucols)] != ucols or any(n not in ADDED_LATER.get(table, ()) for n, _ in extra):
        problems.append("columns differ from ipintel_curated.%s" % table)
    want = (["ip_address"], BUCKETS) if bucketed else ([], 0)
    if (sd.get("BucketColumns") or [], sd.get("NumberOfBuckets") or 0) != want:
        problems.append("bucketing is %s/%s" % (sd.get("BucketColumns"), sd.get("NumberOfBuckets")))
    if "parquet" not in (sd.get("SerdeInfo") or {}).get("SerializationLibrary", "").lower():
        problems.append("not parquet")
    select = []
    for n, t in cols:
        m = _VARCHAR.match(t)
        select.append("CAST(substr(%s, 1, %s) AS %s) AS %s" % (c.ident(n), m.group(1), t, c.ident(n)) if m
                      else c.ident(n))
    return cols, ", ".join(select), problems


def _row_text(cols):
    return " || '|' || ".join("coalesce(CAST(%s AS varchar), '~')" % c.ident(n) for n, _ in cols)


def _bucket_files_ok(keys):
    ids = set()
    for k in keys:
        m = _BUCKET_FILE.match(k.rsplit("/", 1)[-1])
        if not m:
            return False
        ids.add(int(m.group(1)))
    return ids <= set(range(BUCKETS)) and len(ids) >= BUCKETS - 1


def _profile(source, table, cols, sample_ips):
    """Row count, duplicate keys, and a fingerprint of the rows: for sample addresses (read through the
    lookup path an API uses) on the address tables, of every row on the scorecards."""
    keys, _ = SPECS[table]
    key = " || '|' || ".join("coalesce(CAST(%s AS varchar), '~')" % k for k in keys)
    counts = c.rows("SELECT count(*) AS n, count(*) - count(DISTINCT %s) AS dup FROM %s" % (key, source))[0]
    row = _row_text(cols)
    if "ip_address" in keys:
        in_list = ", ".join(c.lit(ip) for ip in sample_ips)
        fp = c.rows("SELECT ip_address AS k, count(*) AS n, to_hex(md5(to_utf8(array_join(array_sort(array_agg(%s)), '\n')))) AS h "
                    "FROM %s WHERE ip_address IN (%s) GROUP BY ip_address" % (row, source, in_list))
    else:
        fp = c.rows("SELECT 'all' AS k, count(*) AS n, to_hex(md5(to_utf8(array_join(array_sort(array_agg(%s)), '\n')))) AS h "
                    "FROM %s" % (row, source))
    return counts["n"], counts["dup"], {r["k"]: (r["n"], r["h"]) for r in fp}


def _samples(table):
    keys, _ = SPECS[table]
    if "ip_address" not in keys:
        return []
    # Addresses spread over every vendor and every bucket.
    r = c.rows("SELECT ip_address FROM (SELECT ip_address, row_number() OVER (PARTITION BY vendor ORDER BY ip_address DESC) rn "
               "FROM %s.%s) WHERE rn <= 20 UNION SELECT ip_address FROM (SELECT ip_address FROM %s.%s "
               "TABLESAMPLE BERNOULLI (0.05) LIMIT 150)" % (c.DB, table, c.DB, table))
    return sorted({x["ip_address"] for x in r})[:300]


def publish_table(table, run_id, dry_run=False):
    cols, select, problems = _guard(table)
    if problems:
        raise RuntimeError("unified.%s is not in the expected shape, nothing written: %s" % (table, "; ".join(problems)))
    _, bucketed = SPECS[table]

    live_keys = _keys(LIVE_DIR[table])
    if not dry_run and not _keys(ARCHIVE_DIR[table]):          # first publish only: keep 11 September forever
        _copy(live_keys, LIVE_DIR[table], ARCHIVE_DIR[table])
        if len(_keys(ARCHIVE_DIR[table])) != len(live_keys):
            raise RuntimeError("the archive copy of unified.%s is incomplete; unified untouched" % table)

    staging = c.Staging(run_id + "-pub-" + table)
    try:
        name = staging.name("copy")
        loc = staging.location("copy")
        layout = ("bucketed_by=ARRAY['ip_address'], bucket_count=%d, " % BUCKETS) if bucketed else ""
        c.run("CREATE TABLE %s.%s WITH (format='PARQUET', write_compression='SNAPPY', %sexternal_location='%s') "
              "AS SELECT %s FROM %s.%s" % (c.DB, name, layout, loc, select, c.DB, table), timeout_s=840)
        staging.names.append(name)
        new_prefix = loc[len("s3://%s/" % c.BUCKET):]
        new_keys = _keys(new_prefix)

        samples = _samples(table)
        source = "(SELECT %s FROM %s.%s)" % (select, c.DB, table)
        cur_n, _, cur_fp = _profile(source, table, cols, samples)
        new_n, new_dup, new_fp = _profile("%s.%s" % (c.DB, name), table, cols, samples)
        files_ok = _bucket_files_ok(new_keys) if bucketed else bool(new_keys) or cur_n == 0
        if new_n != cur_n or new_dup or new_fp != cur_fp or not files_ok:
            raise RuntimeError("the new copy of %s did not match ipintel_curated (rows %s vs %s, duplicates %s, "
                               "rows differ %s, files ok %s); unified untouched"
                               % (table, new_n, cur_n, new_dup, new_fp != cur_fp, files_ok))

        checked = len(samples) if samples else new_n
        if dry_run:
            return {"table": "unified." + table, "rows": new_n, "files": len(new_keys), "samples_checked": checked,
                    "dry_run": True}
        c.delete_prefix(PREVIOUS_DIR[table])
        _copy(live_keys, LIVE_DIR[table], PREVIOUS_DIR[table])
        if len(_keys(PREVIOUS_DIR[table])) != len(live_keys):
            raise RuntimeError("the rollback copy of unified.%s is incomplete; unified untouched" % table)
        try:
            _copy(new_keys, new_prefix, LIVE_DIR[table])     # old + new rows visible for a few seconds
            _delete(live_keys)
            pub_n, pub_dup, pub_fp = _profile("%s.%s" % (UNIFIED_DB, table), table, cols, samples)
            if pub_n != cur_n or pub_dup or pub_fp != cur_fp:
                raise RuntimeError("unified.%s did not read back correctly after the swap (rows %s vs %s, duplicates %s, "
                                   "rows differ %s)" % (table, pub_n, cur_n, pub_dup, pub_fp != cur_fp))
        except Exception as e:
            # Put the previous files back first, then remove anything else, so the table is never empty.
            _copy(_keys(PREVIOUS_DIR[table]), PREVIOUS_DIR[table], LIVE_DIR[table])
            _delete([k for k in _keys(LIVE_DIR[table]) if k not in set(live_keys)])
            raise RuntimeError("%s; the previous files were put back" % e)
        return {"table": "unified." + table, "rows": pub_n, "files": len(new_keys), "samples_checked": checked}
    finally:
        staging.cleanup()


def handler(event, context):
    event = event or {}
    run_id = event.get("run_id") or c.new_run_id("publish-unified")
    log = c.start_run("publish-unified", run_id, {"trigger": event.get("trigger", "manual"),
                                                  "source_run": event.get("source_run")})
    done = []
    try:
        if c.is_paused()[0]:
            return c.finish_run(log, "skipped", "The pipeline is paused.")
        perm = c.permission_check()
        if not c.record_safety([perm]):
            return c.finish_run(log, "failed", "Safety check failed before any work was done: " + (perm["detail"] or ""))
        tables = [t for t in (event.get("tables") or TABLES) if t in TABLES]
        for t in tables:
            if context and context.get_remaining_time_in_millis() < 420000 and done:
                rest = [x for x in tables if x not in [d["table"].split(".")[1] for d in done]]
                c.lam.invoke(FunctionName=context.function_name, InvocationType="Event",
                             Payload=json.dumps({"action": "publish", "tables": rest, "trigger": "hand-over",
                                                 "source_run": event.get("source_run"),
                                                 "dry_run": bool(event.get("dry_run"))}).encode())
                return c.finish_run(log, "succeeded", "Handed over %s to a fresh copy" % rest, published=done,
                                    checks=[perm])
            done.append(publish_table(t, run_id, bool(event.get("dry_run"))))
        checks = [perm] + [{"name": "%s matches ipintel_curated" % d["table"], "passed": True,
                            "detail": "%d rows, %d files, %d %s compared" % (
                                d["rows"], d["files"], d["samples_checked"],
                                "addresses" if SPECS[d["table"].split(".")[1]][0][0] == "ip_address" else "rows")}
                           for d in done]
        if event.get("dry_run"):
            return c.finish_run(log, "succeeded", "Dry run: new copies built and checked; unified not changed",
                                published=done, checks=checks)
        state = c.get_item("publish", "unified") or {}
        tables_state = {x["table"]: x for x in state.get("tables") or []}
        tables_state.update({d["table"]: dict(d, published_at=c.now_iso()) for d in done})
        c.update_item("publish", "unified", last_published_at=c.now_iso(), last_run_id=run_id,
                      tables=list(tables_state.values()))
        app = None
        if set(tables) == set(TABLES):   # a full refresh: bring the app's report data in S3 up to date too
            try:
                app = app_export.run("after-publish")
            except Exception as e:   # the app copy never fails the publish itself
                traceback.print_exc()
                app = {"status": "export failed: %s" % str(e)[:300]}
                c.alert("IP app snapshot export failed", app["status"])
        return c.finish_run(log, "succeeded", None, published=done, checks=checks,
                            app_export=(app or {}).get("status", "not run (partial publish)"))
    except Exception as e:
        traceback.print_exc()
        return c.finish_run(log, "failed", "%s: %s" % (type(e).__name__, str(e)[:900]), published=done)
