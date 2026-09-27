# BUILD KICKOFF — AI STUDIO UI REALITY CHECK

**Spec for Kiro (autonomous execution — no approval needed per turn)**
**Date:** 2026-09-04
**Workspace:** `/Users/garymcdaniel/kiro/ai-studio88`
**Branch:** main (commit `f0eba5c`)

---

## 1. Mandatory First Actions

```bash
git status && git log --oneline -5
```
Then read the **entire** `.kiro/steering/` folder — every `*.md` — before writing a single line.

---

## 2. What Changed Today (ground truth — do not revert)

These are already deployed and proven live. The UI must reflect them:

| Change | Backend | Live Status |
|--------|---------|-------------|
| RunPod + VastAI scrapped → **Thunder Compute** single provider | ✅ 17 files, registry wiring, default config | ✅ A6000 live |
| `/api/v1/infrastructure/thunder/status` | ✅ Probes ComfyUI `/system_stats` | ✅ Returns real GPU data |
| Workflow map: **7 real models** (flux2-klein, flux2-klein-9b, krea2, h3-video, wan2.2-remix, sd15, sdxl-turbo) | ✅ `workflow_selector.py` | ✅ `/available-models` returns them |
| Talent→LoRA injection in ComfyUI provider | ✅ `lora_injector` wired into `comfyui.py` | ⚠️ Frontend doesn't send talent_id yet |
| Launch Worker → provisions real Thunder A6000 | ✅ `provision_worker` async path | ✅ Proven (second worker iktb6jgb) |
| Universes table created | ✅ Migration `20260703_005` | ✅ Story create returns 201 |
| Auth enforcement on (`AUTH_REQUIRED=true`) + JWT fallback | ✅ | ✅ Login works |

**Still stale/not reflected in the UI (this is what you must fix):**
- Studio/quick-generate model list shows only hardcoded defaults, not the 7 real models
- Library/assets page shows broken image tiles for `.mp4` and `.safetensors` files
- Create page dropdowns exist but don't send talent_id/lora in generation requests
- Publish page talks to wrong endpoint (`/publishing/posts` instead of `/publishing/schedule`)
- Home page stats count includes old sim data
- Brain shows generic "reconnecting" message for any error
- BYOLLM provider selects exist in settings but nothing persists them

---

## 3. Lane Rules (must obey)

From `AGENTS.md`:
- **`backend/api_v1.py`** — single-file mutex. Only the backend lane (Hermes/Kiro with explicit scope) modifies this file. If your task needs an api_v1.py change, write a clear note in the commit body saying "api_v1.py: X change needed" and flag it.
- **`frontend/src/components/**`** — frozen for lane agents. Lane-local components go next to the page that owns them (`frontend/src/app/<page>/_components/`).
- Frontend lane owns: `frontend/src/app/**` (page files + local components), `frontend/src/lib/` (api.ts, auth-utils, etc.), `frontend/public/`.
- **Small, focused commits.** One concern per commit. `type(scope): description`.
- **No placeholders.** No TODO, no "coming soon" stubs that pretend to work. Label stubs as stubs.

---

## 4. Priority Build Items (execute in order)

### P1 — Studio/Quick-Generate: Show the 7 real models

**What's wrong:** `use-create-data.ts` uses `/api/v1/models` (28 items — mostly upscalers with bad metadata) as the primary model list, and `/api/v1/generation/available-models` only to mark GPU readiness. The 7 real models ARE in available-models but the frontend doesn't use them as the canonical list.

**Fix:**
1. In `frontend/src/app/create/_hooks/use-create-data.ts`, change the primary model source from `/api/v1/models` to `/api/v1/generation/available-models` (this endpoint returns the WORKFLOW_MAP entries with real descriptions, vram, capabilities).
2. Remove the hardcoded default lists (lines 57-64).
3. Map the available-models response to `ModelOption[]` using the `capabilities` field to split image vs video.
4. Keep `/api/v1/models` fetch only for supplemental info (e.g. B2 status badges).
5. Reorder image models so quality-first models appear first.

