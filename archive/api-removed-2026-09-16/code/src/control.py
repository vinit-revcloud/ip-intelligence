"""Pipeline control endpoints for the Lovable Pipeline pages.

    GET    /safety                      POST /safety/pause     POST /safety/resume
    GET    /input-tables                POST /input-tables
    GET    /input-tables/{id}           PATCH /input-tables/{id}     DELETE /input-tables/{id}
    POST   /input-tables/{id}/validate
    GET    /catalog/databases           GET /catalog/tables?database=   GET /catalog/columns?database=&table=
    GET    /jobs                        PATCH /jobs/{id}
    POST   /jobs/{id}/run               GET /jobs/{id}/runs?limit=30
    GET    /quota

Everything lives in the ipintel-pipeline-state table. Every rule the UI shows is also enforced here:
the budget cap, the emergency stop, refusing to resume while a safety check fails, and refusing to
remove the last enabled base table. Mode (shadow or live) has no endpoint on purpose: switching the
app to the new tables needs written approval and is done outside the UI.

Base tables are only ever read. This module changes the list of them, never the tables themselves,
and the role running it cannot write to them.
"""
import datetime
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import boto3
from boto3.dynamodb.conditions import Key

_state = boto3.resource("dynamodb").Table("ipintel-pipeline-state")
_lambda = boto3.client("lambda")
_glue = boto3.client("glue")
_scheduler = boto3.client("scheduler")
_sm = boto3.client("secretsmanager")

JOBS = {"free-daily": "ipintel-free-daily", "proxycheck-daily": "ipintel-proxycheck-daily"}
SCHEDULES = {"free-daily": "ipintel-free-daily", "proxycheck-daily": "ipintel-proxycheck-daily"}
_ID = re.compile(r"^[a-z0-9_]{1,64}$")
_NAME = re.compile(r"^[a-z0-9_]{1,128}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
PROJECT_DATABASES = {"ipintel_curated"}      # the pipeline's own output can never be its input
RUN_STALE_MINUTES = 16                       # a Lambda cannot run longer than 15
USER_AGENT = "ipintel-control/1.0 (+ip-intelligence)"


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _plain(o):
    """DynamoDB Decimals back to int or float, recursively."""
    import decimal
    if isinstance(o, list):
        return [_plain(x) for x in o]
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, decimal.Decimal):
        return int(o) if o % 1 == 0 else float(o)
    return o


def _dyn(o):
    """Floats to Decimal, recursively, because DynamoDB refuses floats."""
    import decimal
    if isinstance(o, list):
        return [_dyn(x) for x in o]
    if isinstance(o, dict):
        return {k: _dyn(v) for k, v in o.items()}
    if isinstance(o, float):
        return decimal.Decimal(str(o))
    return o


def _num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _get(pk, sk):
    return _plain(_state.get_item(Key={"pk": pk, "sk": sk}).get("Item"))


def _query(pk, limit=None, newest_first=False):
    kw = {"KeyConditionExpression": Key("pk").eq(pk), "ScanIndexForward": not newest_first}
    if limit:
        kw["Limit"] = limit
    return _plain(_state.query(**kw).get("Items", []))


def _audit(action, target, detail):
    """Every change made through the UI is kept for 400 days."""
    _state.put_item(Item={"pk": "audit", "sk": "%s#%s" % (_now(), action), "action": action,
                          "target": target, "detail": json.dumps(detail, default=str)[:4000],
                          "expires_at": int(time.time()) + 400 * 86400})


# ---------------------------------------------------------------- safety

def get_safety():
    s = _get("safety", "state") or {}
    checks = [{"name": c.get("name"), "passed": bool(c.get("passed")),
               "checked_at": c.get("checked_at"), "detail": c.get("detail")} for c in s.get("checks") or []]
    return {"paused": bool(s.get("paused")), "paused_at": s.get("paused_at"),
            "paused_reason": s.get("paused_reason"),
            "mode": "live" if s.get("mode") == "live" else "shadow",
            "production_write_access": "detected" if s.get("production_write_access") == "detected" else "none",
            "checks": checks, "last_audit_at": s.get("last_audit_at"),
            "last_audit_findings": list(s.get("last_audit_findings") or [])}


def _reason(body):
    r = str(body.get("reason") or "").strip()
    if not r:
        raise ApiError(400, "A reason is required.")
    return r[:500]


