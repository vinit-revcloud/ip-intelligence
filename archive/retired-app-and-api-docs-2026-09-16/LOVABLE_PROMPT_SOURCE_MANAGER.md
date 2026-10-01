# Lovable Prompt — Source Manager (add / edit / delete / diagnose)

The API is now **writable**. The source registry moved from a static file to DynamoDB, and every
source can be created, edited, disabled, deleted and probed live from the UI.

No env changes — same `IPINTEL_API_URL` and `IPINTEL_API_TOKEN`. Paste everything below as one
message.

---

> Rebuild `/sources` into a full Source Manager. The API now supports writes and a live diagnose
> probe. Nothing about a source may be hardcoded in a component.
>
> ## Endpoints
>
> ```
> GET    /sources                    → { count, sources: SourceRecord[] }
> POST   /sources                    → create (201) | 409 if the id exists
> GET    /sources/{id}               → one record
> PATCH  /sources/{id}               → partial update
> DELETE /sources/{id}               → remove from the registry
> POST   /sources/{id}/diagnose      → probe one source, returns Diagnosis
> POST   /diagnose                   → probe every enabled source
> ```
>
> ## Contract — `src/lib/api/contract.ts`
>
> ```ts
> export type SourceKind = 'database' | 'api' | 'internal_feed' | 'validator'
> export type Capability = 'geo' | 'risk' | 'asn' | 'validator'
> export type DiagnosisStatus = 'healthy' | 'failed' | 'needs_credential' | 'stale' | 'unknown'
>
> export type SourceRecord = {
>   id: string; company: string; product: string; kind: SourceKind
>   cost_model: string; plan: string | null; limit: string | null
>   capabilities: Capability[]
>   probe_type: 'http' | 'file' | 'athena' | null
>   probe_target: string | null
>   credential_ref: string | null      // Secrets Manager NAME, never a key
>   enabled: boolean; owner: string; note: string | null; url: string | null
>   created_at: string; updated_at: string
>   diagnosis_status: DiagnosisStatus
>   last_diagnosis: string | null      // JSON string of the last Diagnosis
> }
>
> export type Diagnosis = {
>   id: string; checked_at: string; probe_type: string | null; probe_target: string | null
>   status: DiagnosisStatus; detail: string; latency_ms: number
>   http_status?: number; objects?: number; sample?: string
> }
> ```
>
> ## Server functions — `src/lib/api/sources.functions.ts`
>
> `listSources`, `createSource`, `updateSource`, `deleteSource`, `diagnoseSource`, `diagnoseAll`.
> Each is a `createServerFn` reading `IPINTEL_API_URL` / `IPINTEL_API_TOKEN` **inside** `.handler()`.
> Non-OK responses throw with the status code and the API's `error` string — the API returns useful
> validation messages and the user must see them verbatim. After any mutation, call
> `router.invalidate()` so the table refetches.
>
> ## Page layout — `/sources`
>
> **1. KPI row:** Total Sources · Enabled · Healthy (`diagnosis_status === 'healthy'`) ·
> Needs Attention (status `failed`, `needs_credential` or `stale`, `tone="warn"`).
>
> **2. Toolbar:** a **"+ Add source"** primary button and a **"Diagnose all"** secondary button.
> "Diagnose all" calls `POST /diagnose`, shows a spinner while running, then a toast reading
> `Checked {checked} · {healthy} healthy · {failing} need attention`.
>
> **3. Table** (`DataTable`, `minWidth={1240}`), enabled rows first:
>
> Source (company + product) · Kind · Capabilities · Plan · Limit · Cost · Status · Last checked ·
> Actions
>
> - **Capabilities** as small `Pill`s from the array.
> - **Status** is a `StatusPill` mapping: `healthy`→good, `failed`→bad, `needs_credential`→warn,
>   `stale`→warn, `unknown`→neutral. Beside it show the `detail` from `last_diagnosis` (parse the
>   JSON string) truncated to 60 chars with the full text as `title`.
> - **Last checked** = relative time from the parsed `checked_at`, or "never".
> - **Actions** per row: `Diagnose` · `Edit` · `Enable`/`Disable` toggle · `Delete`.
> - A row with `enabled === false` renders at 60% opacity.
> - Where `note` is set, render it under the product name in `text-[11px] text-muted-foreground`,
>   **not truncated**. Several of these notes are the most important text on the page — geojs.io
>   being a MaxMind mirror, PX12 answering 1 of 511, ip-api.com excluded on licence grounds.
>
> **4. Add / Edit drawer.** A `Drawer` with a form covering every writable field: company, product,
> kind (select), capabilities (multi-checkbox), cost_model, plan, limit, probe_type (select:
> http/file/athena), probe_target, credential_ref, owner, url, note, enabled. On create, `id` is
> also required — lowercase snake_case, validated client-side.
>
> `credential_ref` has helper text: *"Name of the secret in AWS Secrets Manager, e.g.
> `ipintel/vpnapi`. Never paste an API key here — the API rejects anything not starting with
> `ipintel/`."*
>
> On save, show the API's error string if the request fails — do not swallow it or substitute a
> generic message.
>
> **5. Diagnosis drawer.** Clicking a status pill or `Diagnose` opens a `Drawer` showing the full
> `Diagnosis`: status pill, detail, latency, probe type and target, HTTP status or object count, and
> the raw `sample` in a `CodeBlock` when present.
>
> **6. Delete confirmation.** A `Drawer`, not a native `confirm()`. State the source name and show
> the API's note: historical observations are retained in the data lake; only the registry entry is
> removed. Require the user to type the source id to confirm.
>
> ## Behaviour that matters
>
> - **After editing `probe_target`, `probe_type`, `credential_ref` or `enabled`, the API sets
>   `diagnosis_status` to `stale`.** Surface that: the row shows a warning pill reading "re-run
>   diagnose" and the response's `diagnosis` field appears in the success toast. A stale diagnosis
>   is a claim about a configuration that no longer exists.
> - **`needs_credential` is not a failure.** MaxMind returns HTTP 401 without its licence key —
>   that is unconfigured, not broken. Render it warn, never bad, and show which secret it wants.
> - Never render a raw credential anywhere. `credential_ref` is a name.
>
> ## Constraints
>
> Existing primitives only (`Card`, `KpiCard`, `DataTable`, `Pill`, `StatusPill`, `Drawer`,
> `Button`, `Select`, `Callout`, `CodeBlock`, `EmptyState`, `Skeleton`). Semantic tokens only, no
> hardcoded colours or vendor names. Do not install a router, do not edit `src/routeTree.gen.ts`.
> Explicit `minWidth` on the table; no horizontal page overflow at 390px. Strict TypeScript, no
> `any`. Build must pass, no console errors.
>
> Verify with Playwright at 1280px and 390px: create a source, edit it, confirm the status flips to
> stale, run diagnose, confirm it returns healthy, then delete it.

