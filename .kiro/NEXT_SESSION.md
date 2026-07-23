# AI Studio — Next Session TODO List

> Generated: 2026-07-19
> Use this file to brief the next chat session on what needs to be done.
> 
> **START OF SESSION:** Read this entire file. Invoke @redteam for a massive audit first.
> Then execute all items in priority order within this single session.

---

## FIRST ACTION — Massive @redteam Audit

**Before doing ANYTHING else:**

1. Run the visual audit: `./scripts/run-visual-audit.sh` (screenshots every page)
2. Have @redteam go through EVERY page — at least 2 passes:
   - Pass 1: UX/UI issues, broken flows, missing connections
   - Pass 2: Fortune 500 enterprise readiness + cybersecurity
3. Include ghost/hidden pages: /login, /projects/[id], /editor, /admin/ise, /admin/keys, /admin/knowledge
4. Produce FULL documentation of all findings
5. Add ALL new findings to this file and execute them in order

---

## Agent & Governance Updates

- [ ] **@redteam: Review the Hermes agent** (`.kiro/agents/hermes.md` and `.kiro/agents/ise-uat.md`) — find enhancements
- [ ] **Hermes Agent Enhancement:** Make Hermes the FULL application health monitor. It should act as @dev_team + @redteam ensuring the app is maintained:
  - Know the source code structure and current defects
  - Propose fixes but ASK FOR APPROVAL before implementing
  - Monitor test results, Red Team findings, and system health
  - Be accessible via LLM chat on the Brain page (`/aios/v1/hermes/chat`)
- [ ] **Update `ise-uat.md`** with everything Red Team found:
  - All P0-P4 findings and resolutions
  - What to watch for (regressions)
  - Integration with visual audit (screenshot testing)
  - Auto-invoke @redteam after major failures
- [ ] **Update the UAT hook** (`.kiro/hooks/uat-on-push.json`) to also trigger visual audit on page changes
- [ ] **After each @redteam update:** Auto-update Ise-UAT and Hermes to learn what the business wants

---

## Full Application Health Dashboard

- [ ] Build a FULL application health dashboard (intuitive, human-centric design):
  - Service status, GPU health, generation stats, error rates, test results
  - One-glance understanding of "is the app healthy?"
  - Small toggle buttons for services (ComfyUI, Ollama, TTS, Training)
  - Cost tracking (daily/weekly/monthly GPU spend)
  - Recent generation thumbnails with success/fail indicators
  - Alert feed from Ise UAT and Red Team findings
- [ ] **Chat with Hermes via LLM** — Enhance Brain page so you can ask:
  - "What's the app health right now?"
  - "Run the tests"
  - "What should I fix next?"
  - "Show me recent errors"
  Hermes responds with real data from the system

---

## Super Admin Page (Consolidate Admin + Settings + Fleet)

- [ ] Admin, Settings, and Fleet should ALL live in one unified "Super Admin" page
- [ ] Toggle controls for every service/feature (human-centric, small buttons)
- [ ] Things to control:
  - GPU provider preference (Vast/RunPod)
  - Which models are active/loaded
  - Service toggles (ComfyUI, Ollama, TTS, Training)
  - Rate limits, budgets, user management
  - Feature flags (live vs preview vs hidden)
- [ ] @redteam: look through entire app, identify what needs admin controls

---

## Login & Multi-Tenant Flow

- [ ] Clean up login flow completely
- [ ] Truly multi-tenant: each user/org sets up THEIR OWN API connections
- [ ] Users should NOT see platform-owner keys — they bring their own (Vast.ai/RunPod/B2)
- [ ] Onboarding flow: sign up → configure providers → start generating

---

## Public Landing Page

- [ ] Marketing landing page explaining what the app is + how it works
- [ ] Pricing — @redteam CFO research competitors:
  - Midjourney ($10-60/mo, limited generations)
  - Leonardo ($12-48/mo, token-based)
  - Runway ($15-76/mo, limited video seconds)
  - Pika ($8-58/mo)
  - Our model: **Everything free except GPU cost** — unlimited generations, pay only for compute
- [ ] CTA: Sign up, connect your GPU provider, start creating

---

## Security & Auth

