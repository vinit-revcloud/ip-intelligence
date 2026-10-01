"""Shared code for the two IP daily jobs.

Everything here runs as ipintel-pipeline-role. That role cannot write to any production table,
bucket or workgroup, and AWS enforces it. The checks below exist so a run notices a problem and
stops, not because the code is the only thing standing between the jobs and production.
"""
import datetime
import json
import os
import re
import time
import uuid
from decimal import Decimal

import boto3
import botocore.config
from boto3.dynamodb.conditions import Key

REGION = "us-west-2"
ACCOUNT = "221490242148"
BUCKET = "datalake-landingzone-221490242148-us-west-2"
PREFIX = "ip-intelligence"
DB = "ipintel_curated"
WORKGROUP = "ipintel_etl"
STATE_TABLE = "ipintel-pipeline-state"
TOPIC_ARN = f"arn:aws:sns:{REGION}:{ACCOUNT}:ipintel-alerts"
PIPELINE_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ipintel-pipeline-role"
DLQ_URL = f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/ipintel-proxycheck-dlq"

athena = boto3.client("athena", region_name=REGION)
glue = boto3.client("glue", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)
# CloudTrail LookupEvents allows 2 requests a second per account; a day of pipeline activity is ~100 pages.
cloudtrail = boto3.client("cloudtrail", region_name=REGION,
                          config=botocore.config.Config(retries={"max_attempts": 12, "mode": "adaptive"}))