**API shape (available-models):**
```json
{
  "models": [
    { "id": "flux2-klein", "name": "FLUX.2 Klein 4B", "description": "fast distilled image model...", "capabilities": ["txt2img", "img2img"], "vram": 12, "ready": true },
    { "id": "h3-video", "capabilities": ["img2video", "txt2video"], "vram": 24 },
    { "id": "wan2.2-remix", "capabilities": ["img2video", "txt2video"], "vram": 24 }
  ]
}
```

**Files:** `frontend/src/app/create/_hooks/use-create-data.ts`, possibly `ModelSelector` component if the id→name mapping logic needs updating.

---

### P2 — Library/Assets: Type-aware rendering

**What's wrong:** The assets grid renders `<img>` for every asset. `.safetensors` (model files) and `.mp4` (video) show broken image icons. Video assets need a player/thumbnail; model assets need a file icon.

**Fix:** In `frontend/src/app/assets/_components/` (or the page file if no local component), check each asset's `mime_type` or file extension:
- `image/*` — show `<img>` ✅
- `video/*` — show a `<video>` element with controls (or poster thumbnail)
- Model files (`.safetensors`, `.pth`, `.bin`) — show a model file icon with filename
- Fallback — generic file icon

**Files:** `frontend/src/app/assets/page.tsx` or any `_components/*.tsx` in that directory.

---

### P3 — Create Page: Wire talent_id + lora to generation requests

**What's wrong:** The backend's `comfyui.py` provider now calls `build_lora_config_for_talent()` and `inject_loras()` when `talent_id` or `lora` is in the `GenerationRequest`. But the frontend's generate button (in the create page) doesn't include these fields in the POST body.

**Fix:** Find the generate function in the create page (probably in a hook or the page component). When the user has selected a talent and/or LoRA, ensure the POST body includes:
```json
{
  "talent_id": "...",
  "lora": "...filename...",
  "lora_strength": 0.7,
  ...
}
```
The generation endpoint is `POST /api/v1/generate` or `POST /api/v1/generation/run` — check which one the create page calls and verify it accepts these fields (the `GenerationRequest` model has `talent_id`, `lora`, `lora_strength`).

**Files:** `frontend/src/app/create/page.tsx` (or its hook), `frontend/src/app/create/_components/` files where `generate()` is called.

---

### P4 — Publish Page: Wire to real scheduler endpoints

**What's wrong:** The publish page calls `POST /api/v1/publishing/posts` (legacy) which hardcodes `status: "draft"` and reads `caption` instead of `title`. The real scheduler lives at:
- `POST /api/v1/publishing/schedule` — schedule a post (requires `asset_id`, `scheduled_for`, `platform`)
- `GET /api/v1/publishing/scheduled` — list scheduled posts
- `POST /api/v1/publishing/scheduler/tick` — dispatch due posts (called by a cron)

**Fix:** Update `frontend/src/app/publish/page.tsx` to call the `/publishing/schedule` and `/publishing/scheduled` endpoints. The legacy `/publishing/posts` call should be removed. The calendar reads from `scheduledPosts` state which should now come from `/publishing/scheduled`.

**Note:** The schedule endpoint requires `asset_id`. If no asset exists yet, the UI should either let users schedule as "no asset" or require creating/uploading one first.

**Files:** `frontend/src/app/publish/page.tsx`, `frontend/src/lib/api.ts` (add `getScheduledPosts()`, `schedulePost()` functions).

---

### P5 — Home Page: Fix stats

**What's wrong:** Shows "7 active projects" when only 1 exists, 18 old simulation jobs, $0 GPU spend. The home page calls `/api/v1/projects` which returns all projects across the org — the count should filter by org_id properly. Jobs should exclude old simulation rows.

**Fix:** In `frontend/src/app/page.tsx`, check the shape of the responses:
- Projects endpoint returns all projects; the UI should count only those with `status === "active"` AND belonging to the current org (the backend already filters by org via auth, so the issue is likely a mismatch in how the endpoint is called or how the data is counted).
- Jobs endpoint: filter out jobs where `provider === "simulation"` or `worker_name` starts with "sim-" when counting.
- GPU spend: this likely reads from `/api/v1/infrastructure/status` — check if the thunder endpoint returns spend data.

