# AI Studio — UI Revamp Design & Requirements

**Date:** 2026-10-04
**Prepared by:** @hermes (product), with @ai-studio (pipeline) and @cto (infrastructure)
**Status:** Design spec — ready for stakeholder approval and Kiro implementation

---

## 1. Product Vision

AI Studio is an AI media generation platform for indie creators making **serialized 60-episode content** with consistent characters across every shot. Our lane is the "Episode 11" creator that Higgsfield and Kling 4.0 don't serve — they do one-off viral clips; we do production discipline that makes episode 34 look like episode 1.

The UI must communicate: **professional creative tool, not a toy.**

---

## 2. Platform Decision

**✅ Migrate to existing Next.js frontend** (`/frontend/`)

**Rationale:**
- Next.js frontend already exists with dark mode, TailwindCSS, shadcn/ui, AppShell layout
- Routes already scaffolded: `admin`, `analytics`, `assets`, `auth`, `brain`, `create`, `editor`, `login`, `models`, `production`, `projects`, `publish`, `settings`, `story`, `talent`, `training`, `workflows`
- Streamlit is prototyping layer — Next.js gives the Kling/Higgsfield-level polish you want

**⚠️ Migration cost is LOW-to-MEDIUM.** Auth/infra layer is ready. But page-level UI needs net-new components: PromptEditor, GenerationQueue, FrameGrid, WRITE 3-panel layout, MAKE Prompt Workshop. Navigation needs full rewrite (sidebar → horizontal 5-step). This is a build from spec, not a port.

**What to do with Streamlit:** Keep as legacy admin panel until Next.js reaches parity. Do not delete — archive.

---

## 3. Visual Design Direction

### Color System
- **Base:** Deep slate/navy `#0f172a` (slate-900) — full dark mode
- **Surface:** `#1e293b` (slate-800) for cards, `#334155` (slate-700) for elevated surfaces
- **Accent:** Purple `#7c3aed` — primary actions only (keep existing codebase token). Used sparingly
- **Muted:** `#64748b` (slate-500) — secondary text, borders
- **Glass:** Subtle backdrop blur on modals and overlays

**Team recommendation:** Keep purple, reduce its footprint to interactive-only (buttons, links, active nav). Strip from decorative elements. Near-monochrome Kling-style dark UI. Zero migration cost.

### Typography
- **Font:** Inter (sans-serif)
- **Scale:** 12/14/16/20/24/32/48
- **Monospace:** JetBrains Mono for prompt editing and code views

### Design Principles
| Principle | Application |
|---|---|
| **Dark first** | Full dark mode default |
| **Minimal chrome** | AppShell with slim sidebar (60px, expands on hover) |
| **Content-forward** | Storyboard frames, character cards, render previews maximize media visibility |
| **Glass/overlays** | Modals use backdrop blur (`bg-black/30 backdrop-blur-xl`) |
| **Generous whitespace** | Never cramped |
| **Micro-animations** | Subtle transitions on page load, hover states, render progress |

---

## 4. Navigation Flow

### Primary Nav (5 steps)

```
START → CAST → WRITE → MAKE → PUBLISH
```

Horizontal nav bar. Active step is accent colored. Completed steps show checkmark. Future steps are muted.

**Responsive behavior:** On viewports below 768px, the 5-step nav collapses to a **hamburger-style "Steps" dropdown** with the current step shown as the label. On tablet (768-1024px), steps become **scrollable tabs** (arrows on each side). The design doc should include a responsive breakpoint plan: `≥1024px = full horizontal`, `768-1024px = scrollable tabs`, `<768px = hamburger dropdown`.

### Page Map (Consolidated from 18 → 8)

| Step | Page | What It Does | Absorbs From Current Routes |
|---|---|---|---|
| **START** | Landing + Auth | Funnel landing → Project dashboard | Replaces dashboard |
| **CAST** | Talent Studio | Characters — ref images, face locks, LoRAs, voice | Absorbs `talent`, `models` (character-facing), `training` |
| **WRITE** | Story + Storyboard | Episode/scene/shot structure + visual storyboard + editable prompts + regenerate + upload | Absorbs `story`, **`editor` (storyboard part)**, `production` (shot sequencing) |
| **MAKE** | Generation Studio | Prompt workshop → generate → inline progress → output review | Absorbs `create`, **`editor` (gen controls)**, `workflows`, models (gen-facing) |
| **PUBLISH** | Library + Campaigns | Episode gallery, share links, asset library, content calendar | Absorbs `assets`, `publish` |
| **—** | Settings | Project config, toggles, API keys | Absorbs `settings` |
| **—** | Admin | Infrastructure, GPU workers, cost dashboard | Absorbs `admin` |
| **—** | Brain | AI chat assistant with project context | Remains at `/brain` (separate nav entry or floating widget) |

