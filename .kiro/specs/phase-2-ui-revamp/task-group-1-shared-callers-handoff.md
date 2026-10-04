# Phase 2 Task Group 1 — Shared Caller Inventory and Handoff

**Scope:** Phase 2 UI Revamp, Task Group 1 only (`tasks.md` 1.1–1.3)
**Audit checkout:** `/Users/garymcdaniel/kiro/ai-studio88`
**Audit status:** `AUDITED; MIGRATION BLOCKED`
**Evidence date:** 2026-08-25

## Ownership gate

`LANES.json` defines `talent`, `creation`, `post`, `platform`, `growth`, `brain`, and `backend` lanes. It does **not** define a `frontend/integration` lane, executor, worktree, or owned path. The repository guidance freezes `frontend/src/components/**` to non-integration lanes.

Therefore no shared component was edited, no shared transport test was added, and no migration is claimed complete. Every migration/handoff status below is explicitly:

> **BLOCKED — designated `frontend/integration` lane is not registered or available in this checkout; `frontend/src/components/**` is frozen and cannot be edited from this lane.**

The source design requires the existing `api` object from `frontend/src/lib/api.ts`; raw `fetch()` and direct `API_BASE` use are not allowed for protected calls. The canonical client already supplies bearer auth from the Supabase session, request IDs, one 401 refresh attempt, redirect handling, and client organization-selector rejection.

## Complete protected-caller inventory

The repository search covered `fetch(`, `API_BASE`, `authFetch`, `axios`, and `XMLHttpRequest` under `frontend/src/components/**`. It found exactly five calls in three shared components and no additional callers.

| Caller | Current call | Classification | Target canonical method | Payload/auth concerns | Component owner | Test owner | Handoff status |
|---|---|---|---|---|---|---|---|
| `frontend/src/components/brain-dock.tsx:32` | `POST /aios/v1/chat` with `{ message, mode: "creative" }` | Protected API | `api.post<BrainResponse>("/aios/v1/chat", { message, mode: "creative" })` | Message and mode are the only client fields currently sent. Do not add `org_id`, user, token, or provider-secret fields. Preserve response fallback (`response`/`message`), loading state, and error UI. The gateway path is canonical; do not silently replace it with the legacy `/api/v1/brain/chat` wrapper. | `frontend/integration` (not registered) | `frontend/integration` (not registered); use canonical transport tests plus a focused BrainDock request/response test when the lane exists | **BLOCKED — designated `frontend/integration` lane unavailable; frozen shared file cannot be edited.** |
| `frontend/src/components/feedback-buttons.tsx:86` | `POST /api/v1/feedback/durable` with rating, lineage, idempotency, and client identity/tenant attribution fields | Protected API | `api.post<DurableFeedbackResponse>("/api/v1/feedback/durable", payload)` | Preserve rating mapping and the stable retry idempotency key. The current body includes client-supplied `org_id`, `user_id`, and `asset_org_id`; migration must not trust or introduce client-selected tenant/actor attribution. Coordinate a backend contract that derives identity and organization from validated auth context, then send only permitted lineage/rating fields. Do not place tokens or secrets in payloads or errors. | `frontend/integration` (not registered) | `frontend/integration` (not registered); focused success, 401/403/422, retry/idempotency, and tenant-isolation transport tests | **BLOCKED — shared edit unavailable; backend identity-contract dependency also requires explicit owner/evidence.** |
| `frontend/src/components/feedback-buttons.tsx:117` | Best-effort `POST /api/v1/learn/feedback` with `{ agent, output_type, rating, context }` | Protected API; legacy learning signal | `api.post<LearningFeedbackResponse>("/api/v1/learn/feedback", { agent, output_type, rating, context })` with a deliberately best-effort catch path | Preserve non-blocking behavior, but route through canonical auth/error handling. Validate bounded rating and avoid including tokens, secrets, or client organization selectors in `context`; do not log context. Confirm whether this legacy endpoint is still approved before enabling a new caller. | `frontend/integration` (not registered) | `frontend/integration` (not registered); focused best-effort success/failure and auth transport tests | **BLOCKED — designated integration owner unavailable; legacy endpoint approval is unresolved.** |
| `frontend/src/components/topbar.tsx:37` | `GET /api/v1/search?q=${encodeURIComponent(searchQuery)}` after 300 ms debounce | Protected API | `api.get<SearchResponse>(
  \`/api/v1/search?q=${encodeURIComponent(searchQuery)}\`
)` | Preserve minimum two-character query behavior, debounce, result shape, and empty/error states. `q` is the only caller-controlled query parameter; do not add any `org_id`, `orgId`, `org-id`, or `organization_id` selector. Auth must come from the canonical client. | `frontend/integration` (not registered) | `frontend/integration` (not registered); focused debounce/request, 401 refresh/redirect, empty result, and tenant-scoped response tests | **BLOCKED — designated integration owner unavailable; frozen shared file cannot be edited.** |
| `frontend/src/components/topbar.tsx:64` | Polling `GET /aios/v1/health/alerts` immediately and every 60 seconds | Health/probe endpoint, but **not an approved public exception** | `api.get<AlertsResponse>("/aios/v1/health/alerts")` | This path is absent from `PUBLIC_PROBE_ALLOWLIST`; it must use authenticated transport and must not be changed to `noAuth`. Preserve polling cadence and alert/count response shape. Handle 401 through canonical refresh/redirect rather than silently bypassing auth. | `frontend/integration` (not registered) | `frontend/integration` (not registered); focused initial poll, interval cleanup, auth expiry, and non-2xx handling tests | **BLOCKED — designated integration owner unavailable; frozen shared file cannot be edited.** |