**Files:** `frontend/src/app/page.tsx`

---

### P6 — Brain: Fix the "reconnecting" error message

**What's wrong:** The Brain chat shows "Brain is reconnecting... The service may need a moment to start." for ANY fetch failure, masking the real error. The backend is healthy (Ollama online, 5 models).

**Fix:** In `frontend/src/app/brain/hooks/use-brain-chat.ts` (or wherever the chat hook lives), replace the generic "reconnecting" catchall with the actual error message from the response. If it's a network error, show the status code. If it's a 401, show "Session expired — log in again." The key: show what actually failed, not the generic "reconnecting" message.

**Files:** `frontend/src/app/brain/hooks/use-brain-chat.ts`, and any component that displays the connection status.

---

### P7 — BYOLLM Persistence (if time allows)

**What's wrong:** Settings page has LLM provider dropdowns (gpu-ollama/local-ollama/openrouter) but they're pure `useState` — nothing saves. No `tenant_settings` or `workspace_settings` table exists.

**Fix:**
1. Create a `tenant_settings` table migration (columns: `org_id`, `key`, `value` JSONB).
2. Add API endpoints: `GET /api/v1/workspace/settings` and `POST /api/v1/workspace/settings` (or use existing scaffold pattern).
3. Wire the Settings page to save/load from these endpoints.

**Note:** This requires an api_v1.py change (mutex) — write the endpoint in a new file under `backend/app/api/v1/endpoints/` and add it to the router registry, OR write a detailed spec for the backend lane to implement.

---

## 5. API Reference (what's live and ready)

| Endpoint | Returns | Auth |
|----------|---------|------|
| `GET /api/v1/generation/available-models` | 7 models with capabilities/vram/ready | Required |
| `GET /api/v1/infrastructure/thunder/status` | Live A6000 info (do5u5dbx) with VRAM stats | Required |
| `POST /api/v1/publishing/schedule` | Schedule a post | Required |
| `GET /api/v1/publishing/scheduled` | List scheduled posts | Required |
| `GET /api/v1/models?type=lora` | 87 LoRAs with metadata | Required |
| `GET /api/v1/talent` | All talents (for talent_id selection) | Required |

---

## 6. Testing Protocol

For every item P1-P4:
1. Run `npx tsc --noEmit` from `frontend/` to confirm TypeScript is clean.
2. Run `npx playwright test e2e/full-stack-audit.spec.ts e2e/auth-audit.spec.ts` to verify no regressions.
3. For P1 (models): visually confirm the Studio dropdown shows the 7 real models with correct names/descriptions.
4. For P2 (library): confirm `.mp4` files show a video element, `.safetensors` show a file icon, images show as before.
5. For P3 (talent): confirm the generate POST includes talent_id and lora fields when a talent is selected.
6. For P4 (publish): confirm a scheduled post appears in the calendar after creation.

Commit after each passing item. Use descriptive commit messages.

---

## 7. Execution Order

1. P1 (Studio models) — highest visibility, user blocked on this
2. P2 (Library rendering) — user explicitly complained about this
3. P3 (Talent wiring) — backend already wired, frontend just needs to send the fields
4. P4 (Publish schedule) — fixes the broken publish flow
5. P5 (Home stats) — cosmetic but confusing
6. P6 (Brain reconnect) — quick error message fix
7. P7 (BYOLLM) — stretch goal, needs backend endpoint

**Run without approval.** Each P-item is self-contained. If you hit a blocker (missing endpoint, unexpected response shape), check the backend first — the endpoints listed above are live and proven. If truly blocked, flag it in the commit message and move to the next item.

---

## 8. One-liner to paste into Kiro's composer

> Read `.kiro/steering/` and then execute `.kiro/specs/hermes-pm-directive-2026-09-03.md` — start with P1 (Studio models) using `/api/v1/generation/available-models` as the canonical source, then P2 (library type-aware rendering), then P3 (talent/lora wired to generate), then P4 (publish→schedule). Run `tsc --noEmit` and the Playwright audit after each item. Report per-item. No approvals needed.