def pause(body):
    reason = _reason(body)
    _state.update_item(Key={"pk": "safety", "sk": "state"},
                       UpdateExpression="SET paused = :t, paused_at = :a, paused_reason = :r",
                       ExpressionAttributeValues={":t": True, ":a": _now(), ":r": reason})
    _audit("pause", "safety", {"reason": reason})
    return get_safety()


def resume(body):
    reason = _reason(body)
    s = get_safety()
    failing = [c["name"] for c in s["checks"] if not c["passed"]]
    if s["production_write_access"] == "detected" or failing or s["last_audit_findings"]:
        raise ApiError(409, "Cannot resume while a safety check is failing: "
                       + "; ".join(failing + s["last_audit_findings"][:3] or ["production write access detected"]))
    _state.update_item(Key={"pk": "safety", "sk": "state"},
                       UpdateExpression="SET paused = :f, resumed_at = :a, resumed_reason = :r "
                                        "REMOVE paused_at, paused_reason",
                       ExpressionAttributeValues={":f": False, ":a": _now(), ":r": reason})
    _audit("resume", "safety", {"reason": reason})
    return get_safety()


# ---------------------------------------------------------------- catalog

def _glue_table(database, table):
    try:
        return _glue.get_table(DatabaseName=database, Name=table)["Table"]
    except _glue.exceptions.EntityNotFoundException:
        return None


def _format(t):
    p = {k.lower(): str(v).lower() for k, v in (t.get("Parameters") or {}).items()}
    if p.get("table_type") == "iceberg":
        return "iceberg"
    return "hive" if t.get("StorageDescriptor") else "unknown"


def catalog_databases():
    names, token = [], None
    while True:
        page = _glue.get_databases(**({"NextToken": token} if token else {}))
        names += [d["Name"] for d in page["DatabaseList"]]
        token = page.get("NextToken")
        if not token:
            break
    return {"databases": sorted(n for n in names if n not in PROJECT_DATABASES)}


def catalog_tables(q):
    db = q.get("database") or ""
    if not _NAME.match(db) or db in PROJECT_DATABASES:
        raise ApiError(400, "database must be a catalog database name")
    out, token = [], None
    try:
        while True:
            kw = {"DatabaseName": db}
            if token:
                kw["NextToken"] = token
            page = _glue.get_tables(**kw)
            out += [{"name": t["Name"], "format": _format(t)} for t in page["TableList"]]
            token = page.get("NextToken")
            if not token:
                break
    except _glue.exceptions.EntityNotFoundException:
        raise ApiError(404, "no database '%s'" % db)
    return {"tables": sorted(out, key=lambda t: t["name"])}


def _columns(t):
    sd = t.get("StorageDescriptor") or {}
    return [{"name": c["Name"], "type": c.get("Type", "")} for c in sd.get("Columns", []) + t.get("PartitionKeys", [])]


def catalog_columns(q):
    db, table = q.get("database") or "", q.get("table") or ""
    if not _NAME.match(db) or not _NAME.match(table) or db in PROJECT_DATABASES:
        raise ApiError(400, "database and table must be catalog names")
    t = _glue_table(db, table)
    if not t:
        raise ApiError(404, "no table %s.%s" % (db, table))
    return {"columns": _columns(t)}


# ---------------------------------------------------------------- base tables

BT_FIELDS = {"database", "table", "ip_column", "seen_at_column", "enabled", "note"}
BT_REQUIRED = {"database", "table", "ip_column", "seen_at_column"}
UNCHECKED = {"status": "unchecked", "checked_at": None, "table_format": "unknown", "write_pattern": "unknown",
             "last_write_at": None, "rows_estimate": None, "valid_ipv4_pct": None, "scan_gb_per_run": None,
             "problems": []}


def _shape_bt(item):
    v = dict(UNCHECKED, **(item.get("validation") or {}))
    for k in ("rows_estimate", "valid_ipv4_pct", "scan_gb_per_run"):
        v[k] = _num(v.get(k))
    return {"id": item["sk"], "database": item.get("database"), "table": item.get("table"),
            "ip_column": item.get("ip_column"), "seen_at_column": item.get("seen_at_column"),
            "enabled": bool(item.get("enabled")), "note": item.get("note"), "validation": v,
            "created_at": item.get("created_at"), "updated_at": item.get("updated_at")}


