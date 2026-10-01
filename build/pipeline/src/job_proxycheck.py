"""Job B: ipintel-proxycheck-daily.

Sends addresses that have no proxycheck.io answer yet, 1,000 per request, up to the daily budget.

Why it cannot lose data, waste the key, or time out:
  * The day's selection is written once, as batch files. Every later run that day reuses them.
  * A batch counts as done only when its raw response file exists. That file is the one record of
    progress, and it is written before anything else happens with the answer.
  * Queries are reserved in a shared DynamoDB counter before each request. The reservation succeeds
    only if it stays inside the budget, and the live lookup reserves from the same counter.
  * When less than SAFETY_MARGIN_S of Lambda time is left, the job starts a fresh copy of itself and
    stops. Only one copy may run at a time (reserved concurrency 1).
"""
import datetime
import json
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

import accuracy
import app_export
import apply
import completeness
import coverage
import pcqueue
import publish
import resolved
import common as c
import vendors as v

JOB = "proxycheck-daily"
FUNCTION_NAMES = ["ipintel-free-daily", "ipintel-proxycheck-daily"]
BATCH = 1000
SAFETY_MARGIN_S = 180
MAX_HOPS = 30
APPLY_NEEDS_S = 600
ENDPOINT = "https://proxycheck.io/v2/?key=%s&vpn=3&asn=1&risk=1&seen=1&days=90"


class KeyRejected(Exception):
    pass


def _key(secret_name):
    return c.secrets.get_secret_value(SecretId=secret_name)["SecretString"].strip()


def usage(key):
    req = urllib.request.Request("https://proxycheck.io/dashboard/export/usage/?key=" + urllib.parse.quote(key),
                                 headers={"User-Agent": v.USER_AGENT})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    if "Daily Limit" not in d:
        raise KeyRejected(json.dumps(d)[:200])
    return {"plan_tier": d.get("Plan Tier"), "daily_limit": int(str(d["Daily Limit"]).replace(",", "")),
            "provider_reported_today": int(str(d.get("Queries Today", 0)).replace(",", ""))}


def reserve(date, n, budget, shared_cap):
    """Reserve n queries atomically. False means the budget or the shared daily cap is reached."""
    try:
        c.state.update_item(
            Key={"pk": "quota", "sk": date},
            UpdateExpression="SET reserved = if_not_exists(reserved, :z) + :n, "
                             "batch_reserved = if_not_exists(batch_reserved, :z) + :n, expires_at = :exp",
            ConditionExpression="(attribute_not_exists(reserved) OR reserved <= :shared) AND "
                                "(attribute_not_exists(batch_reserved) OR batch_reserved <= :budget)",
            ExpressionAttributeValues={":z": 0, ":n": n, ":shared": shared_cap - n, ":budget": budget - n,
                                       ":exp": int(time.time()) + 8 * 86400})
        return True
    except c.state.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def add_extra(date, n):
    if n:
        c.state.update_item(Key={"pk": "quota", "sk": date}, UpdateExpression="ADD reserved :n",
                            ExpressionAttributeValues={":n": n})


def ask(key, ips):
    body = urllib.parse.urlencode({"ips": ",".join(ips)}).encode()
    last = None
    for wait in (0, 5, 15, 30):
        time.sleep(wait)
        try:
            req = urllib.request.Request(ENDPOINT % urllib.parse.quote(key), data=body,
                                         headers={"User-Agent": v.USER_AGENT})
            raw = urllib.request.urlopen(req, timeout=90).read()
            d = json.loads(raw)
            status = d.get("status")
            if status in ("ok", "warning"):
                return raw, d
            if status in ("denied", "error"):
                raise KeyRejected(d.get("message") or status)
            last = "unexpected status %s" % status
        except KeyRejected:
            raise
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last = "%s: %s" % (type(e).__name__, e)
    raise RuntimeError("proxycheck did not answer after 4 attempts (%s)" % last)


