# Lovable Prompt — Pipeline Control (safety, base tables, daily jobs, proxycheck budget)

Adds four pages that let the team run the IP pipeline from the UI: a Safety page with an emergency
stop, which tables IP addresses are collected from, the two daily jobs, and the proxycheck.io budget.
The existing Vendor Sources page stays as it is.

No env changes. Same `IPINTEL_API_URL` and `IPINTEL_API_TOKEN`.

**Backend status (14 September 2026): every endpoint below is live** on the same API and was tested
end to end, including the refusals (pause blocks runs, resume is refused while a check fails, the
budget cap, unknown fields, the pipeline's own database as a base table, a missing column). The 404
"not available yet" handling stays in the prompt as a safety net. Paste everything below the line as
one message.

---

> Add four pages under a new **Pipeline** section in the navigation, in this order: **Safety**,
> **Base Tables**, **Daily Jobs** and **proxycheck Budget**. Keep the existing Vendor Sources page
> unchanged. Follow the
> conventions already used by Vendor Sources exactly: server functions, one contract file, API
> error strings shown to the user word for word, and `router.invalidate()` after every change.
>
> Nothing about a table, job or budget may be hardcoded in a component. Everything comes from the
> API.
>
> ## Two ideas the UI must keep separate
>
> - **Base tables** are where IP addresses *come from*. For example the website session table and
>   the ad-click table. The pipeline only ever **reads** them.
> - **Vendor sources** are who *answers questions* about an address. For example IP2Location or
>   proxycheck.io. They already have their own page.
>
> Never mix the two on one page and never call a base table a "source" in the copy. Call them
> "base tables" everywhere.
>
> ## Endpoints
>
> ```
> GET    /safety                           → Safety
> POST   /safety/pause                     → body { reason }  → Safety
> POST   /safety/resume                    → body { reason }  → Safety | 409 if a safety check is failing
>
> GET    /input-tables                     → { count, input_tables: InputTable[] }
> POST   /input-tables                     → create (201) | 400 invalid | 409 id exists
> GET    /input-tables/{id}                → InputTable
> PATCH  /input-tables/{id}                → partial update
> DELETE /input-tables/{id}                → remove from the list
> POST   /input-tables/{id}/validate       → run checks, returns Validation
>
> GET    /catalog/databases                → { databases: string[] }
> GET    /catalog/tables?database=X        → { tables: CatalogTable[] }
> GET    /catalog/columns?database=X&table=Y → { columns: CatalogColumn[] }
>
> GET    /jobs                             → { jobs: Job[] }
> PATCH  /jobs/{id}                        → partial update
> POST   /jobs/{id}/run                    → 202 { run_id, status } | 409 already running
> GET    /jobs/{id}/runs?limit=30          → { runs: Run[] }
>
> GET    /quota                            → Quota
> ```
>
> ## Contract — add to `src/lib/api/contract.ts`
>
> ```ts
> export type SafetyCheck = {
>   name: string                       // e.g. "Pipeline cannot write to any production table"
>   passed: boolean
>   checked_at: string
>   detail: string | null              // plain-English explanation, always present when failed
> }
>
> export type Safety = {
>   paused: boolean                    // true stops every job and live proxycheck call at once
>   paused_at: string | null
>   paused_reason: string | null
>   mode: 'shadow' | 'live'            // shadow: results written only to the project's own tables
>   production_write_access: 'none' | 'detected'
>   checks: SafetyCheck[]
>   last_audit_at: string | null       // when the pipeline last reviewed its own AWS activity
>   last_audit_findings: string[]      // empty means nothing outside the project was touched
> }
>
> export type ValidationStatus = 'valid' | 'invalid' | 'stale' | 'unchecked'
>
> export type Validation = {
>   status: ValidationStatus
>   checked_at: string | null
>   table_format: 'iceberg' | 'hive' | 'unknown'
>   write_pattern: 'append' | 'overwrite' | 'unknown'   // read from the table's own write log
>   last_write_at: string | null
>   rows_estimate: number | null
>   valid_ipv4_pct: number | null      // share of sampled values that are real IPv4 addresses
>   scan_gb_per_run: number | null     // what one daily run will read from this table
>   problems: string[]                 // plain-English reasons it is not valid, empty when valid
> }
>
> export type InputTable = {
>   id: string
>   database: string
>   table: string
>   ip_column: string
>   seen_at_column: string             // a date or timestamp column saying when the address was seen
>   enabled: boolean
>   note: string | null
>   validation: Validation
>   created_at: string
>   updated_at: string
> }
>
> export type CatalogTable  = { name: string; format: 'iceberg' | 'hive' | 'unknown' }
> export type CatalogColumn = { name: string; type: string }
>
> export type RunStatus = 'running' | 'succeeded' | 'failed' | 'skipped'
>
> export type Check = { name: string; passed: boolean; detail: string | null }
>
> export type Run = {
>   run_id: string
>   status: RunStatus
>   started_at: string
>   finished_at: string | null
>   message: string | null             // why it failed or was skipped, in plain English
>   new_ips: number | null
>   rows_inserted: number | null       // brand-new address and vendor pairs
>   rows_added: number | null          // a vendor's first answer for an address we already had
>   rows_updated: number | null        // an existing answer that changed
>   checks: Check[]
>   // free-sources job only: base-table addresses it queued for proxycheck.io, by reason
>   queued_for_proxycheck?: number
>   queued_by_reason?: Record<string, number>
>   // proxycheck job only
>   queue_waiting?: number             // queued addresses still waiting after this run
>   batches_done?: number
>   batches_total?: number
>   queries_spent?: number
> }
>
> export type Job = {
>   id: 'free-daily' | 'proxycheck-daily'
>   name: string
>   description: string
>   enabled: boolean
>   schedule_utc: string               // "HH:MM"
>   next_run_at: string | null
>   daily_budget?: number              // proxycheck job only
>   budget_cap?: number                // proxycheck job only: the most the server will accept
>   last_run: Run | null
> }
>
> export type Quota = {
>   plan_tier: string                  // e.g. "Free", "Pro"
>   daily_limit: number
>   reserved_today: number             // our own counter, updated the moment a query is reserved
>   provider_reported_today: number    // proxycheck's own counter, runs a few minutes behind
>   live_lookup_reserve: number        // held back so live lookups never run dry
>   batch_budget: number
>   key_status: 'valid' | 'invalid' | 'missing'
>   as_of: string
> }
> ```
>
> ## Server functions
>
> `src/lib/api/safety.functions.ts`: `getSafety`, `pausePipeline`, `resumePipeline`.
>
> `src/lib/api/inputTables.functions.ts`: `listInputTables`, `createInputTable`,
> `updateInputTable`, `deleteInputTable`, `validateInputTable`, `listDatabases`, `listTables`,
> `listColumns`.
>
> `src/lib/api/jobs.functions.ts`: `listJobs`, `updateJob`, `runJob`, `listRuns`, `getQuota`.
>
> Each is a `createServerFn` that reads `IPINTEL_API_URL` and `IPINTEL_API_TOKEN` **inside**
> `.handler()`. Non-OK responses throw with the status code and the API's `error` string, and the
> user sees that string exactly.
>
> **A 404 from any of these endpoints means that part of the backend has not shipped yet.** Do not
> show it as an error. Show a calm panel on that page reading "This part of the pipeline is not
> available yet." with the endpoint name underneath in small monospace text. Every other part of the
> page that does work must keep working.
>
> ## Page 1 — Safety
>
> **Header:** "Safety". Subtitle: "The pipeline only reads production data. This page proves it, and
> stops everything in one click."
>
> **A status banner across the top**, the first thing on the page:
>
> - When `production_write_access` is `none` and every check passed: a success banner reading
>   "Production is read-only for this pipeline. All safety checks passed."
> - When any check failed, or `production_write_access` is `detected`: a danger banner reading
>   "A safety check failed. Jobs are paused until it passes." followed by each failed check's
>   `detail`.
> - When `paused` is true: a warning banner reading "Paused by request", with `paused_reason` and
>   `paused_at` as relative time.
>
> **Emergency stop.** Beside the banner, a large button. When running it reads **Pause everything**
> in the danger style. Clicking it opens a dialog asking for a short reason, required, with the text
> "This stops both daily jobs and all live proxycheck calls immediately. Nothing is deleted. Data
> already written stays as it is." The confirm button reads **Pause everything now**. Call
> `POST /safety/pause`.
>
> When paused, the button reads **Resume** in the normal style, also with a required reason. If the
> API returns 409, show its message exactly and keep the pipeline paused: resuming is refused while a
> safety check is failing.
>
> **Mode.** A pill: `shadow` → info "Shadow mode", with the helper text "The daily jobs are updating
> the new tables, but this app still shows the earlier data while the results are checked." `live` →
> success "Live", with the helper text "This app shows the tables the daily jobs keep up to date."
>
> **Safety checks** as a list, one row each: a tick or cross, the check `name`, and `checked_at` as
> relative time. A failed check shows its `detail` underneath in danger colour.
>
> **Last activity review.** "The pipeline last reviewed its own AWS activity `last_audit_at`." If
> `last_audit_findings` is empty, show "Nothing outside the project was touched." in success colour.
> Otherwise list every finding in danger colour.
>
> Refresh this page every 30 seconds. Also show a small safety pill in the app header on every page:
> green "Read-only" when all checks pass, red "Check failed" otherwise, amber "Paused" when paused.
> Clicking it opens the Safety page.
>
> ## Page 2 — Base Tables
>
> **Header:** "Base Tables". Subtitle: "Tables IP addresses are collected from. The pipeline only
> reads these tables. It never writes to them."
>
> **Table of base tables**, one row each:
>
> | Column | Content |
> |---|---|
> | Name | `id`, with `note` underneath in muted text |
> | Table | `database.table` in monospace |
> | IP column | `ip_column` in monospace |
> | Seen-at column | `seen_at_column` in monospace |
> | Status | a pill from `validation.status` |
> | Last write | `validation.last_write_at` as relative time, e.g. "3 hours ago", with the exact UTC time on hover |
> | Enabled | a switch |
> | Actions | Validate, Edit, Remove |
>
> Status pill tones: `valid` → success "Valid", `invalid` → danger "Invalid", `stale` → warning
> "Needs re-check", `unchecked` → neutral "Not checked".
>
> Above the table, a summary strip with three numbers: **Enabled tables**, **Needs attention**
> (count of `invalid` plus `stale`), and **Scanned per daily run** (sum of `scan_gb_per_run` for
> enabled tables, shown as GB with one decimal).
>
> **Expanding a row** shows the full validation: table format, write pattern ("Adds rows only" for
> `append`, "Rewrites rows" for `overwrite`), rows estimate, valid IPv4 share, scan size, checked
> time, and every entry in `problems` as a bulleted list in danger colour.
>
> **Add base table** opens a form. Build it as three linked pickers, never free-text boxes, so a
> typo cannot reach the backend:
>
> 1. **Database**, a select filled from `GET /catalog/databases`.
> 2. **Table**, a select filled from `GET /catalog/tables?database=…` once a database is chosen.
>    Show the format as a small badge beside each option.
> 3. **IP column** and **Seen-at column**, two selects filled from `GET /catalog/columns`. Show each
>    column's type beside its name. In the IP column select, list `string` and `varchar` columns
>    first. In the seen-at select, list `date` and `timestamp` columns first.
>
> Plus **Name** (becomes `id`, lowercase letters, digits and underscores only, validated as the user
> types), **Note** (optional), and **Enabled** (default on).
>
> On save: `POST /input-tables`, then immediately `POST /input-tables/{id}/validate`, then show the
> validation result in the drawer before closing it. If validation comes back `invalid`, keep the
> drawer open and show `problems`, so the user can fix the column choice straight away.
>
> **Edit** uses the same form. After `PATCH`, if the response says the validation is stale, show a
> warning toast "Settings changed. Re-check this table before the next run." with a **Validate now**
> button in the toast.
>
> **Remove** opens a confirmation dialog: "Stop collecting addresses from `database.table`? Addresses
> already collected from it stay in the IP tables." Buttons: Cancel, Remove. If the API refuses
> because it is the last enabled table, show its error message exactly.
>
> **The enabled switch** calls `PATCH` with `{ enabled }`. Turning a table off shows a toast "Paused.
> The next daily run will skip this table."
>
> ## Page 3 — Daily Jobs
>
> **Header:** "Daily Jobs". Subtitle: "Two scheduled jobs keep the IP tables current. Times are
> UTC."
>
> One **card per job**, side by side on wide screens and stacked on narrow ones, both the same
> height. Each card shows:
>
> - `name` as the title and `description` beneath it
> - An enabled switch in the top right
> - Schedule: "Runs daily at `schedule_utc` UTC" and the next run as relative time
> - **Last run** block: a status pill, started time, duration, then the counts
> - **Checks** list: each check with a tick or a cross and its name. Any failed check shows its
>   `detail` underneath in danger colour
> - A **Run now** button and a **History** link
>
> Status pill tones: `succeeded` → success, `failed` → danger, `running` → info with a spinner,
> `skipped` → neutral. When `status` is `skipped` or `failed`, show `message` directly under the pill.
>
> **Counts on the free-sources card:** New addresses, Inserted, Added, Updated, and "Sent to
> proxycheck.io" (`queued_for_proxycheck`, with `queued_by_reason` in a tooltip). Put a small info icon
> beside "Added" with the tooltip "A vendor's first answer for an address we already had."
>
> **Counts on the proxycheck card:** Batches `batches_done` of `batches_total` as a progress bar,
> then Queries spent, Inserted, Added, Updated. When `queue_waiting` is above 0 show a warning line
> "`queue_waiting` addresses from the base tables are still waiting for proxycheck.io". Also show "Daily budget: `daily_budget` queries" with
> an **Edit** button.
>
> **Edit budget** opens a small dialog with a number input. The input's maximum is `budget_cap`, and
> the helper text reads "At most `budget_cap` a day, so live lookups always have queries left." The
> server enforces the same cap. If it refuses, show its message exactly.
>
> **Run now** on the free-sources job runs immediately after a one-line confirmation.
>
> **When the pipeline is paused** (from `GET /safety`), disable every Run now button and every
> enabled switch on this page, and show above the cards: "The pipeline is paused. Resume it on the
> Safety page." with a link.
>
> **Run now on the proxycheck job spends money**, so it needs a stronger confirmation. Before opening
> the dialog, call `GET /quota`. The dialog reads: "This can spend up to `min(daily_budget,
> daily_limit − reserved_today − live_lookup_reserve)` proxycheck queries today. Already reserved
> today: `reserved_today` of `daily_limit`." The confirm button says **Spend up to N queries** with
> the real number, never a generic "Confirm".
>
> A `409` from Run now means a run is already in progress. Show "Already running" as an info toast,
> not an error.
>
> While any job's last run is `running`, poll `GET /jobs` every 10 seconds and stop polling once no
> run is in progress.
>
> **History** opens a drawer with `GET /jobs/{id}/runs` as a table: started, duration, status, new
> addresses, inserted, added, updated, and queries spent for the proxycheck job. Clicking a row
> expands it to show that run's checks and message.
>
> ## Page 4 — proxycheck Budget
>
> **Header:** "proxycheck Budget". Subtitle: "Queries are reserved before they are sent, so the key
> cannot be used up by accident."
>
> **Key status** at the top as a pill: `valid` → success "Key working", `invalid` → danger "Key
> rejected", `missing` → danger "No key set". Beside it, the plan tier.
>
> When the key is `invalid` or `missing`, show a danger panel: "The proxycheck key is stored in AWS
> Secrets Manager under ipintel/proxycheck-paid. Update it there. For security this page never accepts
> or displays the key." **Never add an input for the API key anywhere in the app.**
>
> **Today's usage** as one horizontal stacked bar drawn to scale against `daily_limit`:
>
> - Reserved today, `reserved_today`, in the accent colour
> - Held back for live lookups, `live_lookup_reserve`, in a warning tint
> - Still available, the remainder, as the empty track
>
> Label the scale with 0 and `daily_limit`. Under the bar, three figures: Reserved today, Held back
> for live lookups, Still available.
>
> Below that, a muted line: "proxycheck's own counter reads `provider_reported_today`. It runs a few
> minutes behind, so our counter is the one the jobs trust." If `provider_reported_today` is more than
> 5% above `reserved_today`, turn that line into a warning: "proxycheck reports more use than we
> reserved. Something outside this pipeline may be using the key."
>
> Show "As of `as_of`" at the bottom and refresh the page data every 60 seconds.
>
> ## Copy and behaviour rules
>
> - Every yes/no value from the API has three states. `true` is Yes, `false` is No, and `null` is a
>   muted em-dash meaning "no answer". Never display `null` as No.
> - The word is **Agreement**, never Accuracy.
> - There is no revenue anywhere in this product. Do not add any.
> - Show times as relative with the exact UTC time on hover, and label every schedule as UTC.
> - Every destructive or money-spending action names exactly what will happen in its button text.
> - Keep the existing visual style. Do not restyle pages that are not listed here.
