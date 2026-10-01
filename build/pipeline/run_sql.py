"""Run one SQL file through Athena as the builder role, in the ETL workgroup only.

usage: python run_sql.py file.sql [--show]   (--show prints the result rows)
Every call uses the ipintel-builder profile, so AWS itself refuses any write outside the project.
"""
import json, subprocess, sys, time
PROFILE = ["--profile", "ipintel-builder", "--region", "us-west-2"]
def aws(*a):
    r = subprocess.run(["aws", *a, *PROFILE], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode: sys.exit(r.stderr.strip())
    return r.stdout
path = sys.argv[1]
sql = open(path, encoding="utf-8").read()
qid = aws("athena", "start-query-execution", "--query-string", sql, "--work-group", "ipintel_etl",
          "--query-execution-context", "Database=ipintel_curated", "--query", "QueryExecutionId", "--output", "text").strip()
while True:
    ex = json.loads(aws("athena", "get-query-execution", "--query-execution-id", qid, "--output", "json"))["QueryExecution"]
    st = ex["Status"]["State"]
    if st in ("SUCCEEDED", "FAILED", "CANCELLED"): break
    time.sleep(3)
stats = ex.get("Statistics", {})
print("%-40s %s  %.2f GB read  %ds" % (path.split("/")[-1], st, stats.get("DataScannedInBytes", 0) / 1e9,
      stats.get("TotalExecutionTimeInMillis", 0) // 1000))
if st != "SUCCEEDED":
    sys.exit("   " + ex["Status"].get("StateChangeReason", ""))
if "--show" in sys.argv:
    res = json.loads(aws("athena", "get-query-results", "--query-execution-id", qid, "--output", "json"))
    for row in res["ResultSet"]["Rows"]:
        print("   " + " | ".join(c.get("VarCharValue", "") for c in row["Data"]))