def _acceptable_answer_check():
    """Every public address in the tables, whatever its age, should have an answer we can act on: FraudLogix
    decided, or proxycheck.io answered. IP2Proxy PX12 only lists known proxies, so it does not count. Queued
    addresses are in progress; addresses proxycheck.io has no record of are reported, not failed."""
    r = c.rows(f"""
WITH seen AS (SELECT DISTINCT ip_address FROM {c.DB}.ip_geo WHERE {c.public_ipv4_sql('ip_address')}),
ans AS (SELECT ip_address, count_if(vendor IN ('fraudlogix_tune', 'proxycheck_io') AND has_answer) AS n
        FROM {c.DB}.ip_intelligence_analytics GROUP BY ip_address),
q AS (SELECT ip_address, bool_or(answered_at IS NULL) AS waiting,
             bool_or(outcome = 'no_record_from_proxycheck') AS no_record
      FROM {pcqueue.QUEUE} GROUP BY ip_address)
SELECT count(*) AS ips, count_if(coalesce(a.n, 0) = 0) AS missing,
       count_if(coalesce(a.n, 0) = 0 AND (coalesce(q.waiting, false) OR coalesce(q.no_record, false))) AS missing_but_queued
FROM seen s LEFT JOIN ans a ON a.ip_address = s.ip_address LEFT JOIN q ON q.ip_address = s.ip_address""",
               timeout_s=300)[0]
    open_gap = r["missing"] - r["missing_but_queued"]
    return {"name": "Every public address has a FraudLogix or proxycheck.io answer (queued ones in progress)",
            "passed": open_gap == 0,
            "detail": "%d of %d public addresses have none (%d queued or with no record at proxycheck.io)" % (r["missing"], r["ips"],
                                                                                   r["missing_but_queued"])
                      if r["missing"] else "%d public addresses, all answered" % r["ips"]}


def _selection_sql(date, limit):
    return f"""
WITH have AS (SELECT DISTINCT ip_address FROM {c.DB}.ip_intelligence WHERE vendor = 'proxycheck_io'),
concl AS (
  SELECT ip_address,
         count_if(vendor = 'fraudlogix_tune' AND has_answer) AS fraudlogix_answered,
         count_if(has_answer) AS answered,
         count_if(has_answer AND flagged) AS flagged_by,
         count_if(has_answer AND flagged AND known_infrastructure) AS confirmed_by
  FROM {c.DB}.ip_intelligence_analytics WHERE vendor <> 'proxycheck_io' GROUP BY ip_address),
seen AS (SELECT ip_address, max(last_seen) AS last_seen FROM {c.DB}.ip_occurrences GROUP BY ip_address),
queued AS (SELECT DISTINCT ip_address FROM {pcqueue.QUEUE} WHERE answered_at IS NULL),
-- Addresses seen in experiment sessions (read only; the production table is never written).
experiment AS (SELECT DISTINCT session_ip AS ip_address FROM unified.unified_session_summary
               WHERE nullif(experiment_id, '') IS NOT NULL AND nullif(session_ip, '') IS NOT NULL),
ranked AS (
  SELECT g.ip_address, g.created_at, s.last_seen, (qu.ip_address IS NOT NULL) AS is_queued,
         (ex.ip_address IS NOT NULL) AS in_experiment,
         (coalesce(k.fraudlogix_answered, 0) = 0) AS no_acceptable_answer,
         CASE WHEN coalesce(k.answered, 0) = 0 THEN 'no_answer'
              WHEN k.flagged_by > 0 AND k.flagged_by < k.answered THEN 'vendors_disagree'
              WHEN k.flagged_by > 0 AND k.confirmed_by = 0 THEN 'flagged_unconfirmed'
              WHEN k.flagged_by > 0 THEN 'flagged_confirmed'
              ELSE 'clean_by_vendors' END AS conclusion
  FROM {c.DB}.ip_geo g
  LEFT JOIN have h ON h.ip_address = g.ip_address
  LEFT JOIN concl k ON k.ip_address = g.ip_address
  LEFT JOIN seen s ON s.ip_address = g.ip_address
  LEFT JOIN queued qu ON qu.ip_address = g.ip_address
  LEFT JOIN experiment ex ON ex.ip_address = g.ip_address
  WHERE g.vendor = 'ip2location_db11' AND h.ip_address IS NULL
    AND {c.public_ipv4_sql('g.ip_address')})
SELECT ip_address, CASE WHEN is_queued THEN 'queued_from_base_tables' ELSE conclusion END AS conclusion FROM ranked
ORDER BY is_queued DESC,
         (substr(created_at, 1, 10) = {c.lit(date)}) DESC,
         -- Owner's rule (18 Sep): every unresolved address first. These have no acceptable answer at all:
         -- FraudLogix never decided and proxycheck.io was never asked (IP2Proxy only lists known proxies, so
         -- its silence is not an answer).
         no_acceptable_answer DESC,
         -- Within each group, recent addresses first: reporting uses the last 30 and 90 days.
         (last_seen >= date_add('day', -30, date {c.lit(date)})) DESC NULLS LAST,
         (last_seen >= date_add('day', -90, date {c.lit(date)})) DESC NULLS LAST,
         in_experiment DESC,
         -- Then addresses no other vendor answered, so every address ends up with at least one proxy answer.
         (conclusion IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed')) DESC,
         CASE conclusion WHEN 'vendors_disagree' THEN 1 WHEN 'flagged_unconfirmed' THEN 2 WHEN 'no_answer' THEN 3 ELSE 4 END,
         last_seen DESC NULLS LAST, ip_address
LIMIT {limit}"""


