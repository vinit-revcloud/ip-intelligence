# Adding the IPs from `experimentation_tools.experiment_router_events`

**Status (18 Sep 2026):** not appended yet.
- The pipeline's AWS roles (`ipintel-builder-role`, `ipintel-pipeline-role`) are refused `s3:GetObject` on `s3://mlbucket-sagemaker/experimentation_tools/experiment_router_events/`, so Athena returns PERMISSION_DENIED.
- The table is already registered as a third source (DynamoDB `ipintel-pipeline-state`, `base_table` / `router_events`), switched **off**.

There are two correct ways to add it. **Path A is the permanent fix.** **Path B works today** without an admin, but has to be repeated to pick up new IPs.

---

## Path A (permanent): an admin grants read access

**Who:** an AWS admin. **Time:** about 5 minutes.

1. Add this inline policy to **both** `ipintel-builder-role` and `ipintel-pipeline-role`. It is read only:
   ```json
   {"Version":"2012-10-17","Statement":[{"Sid":"ReadRouterEvents","Effect":"Allow",
   "Action":["s3:GetObject","s3:GetObjectVersion","s3:ListBucket","s3:GetBucketLocation"],
   "Resource":["arn:aws:s3:::mlbucket-sagemaker",
   "arn:aws:s3:::mlbucket-sagemaker/experimentation_tools/experiment_router_events/*"]}]}
   ```
2. If the bucket is encrypted with a KMS key, also allow `kms:Decrypt` on that key for both roles.
3. If Lake Formation manages `experimentation_tools`, grant both roles **SELECT** on the table.
4. Tell me. I then do the rest:
   - **profile** the table (`sql/checks/router_profile.sql`);
   - **count** the new IPs (step 5 of Path B);
   - **validate and enable** the source;
   - **run** the daily load, which adds the new IPs to both tables with every free vendor's answer;
   - **send** them to proxycheck.io and refresh the `unified` tables.

After that, new router IPs are added **every day automatically**.

---

## Path B (today, no admin): copy the IPs into our project with your own login

You can read the table, so you make a one-column copy inside our project. The pipeline then reads the copy.

**Where:** the Athena console, region us-west-2.
**Workgroup:** `ipintel_etl`. **Not** `primary`.
**Catalog:** AwsDataCatalog.

### Step 1: create the copy (run once)

```sql
CREATE TABLE ipintel_curated.router_ips
WITH (table_type = 'ICEBERG',
      location = 's3://datalake-landingzone-221490242148-us-west-2/ip-intelligence/curated/router_ips/',
      is_external = false)
AS
SELECT trim(ip_address) AS ip_address,
       max(server_timestamp_entry) AS last_seen,
       min(server_timestamp_entry) AS first_seen,
       count(*) AS events
FROM experimentation_tools.experiment_router_events
WHERE nullif(trim(ip_address), '') IS NOT NULL
GROUP BY trim(ip_address);
```

This only **reads** the router table. The copy goes into our project folder and our project database.

### Step 2: check the copy

```sql
SELECT count(*) AS ips, min(last_seen) AS oldest, max(last_seen) AS newest
FROM ipintel_curated.router_ips;
```

`ips` should equal your `SELECT DISTINCT ip_address` count (128,117 in your screenshot). It can be off by a few if some values had spaces.

### Step 3: tell me "router_ips created"

I then:
1. Point the `router_events` source at `ipintel_curated.router_ips` (`ip_address`, `last_seen`).
2. Validate it and switch it on.
3. Run the daily load by hand: new IPs get rows in `ip_geo` and `ip_intelligence` with IP2Location, IP2Proxy and FraudLogix answers, plus a row in `ip_occurrences`, and are **queued for proxycheck.io**.
4. Run proxycheck.io for them, refresh the `unified` tables, and report the numbers.

### Step 4: keep it current (Path B only)

The copy does not update itself. To pick up new router IPs, run this whenever you like (for example weekly), then tell me or wait for the next 07:30 run:

```sql
MERGE INTO ipintel_curated.router_ips t
USING (SELECT trim(ip_address) AS ip_address, max(server_timestamp_entry) AS last_seen,
              min(server_timestamp_entry) AS first_seen, count(*) AS events
       FROM experimentation_tools.experiment_router_events
       WHERE nullif(trim(ip_address), '') IS NOT NULL GROUP BY trim(ip_address)) s
ON t.ip_address = s.ip_address
WHEN MATCHED THEN UPDATE SET last_seen = s.last_seen, events = s.events
WHEN NOT MATCHED THEN INSERT (ip_address, last_seen, first_seen, events)
  VALUES (s.ip_address, s.last_seen, s.first_seen, s.events);
```

Path A removes this step, so ask for it anyway.

### Step 5: how many router IPs are new to us ("uniquely appendable")

```sql
WITH r AS (SELECT DISTINCT ip_address FROM ipintel_curated.router_ips
           WHERE regexp_like(ip_address, '^\d{1,3}(\.\d{1,3}){3}$')),
have AS (SELECT DISTINCT ip_address FROM unified.ip_geo)
SELECT count(*) AS router_ipv4,
       count_if(h.ip_address IS NOT NULL) AS already_in_our_tables,
       count_if(h.ip_address IS NULL) AS new_to_append
FROM r LEFT JOIN have h ON h.ip_address = r.ip_address;
```

Before Step 1 you can run the same query directly on the router table: replace `ipintel_curated.router_ips` with `experimentation_tools.experiment_router_events`.

---

## Rules either way
- Only public IPv4 addresses are added. IPv6 and private addresses (10.x, 192.168.x, …) are skipped, because no vendor can answer them.
- The router table is **only read**. Nothing is written to `experimentation_tools`.
- The `unified` tables are refreshed only after every check passes, as for the other two sources.