def _check_bt_fields(body, partial):
    bad = set(body) - BT_FIELDS
    if bad:
        raise ApiError(400, "unknown field(s): " + ", ".join(sorted(bad)))
    if not partial:
        missing = BT_REQUIRED - set(body)
        if missing:
            raise ApiError(400, "missing required field(s): " + ", ".join(sorted(missing)))
    for f in BT_REQUIRED & set(body):
        if not isinstance(body[f], str) or not _NAME.match(body[f]):
            raise ApiError(400, "%s must be a catalog name (lowercase letters, digits, underscores)" % f)
    if body.get("database") in PROJECT_DATABASES:
        raise ApiError(400, "ipintel_curated is the pipeline's own output and cannot be a base table")
    if "enabled" in body and not isinstance(body["enabled"], bool):
        raise ApiError(400, "enabled must be true or false")
    if body.get("note") is not None and not isinstance(body["note"], str):
        raise ApiError(400, "note must be text")


def _check_catalog(item):
    t = _glue_table(item["database"], item["table"])
    if not t:
        raise ApiError(400, "no table %s.%s in the catalog" % (item["database"], item["table"]))
    cols = {c["name"] for c in _columns(t)}
    for f in ("ip_column", "seen_at_column"):
        if item[f] not in cols:
            raise ApiError(400, "%s.%s has no column '%s'" % (item["database"], item["table"], item[f]))


def list_input_tables():
    items = [_shape_bt(i) for i in _query("base_table")]
    return {"count": len(items), "input_tables": items}


def get_input_table(bt_id):
    item = _get("base_table", bt_id)
    if not item:
        raise ApiError(404, "no base table '%s'" % bt_id)
    return _shape_bt(item)


def create_input_table(body):
    bt_id = body.pop("id", None)
    if not isinstance(bt_id, str) or not _ID.match(bt_id):
        raise ApiError(400, "id must be lowercase letters, digits and underscores")
    _check_bt_fields(body, partial=False)
    item = {"pk": "base_table", "sk": bt_id, "enabled": body.get("enabled", True), "note": body.get("note"),
            "created_at": _now(), "updated_at": _now(), "validation": dict(UNCHECKED)}
    item.update({f: body[f] for f in BT_REQUIRED})
    _check_catalog(item)
    same = [b["sk"] for b in _query("base_table")
            if (b.get("database"), b.get("table")) == (item["database"], item["table"])]
    if same:
        raise ApiError(409, "%s.%s is already the base table '%s'" % (item["database"], item["table"], same[0]))
    try:
        _state.put_item(Item=_dyn(item), ConditionExpression="attribute_not_exists(sk)")
    except _state.meta.client.exceptions.ConditionalCheckFailedException:
        raise ApiError(409, "base table '%s' already exists" % bt_id)
    _audit("create_base_table", bt_id, item)
    return _shape_bt(item)


def _enabled_count(excluding=None):
    return sum(1 for b in _query("base_table") if b.get("enabled") and b["sk"] != excluding)


def update_input_table(bt_id, body):
    item = _get("base_table", bt_id)
    if not item:
        raise ApiError(404, "no base table '%s'" % bt_id)
    body.pop("id", None)
    if not body:
        raise ApiError(400, "no writable fields supplied")
    _check_bt_fields(body, partial=True)
    if body.get("enabled") is False and item.get("enabled") and _enabled_count(excluding=bt_id) == 0:
        raise ApiError(409, "This is the last enabled base table. Add or enable another before switching it off.")
    merged = dict(item, **body)
    identity_changed = any(body.get(f) not in (None, item.get(f)) for f in BT_REQUIRED)
    if identity_changed:
        _check_catalog(merged)
        # A different table or column is a different input: check it again and read it from the start.
        # Reading from the start is safe, the daily job only keeps addresses it has not seen.
        merged["validation"] = dict(item.get("validation") or UNCHECKED, status="stale")
        merged.pop("watermark_snapshot_id", None)
        merged.pop("watermark_at", None)
    merged["updated_at"] = _now()
    _state.put_item(Item=_dyn(merged))
    _audit("update_base_table", bt_id, body)
    out = _shape_bt(merged)
    out["validation_stale"] = identity_changed
    return out


def delete_input_table(bt_id):
    item = _get("base_table", bt_id)
    if not item:
        raise ApiError(404, "no base table '%s'" % bt_id)
    if item.get("enabled") and _enabled_count(excluding=bt_id) == 0:
        raise ApiError(409, "This is the last enabled base table. Add or enable another before removing it.")
    _state.delete_item(Key={"pk": "base_table", "sk": bt_id})
    _audit("delete_base_table", bt_id, item)
    return {"deleted": bt_id,
            "note": "Addresses already collected from %s.%s stay in the IP tables." % (item["database"], item["table"])}


