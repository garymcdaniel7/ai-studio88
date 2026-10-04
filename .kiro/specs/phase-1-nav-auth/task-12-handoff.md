# Phase 1 Task 12 — Frontend handoff evidence

## Scope delivered in this lane

- Added the protected `/start` page at `frontend/src/app/start/page.tsx`.
- Added a page-local `StartStepNavigation` adapter at `frontend/src/app/start/_components/start-navigation.ts` for the exact `START → CAST → WRITE → MAKE → PUBLISH` contract.
- Added the project-only dashboard at `frontend/src/app/start/_components/start-dashboard.tsx`.
- Added typed dashboard state/error helpers in `start-state.ts`, including `ApiError` classification and `X-Request-ID` display.
- Added route-level loading skeleton evidence in `frontend/src/app/start/loading.tsx` and a client loading skeleton.
- Added focused Playwright contract coverage in `frontend/e2e/start-navigation.spec.ts` for route/auth matrix, step order/state, breakpoints, loading/error/empty states, request IDs, and unauthenticated START redirects.

## Lane ownership and integration handoffs

| Surface | Owning lane from `LANES.json` / Phase 1 | Handoff path | Status |
|---|---|---|---|
| `/start` project dashboard | growth (`src/app/page.tsx` is the currently registered growth path) | `frontend/src/app/start/**` adapter; growth lane must own final page placement and public `/` separation | **Adapter ready; integration required** |
| `/cast` | talent | `frontend/src/app/cast/**` | **Future-page handoff; no feature behavior built** |
| `/write` | creation | `frontend/src/app/write/**` | **Future-page handoff; no feature behavior built** |
| `/make` | creation | `frontend/src/app/make/**` | **Future-page handoff; no feature behavior built** |
| `/publish` | growth | `frontend/src/app/publish/**` | **Existing page remains untouched; nav target is explicit** |
| Shared AppShell/AuthGate/TopBar/StepIndicator/NavDropdown | frontend integration lane (not present in current `LANES.json`) | Lift `StartStepNavigation` into shared `frontend/src/components/**` only through the designated integration owner | **BLOCKED pending integration owner** |

## Guard and route notes

- `/` remains the existing public landing route; `/start` is not in `PUBLIC_EXACT_PATHS` and is therefore protected by the existing Next.js proxy when Supabase is configured.
- The page-local guard redirects all non-authenticated auth states to `/login?redirect=%2Fstart`, including unconfigured/expired/error states. It does not weaken or replace proxy enforcement.
- The adapter intentionally does not build CAST, WRITE, MAKE, or PUBLISH behavior. Links are handoff targets only.
- No files under `frontend/src/components/**` were modified because that directory is frozen for lane agents.

## Validation evidence

- Targeted contract suite: `npm --prefix frontend exec playwright test e2e/start-navigation.spec.ts --project=desktop` (run after implementation).
- Frontend checks: `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, and `npm --prefix frontend run build` (run after implementation).
- The authenticated HTTP redirect assertion may be skipped when the server is intentionally running without Supabase configuration; in that mode the client guard remains the fallback authority.