**Remaining route disposition:**
| Current Route | What Happens |
|---|---|
| `/analytics` | Merged into PUBLISH (engagement data per episode) |
| `/create` | 💀 Absorbed into MAKE |
| `/editor` | 💀 Split: timeline → WRITE, gen controls → MAKE |
| `/jobs` | 💀 Inline progress in MAKE. Delete separate page |
| `/login` | Standalone auth page (maps to START logged-out state) |
| `/brain` | Kept separate — floating chat widget available from any page |
| `/models` | Split: character models → CAST, gen models → MAKE settings |
| `/production` | 💀 Absorbed into WRITE (shot/episode sequencing) |
| `/projects` | 💀 Absorbed into START (project dashboard) |
| `/talent` | 💀 Moved to CAST |
| `/training` | 💀 Absorbed into CAST (LoRA training wizard) |
| `/workflows` | 💀 Absorbed into MAKE (workflow selector) |

---

## 5. Page-by-Page Spec

### 5.1 START — Landing + Projects

**Logged out:** Clean dark landing. Hero + CTA + 2 social proof items. No carousel, no feature grid.

**Logged in:** "Welcome back, [name]" + quick stats. Grid of recent projects. CTA: "New Project" button. Empty state: guided onboarding.

### 5.2 CAST — Talent Studio

Left: Character list (cards with avatar, name, status). Right: Character detail panel.

Character detail: Identity fields, Reference Images (upload + gallery, tagged by type), Identity Anchors (auto-extracted hair/costume/color blocks), Voice Profile, LoRA Models (with strength slider), 3-Shot Test (Lock → Turn → Environment, displayed side-by-side with pass/fail overlay).

### 5.3 WRITE — Story + Storyboard

3-panel layout: Episodes list → Storyboard (visual frame timeline) → Shot detail.

Per-frame features: View generated frames as thumbnails, Edit prompts inline (syntax-highlighted 6-section H3 format), Regenerate (same params + new seed), Upload reference images, Shot context (character, location, continuity from previous shot).

**Storyboard uses PREVIEW quality** (Turbo 4-step LoRA, 480p). Full quality renders happen in MAKE.

### 5.4 MAKE — Generation Studio

**Prompt Workshop:** Shot-type template selector (Dialogue/Action/Establishing/Reaction). Section injectors for Subject, Action, Camera, Lighting, Sound. Toggle switches (Anti-Plastic, Speed Verbs, Frame Grid). Model selector + Frame grid snap. Full prompt preview before submit.

**Controls (3 tiers):**

**Tier 1 — Always visible:** Model/checkpoint selector, CFG slider, Steps slider, Sampler + Scheduler dropdown, Seed (random/lock/manual), Aspect ratio presets, Negative prompt field.

**Tier 2 — "Advanced" accordion (collapsed):** Denoise, Batch size, CLIP skip, VAE picker, Precision, LoRA stack with per-LoRA strength, ControlNet picker.

**Tier 3 — Pipeline-level:** Shot sequence editor, Motion preset, Character + Style locks, Batch variation, Upscale stage toggle, **Quality preset toggle (Quick Preview ↔ Full Quality, referencing P8 for exact sampler/step specs)**.

**Generation Queue:** Inline progress bars per job (no separate Jobs page). Status: Queued → Running (progress %) → Completed / Failed.

**Output Review:** Grid of completed renders. Approve / Reject / Retake.

### 5.5 PUBLISH — Library + Campaigns + Calendar

**Purpose:** Organized output library, episode gallery, share links, campaign management, **and a content calendar to schedule posts**.

Episode gallery (per-episode cards with status). Share link generation. Asset library (filterable grid of all renders).

**Content Calendar:**
- Month/week/day visual calendar. Drag episodes/shots onto dates to schedule posts.
- Per-post platform selector — choose which platform(s) each post publishes to.
- Suggested optimal posting times per platform.
- Queue view with status: Queued → Published / Failed.
- Auto-post via background job at scheduled time.

**Platform Connections:**
The publishing calendar serves **both SFW and NSFW content** — every platform listed below is a first-class publishing target depending on what you're making.

| Platform | Lane | AI Content Allowed | NSFW Allowed | Requirements |
|---|---|---|---|---|
| **Instagram** | SFW | ✅ Allowed | ❌ No | Visual content (Reels, carousels, posts) |
| **X/Twitter** | SFW | ✅ Allowed | ⚠️ Gray area | Policy evolving — mature content needs warning label |
| **YouTube** | SFW | ⚠️ Allowed (labeled) | ❌ No | AI content must be labeled for Shorts/long-form |
| **Facebook** | SFW | ✅ Allowed | ❌ No | Standard Meta content policies |
| **TikTok** | SFW | ⚠️ Allowed (labeled) | ❌ No | AI-generated content must be labeled |
| **Threads** | SFW | ✅ Allowed | ❌ No | Text/image-first, Instagram-sourced |
| **Snapchat** | SFW | ⚠️ Allowed | ❌ No | Spotlight has AI labeling requirements |
| **Fanvue** | NSFW + SFW | ✅ Explicitly allowed | ✅ Allowed | AI disclosure (watermark/caption), 18+ verification, "Reasonable Person's Test" moderation |
| **OnlyFans** | NSFW + SFW | ✅ Allowed with label | ✅ Allowed | Must label #ai or #AIGenerated, must feature the verified creator |
| **LoyalFans** | NSFW + SFW | ✅ Allowed | ✅ Allowed | Consent + identity checks, AI labeling |

