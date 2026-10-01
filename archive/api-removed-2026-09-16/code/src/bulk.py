"""Bulk lookup: POST /lookup with up to 1,000 addresses.

Same answers as GET /lookup/{ip}, for many addresses at once:
  1. The tables are read once for all addresses (three queries in parallel, not one per address).
  2. Each address is resolved with the same rules, and lookup.needs_proxycheck decides whether proxycheck.io
     is needed, exactly as for a single lookup.
  3. Every address that needs it goes to proxycheck.io in ONE request (proxycheck.io takes up to 1,000
     addresses per request). Queries are reserved in the shared daily counter first: the number of addresses
     plus 1% for addresses charged twice, topped up afterwards if more were.
  4. Answers are saved before they are used: one file the proxycheck job folds into the tables, and one per
     address so a repeat lookup is free at once.

Request body:
  {"ips": ["1.2.3.4", ...],      required, 1 to 1,000 dotted-quad IPv4 addresses (duplicates are merged)
   "proxycheck": true,           optional, false = answer from the tables only, never spend a query
   "refresh": false,             optional, true = ask proxycheck.io again even where it has answered
   "detail": "summary"}          optional, "full" adds every vendor's rows and the occurrences
"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import lookup as L

MAX_IPS = 1000
PC_BULK_TIMEOUT_S = 25


def _run_all(sql):
    """Like lookup._run, but reads every page of the result."""
    qid = L.athena.start_query_execution(QueryString=sql, WorkGroup=L.WORKGROUP)["QueryExecutionId"]
    deadline = time.time() + L.POLL_BUDGET_S
    delay = 0.12
    while time.time() < deadline:
        ex = L.athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        st = ex["Status"]["State"]
        if st == "SUCCEEDED":
            break
        if st in ("FAILED", "CANCELLED"):
            raise RuntimeError(ex["Status"].get("StateChangeReason", st))
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)
    else:
        raise TimeoutError(qid)
    out, token, first = [], None, True
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        res = L.athena.get_query_results(**kw)
        rows = L._rows(res) if first else L._rows({"ResultSet": {
            "ResultSetMetadata": res["ResultSet"]["ResultSetMetadata"],
            "Rows": [{}] + res["ResultSet"]["Rows"]}})
        out += rows
        first = False
        token = res.get("NextToken")
        if not token:
            return out


def _in_list(ips):
    return ", ".join(L._lit(ip) for ip in ips)


def _group(rows):
    by = {}
    for r in rows:
        by.setdefault(r.pop("ip_address"), []).append(r)
    return by


def _reserve_bulk(daily_limit, n):
    want = n + max(1, n // 100)
    return want if L._reserve(daily_limit, n=want) else 0


def _add_extra(n):
    if n > 0:
        L._state.update_item(Key={"pk": "quota", "sk": time.strftime("%Y-%m-%d", time.gmtime())},
                             UpdateExpression="ADD reserved :n, live_reserved :n", ExpressionAttributeValues={":n": n})


def _ask_bulk(key, ips):
    url = ("https://proxycheck.io/v2/?key=" + urllib.parse.quote(key) + "&vpn=3&asn=1&risk=1&seen=1&days=90")
    body = urllib.parse.urlencode({"ips": ",".join(ips)}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": L.USER_AGENT})
    d = json.loads(urllib.request.urlopen(req, timeout=PC_BULK_TIMEOUT_S).read())
    if d.get("status") not in ("ok", "warning"):
        raise RuntimeError(d.get("message") or "proxycheck status %s" % d.get("status"))
    return d, (d.get("message") if d.get("status") == "warning" else None)


def _save_all(answers, fetched):
    """One file for the proxycheck job to fold in, then one per address for instant repeat lookups."""
    day = time.strftime("%Y-%m-%d", time.gmtime(fetched))
    L._s3.put_object(Bucket=L.BUCKET, Key="%s/dt=%s/bulk-%d.json" % (L.LIVE_PREFIX, day, int(fetched * 1000)),
                     Body=json.dumps(answers).encode(), ContentType="application/json")

    def one(item):
        ip, raw = item
        L._s3.put_object(Bucket=L.BUCKET, Key=L._cache_key(ip), ContentType="application/json",
                         Body=json.dumps({"fetched_epoch": int(fetched), "raw": raw}).encode())
    with ThreadPoolExecutor(max_workers=32) as ex:
        list(ex.map(one, answers.items()))


def parse(body):
    """Validate the request. Returns (ips, options) or raises ValueError with a message for the caller."""
    ips = body.get("ips")
    if not isinstance(ips, list) or not ips:
        raise ValueError("ips must be a non-empty list of IPv4 addresses")
    bad = [ip for ip in ips if not isinstance(ip, str) or not L_IPV4.match(ip.strip())]
    if bad:
        raise ValueError("not dotted-quad IPv4 addresses: %s" % ", ".join(map(str, bad[:10])))
    seen, unique = set(), []
    for ip in (x.strip() for x in ips):
        if ip not in seen:
            seen.add(ip)
            unique.append(ip)
    if len(unique) > MAX_IPS:
        raise ValueError("at most %d distinct addresses per request; got %d" % (MAX_IPS, len(unique)))
    detail = body.get("detail", "summary")
    if detail not in ("summary", "full"):
        raise ValueError("detail must be summary or full")
    for k in ("proxycheck", "refresh"):
        if k in body and not isinstance(body[k], bool):
            raise ValueError("%s must be true or false" % k)
    return unique, {"use_proxycheck": body.get("proxycheck", True), "refresh": body.get("refresh", False),
                    "detail": detail}


import re  # noqa: E402
L_IPV4 = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$")


def serve(body):
    """Handle POST /lookup. Returns (status_code, body)."""
    t0 = time.time()
    try:
        ips, opt = parse(body)
    except ValueError as e:
        return 400, {"error": str(e)}
    safety, job = L._config()
    ins = _in_list(ips)
    try:
        with ThreadPoolExecutor(max_workers=3) as ex:
            fg = ex.submit(_run_all, "SELECT ip_address, 0 AS pref, %s FROM %s.ip_geo WHERE ip_address IN (%s)"
                           % (", ".join(L.GEO_COLS), L.CURATED, ins))
            fi = ex.submit(_run_all, "SELECT ip_address, 0 AS pref, %s FROM %s.ip_intelligence WHERE ip_address IN (%s)"
                           % (", ".join(L.INTEL_COLS), L.CURATED, ins))
            fo = ex.submit(_run_all, "SELECT ip_address, base_table, source_table, CAST(first_seen AS varchar) AS first_seen, "
                                     "CAST(last_seen AS varchar) AS last_seen, days_seen, rows_seen "
                                     "FROM %s.ip_occurrences WHERE ip_address IN (%s)" % (L.CURATED, ins))
            geo_by, intel_by, occ_by = _group(fg.result()), _group(fi.result()), _group(fo.result())
    except TimeoutError:
        return 504, {"error": "lookup timed out; retry, or send fewer addresses"}
    except RuntimeError as e:
        return 502, {"error": "athena rejected the lookup", "detail": str(e)}

    dbs = [L.CURATED]
    state = {}
    for ip in ips:
        geo_rows = L._one_per_vendor(geo_by.get(ip, []), dbs)
        intel_rows = L._one_per_vendor(intel_by.get(ip, []), dbs)
        state[ip] = {"geo_rows": geo_rows, "intel_rows": intel_rows, "in_tables": bool(geo_rows or intel_rows)}

    # Answers fetched live but not folded into the tables yet count as proxycheck's rows.
    no_pc = [ip for ip in ips if L.is_public(ip)
             and not any(r["vendor"] == "proxycheck_io" for r in state[ip]["intel_rows"])]
    with ThreadPoolExecutor(max_workers=32) as ex:
        cached = dict(zip(no_pc, ex.map(L._cached_answer, no_pc)))
    for ip, c in cached.items():
        if c:
            state[ip]["intel_rows"].append(L._intel_row(c["raw"], c["fetched_epoch"]))
            if not any(r["vendor"] == "proxycheck_io" for r in state[ip]["geo_rows"]):
                state[ip]["geo_rows"].append(L._geo_row(c["raw"], c["fetched_epoch"]))

    for ip in ips:
        s = state[ip]
        s["geo"], s["proxy"] = L.resolve_geo(s["geo_rows"]), L.resolve_proxy(s["intel_rows"])
        has_pc = any(r["vendor"] == "proxycheck_io" and r.get("is_proxy") is not None for r in s["intel_rows"])
        s["reason_code"] = L.needs_proxycheck(ip, s["in_tables"], s["geo"], s["proxy"], has_pc, opt["refresh"])
        s["pc"] = {"called": False, "reason_code": s["reason_code"], "reason": L.REASON_TEXT.get(s["reason_code"])}

    need = [ip for ip in ips if state[ip]["reason_code"]]
    summary = {"needed": len(need), "asked": 0, "answered": 0, "queries_reserved": 0, "error": None}
    if need and not opt["use_proxycheck"]:
        summary["error"] = "proxycheck was false in the request, so proxycheck.io was not called."
    elif need and safety.get("paused"):
        summary["error"] = "The pipeline is paused, so proxycheck.io was not called."
    elif need:
        secret = job.get("key_secret") or "ipintel/proxycheck"
        try:
            key = L._pc_key(secret)
        except Exception:
            key = None
            summary["error"] = "no proxycheck credential at %s" % secret
        reserved = _reserve_bulk(int(job.get("daily_limit") or 1000), len(need)) if key else 0
        if key and not reserved:
            summary["error"] = ("proxycheck.io daily limit reached: %d queries were needed and none were sent. "
                                "Retry with fewer addresses, or tomorrow." % len(need))
        elif key:
            summary.update(asked=len(need), queries_reserved=reserved)
            try:
                d, warning = _ask_bulk(key, need)
                fetched = time.time()
                answers = {ip: d[ip] for ip in need if isinstance(d.get(ip), dict)}
                both = sum(1 for raw in answers.values() if raw.get("proxy") == "yes" and raw.get("vpn") == "yes")
                _add_extra(len(need) + both - reserved)
                summary.update(answered=len(answers), queries_charged_estimate=len(need) + both)
                if warning:
                    summary["vendor_warning"] = warning
                try:
                    if answers:
                        _save_all(answers, fetched)
                    summary["saved"] = True
                except Exception as e:
                    summary.update(saved=False, save_error="%s: %s" % (type(e).__name__, e))
                for ip in need:
                    s, raw = state[ip], answers.get(ip)
                    if raw is None:
                        s["pc"]["error"] = "proxycheck.io returned no record for this address"
                        continue
                    s["intel_rows"] = [r for r in s["intel_rows"] if r["vendor"] != "proxycheck_io"] + [L._intel_row(raw, fetched)]
                    s["geo_rows"] = [r for r in s["geo_rows"] if r["vendor"] != "proxycheck_io"] + [L._geo_row(raw, fetched)]
                    s["geo"], s["proxy"] = L.resolve_geo(s["geo_rows"]), L.resolve_proxy(s["intel_rows"])
                    s["pc"].update(called=True, risk_score=raw.get("risk"), type=raw.get("type") or None)
            except Exception as e:
                summary["error"] = "%s: %s" % (type(e).__name__, e)
    if summary["error"]:
        for ip in need:
            state[ip]["pc"].setdefault("error", summary["error"])

    results = []
    for ip in ips:
        s = state[ip]
        occ = occ_by.get(ip, [])
        row = {"ip": ip, "public_address": L.is_public(ip), "found": bool(s["geo_rows"] or s["intel_rows"]),
               "in_tables": s["in_tables"], "seen_in_base_tables": bool(occ),
               "first_seen": min((o["first_seen"] for o in occ if o.get("first_seen")), default=None),
               "last_seen": max((o["last_seen"] for o in occ if o.get("last_seen")), default=None),
               "resolved": {"geo": s["geo"], "proxy": s["proxy"]}, "proxycheck": s["pc"]}
        if opt["detail"] == "full":
            row["vendors"] = {"geo": s["geo_rows"], "proxy": s["intel_rows"]}
            row["occurrences"] = occ
        results.append(row)
    return 200, {"count": len(results), "requested": len(body.get("ips") or []), "proxycheck": summary,
                 "results": results, "elapsed_ms": int((time.time() - t0) * 1000)}
