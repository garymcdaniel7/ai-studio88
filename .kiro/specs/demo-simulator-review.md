# Video Demo/Simulator — Code Review Findings & Fix Outline

**Review date:** 2026-08-23
**Scope:** Video generation demo/simulator — user-facing behavior when ComfyUI/GPU is unavailable
**Reviewer:** Hermes (on behalf of Gary)
**Target:** Fixes for Kiro to implement

---

## TL;DR

The UI **advertises** video generation as SIMULATED (a "Simulated" badge shows, the tab is usable), but the **backend hard-errors** the moment ComfyUI is unreachable. Users are invited into the demo, then hit "ComfyUI not reachable. Launch a GPU worker first." — the exact opposite of "let them get a feel of how it works." On top of that, the simulated state is not persistent across navigation/reload, and there's a model-ID vocabulary mismatch that breaks provider selection.

Three things must be true for the demo to work the way you want:
1. Generation **falls back to simulation** when the real engine is down (transparently labeled).
2. That simulated/demo state **persists for the session** (badge stays stable, page state survives navigation).
3. The model IDs the frontend sends **match** what the providers actually register.

---

## Bug 1 — Video handler removed the simulation fallback (REGRESSION)

**File:** `backend/handlers/video_handler.py` (commit `ef620ce`)
**What happened:** The "fail fast when ComfyUI unavailable" commit deleted the simulation fallback. The handler now raises a hard `RuntimeError` when ComfyUI is unreachable:

```python
# BEFORE (correct):
if not health.get("healthy"):
    reason = health.get("error") or "ComfyUI unreachable"
    logger.warning("ComfyUI unavailable (%s); falling back to simulation", reason)
    provider = get_video_provider(_SIMULATION_PROVIDER_NAME)

# AFTER (regression):
if not health.get("healthy"):
    reason = ...
    raise RuntimeError(f"ComfyUI/WAN video engine unavailable: {reason}. ...")
```

**Why it's wrong:** `CapabilityRegistryService` (`backend/app/services/capability_registry.py`) classifies `video_generation` as **SIMULATED** — the platform's own contract says users should be able to experience it in simulated mode (R24: Simulation Mode Transparency; R36: Video Generation Pipeline). Fail-fast contradicts the SIMULATED classification: the registry invites the user in, the handler slams the door.

**Fix:** Restore the fallback **with a configurable gate**:
- If `ENVIRONMENT` is `local`/`test`/`staging` → fall back to simulation + log warning + set `simulation: true` on the result (R24.1).
- If `ENVIRONMENT` is `production` → keep fail-fast (production must not silently return fake output; R24.5 refuses simulation in prod anyway).
- The result payload must include `"simulation": true, "provider": "simulation"` (R24.1).

---

## Bug 2 — The Create-page video endpoint has NO simulation fallback

**File:** `backend/infrastructure/generate.py`, `POST /api/v1/generate/video` (line ~1290) and `POST /api/v1/generate/video-from-image` (line ~1533)

**What happens:** These are the endpoints the **Create page actually calls** (`frontend/src/app/create/_hooks/use-video-generation.ts` hits `${API_BASE}/api/v1/generate/video`). They check ComfyUI and hard-503:

```python
try:
    health = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=5)
    if health.status_code != 200:
        raise HTTPException(status_code=503, detail="ComfyUI not responding")
except httpx.ConnectError:
    raise HTTPException(status_code=503,
        detail=f"ComfyUI not reachable at {COMFYUI_URL}. Launch a GPU worker first.")
```

There is **no simulation path at all** here. So even if Bug 1 is fixed in the worker handler, the Create page (the surface users actually reach) still hard-fails.

**Fix:** Add the same gated simulation fallback here:
- When ComfyUI is unreachable and env is non-production, route through `SimulationVideoAdapter` / `SimulatedVideoProvider` instead of raising 503.
- Return `success: true` with `"simulation": true` in the payload + a real downloadable artifact (deterministic fake video bytes) so the user can actually experience the flow end-to-end.
- Keep 503 only for production.
- Apply to **both** `/video` and `/video-from-image`.

---

## Bug 3 — "Simulated" badge is not session-stable; capability state is a dead in-memory singleton

**Files:**
- `backend/app/api/v1/endpoints/capabilities.py` — `_registry = CapabilityRegistryService()` is a **module-level in-memory singleton**; classification resets on every process restart and cannot be changed/rolled out without a code deploy.
- `frontend/src/hooks/useCapabilities.ts` — fetches `/api/v1/capabilities` via SWR with `revalidateOnFocus: true` and 30s stale-while-revalidate.
- `frontend/src/components/CapabilityGate.tsx` — SIMULATED renders children with a badge.