def validate_input_table(bt_id):
    if not _get("base_table", bt_id):
        raise ApiError(404, "no base table '%s'" % bt_id)
    try:
        r = _lambda.invoke(FunctionName=JOBS["free-daily"], InvocationType="RequestResponse",
                           Payload=json.dumps({"action": "validate", "id": bt_id}).encode())
    except _lambda.exceptions.TooManyRequestsException:
        raise ApiError(409, "The daily job is running right now. Validate again when it finishes.")
    if r.get("FunctionError"):
        raise ApiError(502, "Validation could not run: " + r["Payload"].read().decode("utf-8", "replace")[:300])
    _audit("validate_base_table", bt_id, {})
    return get_input_table(bt_id)["validation"]


# ---------------------------------------------------------------- jobs

def _shape_run(r):
    if not r:
        return None
    status = r.get("status")
    message = r.get("message")
    if status == "running" and r.get("started_at"):
        started = datetime.datetime.strptime(r["started_at"], "%Y-%m-%dT%H:%M:%SZ")
        if datetime.datetime.utcnow() - started > datetime.timedelta(minutes=RUN_STALE_MINUTES):
            status, message = "failed", "The run stopped without finishing (Lambda time limit or crash)."
    out = {"run_id": r.get("run_id"), "status": status, "started_at": r.get("started_at"),
           "finished_at": r.get("finished_at"), "message": message, "trigger": r.get("trigger"),
           "new_ips": _num(r.get("new_ips")), "rows_inserted": _num(r.get("rows_inserted")),
           "rows_added": _num(r.get("rows_added")), "rows_updated": _num(r.get("rows_updated")),
           "checks": [{"name": c.get("name"), "passed": bool(c.get("passed")), "detail": c.get("detail")}
                      for c in r.get("checks") or []]}
    if r.get("pk") == "run#free-daily":
        q = r.get("queued_for_proxycheck") or {}
        out.update(queued_for_proxycheck=sum(_num(v) or 0 for v in q.values()), queued_by_reason=q)
    if r.get("pk") == "run#proxycheck-daily":
        out.update(batches_done=_num(r.get("batches_done")), batches_total=_num(r.get("batches_total")),
                   queries_spent=_num(r.get("queries_spent")), queue_waiting=_num(r.get("queue_waiting")))
    if r.get("pk") == "run#publish-unified":
        out.update(source_run=r.get("source_run"),
                   published=[{"table": t.get("table"), "rows": _num(t.get("rows")), "files": _num(t.get("files")),
                               "samples_checked": _num(t.get("samples_checked")), "dry_run": bool(t.get("dry_run"))}
                              for t in r.get("published") or []])
    return out


def _next_run(schedule_utc, enabled):
    if not enabled or not schedule_utc or not _HHMM.match(schedule_utc):
        return None
    h, m = map(int, schedule_utc.split(":"))
    now = datetime.datetime.utcnow()
    nxt = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if nxt <= now:
        nxt += datetime.timedelta(days=1)
    return nxt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _budget_cap(cfg):
    return max(0, int(_num(cfg.get("daily_limit")) or 0) - int(_num(cfg.get("live_reserve")) or 0))


def _shape_job(cfg):
    job_id = cfg["sk"]
    last = _query("run#" + job_id, limit=1, newest_first=True)
    out = {"id": job_id, "name": cfg.get("name") or job_id, "description": cfg.get("description") or "",
           "enabled": bool(cfg.get("enabled")), "schedule_utc": cfg.get("schedule_utc"),
           "next_run_at": _next_run(cfg.get("schedule_utc"), cfg.get("enabled")),
           "last_run": _shape_run(last[0] if last else None)}
    if job_id == "proxycheck-daily":
        out.update(daily_budget=_num(cfg.get("daily_budget")) or 0, budget_cap=_budget_cap(cfg),
                   topup_utc=cfg.get("topup_utc"), topup_keep=_num(cfg.get("topup_keep")),
                   daily_limit=_num(cfg.get("daily_limit")), live_reserve=_num(cfg.get("live_reserve")),
                   publish_unified=bool(cfg.get("publish_unified", True)))
    return out


