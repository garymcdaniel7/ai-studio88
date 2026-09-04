# AI Studio — Live UI Defect Report

**Target:** https://ai-studio88.vercel.app (Vercel production build of `/Users/garymcdaniel/kiro/ai-studio88`, `frontend/src/app`)
**Method:** page-to-page read-only QA via `browser_exec` (Browser Use harness). No account created, no credentials guessed, no code modified.
**Date:** 2026-08-23
**Severity legend:** 🔴 **Blocker** (app unusable) · 🟠 **Major** (breaks a real user flow) · 🟡 **Minor** (confusing/broken but recoverable) · ⚪ **Cosmetic** (polish/accessibility)

---

## Executive Summary

The deployed app is **rendering as a static, non-functional showcase**. Two platform-level problems disable nearly every feature:

1. **The Vercel frontend cannot reach its own Railway backend due to a CORS failure** (🔴). Every backend call from `ai-studio88.vercel.app` to `web-production-1f511.up.railway.app` is blocked in the browser (`TypeError: Failed to fetch`). The backend itself is up and healthy — the root `/` returns `{"status":"ok"}` and API routes respond — but the frontend origin is not allowed CORS. Result: a persistent "Backend unreachable — Mutations are disabled" banner on **every page**, zero data loading, and all mutation buttons dead.
2. **Authentication is disabled in production** (🟠). Supabase env vars are not configured in the deploy, so the auth gate (`frontend/src/proxy.ts`) passes *every* intended-protected route through. `/login` renders only "Authentication Unavailable" with no sign-in path, and every landing-page CTA dead-ends there.

Every page is reachable without a session (there is no enforced public/protected split in this deploy), which allowed a full audit of all 17 routes. No broken links (all nav links resolve), no layout overflow at desktop width (1440px), and clean copy in most marketing text — but the app's core actions are all dead.

---

## Route & Auth-Gate Map

| Route | Deploy behavior | Intended (per `auth-utils.ts`) |
|---|---|---|
| `/` | Public — marketing landing renders | Public (exact path) |
| `/login` | Renders **"Authentication Unavailable"** — no form/OAuth | Public |
| `/pricing` | Public — tiers render | **Not** in public list → intended protected |
| `/showcase/*` | Public images | Public |
| `/auth/callback` | Redirects → `/login?error=Authentication+cancelled` | Public |
| `/create`, `/brain`, `/projects`, `/story`, `/training`, `/talent`, `/assets`, `/publish`, `/admin`, `/admin/*`, `/editor`, `/analytics`, `/settings` | **Render without any session** (gate disabled) | Protected (gated by Supabase OAuth) |
| `/does-not-exist` | Standard Next.js 404 — sane ✅ | — |

**Auth-gate assessment:** The intended split is `/`, `/login`, `/showcase` public; everything else protected via Supabase OAuth with a `?redirect=` destination-preserving redirect (`proxy.ts`). **In this deploy the gate is fully disabled** because Supabase is unconfigured (confirmed: `/admin/keys` lists `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` as "Not configured"). The `?redirect=` preservation logic exists in code but is **never exercised** because no route redirects to `/login`. So the "protected" split is effectively **not enforced** — every studio/admin surface is publicly reachable.

---

## PAGE 1 — Global / Cross-Cutting Findings

> Findings here affect every page. They are repeated in per-page context below where relevant.

### G1 🔴 BLOCKER — Frontend cannot reach backend (CORS); app-wide banner + dead data
- **Evidence:** From the Vercel origin, `fetch("https://web-production-1f511.up.railway.app/")` → `TypeError: Failed to fetch` (CORS-blocked read). Direct navigation to the same URL returns `{"status":"ok"}`. `performance.getEntriesByType("resource")` shows every `…railway.app/…` request with `transferSize: 0` (CORS-blocked body). Backend services confirmed down: `/aios/v1/health/alerts` → `comfyui is DOWN`, `ollama is DOWN (Connection refused)`; `/api/v1/brain/health` → ollama `connected:false`.
- **Impact:** Every page shows the persistent banner; no projects/assets/talent/analytics data loads; all mutations disabled.

### G2 🟠 MAJOR — Auth gate disabled in production (no login path)
- **Evidence:** `frontend/src/proxy.ts:49` returns `NextResponse.next()` for all routes when `!isSupabaseServerConfigured`. Deploy has no Supabase env vars (`/admin/keys` shows all keys "Not configured").
- **Impact:** No sign-in/sign-up for real users; intended-protected routes exposed; `/login` is a dead end (see G3).

### G3 🟠 MAJOR — `/login` is a dead end
- **Evidence:** Body = "Authentication Unavailable — Unable to sign in. The authentication service is not configured for this environment." No form, no Google OAuth button, no inputs, no links.
- **Impact:** No user can sign up or sign in anywhere in the product.

