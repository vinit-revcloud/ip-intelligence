"""Athena-backed serving for the four per-IP tables.

The previous implementation read a whole table's JSON export from S3 into Lambda
memory on every request. That works at 14,735 rows and cannot work at the ~34M
rows the full 4.96M-IP backfill produces, so the per-IP tables are now read
through Athena instead. The two vendor-overview tables stay on the JSON path:
they are 7 and 4 rows, and a 2-second Athena round trip to fetch 7 rows would be
a downgrade.

Two pagination modes, and every response carries both:

  offset  Stateless and simple. Each page is a fresh execution, so a deep offset
          re-scans everything before it. Capped at MAX_OFFSET for that reason.
  cursor  Pages through one already-completed execution. No new scan, no wait,
          typically under 100 ms. This is what a client should use past page one.

A single execution is capped at MAX_ROWS. Past that the response sets
`truncated: true` rather than silently serving a partial table, because a report
built on a silently truncated result is worse than no report. Anyone who needs
the whole 34M rows should query Athena directly, which is what that access is
for.

Nothing from the request is ever concatenated into SQL unvalidated. Every filter
is declared in TABLES with a validator, the value must match that validator, and
it is then single-quote-escaped as a second line of defence. A heredoc mangled
an IPv4 regex during the benchmark and a vendor silently returned zero rows for
a whole run; SQL assembled from unchecked strings is the same class of bug.
"""
import base64
import re
import time

import boto3

athena = boto3.client("athena")

WORKGROUP = "ipintel"          # enforced workgroup: output location is fixed there
_PAGE = 1_000                  # GetQueryResults refuses MaxResults above this
MAX_ROWS = 50_000              # hard ceiling on one execution
MAX_OFFSET = 100_000           # past this, offset paging costs more than it returns
DEFAULT_LIMIT = 2_000
MAX_LIMIT = 5_000
POLL_BUDGET_S = 45             # Lambda timeout is 60s; leave room to serialise
REUSE_MINUTES = 60             # identical query within the hour returns free and instant; short enough
                               # that pages show each daily run the same morning

_IPV4 = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
                   r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
_TEXT = re.compile(r"^[A-Za-z0-9 .,'\-]{1,80}$")
_BOOL = {"true": "true", "false": "false", "null": None}

_BOOLS_INTEL = ["is_proxy", "is_vpn", "is_tor", "is_datacenter", "is_bot",
                "is_compromised", "is_scraper", "is_anonymous"]


def _f(col, kind):
    return {"col": col, "kind": kind}


TABLES = {
    "ip-geo": {
        "db": None, "table": "ip_geo",
        "order": ["ip_address", "vendor"],
        "filters": {"ip": _f("ip_address", "ipv4"), "vendor": _f("vendor", "slug"),
                    "state": _f("state", "text"), "city": _f("city", "text"),
                    "zip": _f("zip_code", "text")},
    },
    "ip-geo-analytics": {
        "db": None, "table": "ip_geo_analytics",
        "order": ["ip_address", "vendor"],
        "filters": {"ip": _f("ip_address", "ipv4"), "vendor": _f("vendor", "slug"),
                    "has_answer": _f("has_answer", "bool")},
    },
    "ip-intelligence": {
        "db": None, "table": "ip_intelligence",
        "order": ["ip_address", "vendor"],
        "filters": dict({"ip": _f("ip_address", "ipv4"), "vendor": _f("vendor", "slug")},
                        **{b: _f(b, "bool") for b in _BOOLS_INTEL}),
    },
    "ip-intelligence-analytics": {
        "db": None, "table": "ip_intelligence_analytics",
        "order": ["ip_address", "vendor"],
        "filters": {"ip": _f("ip_address", "ipv4"), "vendor": _f("vendor", "slug"),
                    "has_answer": _f("has_answer", "bool"), "flagged": _f("flagged", "bool"),
                    "is_masked_device": _f("is_masked_device", "bool"),
                    "verdict_class": _f("verdict_class", "slug")},
    },
    # Only in ipintel_curated, so the same in shadow and live mode.
    "ip-resolved": {
        "db": "ipintel_curated", "table": "ip_resolved",
        "order": ["ip_address"],
        "filters": dict({"ip": _f("ip_address", "ipv4"), "geo_status": _f("geo_status", "slug"),
                         "proxy_status": _f("proxy_status", "slug"), "flagged": _f("flagged", "bool"),
                         "state": _f("state", "text"), "city": _f("city", "text"), "zip": _f("zip_code", "text")},
                        **{b: _f(b, "bool") for b in _BOOLS_INTEL}),
    },
    "proxycheck-queue": {
        "db": "ipintel_curated", "table": "proxycheck_queue",
        "order": ["queued_at", "ip_address"],
        "filters": {"ip": _f("ip_address", "ipv4"), "reason": _f("reason", "slug"), "outcome": _f("outcome", "slug")},
    },
    "ip-occurrences": {
        "db": "ipintel_curated", "table": "ip_occurrences",
        "order": ["ip_address", "base_table"],
        "filters": {"ip": _f("ip_address", "ipv4"), "base_table": _f("base_table", "slug")},
    },
}