## Search completeness

- `brain-dock.tsx`: one raw protected POST.
- `feedback-buttons.tsx`: two raw protected POSTs; the second is intentionally best-effort today.
- `topbar.tsx`: one protected tenant search GET and one authenticated health/alerts GET.
- `frontend/src/components/**`: no `authFetch` caller, no additional `API_BASE` use, no axios caller, and no direct `XMLHttpRequest` caller.
- `frontend/src/lib/api.ts`: no existing typed wrapper was found for these five exact paths. The target is therefore direct `api.get`/`api.post` usage unless the integration lane adds narrowly-scoped typed wrappers through the same canonical client.

## Auth, tenant, and secret gate

- No bearer token, API key, provider credential, or secret value is included in this evidence.
- No organization value is included. The feedback identity/tenant field names are recorded only as a security concern because the current caller sends client-supplied attribution; the migration must remove client authority over those fields or use a backend contract that derives them from the validated session.
- Search uses only `q`; the inventory found no client organization selector in the shared caller URLs.
- The canonical client’s `assertNoOrgSelector` rejects `org_id`, `orgid`, `org-id`, and `organization_id` query keys before network access. Shared migration must retain that behavior.
- Protected shared callers must preserve request IDs, one refreshable 401 replay, redirect-on-refresh-failure, structured errors, and no auth bypass.

## Test and validation handoff

**Required owner:** `frontend/integration` (currently unregistered in `LANES.json`).
**Existing transport evidence to reuse:** `frontend/src/lib/__tests__/api.test.ts` covers bearer attachment, request IDs, no-auth health probes, refresh, redirect, and `authFetch` compatibility. It does not prove these shared components have migrated.

When an integration lane is provisioned, it must:

1. Replace all five calls with the target canonical methods without changing the frozen components from another lane.
2. Add focused component transport tests for valid, missing, expired, and refreshable sessions; durable feedback 401/403/422 and idempotent retry; search empty/error behavior; alert polling cleanup; and Brain response fallback.
3. Verify no client organization selector or secret/token is accepted, logged, or returned.
4. Run `npm --prefix frontend run lint`, the configured typecheck/build, focused frontend tests, and `git diff --check` on the lane diff.
5. Update this handoff with the integration lane identity, changed files, exact test node IDs/results, and any remaining `BLOCKED` evidence.

**Current validation result:** inventory complete; migration and focused component tests not run because the required owner/worktree is unavailable. No application source files were changed by this audit.