### G4 🟠 MAJOR — Landing conversion funnel dead-ends at `/login`
- **Evidence:** On `/`, CTAs **Sign In, Get Started, Meet the Talent, Start creating, Get Started Free, Create Free Account** all href → `/login`. Only **See the Work** works (in-page `/#showcase` anchor).
- **Impact:** A prospective customer cannot proceed past the landing page.

### G5 🟡 MINOR — Marketing contradicts itself (landing vs `/pricing`)
- **Evidence:** Landing: "AI Studio **$0/month + GPU compute at cost**", "Pay ~$0.003/image (SDXL) or ~$0.01/image (Flux)", "**Unlimited** generations/training/video", "No vendor lock-in". `/pricing`: subscription tiers **$29–$999/mo** with "2,000 credits / month" (Day Player $29) etc.
- **Impact:** Conflicting pricing models confuse a prospective buyer.

### G6 🟡 MINOR — Dead primary buttons with zero feedback
- **Evidence:** Buttons across /create, /pricing, /projects, /assets, /story, /editor, /training, /admin, /publish are clickable-looking but clicking does nothing (no nav, no modal, no toast, no console error). Mutations are globally disabled by the backend-unreachable state, but buttons are **not** visually disabled and give no explanation.
- **Impact:** Feels broken rather than intentionally locked-down.

### G7 ⚪ COSMETIC — Hero image missing alt text
- **Evidence:** `/showcase/hero.png` loads (1024px) but `alt=""`. (All other 9 showcase images have proper alt text.)

---

## PAGE 2 — `/` Landing

- **F1 🟠 Major** — All conversion CTAs → dead `/login` (see G4). URL: `https://ai-studio88.vercel.app/`
- **F2 🟡 Minor** — Pricing story contradicts `/pricing` (see G5).
- **F3 ⚪ Cosmetic** — Hero image empty alt (see G7).
- **Note:** Marketing copy itself ("Meet Aria, Zuri, Malik, Kofi, Amara, and Nia — your cast of AI models…") is well-written; no typos found.

---

## PAGE 3 — `/login`

- **F4 🟠 Major** — Dead-end "Authentication Unavailable" page; no sign-in/sign-up path (see G3).

---

## PAGE 4 — `/pricing`