# Reserved query-string keys that are not column filters.
_CONTROL = {"limit", "offset", "cursor", "query_id", "count"}


class BadRequest(Exception):
    pass


def _cur_out(token):
    """Athena's page tokens are raw base64 and carry '+', '/' and '='.

    Handed back as-is they break the moment a client puts one in a query string:
    the '+' decodes to a space and the token is rejected as malformed. Re-encode
    to base64url so the value survives any client that forgets to escape it.
    """
    if not token:
        return None
    return base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")


def _cur_in(value):
    pad = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + pad).decode()
    except Exception:
        # A caller that passes a correctly-escaped raw Athena token still works.
        return value


def _lit(value):
    """Single-quoted SQL literal. Validators run first; this is defence in depth."""
    return "'" + str(value).replace("'", "''") + "'"


def _predicate(spec, raw):
    col, kind = spec["col"], spec["kind"]
    if kind == "ipv4":
        if not _IPV4.match(raw):
            raise BadRequest(f"{col} must be a dotted-quad IPv4 address")
        return f"{col} = {_lit(raw)}"
    if kind == "slug":
        if not _SLUG.match(raw):
            raise BadRequest(f"{col} must be lowercase letters, digits and underscores")
        return f"{col} = {_lit(raw)}"
    if kind == "text":
        if not _TEXT.match(raw):
            raise BadRequest(f"{col} contains characters that are not allowed in a filter")
        return f"lower({col}) = lower({_lit(raw)})"
    if kind == "bool":
        key = raw.strip().lower()
        if key not in _BOOL:
            raise BadRequest(f"{col} must be true, false or null")
        # NULL is a real third state here - "the vendor never answered" - so asking
        # for it has to compile to IS NULL, never to = false.
        return f"{col} IS NULL" if _BOOL[key] is None else f"{col} = {_BOOL[key]}"
    raise BadRequest(f"no validator for {col}")


def _database(spec):
    """The four per-vendor tables follow the mode: ipintel_curated when live, the frozen unified copy in
    shadow. Tables that exist only in ipintel_curated name it directly."""
    if spec["db"]:
        return spec["db"]
    import lookup
    return "ipintel_curated" if lookup.read_mode() == "live" else "unified"


