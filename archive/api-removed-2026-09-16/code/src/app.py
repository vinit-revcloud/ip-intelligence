import json, os, re, time, urllib.request, urllib.error, decimal
import boto3

import athena_tables
import bulk
import control
import lookup

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb").Table(os.environ.get("SOURCES_TABLE", "ipintel-sources"))

BKT = os.environ["FINDINGS_BUCKET"]
# The two scorecards are 4 and 3 rows. The daily jobs export them after every run, so they are served
# from those files instead of a 2-second Athena round trip.
OVERVIEW_KEYS = {
  "vendor-overview-geo":   "ip-intelligence/serving/ipintel_curated/tbl_vendor_overview_geo.json",
  "vendor-overview-proxy": "ip-intelligence/serving/ipintel_curated/tbl_vendor_overview_proxy.json",
}
OVERVIEW_TTL_S = 60
# Report files the daily jobs rebuild after every run (aggregates only; no lead or address data).
REPORT_KEYS = {
  "/accuracy/geo": "ip-intelligence/serving/ipintel_curated/geo_accuracy.json",
  "/coverage":     "ip-intelligence/serving/ipintel_curated/enrichment_coverage.json",
}
TOKEN = os.environ["API_TOKEN"]
_IPV4 = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
                   r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$")
_cache = {}

# Fields a client may set. Anything else in the body is rejected, so the UI can never
# invent a column and quietly diverge from what the pipeline reads.
WRITABLE = {"company", "product", "kind", "cost_model", "plan", "limit", "capabilities",
            "probe_type", "probe_target", "credential_ref", "enabled", "owner", "note", "url",
            "cost_per_1k", "paid_tier"}
REQUIRED = {"company", "product", "kind", "capabilities"}
KINDS = {"database", "api", "internal_feed", "validator"}
CAPS = {"geo", "risk", "asn", "validator"}


class DecEnc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _overview(name):
    hit = _cache.get(name)
    if not hit or hit[0] < time.time() - OVERVIEW_TTL_S:
        hit = (time.time(), json.loads(s3.get_object(Bucket=BKT, Key=OVERVIEW_KEYS[name])["Body"].read()))
        _cache[name] = hit
    return hit[1]


def _report(path):
    hit = _cache.get(path)
    if not hit or hit[0] < time.time() - OVERVIEW_TTL_S:
        hit = (time.time(), json.loads(s3.get_object(Bucket=BKT, Key=REPORT_KEYS[path])["Body"].read()))
        _cache[path] = hit
    return hit[1]


def _resp(code, body):
    return {"statusCode": code,
            "headers": {"content-type": "application/json",
                        "cache-control": "no-store" if code >= 400 else "max-age=30"},
            "body": json.dumps(body, cls=DecEnc)}


def _sources():
    items = ddb.scan().get("Items", [])
    return sorted(items, key=lambda x: (not x.get("enabled", False), x.get("id", "")))


def _validate(body, partial=False):
    bad = set(body) - WRITABLE
    if bad:
        return f"unknown field(s): {', '.join(sorted(bad))}"
    if not partial:
        missing = REQUIRED - set(body)
        if missing:
            return f"missing required field(s): {', '.join(sorted(missing))}"
    if "kind" in body and body["kind"] not in KINDS:
        return f"kind must be one of {sorted(KINDS)}"
    if "capabilities" in body:
        c = body["capabilities"]
        if not isinstance(c, list) or not c:
            return "capabilities must be a non-empty list"
        badc = set(c) - CAPS
        if badc:
            return f"unknown capabilities: {sorted(badc)}"
    if body.get("credential_ref") and not str(body["credential_ref"]).startswith("ipintel/"):
        return "credential_ref must be a Secrets Manager name under ipintel/ - never a raw key"
    return None


