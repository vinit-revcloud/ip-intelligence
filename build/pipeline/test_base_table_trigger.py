"""End-to-end check of the base-table path on real data.

Waits for raw_tune_clicks to receive a new load after --after (UTC ISO), runs Job A by hand (which starts
Job B when it succeeds), waits for both, then proves for every address Job A queued:
  1. it needed proxycheck.io by the shared rule (reason recorded),
  2. Job B sent it the same day and the queue row is closed,
  3. proxycheck.io's answer is in ip_intelligence and ip_geo, and ip_resolved now rests on it,
  4. a lookup through the API does not call proxycheck.io again.

usage: python test_base_table_trigger.py --after 2026-09-15T12:00:00Z <api_url_file> <api_token_file>
Read-only except for the two job runs, which are the normal pipeline.
"""
import json
import sys
import time
import urllib.request

import boto3
from boto3.dynamodb.conditions import Key

sess = boto3.Session(profile_name="ipintel-builder", region_name="us-west-2")
athena = sess.client("athena")
lam = sess.client("lambda")
state = sess.resource("dynamodb").Table("ipintel-pipeline-state")


def q(sql):
    qid = athena.start_query_execution(QueryString=sql, WorkGroup="ipintel_etl")["QueryExecutionId"]
    while True:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    if st["State"] != "SUCCEEDED":
        raise RuntimeError(st.get("StateChangeReason"))
    out, token = [], None
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        res = athena.get_query_results(**kw)
        cols = [c["Name"] for c in res["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
        data = res["ResultSet"]["Rows"][1:] if not token else res["ResultSet"]["Rows"]
        out += [dict(zip(cols, [d.get("VarCharValue") for d in r["Data"]])) for r in data]
        token = res.get("NextToken")
        if not token:
            return out


def say(*a):
    print(time.strftime("%H:%M:%SZ", time.gmtime()), *a, flush=True)


def latest_run(job, since):
    items = [i for i in state.query(KeyConditionExpression=Key("pk").eq("run#" + job), ScanIndexForward=False,
                                    Limit=10)["Items"] if i["sk"] >= since]
    return items


def wait_done(job, since, timeout=3000):
    end = time.time() + timeout
    while time.time() < end:
        items = latest_run(job, since)
        if items and items[0]["status"] != "running" and not (items[0].get("message") or "").startswith("Handed over"):
            return json.loads(json.dumps(items[0], default=lambda o: int(o) if o % 1 == 0 else float(o)))
        time.sleep(30)
    raise TimeoutError(job)


def main():
    after = sys.argv[sys.argv.index("--after") + 1]
    url = open(sys.argv[-2]).read().strip().rstrip("/")
    token = open(sys.argv[-1]).read().strip()

    say("waiting for a raw_tune_clicks load after", after)
    while True:
        r = q('SELECT CAST(committed_at AS varchar) AS at FROM raw."raw_tune_clicks$snapshots" ORDER BY committed_at DESC LIMIT 1')
        at = r[0]["at"].replace(" ", "T")[:19] + "Z"
        if at > after:
            say("tune load written at", at)
            break
        time.sleep(120)

    start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    lam.invoke(FunctionName="ipintel-free-daily", InvocationType="Event",
               Payload=json.dumps({"trigger": "manual", "run_id": "free-daily-trigger-test-" + start.replace(":", "")}).encode())
    a = wait_done("free-daily", start)
    say("Job A:", a["status"], a.get("message"), "| new_ips", a.get("new_ips"), "| queued", a.get("queued_for_proxycheck"),
        "| window from", a.get("queue_window_start"))
    for ch in a.get("checks", []):
        say("   ", "PASS" if ch["passed"] else "FAIL", ch["name"], ch.get("detail") or "")
    if a["status"] != "succeeded":
        say("RESULT: FAIL - Job A did not succeed")
        return
    queued = q("SELECT ip_address, reason FROM ipintel_curated.proxycheck_queue WHERE queued_by_run = '%s'" % a["run_id"])
    say("queue rows written by this run:", len(queued))
    if not queued:
        say("RESULT: nothing needed proxycheck.io in this load; the path ran but had no address to send")
        return

    b = wait_done("proxycheck-daily", start)
    say("Job B:", b["status"], b.get("message"), "| queue batches", b.get("queue_batches_added"),
        "| queries", b.get("queries_spent"), "| still waiting", b.get("queue_waiting"))
    for ch in b.get("checks", []):
        say("   ", "PASS" if ch["passed"] else "FAIL", ch["name"], ch.get("detail") or "")

    ids = ",".join("'%s'" % r["ip_address"] for r in queued)
    rows = q(f"""
SELECT q.ip_address, q.reason, q.outcome, q.answered_at,
       (SELECT count(*) FROM ipintel_curated.ip_intelligence i WHERE i.ip_address = q.ip_address AND i.vendor = 'proxycheck_io') AS pc_intel,
       (SELECT count(*) FROM ipintel_curated.ip_geo g WHERE g.ip_address = q.ip_address AND g.vendor = 'proxycheck_io') AS pc_geo,
       r.proxy_decided_by, r.proxy_status, r.geo_status
FROM ipintel_curated.proxycheck_queue q
LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = q.ip_address
WHERE q.ip_address IN ({ids})""")
    closed = [r for r in rows if r["answered_at"]]
    answered = [r for r in rows if r["outcome"] == "answered"]
    in_tables = [r for r in answered if r["pc_intel"] == "1" and r["pc_geo"] == "1" and r["proxy_decided_by"] == "proxycheck_io"]
    no_record = [r for r in rows if r["outcome"] == "no_record_from_proxycheck"]
    reasons = {}
    for r in rows:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    say("queued by reason:", reasons)
    say("closed:", len(closed), "of", len(rows), "| answered and in ip_intelligence + ip_geo + ip_resolved:", len(in_tables),
        "| proxycheck had no record:", len(no_record))

    sample = [r["ip_address"] for r in in_tables[:5]]
    calls = 0
    for ip in sample:
        req = urllib.request.Request("%s/lookup/%s" % (url, ip), headers={"Authorization": "Bearer " + token})
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
        calls += d["proxycheck"]["called"]
        say("   API", ip, "->", d["resolved"]["proxy"]["status"], "decided by", d["resolved"]["proxy"]["decided_by"],
            "| proxycheck called again:", d["proxycheck"]["called"])
    ok = (b["status"] == "succeeded" and len(closed) == len(rows) and len(in_tables) + len(no_record) == len(rows)
          and calls == 0)
    say("RESULT:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