def list_jobs():
    jobs = [j for j in _query("job") if j["sk"] in JOBS]
    return {"jobs": [_shape_job(j) for j in sorted(jobs, key=lambda j: list(JOBS).index(j["sk"]))]}


def _sync_schedule(job_id, enabled, schedule_utc):
    """Keep the EventBridge schedule in step with the job. Missing schedule: the job flag alone decides."""
    try:
        s = _scheduler.get_schedule(Name=SCHEDULES[job_id])
    except _scheduler.exceptions.ResourceNotFoundException:
        return False
    h, m = schedule_utc.split(":")
    kw = {k: s[k] for k in ("Name", "Target", "FlexibleTimeWindow") if k in s}
    for k in ("GroupName", "Description", "ScheduleExpressionTimezone", "ActionAfterCompletion"):
        if s.get(k):
            kw[k] = s[k]
    kw["ScheduleExpression"] = "cron(%d %d * * ? *)" % (int(m), int(h))
    kw["State"] = "ENABLED" if enabled else "DISABLED"
    _scheduler.update_schedule(**kw)
    return True


def update_job(job_id, body):
    cfg = _get("job", job_id)
    if job_id not in JOBS or not cfg:
        raise ApiError(404, "no job '%s'" % job_id)
    allowed = {"enabled", "schedule_utc"} | ({"daily_budget"} if job_id == "proxycheck-daily" else set())
    bad = set(body) - allowed
    if bad:
        raise ApiError(400, "unknown or read-only field(s): " + ", ".join(sorted(bad)))
    if not body:
        raise ApiError(400, "no writable fields supplied")
    if "enabled" in body and not isinstance(body["enabled"], bool):
        raise ApiError(400, "enabled must be true or false")
    if "schedule_utc" in body and not (isinstance(body["schedule_utc"], str) and _HHMM.match(body["schedule_utc"])):
        raise ApiError(400, "schedule_utc must be HH:MM in UTC")
    if "daily_budget" in body:
        b = body["daily_budget"]
        cap = _budget_cap(cfg)
        if not isinstance(b, int) or isinstance(b, bool) or b < 0:
            raise ApiError(400, "daily_budget must be a whole number of queries, 0 or more")
        if b > cap:
            raise ApiError(400, "daily_budget can be at most %d a day, so live lookups always have queries left" % cap)
    fields = dict(body)
    names = {"#f%d" % i: k for i, k in enumerate(fields)}
    values = {":v%d" % i: v for i, v in enumerate(fields.values())}
    _state.update_item(Key={"pk": "job", "sk": job_id},
                       UpdateExpression="SET " + ", ".join("%s = %s" % nv for nv in zip(names, values)),
                       ExpressionAttributeNames=names, ExpressionAttributeValues=values)
    if "enabled" in body or "schedule_utc" in body:
        _sync_schedule(job_id, body.get("enabled", bool(cfg.get("enabled"))),
                       body.get("schedule_utc", cfg.get("schedule_utc") or "07:30"))
    _audit("update_job", job_id, body)
    return _shape_job(_get("job", job_id))


