# IP Intelligence: the owner's requirements (non-negotiable)

These are every requirement the owner has set for this project. They apply to all work: pipeline, tables, docs, app and product. **If anything else (docs, plans, code comments, earlier notes) disagrees, this file wins.** Never soften, drop or re-interpret a requirement without the owner's explicit approval in chat.

## 1. Data and tables
1. **Core tables:** `unified.ip_geo` and `unified.ip_intelligence` are the source of truth and the product core.
   - The analytics tables, `ip_profile`, the app files and any API are **copies built from them**, never replacements.
2. **Sources:** `raw.raw_tune_clicks`, `unified.unified_session_summary` and `experimentation_tools.experiment_router_events`, plus any source added later through the base-table registry.
   - **All sources are read only:** never write to them.
3. **Every IP included:** every unique public IPv4 from every source is in both unified tables.
   - New IPs are **appended**.
   - Existing IPs are **updated**.
4. **Latest timestamp wins:** when an IP returns, the latest answer replaces the old one.
   - **FraudLogix:** the latest decided click wins. When clicks share the exact same timestamp, the tie is broken the same way every run: FLAGGED first, then reason. Decision and reason always come from one click.
   - **proxycheck.io:** re-checked when the IP returns and its answer is over 30 days old.
5. **Reliable answer:** every IP has at least one, meaning **FraudLogix decided, or proxycheck.io answered**. **IP2Proxy PX12 alone never counts.**
6. **FraudLogix (`fraudlogix_tune`) is a stand-alone reliable source.**
   - Its real decisions, flags, `is_bot` and reasons are **never overwritten**.
   - Empty FraudLogix rows (FraudLogix saw the click but never decided) are filled from proxycheck.io and marked `FILLED_FROM_PROXYCHECK_IO`. A later real decision replaces them.
7. **Every column is filled wherever a vendor gives data.** A cell is empty only when the vendor gave no answer or never supplies that column.
8. **Schema:** no column is added, changed or removed without the owner's approval.
   - **Approved additions:** `is_flagged`, `flagged_reason`, `bot_reason`.
   - **Who changes unified:** the builder role cannot alter the `unified` database; an admin or the owner runs the ALTER.
9. **The combine rule (owner, 19 Sep) applies to every current and future source.** Every IP is checked for a reliable, complete answer:
   - **Answered by its original source:** inserted or updated by the latest timestamp.
   - **Partially answered** (e.g. FraudLogix decided but never supplies ISP, ASN, compromised, scraper, anonymous): combined with proxycheck.io. Only empty columns are filled, FraudLogix's own values stay, and the filled columns survive later re-reads of FraudLogix.
   - **Not answered** (FraudLogix undecided, or the IP was seen only in sessions or router events): proxycheck.io resolves it.
   - **Whenever proxycheck.io is asked,** its full answer is also stored as its own `(IP, proxycheck_io)` row, for vendor comparison.
10. **Unresolved IPs:** any unresolved public IP, of any age or source, is queued automatically and resolved first.
    - **Exceptions:** private or reserved addresses, and IPs proxycheck.io has no record of. These are reported, not hidden.

## 2. Bot / bad-signal standard (step 2, owner decision 19 Sep)
11. **`is_bot` = bad signal, not only bot:**
    - **FraudLogix:** the latest decision is FLAGGED for **any** reason: PROXY, VPN, MOBILE_PROXY_SIGNALS, ABNORMAL_TRAFFIC_PATTERNS, BASIC_FRAUD, MASKED_DEVICES, BOT_GENERATED, NON_HUMAN_SCRIPT, SPOOFED, DATA_CENTER, TOR, TOR_EXIT_NODE, OTHER_REASON, 8, 9, 10, NOT_APPLICABLE.
    - **proxycheck.io:** proxy, VPN, TOR, datacenter/hosting, compromised server, scraper, any proxy or threat type (SOCKS/HTTP/Shadowsocks/OpenVPN/Inference Engine…), a cloud network (`CLOUD_ASNS`), or risk score 67+.
    - **IP2Proxy:** listed.
12. **Per IP:**
    - **bad** if FraudLogix **or** proxycheck.io says so;
    - **clean** if either answered and neither says bad;
    - **unknown** otherwise.
    - **No "suspicious" tier.** IP2Proxy is supporting evidence only.