**What happens:** The badge can flash or disappear as health revalidates on every focus/refetch; nothing is cached for the session. If the backend restarts, the classification state is whatever the code ships with. There is no way to hold a "demo mode" for the duration of a user session.

**Fix:**
- **Frontend (session persistence):** Cache the capability response in `sessionStorage` (survives reload + navigation within the tab). Treat the SIMULATED classification as sticky for the session — do not re-badge on every focus revalidation. Add a `demoMode` flag on the capabilities response and/or `sessionStorage` so the whole app knows "this session is in demo/simulated mode."
- **Backend (durable classification):** Persist the capability registry to the DB (the requirements already flag "in-memory singleton, not persisted to DB" as a P0 gap). At minimum, add an endpoint/flag (`/api/v1/capabilities/{name}/transitions`) wired to a real store so demo mode can be toggled without a deploy.

---

## Bug 4 — Create-page state does not persist for the session

**Files:**
- `frontend/src/app/create/_hooks/use-video-generation.ts` — all state is `useState` (prompt, model, settings, result, download URL).
- `frontend/src/app/create/_hooks/use-image-generation.ts` — same pattern.
- `frontend/src/app/create/page.tsx` — all hooks mount fresh on navigation.

**What happens:** Fill in a prompt, pick a model, tweak settings → navigate to Talent or anywhere → come back → everything is gone. For a demo experience ("really get a feel of how it works"), this is death: users lose their work on every navigation.

**Fix:** Persist create-page state to `sessionStorage` (or a tiny zustand store with sessionStorage middleware):
- `videoPrompt`, `selectedVideoModel`, resolution/duration/fps/steps/guidance/seed, `videoResult`, `videoDownloadUrl`
- `prompt`, `selectedModel`, style, seed, width/height for images
- Restore on mount; clear on explicit "new" action. This is exactly R17 (Frontend State Management) territory.

---

## Bug 5 — Model-ID vocabulary mismatch breaks provider selection

**Files:**
- `frontend/src/app/create/_hooks/use-video-generation.ts` — default `selectedVideoModel = "wan2.2-5b"`
- `frontend/src/app/create/_hooks/use-create-data.ts` — initial video models are `wan-2.1-t2v` / `wan-2.1-i2v`
- `backend/video/adapters/simulation_adapter.py` — registered models: `wan-2.1`, `hunyuan`, `ltx`
- `backend/video/adapters/comfyui_adapter.py` — registered model: `wan-2.1`
- `backend/handlers/video_handler.py` — default model `wan-2.1`

**What happens:** The frontend sends `wan2.2-5b`; neither the simulation adapter nor the ComfyUI adapter registers that ID. Provider selection (`registry.select_provider(model="wan2.2-5b")`) finds **no matching provider/model** → falls through to simulation by luck in the handler path, but the Create-page path never even gets there. Model labels are inconsistent across every layer.

**Fix:** Pick ONE canonical model ID (`wan-2.1` is the most-used) and map at every boundary:
- Frontend sends `wan-2.1` (update default + initial list + any presets).
- Provider adapters keep `wan-2.1`.
- Add a normalization map (`wan2.2-5b` → `wan-2.1`, `wan-2.1-t2v` → `wan-2.1`, etc.) in `_build_request` / `_select_provider` for backward compatibility with any stored jobs.
- Do NOT ship three different spellings of the same model.

---

## Summary checklist for Kiro

| # | File(s) | Fix |
|---|---------|-----|
| 1 | `backend/handlers/video_handler.py` | Restore gated simulation fallback (non-prod), `simulation: true` in result |
| 2 | `backend/infrastructure/generate.py` (`/video`, `/video-from-image`) | Add simulation fallback so Create page works without ComfyUI; keep 503 in prod |
| 3 | `frontend/src/hooks/useCapabilities.ts`, `CapabilityGate.tsx`, `backend/app/api/v1/endpoints/capabilities.py` | Session-cache capability state; durable (DB-backed) classification; sticky demo badge |
| 4 | `frontend/src/app/create/_hooks/use-video-generation.ts`, `use-image-generation.ts`, `create/page.tsx` | Persist create state to sessionStorage so demo survives navigation |
| 5 | Frontend model defaults + backend adapters | Canonicalize model ID to `wan-2.1`; add normalization map for legacy IDs |

**Acceptance test:** With ComfyUI **down** and env non-production:
1. Open `/create` → Video tab shows "Simulated" badge.
2. Enter a prompt, hit Generate → you get a **real simulated video result** (downloadable, labeled simulation), not an error.
3. Navigate to another page and back → your prompt/settings/result are **still there**.
4. The "Simulated" badge **stays** through the whole session.