**Phasing:** Phase 1 = share links + library. Phase 2: NSFW platform connections roll out starting with Fanvue (most AI-friendly) and OnlyFans. Phase 3: SFW platforms (Instagram, X, YouTube, TikTok). Calendar UI built in Phase 1 as "Coming Soon" placeholder.

---

## 6. Component Architecture

| Component | Description |
|---|---|
| **AppShell** | Slim sidebar (60px, hover expand) + step indicator nav |
| **PromptEditor** | Syntax-highlighted, 6-section H3 format, collapsible |
| **PromptPreview** | Full assembled format before submit |
| **GenerationQueue** | Inline progress bars per job |
| **FrameGrid** | Media thumbnails with approve/reject overlay |
| **Storyboard** | Visual timeline, drag-reorder, click-to-edit |
| **ReferenceOrderPanel** | Picture 1/2, Video 1, Audio 1 ordering |
| **LoRAMixer** | Multi-character LoRA stack with strength sliders |
| **QAGate** | Auto-grade + "Grade this frame" button |
| **ThreeShotTest** | Side-by-side frame comparison |
| **ComingSoon** | Reusable badge for future features |
| **UploadZone** | Drag-and-drop reference image upload |
| **AuthGate** | Wraps protected content |

---

## 7. Auth Integration (C1)

| Requirement | Detail |
|---|---|
| **Login page** | `/login` — Supabase OAuth (Google + email). Dark, minimal |
| **JWT storage** | Auto-refresh on expiry. Attached to every API call |
| **API client** | Use the existing `api` object from `@/lib/api` — `api.get<T>()`, `api.post()`, `api.put()`, `api.delete()`, `api.upload()`, `api.stream()`. **Never use raw `fetch()` or import `API_BASE` without the auth wrapper.** `authFetch` also exists as a lower-level option but the `api` object is the recommended pattern with retries, timeout, and typed error mapping built in |
| **AuthGate** | Wraps protected routes |
| **Public routes** | `/login`, `/landing` only |

---

## 8. Backend Capability Map

| Step | WIRED | PLANNED |
|---|---|---|
| **CAST** | Talent CRUD, media upload, LoRA assignment | Identity Pipeline (C2, 3-4 weeks), LoRA Training wizard |
| **WRITE** | Story engine (50+ endpoints), universes/characters/episodes/scenes/shots/continuity | Prompt Engine (C3), Series Bible (C5), Retention Analysis auto-gen (P10) |
| **MAKE** | Gen health/providers/models/run, job lifecycle, workflow execution | Frame Grid (C4), Settings API (C6), Speed Verbs (C2), QA Grading Gate (P6), Generator Routing (P11) |
| **PUBLISH** | Asset CRUD, file serving, share link generation | Social publishing (Phase 2-3), Content Calendar |

---

## 9. Phased Rollout Plan

| Phase | What | Timeline |
|---|---|---|
| **1 — Auth** | Stream A + C1 (backend + frontend auth) | Start now |
| **2 — Design Approval** | Lock this spec | After reading |
| **3 — Build** | Backend auth + frontend auth + Next.js migration + new components | 2-3 weeks |
| **4 — Capability Wire** | C4, C2, C1 features, BYO API portal, presets | Week 4-6 |
| **5 — Launch** | Full deployment — "one big go" | After Phase 4 |

---

## 10. SimpliGen Comparison & "Heavy Like ComfyUI" Vision

### Competitive Positioning

| Dimension | SimpliGen (Desktop) | AI Studio (Web) |
|---|---|---|
| **Platform** | Windows-only, local GPU | Any browser, zero install, any device |
| **UX** | 3-step wizard (pick → style → generate) | 5-step production pipeline (CAST→WRITE→MAKE→PUBLISH) |
| **Pricing** | One-time purchase, lifetime updates | **BYO API** — user brings their own keys |
| **Characters** | Upload one face → reuse | Full identity pipeline + continuity across 60 episodes |
| **Scope** | Single image/video | Serialized episode production with memory |
| **Collaboration** | Single-user | Multi-tenant, shared sessions |
| **Agent** | MCP add-on | **Brain IS the agent** (Hermes Agent embedded per tenant) |
| **Model routing** | One ComfyUI or SimpliGen Cloud | Route to cheapest/best provider per job |

### "Simple" vs "Advanced" Mode Toggle

**Simple mode** (default): 3-step flow — media type → style preset → prompt. Matches SimpliGen. 3 clicks to first render.

**Advanced mode:** Collapsible "Node Inspector" panel renders Tier 2 controls as schema-generated form. Not a node graph — a form.

### Preset Pack System

Each preset bundles: model + workflow + LoRAs + CFG + steps + sampler + prompt template. Users pick "Cinematic Portrait" not "SDXL + LoRA + CFG 5.0 + Euler a + 30 steps."

---

## 11. BYO API Architecture

### The Model

