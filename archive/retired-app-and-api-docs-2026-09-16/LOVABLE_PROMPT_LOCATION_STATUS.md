# Lovable Prompt — Two new location statuses (update message)

Paste this **only if the app already has `LOVABLE_PROMPT_FINAL_APP.md` applied** (and the delta prompts
you pasted after it). If not, paste `LOVABLE_PROMPT_FINAL_APP.md`: it already contains this. The API
returns the new values since 16 September 2026.

---

> The API now returns two more location statuses. Update the app; change nothing else.
>
> 1. In `src/lib/api/contract.ts`, `GeoStatus` becomes
>    `'agreed' | 'nearby' | 'same_state' | 'single_source' | 'vendors_disagree' | 'no_answer'`.
> 2. Location status pills everywhere (IP Lookup card, bulk results, Resolved IPs table and its geo_status filter):
>    `agreed` → success "Vendors agree"; `nearby` → success "Same area" (tooltip "Vendors name the same state and
>    places within 25 km"); `same_state` → neutral "Same state" (tooltip "Vendors agree on the state; the cities are
>    more than 25 km apart"); `single_source` → neutral "One source"; `vendors_disagree` → warning "States differ";
>    `no_answer` → neutral "No location". Any other value: neutral pill with the raw text.
> 3. `CoverageCounts` gains `geo_nearby: number`, `geo_same_state: number` and `geo_state_agreed_pct: number | null`;
>    `geo_disagree_or_missing` now means "no two vendors name the same state, or no location".
> 4. Enrichment Coverage page: tile 4 keeps `geo_agreed_pct`% and adds "State agreed: `geo_state_agreed_pct`%" and
>    "`geo_disagree_or_missing` where states differ" underneath. Under the tiles add a thin 100% stacked bar for the
>    last 30 days: agreed (success), nearby (lighter success), same_state (neutral), states differ or missing
>    (warning), one source (muted), with a legend and counts. Add the two new fields to the day-by-day table.