def _diagnose(src):
    """Probe a source and report whether it is actually reachable right now."""
    t0 = time.time()
    ptype = src.get("probe_type")
    target = src.get("probe_target")
    out = {"id": src["id"], "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "probe_type": ptype, "probe_target": target}
    try:
        if ptype == "http":
            req = urllib.request.Request(target, headers={"User-Agent": "ipintel-diagnose/1.0"})
            try:
                r = urllib.request.urlopen(req, timeout=12)
                code, sample = r.getcode(), r.read(400).decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                code, sample = e.code, e.read(200).decode("utf-8", "replace")
            ok = 200 <= code < 300
            out.update(status="healthy" if ok else "failed", http_status=code,
                       detail=("reachable" if ok else f"HTTP {code}"), sample=sample[:300])
            if code in (401, 403):
                # A source that needs a key is not broken - it is unconfigured. Saying
                # "failed" here would cry wolf every time this runs.
                if src.get("credential_ref"):
                    out.update(status="needs_credential",
                               detail=f"HTTP {code} - requires the secret at {src['credential_ref']}")
                else:
                    out.update(status="failed", detail=f"HTTP {code} - access rejected")
        elif ptype == "file":
            b, _, p = target.replace("s3://", "").partition("/")
            r = s3.list_objects_v2(Bucket=b, Prefix=p, MaxKeys=5)
            n = r.get("KeyCount", 0)
            out.update(status="healthy" if n else "failed", objects=n,
                       detail=f"{n} object(s) at prefix" if n else "prefix is empty")
        elif ptype == "athena":
            out.update(status="healthy", detail=f"table {target} is the source of record")
        else:
            out.update(status="unknown", detail="no probe configured for this source")
    except Exception as e:
        out.update(status="failed", detail=f"{type(e).__name__}: {e}")
    out["latency_ms"] = int((time.time() - t0) * 1000)
    ddb.update_item(Key={"id": src["id"]},
                    UpdateExpression="SET last_diagnosis=:d, diagnosis_status=:s, updated_at=:u",
                    ExpressionAttributeValues={":d": json.dumps(out, cls=DecEnc),
                                               ":s": out["status"], ":u": out["checked_at"]})
    return out


def handler(event, context):
    hdrs = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if hdrs.get("authorization") != f"Bearer {TOKEN}":
        return _resp(401, {"error": "unauthorized"})

    method = (event.get("requestContext", {}).get("http", {}).get("method") or "GET").upper()
    path = (event.get("rawPath") or "/").rstrip("/") or "/"
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "body is not valid JSON"})
    if not isinstance(body, dict):
        return _resp(400, {"error": "body must be a JSON object"})

    # ---------- pipeline control: safety, base tables, catalog, jobs, quota ----------
    routed = control.route(method, path, body, event.get("queryStringParameters") or {})
    if routed:
        return _resp(*routed)

    # ---------- source registry ----------
    if path == "/sources":
        if method == "GET":
            items = _sources()
            return _resp(200, {"count": len(items), "sources": items})
        if method == "POST":
            sid = body.pop("id", None)
            if not sid:
                return _resp(400, {"error": "id is required"})
            if ddb.get_item(Key={"id": sid}).get("Item"):
                return _resp(409, {"error": f"source '{sid}' already exists"})
            err = _validate(body)
            if err:
                return _resp(400, {"error": err})
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            item = {"id": sid, "enabled": body.get("enabled", True), "created_at": now,
                    "updated_at": now, "diagnosis_status": "unknown", **body}
            ddb.put_item(Item=item)
            return _resp(201, {"created": sid, "source": item,
                               "next": f"POST /sources/{sid}/diagnose to verify reachability"})
        return _resp(405, {"error": "use GET or POST"})

    if path.startswith("/sources/"):
        rest = path[len("/sources/"):]
        if rest.endswith("/diagnose"):
            sid = rest[:-len("/diagnose")]
            item = ddb.get_item(Key={"id": sid}).get("Item")
            if not item:
                return _resp(404, {"error": f"no source '{sid}'"})
            return _resp(200, _diagnose(item))
        sid = rest
        item = ddb.get_item(Key={"id": sid}).get("Item")
        if method == "GET":
            return _resp(200, item) if item else _resp(404, {"error": f"no source '{sid}'"})
        if method in ("PATCH", "PUT"):
            if not item:
                return _resp(404, {"error": f"no source '{sid}'"})
            body.pop("id", None)
            err = _validate(body, partial=True)
            if err:
                return _resp(400, {"error": err})
            if not body:
                return _resp(400, {"error": "no writable fields supplied"})
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            names = {f"#f{i}": k for i, k in enumerate(body)}
            vals = {f":v{i}": v for i, v in enumerate(body.values())}
            expr = "SET " + ", ".join(f"{n}={v}" for n, v in zip(names, vals)) + ", updated_at=:u"
            vals[":u"] = now
            ddb.update_item(Key={"id": sid}, UpdateExpression=expr,
                            ExpressionAttributeNames=names, ExpressionAttributeValues=vals)
            changed = sorted(body)
            # Changing what a source IS invalidates its last diagnosis.
            needs = any(f in body for f in ("probe_target", "probe_type", "credential_ref", "enabled"))
            if needs:
                ddb.update_item(Key={"id": sid},
                                UpdateExpression="SET diagnosis_status=:s",
                                ExpressionAttributeValues={":s": "stale"})
            return _resp(200, {"updated": sid, "fields": changed,
                               "diagnosis": "stale - re-run diagnose" if needs else "unaffected",
                               "source": ddb.get_item(Key={"id": sid})["Item"]})
        if method == "DELETE":
            if not item:
                return _resp(404, {"error": f"no source '{sid}'"})
            ddb.delete_item(Key={"id": sid})
            return _resp(200, {"deleted": sid,
                               "note": "Historical observations from this source are retained in "
                                       "ipintel_curated; only the registry entry is removed."})
        return _resp(405, {"error": "use GET, PATCH or DELETE"})

    if path == "/diagnose":
        if method != "POST":
            return _resp(405, {"error": "use POST"})
        results = [_diagnose(s) for s in _sources() if s.get("enabled")]
        bad = [r for r in results if r["status"] != "healthy"]
        return _resp(200, {"checked": len(results), "healthy": len(results) - len(bad),
                           "failing": len(bad), "results": results})

    # ---------- live lookup ----------
    q = event.get("queryStringParameters") or {}

    if path == "/lookup":
        if method != "POST":
            return _resp(405, {"error": "use POST /lookup with {\"ips\": [...]}, or GET /lookup/{ip}"})
        code, out = bulk.serve(body)
        return _resp(code, out)

    if path.startswith("/lookup/"):
        if method != "GET":
            return _resp(405, {"error": "use GET"})
        ip = path[len("/lookup/"):]
        if not _IPV4.match(ip):
            return _resp(400, {"error": "not a dotted-quad IPv4 address", "ip": ip})
        code, out = lookup.serve(ip, refresh=str(q.get("refresh", "")).lower() == "true")
        return _resp(code, out)

    # ---------- tables ----------
    # The old benchmark sample files (/findings, /console, /summary, /recommendations, /ip/{ip},
    # /unified/*, the legacy table JSON) were removed on 15 September 2026: everything served now is
    # produced by the running pipeline.
    if method != "GET":
        return _resp(405, {"error": "read-only endpoint"})
    if path in ("/", "/health"):
        return _resp(200, {"ok": True, "mode": lookup.read_mode()})
    if path in REPORT_KEYS and method == "GET":
        try:
            return _resp(200, _report(path))
        except Exception as e:
            return _resp(503, {"error": "report file unavailable", "detail": type(e).__name__})
    if path.startswith("/tables/"):
        name = path[len("/tables/"):]
        if name in athena_tables.TABLES:
            code, out = athena_tables.serve(name, q)
            return _resp(code, out)
        if name in OVERVIEW_KEYS:
            try:
                d = _overview(name)
            except Exception as e:
                return _resp(503, {"error": "scorecard file unavailable", "detail": type(e).__name__})
            return _resp(200, {"table": name, "rows": d["rows"], "count": d["count"],
                               "total": d["count"], "limit": None, "offset": 0,
                               "next_offset": None, "next_cursor": None,
                               "backend": "json", "truncated": False})
    return _resp(404, {"error": "not found", "path": path,
                       "routes": ["GET /health", "GET /lookup/{ip}", "POST /lookup",
                                  "GET /accuracy/geo", "GET /coverage", "GET /tables/ip-geo", "GET /tables/ip-geo-analytics",
                                  "GET /tables/ip-intelligence", "GET /tables/ip-intelligence-analytics",
                                  "GET /tables/ip-resolved", "GET /tables/ip-occurrences",
                                  "GET /tables/vendor-overview-geo", "GET /tables/vendor-overview-proxy",
                                  "GET|POST /sources", "GET|PATCH|DELETE /sources/{id}",
                                  "POST /sources/{id}/diagnose", "POST /diagnose",
                                  "GET /safety", "POST /safety/pause", "POST /safety/resume",
                                  "GET|POST /input-tables", "GET|PATCH|DELETE /input-tables/{id}",
                                  "POST /input-tables/{id}/validate", "GET /catalog/databases",
                                  "GET /catalog/tables", "GET /catalog/columns", "GET /jobs",
                                  "PATCH /jobs/{id}", "POST /jobs/{id}/run", "GET /jobs/{id}/runs",
                                  "GET /quota"]})