Users bring their own:
- **Thunder Compute / RunComfy** — GPU backend
- **B2 / S3-compatible** — storage
- **LLM API key** (OpenAI, DeepSeek, Anthropic, or local Ollama) — for Brain chat
- **ElevenLabs / Kokoro** — TTS for voice tracks
- **Supabase** — database + auth
- **Railway / VPS** — hosting

AI Studio provides: the app, the pipeline, the UI, storyboard, episode management, character identity, prompt engine.

### Architecture

**Key storage** extends the existing `CredentialService` in `backend/credentials.py` (NOT a new `pgp_sym_encrypt` table, NOT `CredentialBroker` — that's job-scoped for GPU workers). The service already handles Fernet encryption (AES-128-CBC + HMAC-SHA256), `CredentialOwnership.CUSTOMER` vs `PLATFORM`, and audit logging. Add `ProviderType.USER_API_KEY` to the `ProviderType` enum at `backend/credentials.py:95`, then call:

```python
CredentialService.store(
    org_id=tenant.org_id,
    provider=ProviderType.USER_API_KEY,
    secret=raw_key,
    ownership=CredentialOwnership.CUSTOMER,
    actor=str(user_id),
)
```

Key resolution at generation time uses `CredentialService.resolve()` at `backend/credentials.py:294`, which already falls back to platform env vars when no workspace credential exists.

**Key routing** in `backend/app/services/generation_service.py` (NOT `backend/infrastructure/generate.py` — that path doesn't exist):
1. Resolve user → org → configured provider for workload class
2. Call `CredentialService.resolve(org_id=..., provider=ProviderType.USER_API_KEY, environment="production", actor=str(user_id), purpose="generate_image")` at `backend/credentials.py:294` → returns decrypted secret
3. Override platform key with user's key in provider adapter (`backend/app/services/generation_service.py`)
4. Check usage cap before dispatch
5. Fallback chain: user's key → org pool key → platform default (already built into `CredentialService.resolve()`)

**Key lifecycle:**
| Feature | Detail | Codebase Path |
|---|---|---|
| Auto-expiry | Keys expire after 90 days (`MCP Auth` already defaults to `expires_in_days=90` at `backend/aios/mcp/auth.py:241`). `CredentialService.expires_at` field exists but needs enforcement in `_find_active()` before prod launch | `backend/credentials.py:442` |
| Revocation | THREE revocation systems already exist: `CredentialService.revoke()` (general secrets, `credentials.py:381`), `CredentialBroker.revoke_credential()` (GPU workers, `credential_broker.py:315`), `mcp/auth.py:revoke_credential()` (MCP client keys, `auth.py:290`). Use the one matching the credential type | `backend/credentials.py:381`, `backend/app/services/credential_broker.py:315`, `backend/aios/mcp/auth.py:290` |
| Rotation | `CredentialService.rotate()` at `credentials.py:359` — stores new secret, marks old as `ROTATED`. `mcp/auth.py:rotate_credential()` at `auth.py:301` — issues new key, deactivates old. Old key remains usable for 24h to allow in-flight jobs | `backend/credentials.py:359`, `backend/aios/mcp/auth.py:301` |
| Audit | Every key access logged with timestamp, requesting user, and operation type. Existing audit infrastructure | `backend/credentials.py` — built into `resolve()` and `store()` |

---

## 12. Free LLM Strategy

**Offer BOTH options:**

| Option | How | Cost | Risk |
|---|---|---|---|
| **BYO API key** | User brings DeepSeek/OpenAI key | User pays usage | None for us |
| **AI Studio managed VPS** | We deploy Ollama + dolphin-llama3 (uncensored) + Honcho | ~$10-20/mo shared VPS | We manage infra, control model |
| **Local Ollama** | User runs on their machine | User's electricity | High friction |

**On uncensored models:** Dolphin-llama3, DeepSeek V4 Flash are legal open-weight models. Risk is brand perception, not legality. Mitigation: uncensored mode is opt-in with clear warning. BYO API means user's key = user's responsibility.

**Recommendation:** Ollama + dolphin-llama3 on a shared VPS as default free option. Users who want higher quality bring DeepSeek/OpenAI key. Honcho for persistent session memory on the VPS.

---

## 13. Deployment Strategy

### Current Live Topology
- **Frontend:** Vercel (Next.js production deployment)
- **Backend:** Railway (FastAPI workers, task queues)
- **Database:** Supabase (PostgreSQL, auth, storage)
- **GPU:** Thunder Compute (generation workers) + RunComfy (supplemental)

### Strategy: Keep Vercel for Frontend, Railway for Backend

✅ **Keep Vercel** for Next.js frontend — it's already configured, has env vars set, and handles SSR/CDN. Migrating frontend off Vercel is not trivial (DNS/SSL/env migration + potential corruption risk documented in `ai-studio-prod-deployment` skill).

✅ **Keep Railway** for FastAPI backend — task queues, webhooks, and generation job orchestration work well here.

❌ **Do NOT move frontend to Railway** — the effort/cost benefit doesn't justify it for MVP. Revisit when the app scales.

### Self-Hosted Option (For Power Users)

**Docker Compose for Linux:** Single `docker-compose up` with Next.js, FastAPI, Supabase (local or cloud), Ollama (optional). For self-hosters, air-gapped, or VPS deployments.

### BYO Self-Service Flow (MVP)
1. User clicks "Deploy to Railway" → provisions backend
2. User connects Supabase project → schema auto-migrates
3. User adds API keys in Settings page
4. Frontend already on Vercel → points at user's Railway backend
5. **Total setup time:** ~15 minutes

**Recommendation: Keep Vercel+Railway for cloud. Docker Compose for self-hosters.**

---

## 14. Pipeline Additions (@ai-studio)

### 🔴 Phase 1 Blockers

**P1. Reference Connection Order Panel (MAKE)** — Ref2VA requires `<Picture 1>` before `<Picture 2>`. Explicit order panel.

**⚠️ CRITICAL — The Brain executor bridge (`execution/tools.py`, NOT `server.py`) has ZERO org_id filtering. This is a cross-tenant data leak. The MCP server (`server.py`) was already fixed — the gap is in the Brain's local executors at `backend/aios/execution/tools.py`. This must be fixed before ANY multi-tenant deployment. See `.kiro/specs/deep-audit-report.md` for exact file paths and fix plan across all 7 workspace variants.**

**P2. Frame Grid Validation → Phase 1** — Invalid frames (e.g. 216, 280) produce garbage video. Valid values (from H3's internal temporal schedule): **124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600** (11 values, not just 4 — the pipeline supports multiple frame counts for different clip lengths and FPS). 216 and 280 are explicitly invalid. Wire dropdown to these valid values — the existing prompt architecture already validates against this list.

**P3. Aspect Ratio Lock** — Portrait ref → landscape = #1 complaint. Lock render ratio to reference.

**P4. 3-Shot Test Side-by-Side** — Three frames displayed with pass/fail color overlay, not just badges.

### 🟡 Phase 2

**P5. TTS Dialogue Overlay** — H3 audio is robotic. Separate TTS track via ElevenLabs/Kokoro.

**P6. QA Grading Gate** — "Never animate a frame graded <7/10." Auto-grade (vision grader via ollama qwen2.5vl:7b) + manual grade button. Grading rubric (5 dimensions): **anatomy** (limbs, proportions, face structure), **photorealism** (skin texture, lighting, material rendering), **prompt_adherence** (does it match the subject/action/camera/lighting from the prompt), **defects** (body horror, extra limbs, fused objects), **overall** (weighted composite). Each dimension scored 1-10. Overall <7 = auto-reject, 7-8 = needs review, 9+ = auto-approve.

**P7. Multi-LoRA Character Mixer** — Per-LoRA strength sliders for multi-character shots.

**P8. Quick Preview vs Full Quality Presets** — Preview (Turbo): 4-step, 480p, `res_multistep`/`simple`, **CFG must be 1.0 / shift 1.0 — any deviation produces garbage output** (scanlines/smear/psychedelic glitch). LoRA: LightX2V Turbo 4-step only. Full: 20-step H3 Ref2VA at 768p+, CFG 1.2, shift 10.0, `res_multistep`/`simple`. See §5.4 Tier 3 toggle.

### 🟢 Spec Cleanup

**P9. Dialogue Carry-Through** — WRITE → MAKE prompt injection as `<d>[English] text</d>`.

**P10. Retention Analysis Auto-Generation** — From reference connection panel.

**P11. Generator Routing** — Currently per-workflow, not per-shot. Label "planned."

---

## 15. RunComfy Integration

| Feature | Benefit |
|---|---|
| **Webhook-based completion** | No polling worker, instant UI updates |
| **Cancel button** | User kills stuck generation |
| **Queue position + progress** | "Your job is #3, ~12 seconds" |
| **Workflow switching** | `workflow_api_json` at request time — swap pipeline per shot |
| **KSampler overrides** | Send `{seed, steps, cfg, sampler_name, scheduler}` per gen |
| **Model API (no deployment)** | Quick gen path, per-request billing |
| **Instance proxy** | Free GPU memory via API — no more manual restarts |
| **LoRA training API** | Managed datasets + training jobs |

**RunComfy supplements Thunder.** Thunder ($0.35/hr A6000) stays for batch rendering. RunComfy ($2.50/hr) for reliability, quick-gen, and the Brain agent.

---

## 16. Generation Error Handling & Reliability

Generation is the most failure-prone surface in AI Studio. This section defines explicit timeout, retry, and error policies.

### Error Scenarios & Responses

| Scenario | Detection | User Experience | Recovery |
|---|---|---|---|
| **GPU OOM (out of memory)** | Worker returns CUDA OOM error code | "GPU ran out of memory. Try a smaller resolution, fewer LoRAs, or a lighter model." | Auto-retry at next-lower resolution tier (once). If retry fails, show error and suggest model swap |
| **CUDA error / model load failure** | Worker returns non-zero exit or REST 500 | "GPU process error. The worker may need a restart." | No auto-retry — different failure likely repeat. Suggest different model |
| **Generation timeout (>480s)** | Job exceeds 480s threshold (H3 30-step renders) | "This generation is taking longer than expected. It may still complete — wait or cancel." | Job continues in background; user can cancel and retry with simpler params |
| **API request timeout** | Frontend timeout per endpoint: default 30s, image gen 120s, model upload 600s (defined in `frontend/src/lib/api.ts`) | "Request timed out. Try again or reduce complexity." | User can retry |
| **Webhook delivery failure** (RunComfy) | No webhook received within 120s of job completion | Fallback to polling (every 15s, max 3 min). If still no result, surface "Result was lost due to a provider issue. Please regenerate." | Auto-fallback polling then surfacing |
| **API key invalid / rate-limited** | Provider returns 401 or 429 | "Your API key for [provider] is invalid or rate-limited. Check your keys in Settings or wait 60 seconds." | No auto-retry for 401. Exponential backoff for 429 |
| **Provider down (Thunder/RunComfy)** | Health check fails or all requests timeout | "[Provider] is currently unreachable. Your job has been queued and will retry automatically." | Queued job retries every 60s, up to 5 attempts, then fails with notification |
| **Queue backlog (>10 jobs)** | Queue depth exceeds threshold | Shows estimated wait time in Generation Queue: "~3 jobs ahead of yours (~45s wait)" | Progressive — user can cancel queue, fast-track a job, or batch at end |

### Retry Policy (from `api.ts` lines 167-176)
| Layer | Max Retries | Backoff | Notes |
|---|---|---|---|
| API request (network/5xx) | 2 retries | Exponential (1s, 2s ×2 per attempt) | Only for safe methods: GET, HEAD, OPTIONS. POST/PUT/DELETE never auto-retried |
| GPU OOM | 1 retry at lower resolution | Immediate (OOM only, not general errors) | Only for OOM, not other errors |
| Provider 429 | 3 retries | Exponential (15s, 30s, 60s) | Different providers retry independently |
| Webhook miss | 1 fallback to polling | Immediate | Then surface result or error |
| Provider down | 5 retries | 60s intervals | After 5 failures, dead-letter the job |

**Lane constraints (from `AGENTS.md` + `LANES.json`):**
- `frontend/src/components/**` is **frozen** — shared components are integration-only changes. Lane-local components belong beside the page that owns them.
- `backend/api_v1.py` is a **single-file mutex** — only the backend lane may modify it.
- Kiro operates in the **backend** lane (`backend/**` owned). Frontend components are built by their respective lane agents (talent, creation, post, growth, platform, brain).
- See `LANES.json` for exact lane-to-path mapping.

---

## 17. Component Architecture

```
src/components/
├── layout/
│   ├── AppShell (rewrite: slim sidebar 60px → hover expand)
│   └── TopBar (step indicator: START | CAST | WRITE | MAKE | PUBLISH)
├── auth/
│   ├── AuthGate
│   └── LoginPage
├── talent/
│   ├── CharacterCard
│   ├── CharacterDetail
│   ├── RefImageUpload
│   └── ThreeShotTest (side-by-side frames)
├── story/
│   ├── EpisodeList
│   ├── Storyboard (shared, visual timeline)
│   └── ShotDetail (metadata + prompt)
├── generation/
│   ├── PromptEditor (syntax-highlighted, 6-section, collapsible)
│   ├── PromptPreview (full assembled format)
│   ├── GenerationQueue (inline progress bars)
│   ├── FrameGrid (thumbnails + approve/reject)
│   ├── ReferenceOrderPanel (Picture 1/2, Video 1, Audio 1)
│   ├── LoRAMixer (multi-character LoRA stack)
│   ├── QAGate (grade button + auto-grade)
│   ├── ModelSelector (checkpoint + VAE picker)
│   ├── KSamplerPanel (steps, cfg, sampler, scheduler, seed)
│   └── WorkflowSelector (switch between active deployments)
├── settings/
│   ├── APIKeyManager (BYO key portal)
│   └── ProviderConfig
├── publish/
│   ├── EpisodeGallery
│   ├── AssetGrid
│   └── ComingSoon (reusable badge)
└── shared/
    ├── UploadZone (drag-and-drop)
    ├── PresetCard (model + workflow + LoRA bundle)
    ├── SimpleMode (3-step wizard)
    └── AdvancedToggle (switch simple/advanced)
```

---

## 18. Open Questions

| Question | Recommendation |
|---|---|
| **Storyboard vs full render?** | ✅ Previews in WRITE, full in MAKE. Quick Preview: Turbo 4-step LoRA at 480p, `res_multistep`/`simple`, cfg 1.0, shift 1.0. Full: 20-step H3 Ref2VA at 768p+ |
| **Upload storage?** | ✅ B2 (already wired) |
| **Social publish buttons?** | ✅ Show with "Coming Soon" badge |
| **Old Streamlit pages?** | ✅ Archive behind `/admin` |
| **Multi-project?** | ✅ Yes |
| **Accent color?** | ✅ Keep purple (#7c3aed), use sparingly. Zero migration cost |
| **/create + /editor?** | ✅ Absorb into WRITE/MAKE. Delete separate routes |
| **Deployment topology?** | ✅ Keep Vercel (frontend) + Railway (backend) + Supabase. Docker Compose for self-hosters |
| **Free LLM?** | ✅ Ollama + dolphin-llama3 on shared VPS as default free option |
| **LoRA training?** | ✅ Include it — essential for character consistency across 60 episodes |
| **MCP agent surface?** | ✅ Expose ALL capabilities (~55 MCP tools) for any agent to connect |
| **Mobile responsive?** | ✅ ≥1024px full horizontal, 768-1024px scrollable tabs, <768px hamburger dropdown |
| **API key lifecycle?** | ✅ 90-day expiry, revocation via CredentialBroker, rotation with 24h overlap |
| **MCP auth model?** | ✅ ALL operations require auth (no open reads). Tenant isolation via org_id threading |

---

## 19. LoRA Training — Yes, Include It

**Decision: ✅ YES — Include LoRA training in the MVP.**

### Why It's Essential

| Reason | Impact |
|---|---|
| **Character consistency** | Serialized 60-episode content needs character-specific LoRAs or identity drifts across episodes. Every main character (Zuri, Kofi, Duma) needs their own LoRA |
| **Competitive parity** | SimpliGen's Character Studio trains per-character LoRAs. We must match this |
| **Existing infra** | CAST already has LoRA assignment + strengths. RunComfy Trainer API provides managed datasets + training jobs. MCP already has `train_lora` tool. Thunder Compute runs LoRA training |
| **RunComfy integration** | LoRA training API: create dataset → upload images → submit training job → poll status → download checkpoint. Full lifecycle |

### LoRA Training Lifecycle

```
User uploads 8-20 character reference images via CAST
         ↓
Create dataset (RunComfy: POST /trainers/datasets)
         ↓
Upload images with signed URLs (RunComfy handles cloud storage)
         ↓
Submit training job (config with base model, trigger word, steps, learning rate)
         ↓
Monitor in-job progress bar in MAKE/CAST
         ↓
Download LoRA checkpoint (.safetensors)
         ↓
Assign LoRA to character in CAST
         ↓
Use LoRA in MAKE (multi-LoRA strength sliders)
```

### UI: LoRA Training Wizard in CAST

- "Train LoRA" button on character detail panel
- Wizard steps: Upload/Label images → Choose base model → Set trigger word → Configure training params (advanced) → Submit
- Progress bar inline during training (jobs feed)
- Success popup → auto-assign LoRA to character
- Character gets a "trained" status badge

### What MCP Currently Exposes

Existing `train_lora` and `get_training_status` tools work. Need to add:
- `create_training_dataset` — Create dataset from character refs
- `upload_training_images` — Upload with signed URLs
- `list_lora_models` — List available LoRAs per character
- `delete_lora` — Remove a trained LoRA

---

## 20. MCP Enhancement — Full Agent Surface

**Decision: ✅ YES — Expose ALL capabilities as MCP tools for Claude, Hermes, Codex/ChatGPT/Ollama, Kiro, and any MCP-compatible agent.**

### Vision

AI Studio is not just a web app — it's an **agent-accessible media operating system**. Any AI agent should be able to connect via MCP and:

1. Create characters, stories, episodes, shots
2. Generate images and video with full ComfyUI-grade controls (KSampler, CFG, steps, sampler, scheduler, seed, LoRA stack, workflows)
3. Manage LoRA training lifecycle (create dataset, upload images, submit job, poll, download)
4. Schedule content to Fanvue, OnlyFans, Instagram, YouTube, or any supported platform
5. Manage user API keys and BYO provider settings
6. Query project status, costs, GPU health
7. Orchestrate full episode production from script to publish

### Current MCP Surface (What Exists)

| Category | Tools | Status |
|---|---|---|
| **Talent** | `search_talent`, `get_talent_dna`, `create_talent` | ✅ Already in tools.py |
| **Generation** | `generate_image`, `generate_video`, `recommend_workflow` | ✅ Already in tools.py |
| **Story** | `continue_story`, `get_story_context` | ✅ Already in tools.py |
| **Training** | `train_lora`, `get_training_status` | ✅ Already in tools.py |
| **Assets** | `search_assets` | ✅ Already in tools.py |
| **Publishing** | `schedule_post` | ✅ Already in tools.py |
| **Infrastructure** | `check_gpu_status`, `estimate_cost`, `list_models` | ✅ Already in tools.py |
| **Knowledge** | `search_knowledge` | ✅ Already in tools.py |

### New MCP Tools to Add

**🧑 Talent & Identity (Expand)**
| Tool | Description |
|---|---|
| `update_talent_dna` | Update visual style, anchor IDs, voice profile |
| `run_identity_test` | Run 3-shot test on a character (lock→turn→environment) |
| `list_talent_lora` | List all LoRAs assigned to a talent |
| `assign_lora_to_talent` | Assign a trained LoRA to a character with strength |

**🎬 Generation (Expand — Heavy ComfyUI Controls)**
| Tool | Description |
|---|---|
| `generate_with_ksampler` | Full KSampler control: steps, cfg, sampler, scheduler, seed, denoise, clip_skip |
| `generate_with_workflow` | Generate using a specific ComfyUI workflow JSON |
| `list_workflows` | List available ComfyUI workflows/deployments |
| `switch_workflow` | Switch active workflow for a project |
| `get_workflow_schema` | Get input schema for a deployment's nodes |
| `generate_batch` | Generate N variants of a prompt (different seeds, sampler sweeps) |
| `cancel_generation` | Cancel a running or queued job |

**📖 Story (Expand)**
| Tool | Description |
|---|---|
| `create_episode` | Create a new episode in a universe |
| `create_scene` | Add a scene to an episode |
| `create_shot` | Add a shot to a scene with metadata |
| `update_shot_prompt` | Update a shot's H3 prompt |
| `get_storyboard` | Get all frames for an episode/scene |
| `list_episodes` | List episodes with status |
| `upload_shot_reference` | Upload a reference image for a specific shot |

**🏋️ Training (Expand — Full LoRA Lifecycle)**
| Tool | Description |
|---|---|
| `create_training_dataset` | Create dataset from character references |
| `upload_training_images` | Upload with signed URLs |
| `list_lora_models` | List available LoRAs |
| `delete_lora` | Remove a trained LoRA |
| `get_lora_details` | Get LoRA metadata, base model, trigger word |

**📅 Publishing (Expand — Calendar + Multi-Platform)**
| Tool | Description |
|---|---|
| `connect_platform` | OAuth connect to Fanvue, OnlyFans, etc. |
| `disconnect_platform` | Revoke platform connection |
| `list_connected_platforms` | List active platform connections |
| `schedule_post` | Schedule a post to one or more platforms (expand) |
| `list_scheduled_posts` | View upcoming scheduled posts |
| `cancel_scheduled_post` | Remove a scheduled post |
| `get_publishing_calendar` | Get calendar view of scheduled content |
| `list_platforms` | List supported platforms with capabilities |

**🔧 BYO API Management**
| Tool | Description |
|---|---|
| `add_api_key` | Add a user API key for a provider |
| `list_api_keys` | List configured API keys |
| `remove_api_key` | Remove an API key |
| `test_api_key` | Test a provider key validity |
| `get_default_provider` | Get default provider for a lane |

**📊 Project Management**
| Tool | Description |
|---|---|
| `create_project` | Create a new project |
| `list_projects` | List user's projects |
| `get_project_settings` | Get project toggles (Anti-Plastic, Speed Verbs, etc.) |
| `update_project_setting` | Toggle a project-level setting |

**📦 Preset Management**
| Tool | Description |
|---|---|
| `list_presets` | List available preset packs |
| `create_preset` | Save current settings as a preset |
| `apply_preset` | Apply a preset to current project |

### MCP Architecture

```
Agent (Claude/Hermes/ChatGPT/Kiro)
      │
      ▼ MCP Client (requires user API key)
      │
      ▼ /backend/aios/mcp/server.py  ← FastAPI + MCP protocol
      │
      ├── tools.py  (tool definitions + handlers)
      ├── auth.py   (authenticates EVERY request via existing infra)
      └── router.py (routes to backend endpoints, threads org_id)
```

**Governance rules:**
| Rule | Detail | Codebase Status |
|---|---|---|
| **ALL operations require auth** | Every MCP endpoint already uses `MCPClientDep` including `GET /tools` and `GET /schema` (reads). The existing `authenticate_mcp_request()` at `backend/aios/mcp/auth.py` handles: SHA-256 hash lookup, status checks (REVOKED/ROTATED/EXPIRED), rate limiting, and returns `MCPClientIdentity` with `org_id`. Tested in `tests/unit/test_core/test_mcp_auth.py` | ✅ Already exists — no build needed, document what's there |
| **Tenant isolation** | Every tool handler receives `org_id` as explicit parameter — matching existing pattern in `backend/aios/mcp/server.py:_exec_search_talent(params, org_id)` (line 375). New handlers must follow same pattern: `org_id` from `MCPClientIdentity`, never from request body | `server.py:375` — follow this pattern |
| **GPU operations** | Cost estimation shown before execution. Auto-approve only for jobs under $1 threshold | Future |
| **Platform publishing** | Requires platform OAuth + explicit user confirmation before posting | Future |
| **Key lifecycle** | API keys already default to 90-day expiry (`backend/aios/mcp/auth.py:241`). Revocation/rotation infrastructure exists across 3 systems. Gap: `CredentialService._find_active()` at `credentials.py:442` doesn't enforce `expires_at` yet — needs a one-line fix | See §11 Key Lifecycle table for exact paths |

### MCP Client Setup

Deliver `docs/mcp-setup.md` that tells users how to connect their agent:

```json
// Claude Desktop / Hermes Agent / ChatGPT MCP config
{
  "mcpServers": {
    "ai-studio": {
      "url": "https://aistudio.io/aios/mcp",
      "apiKey": "${USER_API_KEY}"
    }
  }
}
```

**Supported MCP clients:** Claude Desktop, Claude Code, Hermes Agent, ChatGPT (OpenClaw), Cursor, VS Code, Windsurf, Kiro, and any MCP-compatible tool.