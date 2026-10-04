# Phase 2 Task Group 2 — Platform Lane Handoff

## Scope and ownership

- **Task group:** Phase 2 task group 2 only (Phase 1 carry-forward for platform-owned callers).
- **Lane:** `platform` from `LANES.json`.
- **Worktree:** `/Users/garymcdaniel/kiro/ai-studio88-platform`.
- **Branch:** `agent/platform`.
- **Owned route trees:** `frontend/src/app/admin/**`, `frontend/src/app/settings/**`, `frontend/src/app/models/**`, `frontend/src/app/workflows/**`.
- **Shared/frozen paths:** `frontend/src/components/**` were not changed. `frontend/src/lib/api.ts` was read but not changed because the API-client transport is shared and its owner is serialized separately.
- **Main worktree:** already contained unrelated dirty backend/frontend changes; no application files in the main worktree were changed for this handoff.

## Work completed

The following platform-owned pages were migrated from page-local `API_BASE` + compatibility `authFetch` calls to the canonical `api.get`, `api.post`, `api.put`, or `api.patch` methods:

- `frontend/src/app/admin/page.tsx`
- `frontend/src/app/admin/fleet/page.tsx`
- `frontend/src/app/admin/health/page.tsx`
- `frontend/src/app/admin/keys/page.tsx`
- `frontend/src/app/admin/knowledge/page.tsx`
- `frontend/src/app/admin/objects/page.tsx`
- `frontend/src/app/models/page.tsx`
- `frontend/src/app/settings/page.tsx`
- `frontend/src/app/workflows/page.tsx`

`frontend/src/app/admin/connections/page.tsx` was already using `api.*` directly and `useSWRFetch`, whose fetcher delegates to `api.get`; it required no transport edit.

Governed confirmation flows and action semantics were preserved for worker stop/pause/shutdown and model archive/permanent-delete actions. Non-2xx responses now reject through `ApiError` from the canonical client instead of being manually parsed as `Response` objects. No page-local organization selector was found or added.

## Caller inventory

Every compatibility caller found before migration is listed below. There were no raw `fetch` calls in the four route trees; all listed calls were `authFetch` calls paired with a page-local `API_BASE` constant. All routes are authenticated platform/admin API calls, not public probes. Operational health/status calls are marked as **protected operational probes**: they remain useful probes, but they are sent through the authenticated canonical client and are not approved unauthenticated exceptions.

