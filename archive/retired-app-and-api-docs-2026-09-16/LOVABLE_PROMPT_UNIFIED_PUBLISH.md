# Lovable Prompt — Unified tables card and 50k / 30k split (update message)

Paste this **only if the app already has `LOVABLE_PROMPT_FINAL_APP.md` applied**. If not, paste
`LOVABLE_PROMPT_FINAL_APP.md` instead: it already contains everything below.

---

> Update the IP Intelligence app. Two changes: a read-only "Unified tables" card on the Daily Jobs page, and
> new wording for the proxycheck budget split. Do not change anything else. Keep using `IPINTEL_API_URL` and
> `IPINTEL_API_TOKEN` inside server function handlers only; never expose the token to the browser.
>
> ## 1. Types (add to the existing API types file)
>
> ```ts
> // add to Job (proxycheck job only)
> live_reserve?: number        // queries kept free every day for API lookups (30,000)
> publish_unified?: boolean    // refresh unified.ip_geo / unified.ip_intelligence after each run
>
> export type PublishedTable = {
>   table: string              // "unified.ip_geo" or "unified.ip_intelligence"
>   rows: number | null
>   files: number | null
>   samples_checked: number | null
>   dry_run: boolean
> }
> export type PublishRun = Run & { source_run: string | null; published: PublishedTable[] }
> export type PublishStatus = {
>   tables: string[]
>   last_published_at: string | null
>   last_run_id: string | null
>   last_tables: { table: string; rows: number | null }[]
>   runs: PublishRun[]         // newest first
> }
> ```
>
> ## 2. Server function
>
> In `src/lib/api/jobs.functions.ts` add `getPublish`: a `createServerFn` calling `GET /publish?limit=10`
> with `Authorization: Bearer <IPINTEL_API_TOKEN>`. Read only. A 404 means the backend part is not
> shipped: show the calm "This part of the pipeline is not available yet." panel inside the card only.
>
> ## 3. Daily Jobs page — "Unified tables" card
>
> Change the page subtitle to: "Two scheduled jobs keep the IP tables current, and every successful
> proxycheck run refreshes the two unified tables other APIs read. Times are UTC."
>
> Add a full-width card under the two job cards, titled **Unified tables**. Refresh every 60 seconds, and
> every 10 seconds while `runs[0].status` is `running`. This card is read only: no switch, no Run now, no edit.
>
> - Description: "After every successful proxycheck run, `unified.ip_geo` and `unified.ip_intelligence`
>   are refreshed from the enriched tables, so other teams' APIs read the same answers. The new copy is
>   checked before it replaces the old one, and the previous copy is kept for rollback. If any check
>   fails, the tables keep yesterday's data."
> - "Last refreshed `last_published_at`" as relative time with exact UTC on hover; `null` → "Not refreshed yet".
> - One row per `last_tables` entry: table name in monospace, `rows` with thousands separators.
> - **Newest run** (`runs[0]`): status pill (`succeeded` success, `failed` danger, `running` info with spinner,
>   `skipped` neutral), started time, duration, "Started after proxycheck run `source_run`" or "Started by
>   hand" when null, then its checks with ticks and crosses. Failed checks show `detail` in danger colour;
>   a failed or skipped run shows `message` under the pill.
> - A run whose `published` entries all have `dry_run: true` gets a neutral "Test run — tables not changed" pill.
> - If `runs[0].status` is `failed`: warning line "The unified tables still hold the previous copy. The next
>   proxycheck run will try again."
> - If `last_published_at` is more than 36 hours old and the pipeline is not paused: warning line "The
>   unified tables have not been refreshed for over a day."
> - A **History** link opens a drawer listing `runs`: started, duration, status, rows per table; clicking a
>   row expands its checks and message.
>
> ## 4. Budget wording
>
> On the proxycheck job card, replace the top-up sentence with: "`daily_budget` queries a day enrich the
> tables (backfill plus new base-table addresses). `live_reserve` queries a day always stay free for API
> lookups. Plan limit: `daily_limit`." Under it, muted: "The `topup_utc` UTC top-up only finishes the
> enrichment budget if the morning run stopped early; it never uses the lookup queries."
>
> On the proxycheck Budget page, rename "Held back for live lookups" to "Held back for API lookups" and add
> a muted line under the three figures: "Split: `batch_budget` a day for enrichment, `live_lookup_reserve`
> a day for API lookups."
>
> Rules stay the same: `null` booleans are a muted em-dash, never "No"; never add any input for API keys.