- [ ] Add `require_auth` to ALL mutation endpoints (POST, PUT, DELETE) in `backend/api_v1.py`
- [ ] Verify org_id ownership on DELETE/PUT (prevent cross-tenant modification)

---

## RunPod Configuration

- [ ] Verify all RunPod env vars (does it need SSH key? API secret? S3 key for network volumes?)
- [ ] Test launching a worker via RunPod from Fleet page "Launch Worker" button
- [ ] Update `COMFYUI_BASE_URL` logic to use RunPod HTTP proxy: `https://{pod_id}-8188.proxy.runpod.net`

---

## Code Quality (Tech Debt)

- [ ] Split Create page (1837 lines) into 5 components
- [ ] Centralize all `fetch` calls through `@/lib/api.ts` (13 pages use raw fetch)
- [ ] Remove inner `ai-studio88/ai-studio88/` duplicate directory
- [ ] Add `loading.tsx` files for instant page transitions
- [ ] Add loading skeletons to Assets/Library page

---

## GPU Worker Reliability

- [ ] Get GPU worker running reliably (RunPod preferred)
- [ ] Verify full generation pipeline: models ready → generate → display → save to library
- [ ] Test batch generation (×4) with live GPU
- [ ] Test cancel button during generation

---

## UX Polish

- [ ] Deploy frontend to Vercel
- [ ] Fix Supabase signup (restart frontend with correct key)
- [ ] Real-time generation progress via WebSocket
- [ ] Image inpainting (P4-22) — mask painting UI + ComfyUI inpaint workflow

---

## Movie Production (Big Vision)

- [ ] Scene composition: storyboard → shots → video → assembly
- [ ] Editor page becomes real timeline editor
- [ ] WAN 2.1/2.2 for individual shots, FFMPEG for assembly
- [ ] Aspirational differentiator: "from prompt to feature film"

---

## Deeper Connections

- [ ] Projects page shows linked assets
- [ ] Talent page "Generations" tab shows thumbnails
- [ ] Brain memory persists conversations (verify)
- [ ] Generation history timeline with remix buttons

---

## Context from Previous Session

**What was accomplished:**
- All Red Team P0-P3 findings resolved (25/26 total)
- Supabase Auth end-to-end (frontend middleware + backend JWT)
- Multi-tenant org_id filtering on queries
- Async generation with rate limiting + cancel button
- Batch generation (×1, ×2, ×4 variations)
- Mobile hamburger menu + navigation drawer
- Docker worker image (ComfyUI + SimpleTuner + MOSS TTS + Ollama + FFMPEG)
- B2 model cache download script
- Fleet page UX fixes (Launch Worker, Settings toggle, error handling)
- GPU provider preference in Settings (RunPod vs Vast.ai)
- Visual audit script for Red Team screenshot reviews
- Toast notifications, cost estimates, empty states, remix flow
- CORS restriction, fleet settings debounce, assets pagination
- Image persistence (local file serving when B2 unavailable)
- Training page marked as "Preview" (simulation mode)
- Real generation proven: SDXL Turbo (3.1s) + Flux Dev (52s) on V100

**What's running:**
- Backend: FastAPI with 27 routes
- RunPod API key: configured in .env
- Vast.ai API key: configured in .env ($16+ balance)
- No GPU worker currently active (destroyed to save money)
- Frontend: Next.js (localhost:3000 when running)

**Key files:**
- `.kiro/PROGRESS.md` — overall project status
- `docs/UAT_RED_TEAM_REPORT.md` — full defect/enhancement list
- `.kiro/steering/uat-system.md` — test health and patterns
- `.kiro/agents/redteam.md` — Red Team agent definition
- `.kiro/agents/ise-uat.md` — Ise UAT agent
- `.kiro/agents/hermes.md` — Hermes agent
- `.kiro/agents/dev_team.md` — Dev Team agent
- `docker/comfyui-worker/` — Docker image for GPU workers
- `scripts/vast/onstart_full.sh` — Bootstrap script for Vast.ai
- `scripts/run-visual-audit.sh` — E2E visual audit script
- `frontend/e2e/visual-audit.spec.ts` — Playwright visual capture

**Estimated total items:** ~50+ (will grow after @redteam audit)