| Original caller | Classification | Canonical target | Owner | Evidence/status |
|---|---|---|---|---|
| `admin/page.tsx:73`, `:341` — Ollama status GET | Protected operational probe | `api.get("/api/v1/infrastructure/ollama/status", { signal })` | Platform | Migrated; typecheck/build pass |
| `admin/page.tsx:102` — output directory GET | Protected API | `api.get("/api/v1/generate/output-dir", { signal })` | Platform | Migrated; typecheck/build pass |
| `admin/page.tsx:117` — services health GET | Protected operational probe | `api.get("/api/v1/infrastructure/services/health", { signal })` | Platform | Migrated; typecheck/build pass |
| `admin/page.tsx:185` — worker progress GET | Protected operational probe | `api.get("/api/v1/infrastructure/worker/progress")` | Platform | Migrated; polling behavior retained |
| `admin/page.tsx:283` — service toggle POST | Protected governed mutation | `api.post("/api/v1/infrastructure/services/{service}/toggle", body)` | Platform | Migrated; service toggle guard retained |
| `admin/page.tsx:303` — Ollama preference PUT | Protected mutation | `api.put("/api/v1/infrastructure/ollama/preference", body)` | Platform | Migrated |
| `admin/page.tsx:316` — output directory PUT | Protected mutation | `api.put("/api/v1/generate/output-dir", body)` | Platform | Migrated |
| `admin/keys/page.tsx:41` — service status GET | Protected operational probe | `api.get("/api/v1/infrastructure/admin/services")` | Platform | Migrated |
| `admin/keys/page.tsx:55` — RunPod status GET | Protected operational probe | `api.get("/api/v1/infrastructure/runpod/status")` | Platform | Migrated |
| `admin/keys/page.tsx:70` — admin keys POST | Protected credential mutation | `api.post("/api/v1/infrastructure/admin/keys", body)` | Platform | Migrated; no secret logging/display added |
| `admin/fleet/page.tsx:68` — workers GET | Protected API | `api.get("/api/v1/infrastructure/workers")` | Platform | Migrated |
| `admin/fleet/page.tsx:69` — fleet settings GET | Protected API | `api.get("/api/v1/infrastructure/fleet/settings")` | Platform | Migrated |
| `admin/fleet/page.tsx:84` — worker action POST | Protected governed mutation | `api.post("/api/v1/infrastructure/workers/{id}/{action}")` | Platform | Migrated; existing action UI retained |
| `admin/fleet/page.tsx:97` — fleet settings PUT | Protected mutation | `api.put("/api/v1/infrastructure/fleet/settings", body)` | Platform | Migrated |
| `admin/fleet/page.tsx:120` — idle-worker shutdown POST | Protected governed mutation | `api.post("/api/v1/infrastructure/workers/idle/shutdown")` | Platform | Migrated; governed confirmation retained |
| `admin/fleet/page.tsx:132` — worker launch POST | Protected cost-affecting mutation | `api.post("/api/v1/infrastructure/launch", body)` | Platform | Migrated; launch UX retained |
| `admin/fleet/page.tsx:323` — model placements GET | Protected operational probe | `api.get("/aios/v1/models/placements")` | Platform | Migrated |
| `admin/fleet/page.tsx:431` — model unload POST + placements GET | Protected mutation + probe | `api.post("/aios/v1/models/unload", body)` + `api.get(placements)` | Platform | Migrated |
| `admin/fleet/page.tsx:442` — ensure-loaded POST + placements GET | Protected mutation + probe | `api.post("/aios/v1/models/ensure-loaded", body)` + `api.get(placements)` | Platform | Migrated |
| `admin/fleet/page.tsx:453` — archive POST + placements GET | Protected mutation + probe | `api.post("/aios/v1/models/archive", body)` + `api.get(placements)` | Platform | Migrated |
| `admin/fleet/page.tsx:464` — restore POST + placements GET | Protected mutation + probe | `api.post("/aios/v1/models/restore", body)` + `api.get(placements)` | Platform | Migrated |
| `admin/health/page.tsx:376` — stuck-job check POST | Protected operational mutation | `api.post("/aios/v1/health/check-stuck-jobs")` | Platform | Migrated; governance section retained |
| `admin/health/page.tsx:377` — decisions GET | Protected API | `api.get("/aios/v1/decisions?limit=10")` | Platform | Migrated |
| `admin/health/page.tsx:479` — full health GET | Protected operational probe | `api.get("/aios/v1/health/full")` | Platform | Migrated |
| `admin/health/page.tsx:480` — alerts GET | Protected operational probe | `api.get("/aios/v1/health/alerts")` | Platform | Migrated |
| `admin/health/page.tsx:481` — latest UAT GET | Protected API | `api.get("/aios/v1/ise/uat/latest")` | Platform | Migrated |
| `admin/health/page.tsx:482` — infrastructure dashboard GET | Protected API | `api.get("/api/v1/infrastructure/dashboard")` | Platform | Migrated |
| `admin/health/page.tsx:517` — UAT run POST | Protected operational mutation | `api.post("/aios/v1/ise/uat/run", {})` | Platform | Migrated |
| `admin/knowledge/page.tsx:30` — knowledge search GET | Protected API | `api.get("/aios/v1/knowledge/search?q=...&limit=20")` | Platform | Migrated; query encoding retained |
| `admin/knowledge/page.tsx:41` — talent knowledge GET | Protected API | `api.get("/aios/v1/knowledge/talent/{id}")` | Platform | Migrated |
| `admin/knowledge/page.tsx:48` — workflow DNA stats GET | Protected API | `api.get("/aios/v1/knowledge/workflow-dna/stats")` | Platform | Migrated |
| `admin/knowledge/page.tsx:55` — session insights GET | Protected API | `api.get("/aios/v1/session/insights")` | Platform | Migrated |
| `admin/objects/page.tsx:47` — object DNA GET | Protected API | `api.get("/api/v1/object-intelligence/object-dna")` | Platform | Migrated |
| `admin/objects/page.tsx:48` — product DNA GET | Protected API | `api.get("/api/v1/object-intelligence/product-dna")` | Platform | Migrated |
| `admin/objects/page.tsx:49` — digital twins GET | Protected API | `api.get("/api/v1/object-intelligence/digital-twins")` | Platform | Migrated |
| `models/page.tsx:230` — restore model PATCH | Protected governed mutation | `api.patch("/api/v1/models/{id}", body)` | Platform | Migrated; restore UX retained |
| `models/page.tsx:276` — upload model to GPU POST | Protected cost-affecting mutation | `api.post("/api/v1/models/{id}/upload-to-gpu")` | Platform | Migrated |
| `models/page.tsx:293` — free GPU model POST | Protected mutation | `api.post("/api/v1/models/{id}/free-gpu")` | Platform | Migrated |
| `settings/page.tsx:26` — completed jobs GET | Protected API | `api.get("/api/v1/jobs?status=completed")` | Platform | Migrated |
| `settings/page.tsx:33` — LoRA models GET | Protected API | `api.get("/api/v1/models?type=lora")` | Platform | Migrated |
| `workflows/page.tsx:59` — workflow list GET | Protected API | `api.get("/api/v1/workflows")` | Platform | Migrated |
| `workflows/page.tsx:69` — workflow detail GET | Protected API | `api.get("/api/v1/workflows/{id}")` | Platform | Migrated |