cloudwatch = boto3.client("cloudwatch", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)
secrets = boto3.client("secretsmanager", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
state = boto3.resource("dynamodb", region_name=REGION).Table(STATE_TABLE)

_NAME = re.compile(r"^[a-z0-9_]{1,128}$")


# ---------------------------------------------------------------- small helpers

def now_iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def new_run_id(job):
    return "%s-%s-%s" % (job, datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S"), uuid.uuid4().hex[:6])


def ident(name):
    """A database, table or column name, quoted. Names that come from the UI are validated here,
    so nothing typed into a form can ever become SQL."""
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError("not a valid name: %r" % (name,))
    return '"%s"' % name


def lit(value):
    return "'" + str(value).replace("'", "''") + "'"


def to_plain(obj):
    """DynamoDB returns Decimals. Turn them back into ints and floats."""
    if isinstance(obj, list):
        return [to_plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


def to_dynamo(obj):
    if isinstance(obj, list):
        return [to_dynamo(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dynamo(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


# ---------------------------------------------------------------- Athena

class QueryFailed(Exception):
    pass


def run(sql, timeout_s=600):
    """Run one statement in the project's ETL workgroup and wait for it."""
    qid = athena.start_query_execution(
        QueryString=sql, WorkGroup=WORKGROUP,
        QueryExecutionContext={"Database": DB})["QueryExecutionId"]
    deadline = time.time() + timeout_s
    delay = 0.5
    while True:
        ex = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        st = ex["Status"]["State"]
        if st == "SUCCEEDED":
            stats = ex.get("Statistics", {})
            return qid, {"bytes": stats.get("DataScannedInBytes", 0),
                         "ms": stats.get("TotalExecutionTimeInMillis", 0)}
        if st in ("FAILED", "CANCELLED"):
            raise QueryFailed("%s: %s" % (st, ex["Status"].get("StateChangeReason", "")))
        if time.time() > deadline:
            athena.stop_query_execution(QueryExecutionId=qid)
            raise QueryFailed("timed out after %ds" % timeout_s)
        time.sleep(delay)
        delay = min(delay * 1.4, 3)


def _cast(value, kind):
    if value is None:
        return None
    k = kind.lower()
    if k == "boolean":
        return value == "true"
    if k in ("tinyint", "smallint", "integer", "int", "bigint"):
        return int(value)
    if k in ("double", "float", "real", "decimal"):
        return float(value)
    return value


def rows(sql, timeout_s=600):
    qid, _ = run(sql, timeout_s)
    out, token, first, names, kinds = [], None, True, None, None
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        res = athena.get_query_results(**kw)
        if names is None:
            meta = res["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            names = [c["Name"] for c in meta]
            kinds = [c["Type"] for c in meta]
        data = res["ResultSet"]["Rows"][1:] if first else res["ResultSet"]["Rows"]
        first = False
        for r in data:
            cells = r.get("Data", [])
            out.append({n: _cast((cells[i] if i < len(cells) else {}).get("VarCharValue"), kinds[i])
                        for i, n in enumerate(names)})
        token = res.get("NextToken")
        if not token:
            return out


def scalar(sql):
    r = rows(sql)
    return list(r[0].values())[0] if r else None


def table_exists(name):
    try:
        glue.get_table(DatabaseName=DB, Name=name)
        return True
    except glue.exceptions.EntityNotFoundException:
        return False


# ---------------------------------------------------------------- staging tables

class Staging:
    """Short-lived tables for one run, in ipintel_curated, removed at the end."""

    def __init__(self, run_id):
        self.run_id = re.sub(r"[^a-z0-9]", "_", run_id.lower())
        self.names = []

    def name(self, label):
        return "stg_%s_%s" % (self.run_id, label)

    def location(self, label):
        return "s3://%s/%s/staging/%s/%s/" % (BUCKET, PREFIX, self.run_id, label)

    def ctas(self, label, select_sql):
        n = self.name(label)
        run("CREATE TABLE %s.%s WITH (format='PARQUET', write_compression='SNAPPY', "
            "external_location='%s') AS %s" % (DB, n, self.location(label), select_sql))
        self.names.append(n)
        return "%s.%s" % (DB, n)

    def json_table(self, label, columns_ddl):
        """An external table over newline-delimited JSON files the job writes itself."""
        n = self.name(label)
        run("CREATE EXTERNAL TABLE %s.%s (%s) ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe' "
            "LOCATION '%s'" % (DB, n, columns_ddl, self.location(label)))
        self.names.append(n)
        return "%s.%s" % (DB, n)

    def put_ndjson(self, label, records, part="part-00000.json"):
        key = "%s/staging/%s/%s/%s" % (PREFIX, self.run_id, label, part)
        body = "\n".join(json.dumps(r) for r in records)
        s3.put_object(Bucket=BUCKET, Key=key, Body=body.encode("utf-8"))

    def cleanup(self):
        for n in self.names:
            try:
                run("DROP TABLE IF EXISTS %s.%s" % (DB, n))
            except Exception:
                pass
        delete_prefix("%s/staging/%s/" % (PREFIX, self.run_id))


NON_PUBLIC_RANGES = ["0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
                     "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
                     "203.0.113.0/24", "224.0.0.0/3"]


def public_ipv4_sql(col):
    """True when the address is outside every range in NON_PUBLIC_RANGES: private, carrier NAT, loopback,
    link-local, documentation, benchmarking, multicast and reserved addresses have no record at any vendor.
    The API's lookup.py tests the same list."""
    o = ["try_cast(split_part(%s, '.', %d) AS integer)" % (col, i) for i in (1, 2, 3)]
    return ("NOT (%(a)s IN (0, 10, 127) OR %(a)s >= 224 OR (%(a)s = 100 AND %(b)s BETWEEN 64 AND 127)"
            " OR (%(a)s = 169 AND %(b)s = 254) OR (%(a)s = 172 AND %(b)s BETWEEN 16 AND 31)"
            " OR (%(a)s = 192 AND %(b)s = 168) OR (%(a)s = 192 AND %(b)s = 0 AND %(c)s IN (0, 2))"
            " OR (%(a)s = 198 AND %(b)s IN (18, 19)) OR (%(a)s = 198 AND %(b)s = 51 AND %(c)s = 100)"
            " OR (%(a)s = 203 AND %(b)s = 0 AND %(c)s = 113))") % {"a": o[0], "b": o[1], "c": o[2]}


def sweep_staging(max_age_hours=3):
    """Drop staging tables and files a crashed or timed-out run left behind. Only tables named stg_* in
    ipintel_curated and older than max_age_hours: no run lasts longer than 15 minutes, so a table that old
    can never belong to a run still in progress. Returns the names dropped."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=max_age_hours)
    dropped, token = [], None
    while True:
        kw = {"DatabaseName": DB, "Expression": "stg_*"}
        if token:
            kw["NextToken"] = token
        page = glue.get_tables(**kw)
        for t in page["TableList"]:
            if t["Name"].startswith("stg_") and t["CreateTime"] < cutoff:
                run("DROP TABLE IF EXISTS %s.%s" % (DB, ident(t["Name"]).strip('"')))
                loc = (t.get("StorageDescriptor") or {}).get("Location", "")
                marker = "s3://%s/%s/staging/" % (BUCKET, PREFIX)
                if loc.startswith(marker):
                    run_dir = loc[len("s3://%s/" % BUCKET):].split("/")
                    delete_prefix("/".join(run_dir[:3]) + "/")
                dropped.append(t["Name"])
        token = page.get("NextToken")
        if not token:
            break
    return dropped


def delete_prefix(prefix):
    if not prefix.startswith(PREFIX + "/"):
        raise ValueError("refusing to delete outside the project folder: " + prefix)
    token = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        page = s3.list_objects_v2(**kw)
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": keys, "Quiet": True})
        if not page.get("IsTruncated"):
            return
        token = page["NextContinuationToken"]


def s3_exists(key):
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except s3.exceptions.ClientError:
        return False


def s3_put_json(key, obj):
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(obj).encode("utf-8"),
                  ContentType="application/json")


def s3_get_json(key):
    return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())


# ---------------------------------------------------------------- state

def get_item(pk, sk):
    return to_plain(state.get_item(Key={"pk": pk, "sk": sk}).get("Item"))


def put_item(item):
    state.put_item(Item=to_dynamo(item))


def update_item(pk, sk, **fields):
    names = {"#f%d" % i: k for i, k in enumerate(fields)}
    values = {":v%d" % i: to_dynamo(v) for i, v in enumerate(fields.values())}
    state.update_item(Key={"pk": pk, "sk": sk},
                      UpdateExpression="SET " + ", ".join("%s = %s" % (n, v) for n, v in zip(names, values)),
                      ExpressionAttributeNames=names, ExpressionAttributeValues=values)


def query(pk, limit=None, newest_first=False):
    kw = {"KeyConditionExpression": Key("pk").eq(pk),
          "ScanIndexForward": not newest_first}
    if limit:
        kw["Limit"] = limit
    return to_plain(state.query(**kw).get("Items", []))


# ---------------------------------------------------------------- safety

PRODUCTION_WRITES = [
    (["glue:UpdateTable", "glue:DeleteTable", "glue:CreateTable"],
     f"arn:aws:glue:{REGION}:{ACCOUNT}:table/unified/unified_session_summary"),
    (["glue:UpdateTable", "glue:DeleteTable"], f"arn:aws:glue:{REGION}:{ACCOUNT}:table/raw/raw_tune_clicks"),
    (["glue:UpdateTable", "glue:DeleteTable"], f"arn:aws:glue:{REGION}:{ACCOUNT}:table/unified/ip_geo"),
    (["glue:DeleteDatabase", "glue:UpdateDatabase"], f"arn:aws:glue:{REGION}:{ACCOUNT}:database/unified"),
    (["s3:PutObject", "s3:DeleteObject"],
     "arn:aws:s3:::datalake-unified-221490242148-us-west-2/unified_session_summary/data/x"),
    (["s3:PutObject", "s3:DeleteObject"], "arn:aws:s3:::datalake-raw-221490242148-us-west-2/tune/x"),
    (["s3:PutBucketNotification", "s3:PutLifecycleConfiguration"], f"arn:aws:s3:::{BUCKET}"),
    (["athena:StartQueryExecution"], f"arn:aws:athena:{REGION}:{ACCOUNT}:workgroup/primary"),
]


def permission_check():
    """Ask AWS whether this role could write to production. Every answer must be a refusal."""
    allowed = []
    for actions, resource in PRODUCTION_WRITES:
        res = iam.simulate_principal_policy(PolicySourceArn=PIPELINE_ROLE_ARN, ActionNames=actions,
                                            ResourceArns=[resource])
        for r in res["EvaluationResults"]:
            if r["EvalDecision"] == "allowed":
                allowed.append("%s on %s" % (r["EvalActionName"], resource))
    return {"name": "Pipeline cannot write to any production table", "passed": not allowed,
            "checked_at": now_iso(),
            "detail": ("AWS would allow: " + "; ".join(allowed)) if allowed else None}


ALLOWED_WRITE_TARGETS = ("ipintel_curated", "ipintel_etl", "ipintel-", "ipintel/", "ip-intelligence/")


def activity_review(session_names, hours=24, deadline=None):
    """Read CloudTrail for every call the jobs made. Any change aimed outside the project is a finding.

    Reads only what earlier reviews have not covered (at most `hours` back), oldest first, one hour at a time.
    After each hour is fully read, the audit mark (safety/state last_audit_at) moves to the end of that hour.
    If `deadline` (time.time()) comes first, the review stops and is partial: the next run carries on from the
    mark, so no event is ever skipped and a busy day (a big backfill) can never push a job past its limit.
    Returns (events seen, findings, partial)."""
    now = datetime.datetime.utcnow()
    start = now - datetime.timedelta(hours=hours)
    last = (get_item("safety", "state") or {}).get("last_audit_at")
    if last:
        try:
            start = max(start, datetime.datetime.strptime(last[:19], "%Y-%m-%dT%H:%M:%S") - datetime.timedelta(minutes=10))
        except ValueError:
            pass
    findings, seen, partial = [], 0, False
    w_start = start
    while w_start < now and not partial:
        w_end = min(w_start + datetime.timedelta(hours=1), now)
        for name in session_names:
            token = None
            while True:
                if deadline and time.time() > deadline:
                    partial = True
                    break
                kw = {"LookupAttributes": [{"AttributeKey": "Username", "AttributeValue": name}],
                      "StartTime": w_start, "EndTime": w_end, "MaxResults": 50}
                if token:
                    kw["NextToken"] = token
                page = cloudtrail.lookup_events(**kw)
                time.sleep(0.6)                      # stay under the 2-per-second limit
                for ev in page.get("Events", []):
                    seen += 1
                    detail = json.loads(ev["CloudTrailEvent"])
                    if detail.get("readOnly") is True:
                        continue
                    if detail.get("eventName") in ("PutMetricData", "Publish", "SendMessage", "Invoke",
                                                   "SimulatePrincipalPolicy", "LookupEvents"):
                        continue
                    target = json.dumps(detail.get("requestParameters") or {})
                    if not any(t in target for t in ALLOWED_WRITE_TARGETS):
                        findings.append("%s %s by %s at %s: %s" % (
                            detail.get("eventSource"), detail.get("eventName"), name,
                            detail.get("eventTime"), target[:200]))
                token = page.get("NextToken")
                if not token:
                    break
            if partial:
                break
        if not partial:
            update_item("safety", "state", last_audit_at=w_end.strftime("%Y-%m-%dT%H:%M:%SZ"))
            w_start = w_end
    return seen, findings, partial


def is_paused():
    s = get_item("safety", "state") or {}
    return bool(s.get("paused")), s


def record_safety(checks, audit_seen=None, findings=None, partial=False):
    s = get_item("safety", "state") or {"pk": "safety", "sk": "state", "paused": False, "mode": "shadow"}
    s["checks"] = checks
    if findings is not None and not partial:       # a partial review does not move the mark
        s["last_audit_at"] = now_iso()
        s["last_audit_events"] = audit_seen
        s["last_audit_findings"] = findings
    failing = [c for c in checks if not c["passed"]] or (findings or [])
    s["production_write_access"] = "detected" if failing else "none"
    if failing and not s.get("paused"):
        s["paused"], s["paused_at"] = True, now_iso()
        s["paused_reason"] = "Paused automatically: a safety check failed"
        alert("IP pipeline paused: safety check failed",
              json.dumps({"checks": checks, "findings": findings}, indent=2))
    put_item(s)
    return not failing


def alert(subject, message):
    try:
        sns.publish(TopicArn=TOPIC_ARN, Subject=subject[:99], Message=message[:200000])
    except Exception as e:
        print("alert not sent:", e)


def metric(name, value, job):
    try:
        cloudwatch.put_metric_data(Namespace="ipintel", MetricData=[{
            "MetricName": name, "Value": float(value),
            "Dimensions": [{"Name": "job", "Value": job}]}])
    except Exception as e:
        print("metric not sent:", e)


# ---------------------------------------------------------------- run log

def start_run(job, run_id, extra=None):
    item = {"pk": "run#" + job, "sk": now_iso() + "#" + run_id, "run_id": run_id, "status": "running",
            "started_at": now_iso(), "checks": [], "message": None}
    item.update(extra or {})
    put_item(item)
    return item


def finish_run(item, status, message=None, **fields):
    item.update(fields)
    item["status"], item["message"], item["finished_at"] = status, message, now_iso()
    put_item(item)
    job = item["pk"].split("#", 1)[1]
    metric("RunFailed", 1 if status == "failed" else 0, job)
    if status == "failed":
        alert("IP pipeline job failed: " + job, json.dumps(to_plain(item), indent=2, default=str))
    return item