- **F5 🟠 Major** — **All 4 "Join the waitlist" buttons + "Request an invite" are dead.** Tested: click → no modal, no navigation, no feedback. URL `https://ai-studio88.vercel.app/pricing`.
- **F6 🟡 Minor** — The **free** tier ("Screen Test — $0/month — 250 credits/month") is gated behind "Join the waitlist" — a $0 tier shouldn't require a waitlist, and it contradicts the landing page's "Create Free Account / Get Started Free".
- **F7 ⚪ Cosmetic** — "**Hefner**" tier name ($999+, "Studio-grade, by application"). References Hugh Hefner/Playboy; questionable branding for a production product in an 18+/adult-adjacent space.
- **F8 🟡 Minor** — The "Backend unreachable" banner appears on this public marketing page (should not, and it's gated to protected routes by design intent).

---

## PAGE 5 — `/create` (Studio)

- **F9 🟠 Major** — **Primary mode buttons (Image Generation, Video Generation, Voice & Music) are dead.** Tested "Image Generation" → click produces nothing (no navigation, no panel). This is the app's core action and it does nothing.
- **(G1/G6 apply — banner + no feedback.)**

---

## PAGE 6 — `/brain` (AI Brain)

- **F10 🟡 Minor** — **Placeholder/demo content presented as real data:** hardcoded AI welcome message with a fake-looking timestamp ("Hey! 👋 Welcome to AI Studio. I'm your Creative Director AI… 06:08 PM") and personalized "Brain Memory" items ("You use FLUX for images", "You prefer cinematic visual style", "Updated 2 days ago") — none backed by any real session/data.
- **F11 🟡 Minor** — "🔴 Brain offline — check Admin → Services" (accurate — ollama/comfyui down), yet action buttons (New Chat, New, Share, Create Storyboard, Generate Prompt, Brainstorm Ideas, Suggest Music, View all, memory suggestions) are all clickable-but-dead with no feedback.
- **F12 ⚪ Cosmetic** — Engine label "Hermes — Offline" (branding quirk).

---

## PAGE 7 — `/projects`, `/assets`, `/story`, `/editor`

- **F13 🟡 Minor — /projects** — "New Project" and "Create Your First Project" dead; empty state "No projects yet" (accurate but no retry/connect hint).
- **F14 🟡 Minor — /assets** — "Upload Asset" and "Export All" dead; empty state "Upload assets to get started".
- **F15 🟡 Minor — /story** — "New Universe" dead; empty state "No universes yet".
- **F16 🟡 Minor — /editor** — "Add Shot", "Save", "Load", "Generate All (0)", "Assemble Video" all dead. "Assemble Video" appears enabled with **0 shots** (should be disabled until shots exist).

---

## PAGE 8 — `/talent`, `/training`

- **F17 🟠 Major — /talent** — **Stuck on "Loading talent…" forever.** No empty state, no error, no retry — an indefinite spinner caused by the backend-unreachable state. (Worst loading-state on the site.)
- **F18 🟡 Minor — /training** — **Quality selector labels render merged/confusing:** buttons read "**Quick | Fast**", "**Standard | Best**", "**Quality | Pro**" — name+descriptor concatenated (the third is "Quality/Pro", i.e. header+option merged).
- **F19 🟡 Minor — /training** — **Estimate contradicts the selected tier:** estimate shows "~17 min · ~$0.42 GPU cost · Provider: simpletuner" while the (default) Quick tier shows "15 min • $1.50". Neither duration nor cost matches.
- **F20 🟡 Minor — /training** — "Start Training" dead; page honestly notes "Currently runs in simulation mode — no real training occurs until infrastructure is connected" (good honesty, but the dead button + estimate mismatch is confusing).

---

## PAGE 9 — `/publish`, `/settings`

- **F21 🟡 Minor — /publish** — "Schedule Post" and "Schedule Your First Post" dead; "No platforms configured yet" and no way to connect (admin API keys all unconfigured). "Draft Mode" notice is accurate.
- **F22 🟡 Minor — /settings** — Profile shows placeholder values ("Studio Owner", "Total Generations —", "Models Trained —"); content across Profile/Preferences/API Keys/How to Use/About tabs is thin/empty.

---

## PAGE 10 — `/admin` (+ `/admin/health`, `/admin/fleet`, `/admin/keys`)

- **F23 🟠 Major — /admin** — Dashboard stuck on **"Loading services…"** indefinitely (backend unreachable). No error/empty fallback.
- **F24 🟡 Minor** — **Inconsistent admin subnav:** the sub-tab bar (Dashboard / Health / Fleet·GPU / API Keys / Settings) renders on `/admin` and `/admin/fleet` but is **absent** on `/admin/health` and `/admin/keys`. On `/admin` the tabs render as buttons, not links (inconsistent with the main nav which uses links).
- **F25 🟡 Minor — /admin/health** — "Platform is Down — Critical services are unavailable" (accurate). "Run Tests" dead. **Alert Feed labeled "Ise + Red Team"** — "Ise" looks like a stray label/typo.
- **F26 🟡 Minor — /admin/fleet** — "**Shutdown Idle**" button shown with **0 active workers** (nothing to shut down — should be disabled); "Launch Worker" and "Refresh" dead.
- **F27 🟡 Minor — /admin/keys** — **Every service key "Not configured"** (VAST, RUNPOD, B2, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, HF_TOKEN, OPENAI, ANTHROPIC, ELEVENLABS, KLING). "Save Keys" dead. (This is the on-page evidence for G2/G1.)

---

## PAGE 11 — `/analytics`, 404

- **F28 🟡 Minor — /analytics** — All metrics empty (0 Total Generations, "—" GPU Hours Used, "—" Total Spend, 0 Assets Created); charts (Generation History, Cost Over Time) render empty with **no empty-state explanation**. 7d/30d/90d buttons are plain buttons.
- **F29 ⚪ Cosmetic — /analytics** — Stat-card label/value layout is confusingly interleaved ("Total Generations / Today", "— / GPU Hours Used / This month").
- **F30 ✅ PASS — `/does-not-exist`** — Standard, sane Next.js 404 ("This page could not be found.").

---

## Top 5 Most Impactful Fixes

1. **🔴 Fix CORS on the Railway backend to allow `https://ai-studio88.vercel.app`.** This is the single highest-impact fix — it unblocks all data loading, clears the global "Backend unreachable" banner, and re-enables mutations across the entire app. (Root cause of G1, F9, F13–F17, F23, F28.)
2. **🟠 Decide and configure the production auth posture.** Either configure Supabase (set `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`, plus service key, and register the OAuth callback URI) so `/login` works, or explicitly ship a documented auth-less/demo mode. Today `/login` is a dead "Authentication Unavailable" page and the intended-protected routes are exposed. (G2, G3, F4.)
3. **🟠 Make landing-page CTAs resolve to a working destination.** Point conversion CTAs (Sign In, Get Started, Meet the Talent, Create Free Account, etc.) at a functional sign-up/sign-in path instead of a dead `/login`. (G4, F1.)
4. **🟠 Wire up or visually disable all mutation buttons.** With the backend down, buttons on /create, /pricing, /projects, /assets, /story, /editor, /training, /admin, /publish silently do nothing. Either render them disabled with a "connectivity required" tooltip/toast, or fix the underlying connectivity so they work. (G6, F5, F9, F13–F16, F20, F21.)
5. **🟠 Add error/empty fallbacks for perpetual loaders and reconcile pricing.** Replace the indefinite "Loading talent…" (/talent) and "Loading services…" (/admin) spinners with an error + retry state; and reconcile the "$0 + GPU at cost / unlimited" landing story with the "$29–$999 monthly credits" `/pricing` story. (F17, F23, G5, F2.)

---

*Report generated read-only. No account created, no credentials guessed, no code modified.*
