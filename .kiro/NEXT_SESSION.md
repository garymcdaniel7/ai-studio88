# AI Studio — Next Session TODO List

> Generated: 2026-07-19
> Use this file to brief the next chat session on what needs to be done.

---

## Priority 1 — Security & Auth (Must Do)

- [ ] Add `require_auth` to ALL mutation endpoints (POST, PUT, DELETE) in `backend/api_v1.py`
  - Talent: POST /talent, PUT /talent/{id}, DELETE /talent/{id}
  - Training: POST /training/start
  - Jobs: POST /jobs
  - Currently only generate_image, save-generation, and create_project have it
- [ ] Verify org_id ownership on DELETE/PUT (don't let org A delete org B's resources)

---

## Priority 2 — RunPod Configuration

- [ ] Verify all RunPod env vars are correctly set in `.env`:
  - `RUNPOD_API_KEY` ✅ (set: rpa_GC092P...)
  - Does it need SSH key? API secret? S3 API key for network volumes?
  - Check RunPod dashboard for what credentials are needed
- [ ] Test launching a worker via RunPod from the Fleet page "Launch Worker" button
- [ ] RunPod doesn't need SSH tunnel — it has HTTP proxy. Update the `COMFYUI_BASE_URL` logic to use RunPod's proxy URL format: `https://{pod_id}-8188.proxy.runpod.net`

---

## Priority 3 — Agent & Testing Updates

- [ ] Update Hermes/Ise UAT agent (`/.kiro/agents/ise-uat.md`) to include Red Team visual testing
- [ ] Update Playwright test infrastructure to run Red Team screenshot audits automatically
- [ ] Update the UAT hook (`.kiro/hooks/uat-on-push.json`) to also trigger visual audit on page changes
- [ ] Update `.kiro/steering/uat-system.md` with latest test counts and Red Team integration notes

---

## Priority 4 — Code Quality (Tech Debt)

- [ ] Split Create page (1837 lines) into 5 components:
  - `components/create/ImageGenerator.tsx`
  - `components/create/VideoGenerator.tsx`
  - `components/create/VoiceMusic.tsx`
  - `components/create/AdvancedPanel.tsx`
  - `components/create/BatchResults.tsx`
- [ ] Centralize all `fetch` calls through `@/lib/api.ts` (13 pages still use raw `fetch` + per-file `API_BASE`)
  - This ensures auth Bearer token is sent with ALL requests
- [ ] Remove inner `ai-studio88/ai-studio88/` duplicate directory (stale copy with Railway URLs)
- [ ] Add `loading.tsx` files for instant page transitions (Next.js built-in)
- [ ] Add loading skeletons to Assets/Library page

---

## Priority 5 — GPU Worker Reliability

- [ ] Get a GPU worker running reliably (RunPod recommended — faster boot, persistent volumes)
- [ ] Once running, verify:
  - Models show as "Ready" in Create page model selector
  - Generation works end-to-end through the UI
  - Images display in the result area
  - "Save to Library" persists and image shows in Assets page
- [ ] Test batch generation (×4) with live GPU
- [ ] Test cancel button during generation

---

## Priority 6 — UX Polish

- [ ] Deploy frontend to Vercel (instructions in previous session — just connect GitHub repo)
- [ ] Fix Supabase signup (need correct anon key format — `sb_publishable_` should work with SDK v2.110+, restart frontend to pick up new .env.local)
- [ ] Add real-time generation progress via WebSocket (ComfyUI reports per-node progress)
- [ ] Image inpainting (P4-22) — UI for painting a mask, ComfyUI inpaint workflow

---

## Priority 7 — Deeper Connections

- [ ] Projects page should show linked assets (generated images within that project)
- [ ] Talent page "Generations" tab should show thumbnails from B2/local storage
- [ ] Brain memory should persist conversations across page refreshes (already wired but verify)
- [ ] Generation history timeline (recent generations with re-generate/remix buttons)

---

## Context from This Session

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

**What's running:**
- Backend: FastAPI with 27 routes (via uvicorn)
- RunPod API key: configured in .env
- Vast.ai API key: configured in .env ($16+ balance)
- No GPU worker currently active (destroyed to save money)
- Frontend: Next.js (localhost:3000 when running)

**Key files to reference:**
- `.kiro/PROGRESS.md` — overall project status
- `docs/UAT_RED_TEAM_REPORT.md` — full defect/enhancement list
- `.kiro/steering/uat-system.md` — test health and patterns
- `.kiro/agents/redteam.md` — Red Team agent definition
- `.kiro/agents/ise-uat.md` — Ise UAT agent (needs updating)
- `docker/comfyui-worker/` — Docker image for GPU workers
- `scripts/vast/onstart_full.sh` — Bootstrap script for Vast.ai instances
- `scripts/run-visual-audit.sh` — E2E visual audit script