def build_sql(name, params):
    """Return (sql, where_count, parsed_paging). Raises BadRequest on bad input."""
    spec = TABLES[name]
    unknown = set(params) - _CONTROL - set(spec["filters"])
    if unknown:
        allowed = sorted(set(spec["filters"]) | _CONTROL)
        raise BadRequest(f"unknown parameter(s): {', '.join(sorted(unknown))}. "
                         f"allowed: {', '.join(allowed)}")

    where = [_predicate(spec["filters"][k], v)
             for k, v in params.items() if k in spec["filters"] and v not in (None, "")]

    try:
        limit = int(params.get("limit", DEFAULT_LIMIT))
        offset = int(params.get("offset", 0))
    except (TypeError, ValueError):
        raise BadRequest("limit and offset must be integers")
    if limit < 1:
        raise BadRequest("limit must be at least 1")
    limit = min(limit, MAX_LIMIT)
    if offset < 0:
        raise BadRequest("offset must not be negative")
    if offset > MAX_OFFSET:
        raise BadRequest(f"offset above {MAX_OFFSET:,} is not supported. Narrow the filters, "
                         f"or page with next_cursor which has no depth limit")

    # count(*) OVER () gives the exact matched total in the same pass, but it forces
    # Athena to materialise every matching row and so defeats the ORDER BY ... LIMIT
    # top-N optimisation. Cheap when a filter narrows the scan, expensive across 34M
    # rows, so it is automatic only when filtered and otherwise opt-in.
    want_count = bool(where) or str(params.get("count", "")).lower() == "true"
    cols = "*, count(*) OVER () AS _matched" if want_count else "*"

    sql = (f"SELECT {cols} FROM {_database(spec)}.{spec['table']}"
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY " + ", ".join(spec["order"])
           + f" LIMIT {MAX_ROWS}")
    return sql, want_count, {"limit": limit, "offset": offset}


def _cast(value, kind):
    """Athena hands back every cell as text. Rebuild the real JSON type.

    A NULL arrives as a missing VarCharValue and must stay None: the boolean
    columns are tri-state and collapsing NULL to false would turn "this vendor
    never answered" into "this vendor said no".
    """
    if value is None:
        return None
    k = kind.lower()
    if k == "boolean":
        return value == "true"
    if k in ("tinyint", "smallint", "integer", "int", "bigint"):
        try:
            return int(value)
        except ValueError:
            return value
    if k in ("float", "real", "double", "decimal"):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _shape(result, skip_header):
    """Turn an Athena GetQueryResults payload into rows, and pull out _matched."""
    meta = result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
    names = [c["Name"] for c in meta]
    kinds = [c["Type"] for c in meta]
    raw = result["ResultSet"]["Rows"]
    if skip_header:
        raw = raw[1:]

    rows, matched = [], None
    for r in raw:
        data = r.get("Data", [])
        rec = {}
        for i, name in enumerate(names):
            cell = data[i] if i < len(data) else {}
            rec[name] = _cast(cell.get("VarCharValue"), kinds[i])
        if "_matched" in rec:
            matched = rec.pop("_matched")
        rows.append(rec)
    return rows, matched


def _page_rows(qid, token, first, want):
    """Read up to `want` rows from a finished execution.

    GetQueryResults refuses MaxResults above 1000, so a 5,000-row page is five
    calls, not one. Only the very first page of an execution carries a header
    row, which is why `first` has to travel with the token.

    Returns (rows, matched, next_token, first).
    """
    out, matched = [], None
    while len(out) < want:
        n = min(_PAGE, (want - len(out)) + (1 if first else 0))
        kw = {"QueryExecutionId": qid, "MaxResults": n}
        if token:
            kw["NextToken"] = token
        res = athena.get_query_results(**kw)
        rows, m = _shape(res, skip_header=first)
        if m is not None:
            matched = m
        out.extend(rows)
        first = False
        token = res.get("NextToken")
        if not token:
            break
    return out, matched, token, first