---

## The registry as seeded — 12 sources, all free

### Enabled and scored (9)

| Source | Kind | Capabilities | Limit | Diagnose |
|---|---|---|---|---|
| **ipinfo.io** | api | geo, asn | 50k/mo w/ token | ✅ 136 ms |
| **ipwho.is** | api | geo, asn | fair use | ✅ 43 ms |
| **proxycheck.io** | api | geo, risk, asn | 1,000/day | ✅ 31 ms |
| **MaxMind GeoLite2** | database | geo, asn | — | ⚠️ needs `ipintel/maxmind` |
| **DB-IP combined** | database | geo, asn | — | ✅ 39 ms |
| **IP2Location DB11** | database | geo | — | ✅ 22 ms |
| **IP2Proxy PX12** | database | risk | — | ✅ 16 ms |
| **FraudLogix via TUNE** | internal_feed | risk | — | ✅ table of record |
| **Authoritative lists** | validator | validator | — | ✅ 530 ms |

### Disabled, deliberately (3)

| Source | Why |
|---|---|
| **geojs.io** | Byte-identical to MaxMind on all 511 IPs. Enabling it gives MaxMind two votes |
| **vpnapi.io** | Needs a free API key. Would add a third independent risk voter |
| **ip-api.com** | Free tier is **non-commercial only**. Do not enable |

Live diagnose result: **8 healthy, 1 needs credential, 0 failed.**

## Two fixes made while wiring this

1. **The Lambda role could not list the reference prefix**, so IP2Location and IP2Proxy both
   reported `AccessDenied` — they looked broken when they were fine. Added a scoped
   `s3:ListBucket` on `ip-intelligence/*`.
2. **MaxMind reported `failed`** on its 401. A source that needs a key is unconfigured, not broken;
   it now returns `needs_credential` and names the secret it wants. Otherwise every run would cry
   wolf.

## To enable vpnapi.io

1. Get the free key at vpnapi.io
2. `aws secretsmanager create-secret --name ipintel/vpnapi --secret-string '<key>'`
3. In the UI: edit `vpnapi_io` → set enabled → Diagnose

No code change, no redeploy. That is the point of the registry.