13. **Reasons:** every bad row carries its reason in `bot_reason`; the vendor's own reason is in `flagged_reason`.
    - `is_bot` must always equal `is_flagged`.
    - `signal_type` (automation / behaviour / anonymiser) is a breakdown and filter only. It never changes a verdict.

## 3. proxycheck.io budget and schedule
14. **Current plan: $199.99/month, 5.12M queries/day, this month only.**
    - **Owner decision, 20 Sep:** no 50k enrichment cap this month (`daily_budget` 5,090,000).
    - **Owner's reserve:** **30,000/day stays reserved** for the owner's own use (`live_reserve` / `topup_keep`).
15. **From next month:** the owner switches to the **$10 plan**.
    - **Before the switch,** get the owner's split between enrichment and their own use.
    - **Why:** if the plan's limit is below the 30k reserve, enrichment would get 0.
    - **Never raise spending** without asking.
16. **Schedule (IST):** daily load 13:00; proxycheck.io 05:45 (after the 05:30 quota reset) and right after the load. Unified tables are published only after all checks pass.
17. **Live proxycheck.io calls** for a future lookup API are **off** unless the owner approves a budget for them.

## 4. Safety and access
18. **Production must never be disturbed:** nothing may be modified, deleted or added in production in a way that affects the existing system or any dependency.
    - **Read only:** `raw`, `unified.unified_session_summary`, `experimentation_tools`, `sampledb`.
    - **Never touched:** `ip-database`.
19. **Athena:** only the `ipintel_etl` workgroup, **never `primary`**.
20. **AWS:** only the `ipintel-builder` profile. The default profile (`alyson-training-app`) is never used, and permission boundaries are never worked around.
21. **Keys:** stay in Secrets Manager and are **never shown**.
22. **Nothing is deleted** (data, tables, S3 folders, old IPs) without the owner's go-ahead. Retention rules are the owner's decision.
23. **Before every deploy:** back up the running code to `archive/deployed-code-before-<change>-<date>/`, and keep rollback snapshot ids for every table change.
24. **Nothing dummy or benchmark:** no sample, placeholder, example or made-up numbers, logos, testimonials or prices anywhere. When data is missing, say so honestly.

## 5. Truth and accuracy
25. **Ground truth:** `sampledb.revenue_leads_plus` (`expected_revenue > 0` = paying; `fake = true` = known fake), joined on `utm_content = session_id`.
    - The session `has_revenue` flag is **not** revenue and is never used.
26. **Before any rule is used,** test it against the paying-customer IPs, and report the results honestly (including uncomfortable findings).

## 6. Delivery and communication
27. **Docs:** Markdown files only. **Never create HTML pages or artifacts.**
28. **Lovable:** company account, **no GitHub**.
    - **Data:** reaches the app via the Data Upload page, and via S3 once the read-only key exists.
    - **No direct pushes:** a direct push from the pipeline to Lovable is not rebuilt without the owner's OK.
29. **Design:** only the **Alyson brand guidelines** (`Alyson Brand Guidelines - UI _UX.pdf`).
    - **Colours:** `#F8FAFC` background; white cards, `#E5E7EB` border, 12px radius; single accent `#2563EB` / `#3B82F6`; verdict colours only as small dots and chips.
    - **Type and layout:** Inter; 8px grid; 240px sidebar `#F1F5F9`; Lucide icons.
30. **Public pages:** no vendor names until the vendor-licence check allows it. No selling outside the company until the vendor licences and privacy (DPA, policy) are cleared.
31. **Answers:** short and simple when the owner asks. Report outcomes faithfully, including failures, and confirm before anything outward-facing.

## Where things are
- **How the system works and daily flow:** `docs/SYSTEM_GUIDE.md`.
- **Rules and column meanings:** `IS_BOT_MAPPING.md`.
- **Product:** `SAAS_PRODUCT_BLUEPRINT.md`; app prompts `LOVABLE_PROMPT_SAAS.md`, `LOVABLE_PROMPT_LANDING.md`.
- **Admin requests:** `ADMIN_DELETION_STEPS.md`.
- **Checks:**
  - `build/pipeline/sql/checks/final_verification.sql` (both unified tables);
  - `build/pipeline/sql/checks/source_mapping_verification.sql` (every source IP mapped correctly).
- **Pipeline code:** `build/pipeline/src/`. Deploy by zipping `*.py` and updating both `ipintel-free-daily` and `ipintel-proxycheck-daily`.