def _plan(date, cfg, budget):
    prefix = "%s/proxycheck/plan/dt=%s/" % (c.PREFIX, date)
    manifest_key = prefix + "manifest.json"
    if c.s3_exists(manifest_key):
        return c.s3_get_json(manifest_key)
    # Order of asking:
    #   0. addresses queued from the base tables
    #   1. addresses first seen today
    #   1b. every address seen in the base tables in the last 30 days that proxycheck.io has not answered
    #   2. addresses the other vendors leave without a conclusion (no answer, disagreement, or a flag
    #      nothing confirms), seen in the last 90 days, then older ones
    #   3. addresses every answering vendor calls clean, most recently seen first
    # About 1% of addresses are charged twice (proxy and VPN), so 1% of the budget is kept for that.
    picked = c.rows(_selection_sql(date, budget * 100 // 101), timeout_s=300)
    ips = [r["ip_address"] for r in picked]
    by_conclusion = {}
    for r in picked:
        by_conclusion[r["conclusion"]] = by_conclusion.get(r["conclusion"], 0) + 1
    batches = []
    for i in range(0, len(ips), BATCH):
        key = prefix + "batch-%05d.json" % (i // BATCH + 1)
        c.s3_put_json(key, ips[i:i + BATCH])
        batches.append(key)
    manifest = {"date": date, "created_at": c.now_iso(), "addresses": len(ips), "by_conclusion": by_conclusion,
                "batches": batches}
    c.s3_put_json(manifest_key, manifest)
    return manifest


def _queue_batches(date, manifest):
    """Queued base-table addresses not in today's batches yet, as extra batches sent before the rest.
    Runs on every copy of the job, so addresses queued after today's plan was made still go out today."""
    waiting = [r["ip_address"] for r in c.rows(pcqueue.waiting_sql() + " AND " + c.public_ipv4_sql("q.ip_address"),
                                                timeout_s=300)]
    if not waiting:
        return []
    planned = set()
    for b in manifest["batches"]:
        planned.update(c.s3_get_json(b))
    new = [ip for ip in waiting if ip not in planned]
    if not new:
        return []
    prefix = "%s/proxycheck/plan/dt=%s/" % (c.PREFIX, date)
    stamp = time.strftime("%H%M%S", time.gmtime())
    added = []
    for i in range(0, len(new), BATCH):
        key = prefix + "batch-q%s-%03d.json" % (stamp, i // BATCH + 1)
        c.s3_put_json(key, new[i:i + BATCH])
        added.append(key)
    manifest["batches"] = manifest["batches"] + added
    manifest["queue_batches"] = manifest.get("queue_batches", []) + added
    c.s3_put_json("%smanifest.json" % prefix, manifest)
    return added


def _topup_batches(date, manifest, n):
    """Late in the day, the part of the live-lookup reserve nobody used goes to the backfill: the next n
    addresses in the same order, skipping any already in today's batches."""
    planned = set()
    for b in manifest["batches"]:
        planned.update(c.s3_get_json(b))
    picked = [r["ip_address"] for r in c.rows(_selection_sql(date, n + len(planned)), timeout_s=600)
              if r["ip_address"] not in planned][:n]
    if not picked:
        return []
    prefix = "%s/proxycheck/plan/dt=%s/" % (c.PREFIX, date)
    stamp = time.strftime("%H%M%S", time.gmtime())
    added = []
    for i in range(0, len(picked), BATCH):
        key = prefix + "batch-t%s-%03d.json" % (stamp, i // BATCH + 1)
        c.s3_put_json(key, picked[i:i + BATCH])
        added.append(key)
    manifest["batches"] = manifest["batches"] + added
    manifest["topup_batches"] = manifest.get("topup_batches", []) + added
    c.s3_put_json("%smanifest.json" % prefix, manifest)
    return added


def _response_key(batch_key):
    return batch_key.replace("/plan/", "/responses/")


def _applied_key(batch_key):
    return batch_key.replace("/plan/", "/applied/")


LIVE_DAYS = 7


def _live_pending(date):
    """Answers the live lookup saved in the last LIVE_DAYS days that are not in the tables yet.

    The API only saves the raw answer and appends one row to pc_live. Folding it into the Iceberg tables
    happens here, through the same tested merge, so the API never races a job on a large table write.
    Re-applying a file is harmless: the merge is an upsert.
    """
    d0 = datetime.date.fromisoformat(date)
    out = []
    for i in range(LIVE_DAYS):
        prefix = "%s/proxycheck/live/dt=%s/" % (c.PREFIX, (d0 - datetime.timedelta(days=i)).isoformat())
        token = None
        while True:
            kw = {"Bucket": c.BUCKET, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            page = c.s3.list_objects_v2(**kw)
            for o in page.get("Contents", []):
                marker = o["Key"].replace("/proxycheck/live/", "/proxycheck/live-applied/")
                if not c.s3_exists(marker):
                    out.append((o["Key"], marker))
            token = page.get("NextContinuationToken")
            if not token:
                break
    return out


def apply_saved(date, manifest, run_id, log_extra):
    pending = [(_response_key(b), _applied_key(b), b) for b in manifest["batches"]
               if c.s3_exists(_response_key(b)) and not c.s3_exists(_applied_key(b))]
    live = _live_pending(date)
    pending += [(key, marker, None) for key, marker in live]
    if not pending:
        return None
    now = c.now_iso()
    # Only queue batches can hold re-checks, so only their addresses are kept for closing queue rows.
    queue_keys = set(manifest.get("queue_batches", []))
    staging = c.Staging(run_id)
    try:
        # One response file at a time, straight to the staging folder: a 500,000-address chunk never has to
        # fit in memory at once (it ran out of 1 GB on 18 Sep when every row was held in a list).
        for n, (response_key, _, batch_key) in enumerate(pending):
            d = c.s3_get_json(response_key)
            intel, geo = [], []
            for ip in (c.s3_get_json(batch_key) if batch_key else list(d)):
                raw = d.get(ip)
                if batch_key in queue_keys:
                    log_extra.setdefault("sent_ips", []).append(ip)
                if isinstance(raw, dict):
                    intel.append(v.proxycheck_intel_row(ip, raw, now))
                    geo.append(v.proxycheck_geo_row(ip, raw, now))
                elif batch_key:
                    log_extra.setdefault("no_record_ips", []).append(ip)
            if intel:
                staging.put_ndjson("pc_intel", intel, part="part-%05d.json" % n)
                staging.put_ndjson("pc_geo", geo, part="part-%05d.json" % n)
            del d, intel, geo
        before = apply.table_counts()
        pre_geo, pre_intel = apply.latest_snapshot("ip_geo"), apply.latest_snapshot("ip_intelligence")
        ji = staging.json_table("pc_intel", v.INTEL_JSON_DDL)
        jg = staging.json_table("pc_geo", v.GEO_JSON_DDL)
        dedupe = "SELECT %s FROM (SELECT x.*, row_number() OVER (PARTITION BY ip_address, vendor ORDER BY seen_at DESC) AS rn FROM %s x) WHERE rn = 1"
        stg_intel = staging.ctas("intel", dedupe % (v.INTEL_COLS, ji))
        stg_geo = staging.ctas("geo", dedupe % (v.GEO_COLS, jg))
        ip_plan = apply.plan_changes(stg_intel, "ip_intelligence", apply.INTEL_FIELDS)
        g_plan = apply.plan_changes(stg_geo, "ip_geo", apply.GEO_FIELDS)
        apply.merge_intel(stg_intel)
        apply.merge_geo(stg_geo)
        apply.refresh_intel_analytics(stg_intel)
        apply.refresh_geo_analytics(stg_geo)
        filled = apply.fill_fraudlogix_from_proxycheck()   # empty FraudLogix rows take proxycheck.io's answer
        apply.refresh_flag_columns()                       # is_flagged / flagged_reason / bot_reason
        geo_vendors = v.scoreable(_enabled("geo"))
        geo_pool, geo_done = apply.refresh_geo_scorecard(staging, geo_vendors)
        proxy_pool, proxy_done = apply.refresh_proxy_scorecard(staging, _enabled("risk"))
        apply.export_scorecards()
        resolved_changed, resolved_rows = resolved.refresh(staging, now)
        checks, after = apply.assertions(before, None, stg_geo, stg_intel, pre_geo, pre_intel, [])
        checks += resolved.checks()
        checks.append(accuracy.export())
        checks.append(coverage.export())
        checks.append(_acceptable_answer_check())
        checks += completeness.export()
        checks += apply.flag_column_checks()
        failed = [x for x in checks if not x["passed"]]
        if not failed:
            for _, marker, _ in pending:
                c.s3_put_json(marker, {"applied_at": c.now_iso(), "run_id": run_id})
        notes = []
        for label, pool, done in (("location", geo_pool, geo_done), ("proxy", proxy_pool, proxy_done)):
            if not done:
                notes.append("%s scorecard kept as it was: only %d addresses were asked of every vendor on it, below %d"
                             % (label, pool, apply.MIN_SCORECARD_POOL))
        log_extra.update(rows_inserted=ip_plan["inserted"] + g_plan["inserted"],
                         rows_added=ip_plan["added"] + g_plan["added"],
                         rows_updated=ip_plan["updated"] + g_plan["updated"],
                         intel_changes=ip_plan, geo_changes=g_plan, rows_after=after, notes=notes,
                         scorecard_pools={"location": geo_pool, "proxy": proxy_pool},
                         resolved_changed=resolved_changed, resolved_rows=resolved_rows,
                         batches_applied=(len(pending) - len(live)) if not failed else 0,
                         live_answers_applied=len(live) if not failed else 0)
        return checks
    finally:
        staging.cleanup()


def _enabled(capability):
    items = c.boto3.resource("dynamodb", region_name=c.REGION).Table("ipintel-sources").scan().get("Items", [])
    return sorted(i["id"] for i in c.to_plain(items) if i.get("enabled") and capability in (i.get("capabilities") or []))


def handler(event, context):
    event = event or {}
    if event.get("action") == "app_export":
        return app_export.run(event.get("trigger", "manual"))
    if event.get("action") == "publish":
        return publish.handler(event, context)
    date = event.get("date") or c.today_utc()
    hop = int(event.get("hop", 0))
    run_id = event.get("run_id") or c.new_run_id(JOB)
    log = c.start_run(JOB, run_id, {"trigger": event.get("trigger", "manual"), "plan_date": date, "hop": hop})
    try:
        paused, _ = c.is_paused()
        if paused:
            return c.finish_run(log, "skipped", "The pipeline is paused. Resume it on the Safety page.")
        cfg = c.get_item("job", JOB) or {}
        if not cfg.get("enabled") and event.get("trigger") != "manual":
            return c.finish_run(log, "skipped", "This job is switched off.")
        perm = c.permission_check()
        if not c.record_safety([perm]):
            return c.finish_run(log, "failed", "Safety check failed before any work was done: " + (perm["detail"] or ""))

        key = _key(cfg.get("key_secret", "ipintel/proxycheck"))
        try:
            u = usage(key)
        except KeyRejected as e:
            c.update_item("job", JOB, key_status="invalid")
            return c.finish_run(log, "failed", "proxycheck rejected the key: %s" % e)
        live_reserve = int(cfg.get("live_reserve", 10000))
        shared_cap = u["daily_limit"]
        budget = max(0, min(int(cfg.get("daily_budget", 0)), u["daily_limit"] - live_reserve))
        # The owner also uses the key directly (live_reserve is kept for that). Queries proxycheck.io has counted
        # today that are not ours are theirs: enrichment gives way, so the day's total never passes the plan limit.
        ours_today = int((c.get_item("quota", date) or {}).get("reserved") or 0)
        others_today = max(0, u["provider_reported_today"] - ours_today)
        budget = max(0, min(budget, u["daily_limit"] - others_today))
        c.update_item("job", JOB, key_status="valid", plan_tier=u["plan_tier"], daily_limit=u["daily_limit"],
                      budget_cap=max(0, u["daily_limit"] - live_reserve))
        manifest = _plan(date, cfg, budget) if budget > 0 else {"batches": []}
        queue_added = _queue_batches(date, manifest) if budget > 0 else []
        total = len(manifest["batches"])
        # Queued base-table addresses may also use half of the live-lookup reserve, so a busy backfill day
        # never leaves them waiting until tomorrow.
        # queue_extra is set to 0 when the whole live reserve must stay free for API lookups.
        queue_budget = budget + int(cfg.get("queue_extra", live_reserve // 2))
        # Top-up run (scheduled late in the day): spend what is left of today's limit except topup_keep,
        # judged by the larger of our counter and proxycheck.io's own, so nothing is double counted.
        topup_keep = int(cfg.get("topup_keep", 2000))
        backfill = bool(event.get("max_addresses") or event.get("backfill"))
        topup_cap = max(0, u["daily_limit"] - topup_keep)
        topup_added = []
        if event.get("topup") and budget > 0 and hop == 0:   # a hand-over continues the batches already planned
            used_now = max(int((c.get_item("quota", date) or {}).get("reserved") or 0), u["provider_reported_today"])
            # The scheduled top-up only finishes the normal daily budget. Only a chunked backfill run (which
            # passes max_addresses) may go past it, so a plan upgrade can never trigger one giant unchunked run.
            cap = topup_cap if event.get("max_addresses") else min(topup_cap, budget)
            room = cap - used_now
            if room >= BATCH:
                n = room * 100 // 101
                # A large backfill runs in chunks (max_addresses), so each chunk is sent, merged and checked
                # before the next one starts, and a problem can never spread across millions of rows.
                if event.get("max_addresses"):
                    # batches already planned today but not yet sent count towards this chunk
                    pending = sum(1 for k in manifest["batches"] if not c.s3_exists(_response_key(k)))
                    n = min(n, max(0, int(event["max_addresses"]) - pending * BATCH))
                topup_added = _topup_batches(date, manifest, n) if n >= BATCH else []
        total = len(manifest["batches"])

        deadline = time.time() + context.get_remaining_time_in_millis() / 1000.0 - SAFETY_MARGIN_S
        spent, stopped, handed_over = 0, None, False
        queue_keys = set(manifest.get("queue_batches", []))
        topup_keys = set(manifest.get("topup_batches", []))
        for b in sorted(manifest["batches"], key=lambda k: (k in topup_keys, k not in queue_keys)):
            if c.s3_exists(_response_key(b)):
                continue
            if time.time() > deadline:
                if hop >= MAX_HOPS:
                    stopped = "reached %d hand-overs in one day" % MAX_HOPS
                    break
                c.lam.invoke(FunctionName=context.function_name, InvocationType="Event",
                             Payload=json.dumps({"date": date, "hop": hop + 1, "trigger": "hand-over", "topup": bool(event.get("topup")), "skip_publish": bool(event.get("skip_publish")), "backfill": backfill}).encode())
                handed_over = True
                break
            ips = c.s3_get_json(b)
            want = len(ips) + max(1, len(ips) // 100)       # a little extra for addresses charged twice
            if b in topup_keys or backfill:
                # A chunked backfill run (after a plan upgrade) may also send the day's queued and planned
                # batches out of the upgraded headroom; the owner's topup_keep is still left untouched.
                ok = reserve(date, want, topup_cap, topup_cap)
            else:
                ok = reserve(date, want, queue_budget if b in queue_keys else budget, shared_cap)
            if not ok:
                stopped = "daily budget reached"
                break
            try:
                raw, d = ask(key, ips)
            except KeyRejected as e:
                c.update_item("job", JOB, key_status="invalid")
                c.alert("IP pipeline: proxycheck rejected the key", str(e))
                stopped = "proxycheck rejected the key: %s" % e
                break
            c.s3.put_object(Bucket=c.BUCKET, Key=_response_key(b), Body=raw, ContentType="application/json")
            both = sum(1 for ip in ips if isinstance(d.get(ip), dict)
                       and d[ip].get("proxy") == "yes" and d[ip].get("vpn") == "yes")
            add_extra(date, max(0, both - (want - len(ips))))
            spent += len(ips) + both

        used = max(int((c.get_item("quota", date) or {}).get("reserved") or 0), u["provider_reported_today"])
        c.metric("QuotaUsedPct", 100.0 * used / max(1, u["daily_limit"]), JOB)
        if used >= 0.9 * u["daily_limit"]:
            c.alert("IP pipeline: proxycheck use passed 90% of the daily limit",
                    "%d of %d queries used today (%s)." % (used, u["daily_limit"], date))

        done = sum(1 for b in manifest["batches"] if c.s3_exists(_response_key(b)))
        extra = {"batches_done": done, "batches_total": total, "queries_spent": spent,
                 "queue_batches_added": len(queue_added), "topup_batches_added": len(topup_added),
                 "planned_by_conclusion": manifest.get("by_conclusion"),
                 "provider_reported_today": u["provider_reported_today"]}
        # The merge, analytics and scorecards take several minutes. Start them in a fresh copy with a full
        # time allowance rather than risk a timeout halfway through. Sent answers are already saved.
        if not handed_over and spent and time.time() + APPLY_NEEDS_S > deadline + SAFETY_MARGIN_S and hop < MAX_HOPS:
            c.lam.invoke(FunctionName=context.function_name, InvocationType="Event",
                         Payload=json.dumps({"date": date, "hop": hop + 1, "trigger": "hand-over", "topup": bool(event.get("topup")), "skip_publish": bool(event.get("skip_publish")), "backfill": backfill}).encode())
            handed_over = True
        if handed_over:
            return c.finish_run(log, "succeeded", "Handed over to a fresh copy to continue", **extra)

        if budget <= 0:
            stopped = "Daily budget is 0."
        elif total == 0:
            stopped = "Every address already has a proxycheck answer."
        checks = apply_saved(date, manifest, run_id, extra) or []
        qstage = c.Staging(run_id + "-queue")
        try:
            waiting = pcqueue.close(qstage, c.now_iso(), extra.pop("no_record_ips", []), extra.pop("sent_ips", []))
        finally:
            qstage.cleanup()
        extra["queue_waiting"] = waiting
        held = stopped if stopped and stopped != "Every address already has a proxycheck answer." else None
        checks.append({"name": "Every queued base-table address was sent to proxycheck.io",
                       "passed": waiting == 0 or bool(held),
                       "detail": None if waiting == 0 else "%d still waiting%s" % (waiting, ("; " + held) if held else "")})
        seen, findings, partial = c.activity_review(FUNCTION_NAMES, deadline=deadline - 60)
        c.record_safety([perm], seen, findings, partial)
        checks = [perm] + checks + [{"name": "Nothing outside the project was touched in the last 24 hours",
                                     "passed": not findings,
                                     "detail": "; ".join(findings[:5]) or ("review partial (%d events); the next run continues it" % seen if partial else None)}]
        extra["checks"], extra["audit_events"] = checks, seen
        failed = [x for x in checks if not x["passed"]]
        if failed:
            return c.finish_run(log, "failed", "%d assertion(s) failed; answers are saved and will be applied again next run" % len(failed), **extra)
        result = c.finish_run(log, "succeeded", stopped, **extra)
        # Refresh unified.ip_geo and unified.ip_intelligence from the tables just updated. A fresh copy of
        # this function does it (it waits for this run to end: reserved concurrency 1). Only after a run whose
        # every check passed, so a bad run never reaches the unified tables.
        if cfg.get("publish_unified", True) and not event.get("skip_publish"):   # skipped between backfill chunks
            c.lam.invoke(FunctionName=context.function_name, InvocationType="Event",
                         Payload=json.dumps({"action": "publish", "trigger": "after-proxycheck", "source_run": run_id}).encode())
        return result
    except Exception as e:
        traceback.print_exc()
        return c.finish_run(log, "failed", "%s: %s" % (type(e).__name__, str(e)[:900]))