Post-migration search in the platform worktree:

```text
git grep -n -E 'authFetch|API_BASE|fetch\(' -- frontend/src/app/admin frontend/src/app/settings frontend/src/app/models frontend/src/app/workflows
(no matches)
```

The only remaining raw `fetch` implementation is inside the shared `frontend/src/lib/api.ts` transport itself, as expected. `admin/connections/page.tsx` and `useSWRFetch` use canonical `api.*` transport and were retained.

## Validation evidence

All commands were run from `/Users/garymcdaniel/kiro/ai-studio88-platform/frontend` unless noted:

| Command | Result |
|---|---|
| `npm run typecheck` | **PASS** (`tsc --noEmit`) |
| `npm run lint` | **PASS** (0 errors, 95 warnings; warnings are repository-wide/pre-existing and not promoted to errors) |
| `npm run build` | **PASS**; Next.js 16.2.10 production build completed. It emitted the existing `NEXT_PUBLIC_API_URL is not set in production` warning during static generation. |
| `git diff --check` (platform worktree) | **PASS** |
| Frontend unit tests | **BLOCKED** — `frontend/package.json` defines no test script/test runner, and no platform-local focused transport test file is available in this worktree. |

## Exact handoff status

**Status: BLOCKED — not `UNIT-READY`.**

The page migration is complete and the route trees are clean, but the platform worktree's shared `frontend/src/lib/api.ts` is an older contract. It adds request IDs and typed error mapping, but its `authFetch`/`api.*` implementation does not perform the required one-refresh-on-401 behavior or no-loop session redirect behavior, and it does not reject client organization selectors/origin changes. The main worktree contains a newer hardened `api.ts`, but it is an unrelated pre-existing dirty file and `frontend/src/lib/api.ts` is outside the platform lane's owned route paths. The API-client owner must sync the hardened transport into this platform branch (or explicitly authorize a serialized shared-client handoff) before this lane can claim preservation of refresh/no-loop and tenant-selector protections.

No backend files, secrets, `.env*`, `.config.kiro`, old specs, frozen shared components, or unrelated dirty files were changed. No commit was created.

Focused lint follow-up:

| `npx eslint src/app/admin/page.tsx src/app/admin/fleet/page.tsx src/app/admin/health/page.tsx src/app/admin/keys/page.tsx src/app/admin/knowledge/page.tsx src/app/admin/objects/page.tsx src/app/models/page.tsx src/app/settings/page.tsx src/app/workflows/page.tsx` | **PASS** (0 errors, 6 warnings; existing hook/unused-symbol warnings) |
