"""Ask AWS's permission simulator what a role may do. Nothing is ever performed."""
import json, subprocess, sys
role = sys.argv[1]
A = "arn:aws:"; ACC = "221490242148"; R = "us-west-2"
def sim(actions, resource, context=None):
    cmd = ["aws", "iam", "simulate-principal-policy", "--policy-source-arn", f"arn:aws:iam::{ACC}:role/{role}",
           "--action-names", *actions, "--resource-arns", resource,
           "--query", "EvaluationResults[].[EvalActionName,EvalDecision]", "--output", "json"]
    if context: cmd += ["--context-entries", json.dumps(context)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode: return [(a, "ERROR " + out.stderr.strip()[:80]) for a in actions]
    return json.loads(out.stdout)

must_deny = [
 (["glue:UpdateTable","glue:DeleteTable","glue:CreateTable"], f"{A}glue:{R}:{ACC}:table/unified/unified_session_summary", "production table unified_session_summary"),
 (["glue:UpdateTable","glue:DeleteTable"], f"{A}glue:{R}:{ACC}:table/raw/raw_tune_clicks", "production table raw_tune_clicks"),
 (["glue:UpdateTable","glue:DeleteTable","glue:CreateTable"], f"{A}glue:{R}:{ACC}:table/unified/ip_geo", "existing unified.ip_geo"),
 (["glue:UpdateTable","glue:DeleteTable"], f"{A}glue:{R}:{ACC}:table/unified/lu_connector", "production table lu_connector"),
 (["glue:DeleteDatabase","glue:UpdateDatabase","glue:CreateDatabase"], f"{A}glue:{R}:{ACC}:database/unified", "database unified"),
 (["glue:StartCrawler","glue:UpdateCrawler"], f"{A}glue:{R}:{ACC}:crawler/agents", "an existing Glue crawler"),
 (["glue:StartJobRun","glue:UpdateJob"], f"{A}glue:{R}:{ACC}:job/acquire_unified_ads_data_job", "an existing Glue job"),
 (["s3:PutObject","s3:DeleteObject"], "arn:aws:s3:::datalake-unified-221490242148-us-west-2/unified_session_summary/data/x.parquet", "session summary data files"),
 (["s3:PutObject","s3:DeleteObject"], "arn:aws:s3:::datalake-raw-221490242148-us-west-2/tune/raw_tune_clicks_3/data/x.parquet", "tune clicks data files"),
 (["s3:PutObject","s3:DeleteObject"], "arn:aws:s3:::datalake-landingzone-221490242148-us-west-2/client_data/x.csv", "another team's landing-zone folder"),
 (["s3:PutBucketNotification","s3:PutLifecycleConfiguration","s3:PutBucketPolicy","s3:PutBucketVersioning"], "arn:aws:s3:::datalake-landingzone-221490242148-us-west-2", "landing-zone bucket settings"),
 (["athena:StartQueryExecution","athena:UpdateWorkGroup"], f"{A}athena:{R}:{ACC}:workgroup/primary", "Athena workgroup primary"),
 (["lambda:InvokeFunction","lambda:UpdateFunctionCode"], f"{A}lambda:{R}:{ACC}:function:acquire_tune_polling_lambda", "an existing production Lambda"),
 (["lambda:DeleteFunction"], f"{A}lambda:{R}:{ACC}:function:ipintel-findings-api", "the existing IP API Lambda (delete)"),
 (["dynamodb:DeleteTable"], f"{A}dynamodb:{R}:{ACC}:table/ipintel-sources", "the existing vendor list table (delete)"),
 (["dynamodb:PutItem","dynamodb:DeleteTable"], f"{A}dynamodb:{R}:{ACC}:table/any-production-table", "any other DynamoDB table"),
 (["events:PutRule","events:PutTargets","events:DeleteRule"], f"{A}events:{R}:{ACC}:rule/BounceEvents", "an existing EventBridge rule"),
 (["lakeformation:GrantPermissions","lakeformation:PutDataLakeSettings"], "*", "Lake Formation"),
 (["iam:PutUserPolicy","iam:AttachUserPolicy"], f"arn:aws:iam::{ACC}:user/source_creation_tool_user", "the shared login itself"),
 (["iam:PutRolePolicy","iam:AttachRolePolicy","iam:DeleteRolePermissionsBoundary"], f"arn:aws:iam::{ACC}:role/ipintel-builder-role", "loosening the builder role"),
 (["iam:CreatePolicyVersion","iam:DeletePolicy"], f"arn:aws:iam::{ACC}:policy/ipintel-boundary", "loosening the boundary"),
 (["secretsmanager:PutSecretValue","secretsmanager:DeleteSecret"], f"{A}secretsmanager:{R}:{ACC}:secret:ipintel/proxycheck-paid-bds743", "changing the paid proxycheck key"),
]
must_allow = [
 (["glue:GetTable","glue:GetPartitions"], f"{A}glue:{R}:{ACC}:table/unified/unified_session_summary", "read session summary definition"),
 (["s3:GetObject"], "arn:aws:s3:::datalake-unified-221490242148-us-west-2/unified_session_summary/data/x.parquet", "read session summary data"),
 (["s3:GetObject"], "arn:aws:s3:::datalake-raw-221490242148-us-west-2/tune/raw_tune_clicks_3/data/x.parquet", "read tune clicks data"),
 (["athena:StartQueryExecution"], f"{A}athena:{R}:{ACC}:workgroup/ipintel_etl", "query in ipintel_etl"),
 (["glue:CreateTable","glue:UpdateTable"], f"{A}glue:{R}:{ACC}:table/ipintel_curated/ip_geo", "write ipintel_curated.ip_geo"),
 (["s3:PutObject"], "arn:aws:s3:::datalake-landingzone-221490242148-us-west-2/ip-intelligence/curated/x.parquet", "write the project folder"),
 (["lambda:CreateFunction"], f"{A}lambda:{R}:{ACC}:function:ipintel-free-daily", "create ipintel-free-daily"),
 (["dynamodb:CreateTable"], f"{A}dynamodb:{R}:{ACC}:table/ipintel-pipeline-state", "create ipintel-pipeline-state"),
]
PIPELINE_ALLOW = [
 (["glue:GetTable"], f"{A}glue:{R}:{ACC}:table/unified/unified_session_summary", "read session summary definition"),
 (["s3:GetObject"], "arn:aws:s3:::datalake-unified-221490242148-us-west-2/unified_session_summary/data/x.parquet", "read session summary data"),
 (["s3:GetObject"], "arn:aws:s3:::datalake-raw-221490242148-us-west-2/tune/raw_tune_clicks_3/data/x.parquet", "read tune clicks data"),
 (["athena:StartQueryExecution"], f"{A}athena:{R}:{ACC}:workgroup/ipintel_etl", "query in ipintel_etl"),
 (["glue:CreateTable","glue:UpdateTable"], f"{A}glue:{R}:{ACC}:table/ipintel_curated/ip_geo", "write ipintel_curated.ip_geo"),
 (["s3:PutObject"], "arn:aws:s3:::datalake-landingzone-221490242148-us-west-2/ip-intelligence/curated/x.parquet", "write the project folder"),
 (["dynamodb:UpdateItem"], f"{A}dynamodb:{R}:{ACC}:table/ipintel-pipeline-state", "update pipeline state"),
 (["lambda:InvokeFunction"], f"{A}lambda:{R}:{ACC}:function:ipintel-proxycheck-daily", "start the proxycheck job"),
]
PIPELINE_DENY_EXTRA = [
 (["athena:StartQueryExecution"], f"{A}athena:{R}:{ACC}:workgroup/ipintel", "the API's workgroup"),
 (["lambda:CreateFunction","lambda:UpdateFunctionCode"], f"{A}lambda:{R}:{ACC}:function:ipintel-free-daily", "changing its own code"),
 (["iam:CreateRole","iam:PutRolePolicy"], f"arn:aws:iam::{ACC}:role/ipintel-pipeline-role", "changing its own permissions"),
 (["dynamodb:PutItem"], f"{A}dynamodb:{R}:{ACC}:table/ipintel-sources", "writing the vendor list"),
]
if role == "ipintel-pipeline-role":
    must_allow = PIPELINE_ALLOW
    must_deny = must_deny + PIPELINE_DENY_EXTRA
bad = 0
print("MUST BE DENIED")
for actions, res, label in must_deny:
    for act, dec in sim(actions, res):
        ok = dec in ("explicitDeny", "implicitDeny")
        bad += not ok
        print("  %s %-42s %-36s %s" % ("PASS" if ok else "FAIL", label[:42], act, dec))
print("\nMUST BE ALLOWED")
for actions, res, label in must_allow:
    for act, dec in sim(actions, res):
        ok = dec == "allowed"
        bad += not ok
        print("  %s %-42s %-36s %s" % ("PASS" if ok else "FAIL", label[:42], act, dec))
if role != 'ipintel-builder-role':
    print()
    print('ALL CHECKS PASSED' if bad == 0 else '%d CHECK(S) FAILED' % bad)
    sys.exit(1 if bad else 0)
ctx = [{"ContextKeyName": "iam:PermissionsBoundary", "ContextKeyValues": [f"arn:aws:iam::{ACC}:policy/ipintel-boundary"], "ContextKeyType": "string"}]
for act, dec in sim(["iam:CreateRole"], f"arn:aws:iam::{ACC}:role/ipintel-pipeline-role", ctx):
    ok = dec == "allowed"; bad += not ok
    print("  %s %-42s %-36s %s" % ("PASS" if ok else "FAIL", "create pipeline role WITH the fence", act, dec))
ctx_bad = [{"ContextKeyName": "iam:PermissionsBoundary", "ContextKeyValues": [f"arn:aws:iam::{ACC}:policy/SomethingElse"], "ContextKeyType": "string"}]
for act, dec in sim(["iam:CreateRole"], f"arn:aws:iam::{ACC}:role/ipintel-pipeline-role", ctx_bad):
    ok = dec != "allowed"; bad += not ok
    print("  %s %-42s %-36s %s" % ("PASS" if ok else "FAIL", "create pipeline role WITHOUT the fence", act, dec))
print("\n%s" % ("ALL CHECKS PASSED" if bad == 0 else "%d CHECK(S) FAILED" % bad))
sys.exit(1 if bad else 0)
