# Lovable prompts: Alyson Traffic Intelligence landing page

This is a public marketing site in front of the app, in the style of your references (Veris, NuroAI) and Claude's landing pages:
- a floating pill navigation;
- a big centred headline;
- a product shot with floating metric cards;
- a bento feature grid;
- how it works, trust, FAQ and a closing CTA.

It follows **only the Alyson brand guidelines** and **your requirements** (`SAAS_PRODUCT_BLUEPRINT.md`, "Your requirements").

**How to use this pack:**
- **Order:** add L0 to Knowledge once, then send L1–L6 one at a time and check each.
- **Assets:** in `landing-assets/`, upload them to Lovable (see "Assets").
- **App safety:** nothing in the signed-in app changes. Every prompt says so, and the checklist at the end verifies it.

**Four differences from the reference designs, all because of your requirements:**

| References show | This page does instead | Why |
|---|---|---|
| "Trusted by" logo strip (Airbnb, GitHub…) | **Leave it out** until real customers agree to be named | Nothing dummy (requirement 18) |
| Testimonials with names and photos | **Leave it out** until real quotes exist | Nothing dummy |
| Made-up dashboard numbers ($7,85421, 88%…) | **Only real numbers from our own data**, with an "as of" date | Nothing dummy |
| Pricing table | **"Request access"**, no prices until you set them | Blueprint: pricing is your decision |

Vendor names (FraudLogix, proxycheck.io, IP2Location) are **not** shown on the public page. It says "multiple independent IP-intelligence sources" until the licence check in the blueprint (section 0) confirms we may name them.

---

## L0: add to Project Knowledge (below the existing Prompt 0 text)

> **Marketing site rules:**
> - **Separate from the app.** The public site lives in `src/marketing/` and its own public layout. It must never import from, restyle, or change any signed-in app page, route, component, data loader, table or auth logic.
> - **Brand:** only the Alyson brand guidelines, with the same tokens as the app:
>   - Colours: `#F8FAFC`, white cards, `#E5E7EB` borders, 12px radius, single accent `#2563EB` / `#3B82F6`.
>   - Typography: Inter, 8px grid.
>   - Icons: Lucide outline.
>   - Verdict colours only as small dots and chips.
> - **Nothing dummy:**
>   - No fake customer logos, testimonials, ratings, user counts or made-up metrics.
>   - Every number comes from `src/marketing/content/facts.ts`, with its "as of" date.
>   - A section with no real content yet is simply not rendered.
> - **Wording:** no vendor names on public pages. Say "multiple independent IP-intelligence sources".
> - **Honest verdict story:**
>   - An IP is **bad** when any source flags it (bots, automation, fraud patterns, proxies/VPNs, datacenter/cloud, high risk).
>   - Every verdict comes with its reason.
>   - Never claim "blocks fraud" or "stops all bots". Say "identifies", "explains", "scores".

---

## L1: routes and public layout (without touching the app)

