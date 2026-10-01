# Lovable Prompt — Remove the Benchmark Pages

On 15 September 2026 the API stopped serving the one-off benchmark sample files. These endpoints now
return 404:

| Removed endpoint | Built by | Page(s) that used it |
|---|---|---|
| `GET /findings`, `GET /summary`, `GET /ip/{ip}` | LOVABLE_PROMPT_FINAL / FINDINGS | Findings page and its IP lookup card |
| `GET /console` | LOVABLE_PROMPT_REAL_DATA | Overview, Vendor Comparison, Jobs & Sampling, Operations, Sources & Plans |
| `GET /recommendations` | LOVABLE_PROMPT_RECOMMENDATIONS | Source Recommendations |
| `GET /unified/geo`, `GET /unified/intelligence`, `GET /tables/ip-proxy`, `GET /tables/ip-geo-legacy` | earlier table prompts | any page still reading them |

Everything the app should show now comes from the running pipeline: IP Lookup and Resolved IPs
(`LOVABLE_PROMPT_IP_LOOKUP.md`), the table pages, the Pipeline pages
(`LOVABLE_PROMPT_PIPELINE_CONTROL.md`) and Vendor Sources. Paste everything below the line as one
message, **after** the IP Lookup and Pipeline prompts.

---

> The API no longer serves benchmark sample data. Remove every page and component that depends on it,
> so the app shows only live pipeline data.
>
> ## Remove
>
> 1. Delete the routes and their files: `/findings`, `/recommendations`, and the Overview, Vendor
>    Comparison, Jobs & Sampling, Operations and Sources & Plans pages that read `getConsoleData`.
>    Delete their navigation entries.
> 2. Delete the server functions `getFindings`, `getSummary`, `lookupIp` **only if it calls `/ip/{ip}`**
>    (keep the new one that calls `/lookup/{ip}`), `getConsoleData`, `getRecommendations`, and any
>    function calling `/unified/geo`, `/unified/intelligence`, `/tables/ip-proxy` or
>    `/tables/ip-geo-legacy`. Delete `src/lib/api/findings.functions.ts` if nothing is left in it.
> 3. Delete from `src/lib/api/contract.ts` every type used only by the deleted pages (the findings,
>    summary, console and recommendations types). Keep every type the remaining pages use; let the
>    TypeScript compiler confirm nothing still references a deleted type.
> 4. Remove the print stylesheet added for the Recommendations page if no other page uses it.
>
> ## Keep and adjust
>
> - Make **IP Lookup** the home route (`/`), so the app opens on it.
> - Navigation, in this order: IP Lookup, Resolved IPs, Tables (the six table pages), Pipeline
>   (Safety, Base Tables, Daily Jobs, proxycheck Budget), Vendor Sources.
> - **Vendor overview – proxy** can legitimately be empty for a day or two: it is recalculated once
>   1,000 addresses have been asked of every running risk vendor. When `rows` is empty, show a calm
>   panel: "The proxy scorecard is being recalculated from the daily proxycheck.io backfill. It appears
>   after the next daily run." Never show it as an error.
> - **Vendor overview – location** now lists only the vendors the system runs: IP2Location DB11,
>   ipinfo.io, ipwho.is and proxycheck.io. Do not hardcode vendor rows; render whatever the API returns.
> - Any remaining text that mentions "benchmark", "sample", "485 IPs", "2,105 IPs", MaxMind, DB-IP,
>   GeoJS or "published ranges" as live sources: remove it.
>
> ## Check before finishing
>
> - The app builds with no TypeScript errors and no unused imports of deleted modules.
> - No request goes to `/findings`, `/summary`, `/console`, `/recommendations`, `/ip/`, `/unified/`,
>   `/tables/ip-proxy` or `/tables/ip-geo-legacy` (search the codebase for each string).
> - Every remaining page loads without an error panel.
