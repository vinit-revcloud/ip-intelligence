"""Wait for the newest run of a job to finish, then print its result. Usage: python watch_run.py free-daily [since_iso]"""
import boto3, json, sys, time
from boto3.dynamodb.conditions import Key
job = sys.argv[1]; since = sys.argv[2] if len(sys.argv) > 2 else ""
t = boto3.Session(profile_name="ipintel-builder", region_name="us-west-2").resource("dynamodb").Table("ipintel-pipeline-state")
end = time.time() + 1000
while time.time() < end:
    items = [i for i in t.query(KeyConditionExpression=Key("pk").eq("run#" + job), ScanIndexForward=False, Limit=5)["Items"]
             if i["sk"] >= since]
    if items and items[0].get("status") != "running":
        d = json.loads(json.dumps(items[0], default=lambda o: int(o) if o % 1 == 0 else float(o)))
        for k in ("sk","status","message","new_ips","rows_inserted","rows_added","rows_updated","batches_done","batches_total",
                  "queries_spent","changed_tables","scorecard_pools","notes","audit_events","geo_changes","intel_changes","rows_after"):
            if k in d and d[k] is not None: print("%-16s %s" % (k, json.dumps(d[k])))
        for ch in d.get("checks", []) or []:
            print("  %s %s%s" % ("PASS" if ch["passed"] else "FAIL", ch["name"], ("  -> " + ch["detail"]) if ch.get("detail") else ""))
        sys.exit(0)
    time.sleep(15)
print("still running after the wait")