> Add a public marketing site **without changing the signed-in app**.
>
> 1. **Routes.**
>    - Public: `/` (landing), `/security`, `/request-access`, `/privacy`, `/terms`.
>    - **Visitors who aren't signed in** see the landing page at `/`.
>    - **Signed-in users** who open `/` see exactly what they see today (the app's Overview). Do not move or rename any existing app route.
>    - The app's sign-in page stays where it is.
> 2. **Layout.** Create `src/marketing/MarketingLayout.tsx`. It uses its own header and footer, never the app sidebar.
> 3. **Header:** a floating pill nav, like the references.
>    - Centred, max-width 1080px, white with a `#E5E7EB` border, radius 999px, subtle shadow, sticky 16px from the top.
>    - **Left:** logo "Alyson" and a muted "Traffic Intelligence".
>    - **Middle links:** Product, How it works, Trust, FAQ (smooth-scroll anchors on `/`), and Security (`/security`).
>    - **Right:** "Sign in" (secondary button, to the existing sign-in) and "Request access" (primary `#2563EB` button, to `/request-access`).
>    - **Mobile:** collapses into a sheet menu.
> 4. **Footer:** four columns:
>    - brand and a one-line description;
>    - Product (anchors);
>    - Company: Security, Request access;
>    - Legal: Privacy, Terms.
>    Then a bottom line "© {current year} Alyson".
> 5. **Content files:** put all copy in `src/marketing/content/copy.ts` and all numbers in `src/marketing/content/facts.ts` (below), typed with the props in "Component props".
>
> **Check:** sign in and confirm every app page looks and works exactly as before.

`src/marketing/content/facts.ts` (real numbers from our tables, 19 Sep 2026; update with each release):

```ts
export const FACTS = {
  asOf: '2026-09-19',
  ipsAnalysed: 4_989_853,            // public IPs across our 3 traffic sources
  ipsWithVerdict: 4_989_792,         // every public IP has a reliable answer (99.99%)
  vendorAnswers: 14_513_895,         // source answers stored (one row per IP per source)
  trafficSources: 3,                 // click stream, website sessions, experiment router
  refresh: 'daily',                  // new IPs added and answered every day
  rulesTestedOnPayingIPs: 1_044,     // verdict rules tested against real paying customers
  last30Days: { visits: 188_676, uniqueIps: 81_910, badPct: 37.7, strictBadPct: 20.2 },
} as const
```

---

## L2: hero section

> Build the landing hero in `src/marketing/sections/Hero.tsx`, in the style of the references and the Alyson brand.
> - **Background:** `landing-assets/hero-backdrop.svg` (soft blue glow, faint grid, two thin orbit lines), full-bleed, behind the content.
> - **Eyebrow chip:** "IP intelligence · updated daily". A small white pill with a blue dot.
> - **Headline:** Inter 56px desktop / 36px mobile, weight 700, tight tracking, `#111827`. "Know which traffic is real."
> - **Subhead:** 18px, `#6B7280`, max 620px. "Every visitor IP gets a verdict, a reason and a location, from multiple independent intelligence sources, checked every day."
> - **CTAs:** primary "Request access" (to `/request-access`) and secondary "See how it works" (scrolls to `#how`).
> - **Product shot** under the CTAs:
>   - a **real screenshot of our app's Overview page** (upload `overview.png`, see Assets);
>   - inside a white card with 12px radius, a `#E5E7EB` border and a soft shadow, slightly tilted into perspective on desktop, flat on mobile.
> - **Floating metric cards** around the product shot, as in the references. They are small white cards with a gentle float animation (4–6px, 6s loop), and **only real facts** from `FACTS`:
>   - "IPs analysed": `ipsAnalysed`, formatted 4.99M;
>   - "With a verdict": `ipsWithVerdict / ipsAnalysed` %, shown as 99.99%;
>   - "Traffic sources": `trafficSources`;
>   - "Refresh": "Daily".
>   Each card has a muted "as of {asOf}" line.
> - **Honest caption** under the shot: "Screenshot of the live product. Figures from our own traffic, as of {asOf}."
> - **Accessibility:** the float animation respects `prefers-reduced-motion`.

---

## L3: product sections

> Add these sections to the landing page, in order. Each is a separate component in `src/marketing/sections/`, with anchor ids as noted. Use the Alyson layout rhythm: sections 96px apart on desktop, 64px on mobile; section title 36px/700; section eyebrow 13px uppercase `#2563EB`.
>
> 1. **Problem** (`#product`):
>    - Eyebrow "The problem". Title "Paying for traffic you can't see".
>    - Three cards with Lucide icons:
>      - "Automation and bots": ShieldAlert, "Scripts, headless browsers and click farms look like visitors."
>      - "Hidden infrastructure": Server, "Datacenter, cloud and proxy traffic blends into real audiences."
>      - "One source isn't enough": Layers, "A single vendor misses what others catch. Answers disagree."
> 2. **How it works** (`#how`):
>    - Title "One IP, every source, one verdict".
>    - Left: `landing-assets/ip-network.svg`.
>    - Right, 3 numbered steps:
>      1. "Collect": every IP from your click stream, website sessions and experiments, as it arrives.
>      2. "Combine": multiple independent intelligence sources answer; gaps in one are filled by another; the latest answer always wins.
>      3. "Explain": a bad / clean / unknown verdict with the exact reason, location and network, in the tables, the API and dashboards.
> 3. **Features bento grid**, like the references' "Why teams love us": a 3-column grid of cards (2 large, 4 small).
>    - Each card has a title, one line of text, and a small visual built from **real UI pieces** (verdict chips, a reason list, a sparkline from `traffic_analytics.json` shape). No fake numbers: visuals carry no figures, or real `FACTS`.
>    - Cards:
>      - "Verdict with a reason" (large): chips `Bad · BOT_GENERATED`, `Bad · CLOUD_ASN`, `Clean`;
>      - "Traffic quality by source" (large): affiliates, campaigns, experiments, devices, regions;
>      - "Reasons you can filter": automation, behaviour and anonymiser signals;
>      - "Network intelligence": cloud, datacenter, VPN, proxy and mobile shares;
>      - "Updated every day": new IPs added, returning IPs refreshed, and every run checked before it's published;
>      - "API and bulk lookups", with a small "Coming soon" chip (the API is not live yet).
> 4. **Numbers band:** a full-width white band with 4 big metrics from `FACTS`: IPs analysed, with a verdict, source answers stored, rules tested on paying customers. Each has an "as of {asOf}" caption.
> 5. **Trust** (`#trust`):
>    - Title "Accuracy you can check".
>    - Two cards:
>      - "Tested on real customers": "Every rule is tested against IPs of {rulesTestedOnPayingIPs} paying customers, and the results are published in the product, including where a signal also flags real people (e.g. VPN users)."
>      - "Checked before it's published": "Each daily run passes automatic checks (no duplicates, no unanswered IPs, every verdict has a reason) before the data goes live. A failed run never replaces good data."
>    - A link to `/security`.
> 6. **FAQ** (`#faq`): an accordion.
>    - Left: title "Questions, answered".
>    - Right, 6 items:
>      - "What counts as a bad IP?": "Any IP a source flags: automation or bots, fraud patterns, proxies or VPNs, datacenter or cloud networks, or a high risk score. Each verdict shows which one, so you choose what to act on."
>      - "Where does the data come from?": "Your own traffic (click stream, website sessions, experiments), checked against multiple independent IP-intelligence sources."
>      - "How fresh is it?": "New IPs are added and answered every day; returning IPs are refreshed so the latest answer always wins."
>      - "Can I use it from my systems?": "Yes: the lookup API and bulk enrichment are coming. Request access to join early."
>      - "Is my data secure?": "Data is read only, keys stay server-side, access is per organisation, and IPs are never put in URLs or third-party analytics. See Security."
>      - "Is there a free trial?": "Request access and we'll set you up."
> 7. **Closing CTA:**
>    - A large rounded panel with a soft blue gradient (`rgba(37,99,235,0.08)` → white).
>    - Title "See your traffic clearly". Primary "Request access".
>    - Below it, a second **real** app screenshot (`traffic-quality.png`) in the same card frame as the hero.
>
> **Do not add:** a logo strip, testimonials, a pricing table, ratings or any number not in `FACTS`.

---

## L4: pages: Request access, Security, Privacy, Terms

> 1. **`/request-access`:**
>    - A centred card form: full name, work email, company, role (select), monthly visits (select: <100k, 100k–1M, 1M–10M, 10M+), "What would you like to see?" (textarea).
>    - Store submissions in a new Lovable Cloud table `access_requests` (`id`, `created_at`, `name`, `email`, `company`, `role`, `monthly_visits`, `message`, `status` default `new`).
>    - **Access:** row-level security lets anyone insert, and only platform admins read.
>    - **Protection:** validate the email format, rate-limit to 3 submissions per email per day, and add a honeypot field.
>    - **Success state:** "Thanks, we'll be in touch." Never send data to third parties.
>    - **Admin:** add an "Access requests" tab to the existing internal Admin page (platform admins only). This is the only change inside the app, and it's additive.
> 2. **`/security`:** a simple article page, sections:
>    - Data handling: read only, per-organisation access, row-level security.
>    - Secrets: server-side only.
>    - Checks before every data release.
>    - No IPs in URLs or third-party analytics.
>    - Contact for security questions.
>    All statements must stay true to the Knowledge rules.
> 3. **`/privacy` and `/terms`:** show the heading plus "This document is being prepared by our legal team." **Do not write or generate legal text.**

---

## L5: polish: motion, SEO, performance, accessibility

> - **Motion (brand: subtle):**
>   - sections fade and rise 12px on scroll-in (once);
>   - hero cards float gently;
>   - buttons shift colour on hover;
>   - all motion off when `prefers-reduced-motion` is set.
> - **SEO:**
>   - Title "Alyson Traffic Intelligence: know which traffic is real".
>   - Meta description from the hero subhead.
>   - Open Graph and Twitter card use `og-image.png` (1200×630, from `landing-assets/og-image.svg`).
>   - Canonical URL, `robots.txt`, and `sitemap.xml` for the public routes only. App routes are `noindex`.
> - **Performance:**
>   - lazy-load images below the fold;
>   - serve screenshots as WebP at 1x and 2x;
>   - use the Inter variable font with `font-display: swap`;
>   - target Lighthouse ≥ 95 for performance, accessibility and SEO.
> - **Accessibility:**
>   - AA contrast;
>   - visible focus rings in `#2563EB`;
>   - one `h1`;
>   - landmarks (`header`, `main`, `footer`);
>   - the FAQ accordion is keyboard-operable;
>   - every image has alt text.
> - **Analytics:** optional page-view counting in Lovable Cloud only (route and timestamp). Never store IP addresses or send them to third parties.

---

## L6: final check (paste as the last prompt)

> Check and fix, without changing app behaviour:
> 1. **App unchanged:** signed out, `/` shows the landing page. Signed in, `/` and every app page look and work exactly as before (sidebar, Overview, IP Lookup, Data Upload, reports).
> 2. **Real numbers only:**
>    - no logo strip, testimonials, pricing or made-up numbers anywhere;
>    - every figure comes from `FACTS` and shows "as of";
>    - no vendor names on public pages.
> 3. **Brand:** only the tokens (`#F8FAFC`, white, `#E5E7EB`, `#2563EB`/`#3B82F6`, text `#111827`/`#6B7280`, and verdict colours only in chips); Inter; 240px sidebar untouched in the app.
> 4. **Mobile 375px:** no horizontal scroll, the nav collapses, and the hero shot and cards stack.
> 5. **Request access:** saves a row, the success state shows, and the admin tab lists it.

---

## Component props (for Lovable to type the sections)

```ts
// src/marketing/types.ts
export type Fact = { label: string; value: string; asOf: string }          // value already formatted, e.g. "4.99M"
export type Cta = { label: string; href: string; variant: 'primary' | 'secondary' }
export type HeroProps = { eyebrow: string; title: string; subtitle: string; ctas: Cta[]
  screenshot: { src: string; alt: string }; floatingFacts: Fact[]; caption: string }
export type FeatureCard = { title: string; body: string; icon: string /* Lucide name */; size: 'lg' | 'sm'
  visual?: 'verdict-chips' | 'source-table' | 'reason-filter' | 'network-shares' | 'daily-refresh' | 'api'; badge?: 'Coming soon' }
export type Step = { n: number; title: string; body: string }
export type FaqItem = { q: string; a: string }
export type SectionProps = { id?: string; eyebrow?: string; title: string; subtitle?: string }
export type NumbersBandProps = { facts: Fact[] }
export type TrustCard = { title: string; body: string; link?: { label: string; href: string } }
export type ClosingCtaProps = { title: string; cta: Cta; screenshot: { src: string; alt: string } }
```

---

## Copy deck (all public copy, in one place)

| Place | Text |
|---|---|
| Hero eyebrow | IP intelligence · updated daily |
| Hero title | Know which traffic is real. |
| Hero subtitle | Every visitor IP gets a verdict, a reason and a location, from multiple independent intelligence sources, checked every day. |
| CTAs | Request access · See how it works |
| Problem | Paying for traffic you can't see |
| How it works | One IP, every source, one verdict (Collect → Combine → Explain) |
| Features | Verdict with a reason · Traffic quality by source · Reasons you can filter · Network intelligence · Updated every day · API and bulk lookups (coming soon) |
| Trust | Accuracy you can check |
| FAQ | Questions, answered |
| Closing | See your traffic clearly |
| SEO title | Alyson Traffic Intelligence: know which traffic is real |

---

## Assets

| Asset | Where it comes from | What to do |
|---|---|---|
| `hero-backdrop.svg` | `landing-assets/` (made for you, brand colours only) | Upload to Lovable; hero background |
| `ip-network.svg` | `landing-assets/` | Upload; "How it works" illustration |
| `og-image.svg` | `landing-assets/` | Export to PNG 1200×630 (open in a browser, screenshot, or any SVG→PNG tool) and upload as `og-image.png` |
| `overview.png` | **You:** a screenshot of the app's Overview page after Prompt 2, at 1440px wide | Upload; hero product shot (real UI, real data) |
| `traffic-quality.png` | **You:** a screenshot of the Traffic Quality page | Upload; closing CTA shot |
| Logo | Your existing Alyson logo file | Upload as `logo.svg` / `logo.png` and use in the header, footer and favicon |
| Icons | Lucide (already in the app): ShieldAlert, Server, Layers, Network, Filter, RefreshCw, Code2, Lock, CheckCircle2 | No upload needed |
| Font | Inter (Google Fonts, variable) | Loaded by L5 |

**Screenshot tips:**
- Take them after the brand restyle (Prompt 1) and with real data loaded.
- Crop to the content area, hiding any personal or customer-identifying values.
- No raw IP addresses should be visible.