def _run(sql, deadline):
    """Start a query and wait for it. Returns the execution id or raises TimeoutError."""
    qid = athena.start_query_execution(
        QueryString=sql,
        WorkGroup=WORKGROUP,
        ResultReuseConfiguration={"ResultReuseByAgeConfiguration":
                                  {"Enabled": True, "MaxAgeInMinutes": REUSE_MINUTES}},
    )["QueryExecutionId"]

    delay = 0.15
    while time.time() < deadline:
        ex = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = ex["Status"]["State"]
        if state == "SUCCEEDED":
            stats = ex.get("Statistics", {})
            return qid, {
                "scanned_bytes": stats.get("DataScannedInBytes", 0),
                "elapsed_ms": stats.get("TotalExecutionTimeInMillis", 0),
                "reused": bool(stats.get("ResultReuseInformation", {}).get("ReusedPreviousResult")),
            }
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(ex["Status"].get("StateChangeReason", state))
        time.sleep(delay)
        delay = min(delay * 1.5, 1.5)

    athena.stop_query_execution(QueryExecutionId=qid)
    raise TimeoutError(qid)


def serve(name, params):
    """Handle one /tables/{name} request. Returns (status_code, body)."""
    deadline = time.time() + POLL_BUDGET_S
    cursor = params.get("cursor")
    qid = params.get("query_id")

    # --- cursor mode: page an execution that already ran. No scan, no wait. ---
    if cursor:
        if not qid:
            return 400, {"error": "cursor requires the query_id it was issued with"}
        try:
            limit = min(max(int(params.get("limit", DEFAULT_LIMIT)), 1), MAX_LIMIT)
        except (TypeError, ValueError):
            return 400, {"error": "limit must be an integer"}
        try:
            rows, matched, next_token, _ = _page_rows(qid, _cur_in(cursor), False, limit)
        except athena.exceptions.InvalidRequestException as e:
            return 400, {"error": "cursor is not valid for this query_id", "detail": str(e)}
        return 200, {"table": name, "rows": rows, "count": len(rows), "total": matched,
                     "limit": limit, "query_id": qid,
                     "next_cursor": _cur_out(next_token), "offset": None,
                     "next_offset": None, "mode": "cursor"}

    # --- offset mode: fresh execution. ---
    try:
        sql, want_count, page = build_sql(name, params)
    except BadRequest as e:
        return 400, {"error": str(e)}

    try:
        qid, stats = _run(sql, deadline)
    except TimeoutError as e:
        return 504, {"error": "query did not finish in time", "query_id": str(e),
                     "hint": "retry with query_id and cursor once it completes, "
                             "or narrow the filters"}
    except RuntimeError as e:
        return 502, {"error": "athena rejected the query", "detail": str(e)}

    limit, offset = page["limit"], page["offset"]

    # Athena pages the result set by token, not by row number, so reaching an
    # offset means reading and discarding everything before it. That is exactly
    # why MAX_OFFSET exists and why cursor mode is the one to use past page one.
    token, first, matched = None, True, None
    if offset:
        _, matched, token, first = _page_rows(qid, None, True, offset)
    rows, m, next_token, _ = _page_rows(qid, token, first, limit)
    if m is not None:
        matched = m

    body = {
        "table": name,
        "rows": rows,
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "next_offset": (offset + limit) if next_token else None,
        "next_cursor": _cur_out(next_token),
        "query_id": qid,
        "mode": "offset",
        "scanned_bytes": stats["scanned_bytes"],
        "elapsed_ms": stats["elapsed_ms"],
        "cached": stats["reused"],
    }
    if want_count:
        # count(*) OVER () rides on the rows, so a filter that matches nothing carries no count at all.
        # No rows on the first page means nothing matched: that is 0, not unknown.
        if matched is None and not rows and not offset:
            matched = 0
        body["total"] = matched
        body["truncated"] = bool(matched is not None and matched > MAX_ROWS)
    else:
        body["total"] = None
        body["total_note"] = ("exact match count is omitted on unfiltered reads because it "
                              "forces a full scan. add count=true to compute it")
        body["truncated"] = None
    if body.get("truncated"):
        body["truncated_note"] = (f"{matched:,} rows match but one execution returns at most "
                                  f"{MAX_ROWS:,}. narrow the filters, or query Athena directly")
    return 200, body