def run_job(job_id):
    if job_id not in JOBS or not _get("job", job_id):
        raise ApiError(404, "no job '%s'" % job_id)
    if get_safety()["paused"]:
        raise ApiError(409, "The pipeline is paused. Resume it on the Safety page.")
    last = _query("run#" + job_id, limit=1, newest_first=True)
    shaped = _shape_run(last[0] if last else None)
    if shaped and shaped["status"] == "running":
        raise ApiError(409, "Already running")
    run_id = "%s-%s-ui%s" % (job_id, datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S"), str(int(time.time() * 1000))[-4:])
    _lambda.invoke(FunctionName=JOBS[job_id], InvocationType="Event",
                   Payload=json.dumps({"trigger": "manual", "run_id": run_id}).encode())
    _audit("run_job", job_id, {"run_id": run_id})
    return {"run_id": run_id, "status": "running"}


def list_runs(job_id, q):
    if job_id not in JOBS:
        raise ApiError(404, "no job '%s'" % job_id)
    try:
        limit = max(1, min(int(q.get("limit") or 30), 100))
    except ValueError:
        raise ApiError(400, "limit must be a number")
    return {"runs": [_shape_run(r) for r in _query("run#" + job_id, limit=limit, newest_first=True)]}


# ---------------------------------------------------------------- publish to unified

def get_publish(q):
    """Read only. When unified.ip_geo and unified.ip_intelligence were last refreshed from ipintel_curated."""
    try:
        limit = max(1, min(int(q.get("limit") or 10), 50))
    except ValueError:
        raise ApiError(400, "limit must be a number")
    st = _get("publish", "unified") or {}
    return {"tables": ["unified.ip_geo", "unified.ip_intelligence"],
            "last_published_at": st.get("last_published_at"), "last_run_id": st.get("last_run_id"),
            "last_tables": [{"table": t.get("table"), "rows": _num(t.get("rows"))} for t in st.get("tables") or []],
            "runs": [_shape_run(r) for r in _query("run#publish-unified", limit=limit, newest_first=True)]}


# ---------------------------------------------------------------- quota

def get_quota():
    cfg = _get("job", "proxycheck-daily") or {}
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    counter = _get("quota", today) or {}
    out = {"plan_tier": cfg.get("plan_tier") or "unknown", "daily_limit": _num(cfg.get("daily_limit")) or 0,
           "reserved_today": _num(counter.get("reserved")) or 0, "provider_reported_today": 0,
           "live_lookup_reserve": _num(cfg.get("live_reserve")) or 0,
           "batch_budget": _num(cfg.get("daily_budget")) or 0, "key_status": "missing", "as_of": _now()}
    try:
        key = _sm.get_secret_value(SecretId=cfg.get("key_secret") or "ipintel/proxycheck")["SecretString"].strip()
    except Exception:
        return out
    try:
        req = urllib.request.Request("https://proxycheck.io/dashboard/export/usage/?key=" + urllib.parse.quote(key),
                                     headers={"User-Agent": USER_AGENT})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read())
    except (urllib.error.URLError, TimeoutError, ValueError):
        out["key_status"] = cfg.get("key_status") or "valid"
        return out
    if "Daily Limit" not in d:
        out["key_status"] = "invalid"
        return out
    out.update(key_status="valid", plan_tier=d.get("Plan Tier") or out["plan_tier"],
               daily_limit=int(str(d["Daily Limit"]).replace(",", "")),
               provider_reported_today=int(str(d.get("Queries Today", 0)).replace(",", "")))
    return out


# ---------------------------------------------------------------- router

def route(method, path, body, q):
    """Returns (status, body) for a control path, or None when the path is not a control path."""
    parts = [p for p in path.split("/") if p]
    if not parts or parts[0] not in ("safety", "input-tables", "catalog", "jobs", "quota", "publish"):
        return None
    try:
        head = parts[0]
        if head == "safety":
            if parts == ["safety"] and method == "GET":
                return 200, get_safety()
            if parts == ["safety", "pause"] and method == "POST":
                return 200, pause(body)
            if parts == ["safety", "resume"] and method == "POST":
                return 200, resume(body)
        elif head == "publish" and parts == ["publish"] and method == "GET":
            return 200, get_publish(q)
        elif head == "quota" and parts == ["quota"] and method == "GET":
            return 200, get_quota()
        elif head == "catalog" and method == "GET" and len(parts) == 2:
            if parts[1] == "databases":
                return 200, catalog_databases()
            if parts[1] == "tables":
                return 200, catalog_tables(q)
            if parts[1] == "columns":
                return 200, catalog_columns(q)
        elif head == "input-tables":
            if len(parts) == 1:
                if method == "GET":
                    return 200, list_input_tables()
                if method == "POST":
                    return 201, create_input_table(body)
            elif len(parts) == 2:
                if method == "GET":
                    return 200, get_input_table(parts[1])
                if method in ("PATCH", "PUT"):
                    return 200, update_input_table(parts[1], body)
                if method == "DELETE":
                    return 200, delete_input_table(parts[1])
            elif len(parts) == 3 and parts[2] == "validate" and method == "POST":
                return 200, validate_input_table(parts[1])
        elif head == "jobs":
            if len(parts) == 1 and method == "GET":
                return 200, list_jobs()
            if len(parts) == 2 and method in ("PATCH", "PUT"):
                return 200, update_job(parts[1], body)
            if len(parts) == 3 and parts[2] == "run" and method == "POST":
                return 202, run_job(parts[1])
            if len(parts) == 3 and parts[2] == "runs" and method == "GET":
                return 200, list_runs(parts[1], q)
        return 405, {"error": "method %s is not supported on %s" % (method, path)}
    except ApiError as e:
        return e.code, {"error": str(e)}
