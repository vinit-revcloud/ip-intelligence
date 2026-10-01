"""Check that ipintel_curated.ip_resolved and GET /lookup/{ip} give the same answer.

Picks addresses of every status the API would answer from the tables alone (no proxycheck.io call, so
the check spends nothing), looks each one up through the API, and compares field by field.

usage: python compare_resolved.py <api_url_file> <api_token_file> [per_status]
"""
import json
import sys
import time
import urllib.request

import boto3

sess = boto3.Session(profile_name="ipintel-builder", region_name="us-west-2")
athena = sess.client("athena")


def query(sql):
    qid = athena.start_query_execution(QueryString=sql, WorkGroup="ipintel_etl")["QueryExecutionId"]
    while True:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if st["State"] != "SUCCEEDED":
        sys.exit(st.get("StateChangeReason"))
    res = athena.get_query_results(QueryExecutionId=qid, MaxResults=1000)["ResultSet"]
    names = [c["Name"] for c in res["ResultSetMetadata"]["ColumnInfo"]]
    return [dict(zip(names, [d.get("VarCharValue") for d in r["Data"]])) for r in res["Rows"][1:]]


url = open(sys.argv[1]).read().strip().rstrip("/")
token = open(sys.argv[2]).read().strip()
per = int(sys.argv[3]) if len(sys.argv) > 3 else 5

# Statuses the API answers without calling proxycheck: it already answered, or the vendors agree it is clean
# and a location exists.
rows = query(f"""
SELECT * FROM (
  SELECT r.*, row_number() OVER (PARTITION BY geo_status, proxy_status ORDER BY xxhash64(to_utf8(ip_address))) AS rn
  FROM ipintel_curated.ip_resolved r
  WHERE geo_status <> 'no_answer' AND proxy_status NOT IN ('no_answer', 'vendors_disagree', 'flagged_unconfirmed'))
WHERE rn <= {per}""")

GEO = [("geo_status", "status"), ("state", "state"), ("city", "city"), ("geo_decided_by", "decided_by"),
       ("geo_agreeing_vendors", "agreeing_vendors")]
PROXY = [("proxy_status", "status"), ("flagged", "flagged"), ("is_proxy", "is_proxy"), ("is_vpn", "is_vpn"),
         ("is_datacenter", "is_datacenter"), ("is_bot", "is_bot"), ("proxy_decided_by", "decided_by"),
         ("proxy_agreeing_vendors", "agreeing_vendors"), ("isp", "isp")]


def norm(v):
    if isinstance(v, list):
        return ",".join(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return "" if v is None else str(v)


same = differ = called = 0
for t in rows:
    ip = t["ip_address"]
    req = urllib.request.Request("%s/lookup/%s" % (url, ip), headers={"Authorization": "Bearer " + token})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if d["proxycheck"]["called"]:
        called += 1
    diffs = []
    for side, pairs in (("geo", GEO), ("proxy", PROXY)):
        for tcol, acol in pairs:
            a, b = norm(t[tcol]), norm(d["resolved"][side][acol])
            if a != b:
                diffs.append("%s.%s table=%r api=%r" % (side, acol, a, b))
    if diffs:
        differ += 1
        srcs = sorted({r["table"].split(".")[0] for r in d["vendors"]["geo"] + d["vendors"]["proxy"]})
        print("DIFF %s (%s/%s, api read %s): %s" % (ip, t["geo_status"], t["proxy_status"], srcs, "; ".join(diffs)))
    else:
        same += 1
print("compared %d addresses: %d identical, %d different, proxycheck called %d times" % (len(rows), same, differ, called))
