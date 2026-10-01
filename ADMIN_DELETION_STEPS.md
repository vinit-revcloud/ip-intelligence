# Admin Deletion Steps

Updated 16 Sep 2026, 20:10 UTC. What's left needs an AWS admin, because the project's safety rules don't let the project roles delete these items (confirmed with the AWS permission simulator). What's left: delete the retired API, and drop 5 unused benchmark tables. **No `unified` table and nothing in `ip-database` is to be dropped.**

## Before you start (already done)
- **API blocked:** `ipintel-findings-api` refuses every call (reserved concurrency set to 0). The teammate's API (`9w07dr3qq2`) is unaffected.
- **Backups:** the API's URL config, resource policy and settings (without secrets) are in `archive/api-removed-2026-09-16/`. So is its code.
- **Nothing depends on it:** no daily job uses this API.

## 1. Delete our API (region us-west-2)
```
aws lambda delete-function-url-config --function-name ipintel-findings-api
aws lambda delete-function --function-name ipintel-findings-api
aws logs delete-log-group --log-group-name /aws/lambda/ipintel-findings-api
```

## 2. Delete the API's role
The role has no attached policies, only these five inline ones:
```
aws iam delete-role-policy --role-name ipintel-api-role --policy-name ipintel-api-control
aws iam delete-role-policy --role-name ipintel-api-role --policy-name ipintel-api-lookup
aws iam delete-role-policy --role-name ipintel-api-role --policy-name ipintel-api-read
aws iam delete-role-policy --role-name ipintel-api-role --policy-name ipintel-list-reference
aws iam delete-role-policy --role-name ipintel-api-role --policy-name ipintel-sources-crud
aws iam delete-role-permissions-boundary --role-name ipintel-api-role
aws iam delete-role --role-name ipintel-api-role
```

## 3. Drop 5 unused tables this project created in its benchmark phase (3–8 Sep)
No running code uses them. They are external tables, so dropping them removes only the catalog entry and their files stay. Their definitions are backed up in `archive/other-project-tables-2026-09-16/` and `s3://…/ip-intelligence/archive/other-project-tables-2026-09-16/`.

Run in Athena, in your own workgroup:
```sql
DROP TABLE IF EXISTS ipintel_analytics.geo_accuracy;
DROP TABLE IF EXISTS ipintel_analytics.geo_score;
DROP TABLE IF EXISTS ipintel_analytics.pairwise_agreement;
DROP TABLE IF EXISTS ipintel_analytics.risk_score;
DROP TABLE IF EXISTS ipintel_reference.zip_centroid;
```

Afterwards the two databases are empty. Dropping them is optional:
```sql
DROP DATABASE IF EXISTS ipintel_analytics;
DROP DATABASE IF EXISTS ipintel_reference;
```

**Do not touch the `ip-database` database or any of its tables.** It existed before this project, and the project only reads it.

## Do not drop any `unified` table
All six project tables in `unified` stay, and the daily pipeline refreshes them with the latest data after every passed run:
- `ip_geo`
- `ip_intelligence`
- `ip_geo_analytics`
- `ip_intelligence_analytics`
- `vendor_overview_geo`
- `vendor_overview_proxy`

## 4. Tell the project owner when done
I then delete the API's lookup cache, `ip-intelligence/proxycheck/live/by-ip/`. Only the retired API used it.

## To undo (before step 1)
Unblock the API with:
```
aws lambda delete-function-concurrency --function-name ipintel-findings-api
```

## Request 2: read-only key for the app (17 Sep)

This lets the Lovable app read its 9 report files without anyone uploading them.

1. Create IAM user `ipintel-app-reader` with no console access and this inline policy only:

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"s3:GetObject",
"Resource":"arn:aws:s3:::datalake-landingzone-221490242148-us-west-2/ip-intelligence/serving/app/*"}]}
```

2. Create one access key for it. Give it to the app owner privately; it goes only into the Lovable secrets `APP_S3_ACCESS_KEY_ID` and `APP_S3_SECRET_ACCESS_KEY`.
3. **Undo:** delete the access key and the user.

## Request 3: read access to the third IP source (17 Sep, blocking)

`experimentation_tools.experiment_router_events` is to become our third source of IP addresses. Its Glue definition
is readable, but its data sits in another bucket, so Athena refuses the query:

```
PERMISSION_DENIED: ... is not authorized to perform: s3:GetObject on resource:
"arn:aws:s3:::mlbucket-sagemaker/experimentation_tools/experiment_router_events/metadata/...metadata.json"
```

Please add this **read-only** statement to both `ipintel-builder-role` and `ipintel-pipeline-role`:

```json
{"Version":"2012-10-17","Statement":[{"Sid":"ReadRouterEvents","Effect":"Allow",
"Action":["s3:GetObject","s3:GetObjectVersion","s3:ListBucket","s3:GetBucketLocation"],
"Resource":["arn:aws:s3:::mlbucket-sagemaker",
"arn:aws:s3:::mlbucket-sagemaker/experimentation_tools/experiment_router_events/*"]}]}
```

- No write permission is asked for, and none should be granted.
- If Lake Formation manages that table, the two roles also need SELECT on it.
- **Undo:** remove the statement.

Once it is in place, tell me and I will profile the table, run the validation and switch the source on.

## Request 4: add three columns to `unified.ip_intelligence` (18 Sep, owner decision) — DONE 18 Sep by the owner; published 19:01 UTC

The builder role cannot change table definitions in the `unified` database (`glue:UpdateTable` is denied), so this needs an admin. It only **adds** three columns at the end; no data, row, or existing column changes.

**Where:** Athena console, us-west-2, workgroup `ipintel_etl` (not `primary`).

```sql
ALTER TABLE unified.ip_intelligence ADD COLUMNS (is_flagged boolean, flagged_reason string, bot_reason string);
```

- **Already done on our side:** the same three columns exist and are filled in `ipintel_curated.ip_intelligence`, and the daily jobs keep them current. The publish step copies them into unified automatically from the first publish after this statement runs. Until then, it publishes the other columns as before.
- **Check afterwards:** `SELECT is_flagged, flagged_reason, bot_reason FROM unified.ip_intelligence LIMIT 10;` Values are empty until the next publish (after the 05:45 IST run, or ask me to publish straight away).
- **Undo:** `ALTER TABLE unified.ip_intelligence REPLACE COLUMNS (...)` with the original 14 columns. The saved definition is in `archive/schema-before-flag-columns-2026-09-18/unified.ip_intelligence.json`.
