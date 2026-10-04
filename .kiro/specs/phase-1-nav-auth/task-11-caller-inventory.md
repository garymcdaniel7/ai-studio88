# Phase 1 Task 11 — Frontend Caller Inventory

Audited from the current checkout on 2026-08-23. The working tree had pre-existing changes; this inventory does not treat unrelated dirty files as authored by Task 11.

## Raw `fetch()` classification

| Source | Classification | Status / rationale |
|---|---|---|
| `frontend/src/lib/api.ts` (`executeRequest`, `executeRawRequest`, `stream`) | API-client internal | Canonical transport internals. These are the only protected `fetch()` calls permitted in the client. |
| `frontend/src/components/brain-dock.tsx` | Protected caller | **Blocked: shared `frontend/src/components/**` is frozen for this lane.** Requires frontend/integration lane migration to `api.post("/aios/v1/chat", ...)`. |
| `frontend/src/components/feedback-buttons.tsx` (durable feedback and legacy learning) | Protected caller | **Blocked: frozen shared component.** Requires frontend/integration lane migration to `api.post(...)`; the payload currently includes legacy client `org_id`/`user_id` fields that need an owner-approved server-derived contract. |
| `frontend/src/components/topbar.tsx` (search and alerts) | Protected caller | **Blocked: frozen shared component.** Requires frontend/integration lane migration to `api.get(...)`. |
| `frontend/src/app/create/_hooks/use-audio-generation.ts` (preview and save) | Protected caller | **Blocked: creation lane owns `src/app/create/**`.** Requires creation-lane migration to `api.post(...)`. |
| `frontend/src/app/create/_hooks/use-create-data.ts` (ElevenLabs and MOSS catalogs) | Protected caller | **Blocked: creation lane owns `src/app/create/**`.** The other requests in this hook already use the compatibility `authFetch` facade. |
| `frontend/src/lib/error-logger.ts` | Protected caller | Migrated in this task to `api.post("/api/v1/errors/log", entry)`. Fire-and-forget behavior remains unchanged. |
| `frontend/src/hooks/useOnlineStatus.ts` | Health/probe | Approved exception. Performs an unauthenticated `GET /` reachability check with a 5-second timeout and does not access tenant data. It intentionally does not refresh or redirect on a probe failure. |

The `frontend/src/app/brain/RESPONSIBILITY_MAP.md` `fetch(...)` strings are documentation examples, not executable callers.

## Compatibility `authFetch` callers

`authFetch` remains only as a response-preserving compatibility facade for existing page code. It now delegates to the same canonical policy as `api.*`: Supabase session token sourcing, bearer attachment, request IDs, one refresh replay on 401, session clearing/login redirect, same-origin validation, and organization-selector rejection.

Current compatibility callers: `app/admin/fleet/page.tsx`, `app/admin/health/page.tsx`, `app/admin/keys/page.tsx`, `app/admin/knowledge/page.tsx`, `app/admin/objects/page.tsx`, `app/admin/page.tsx`, `app/brain/components/ApprovalCard.tsx`, `app/brain/hooks/use-brain-chat.ts`, `app/brain/hooks/use-brain-memory.ts`, `app/brain/hooks/use-collections.ts`, `app/create/_hooks/use-create-data.ts`, `app/create/_hooks/use-image-generation.ts`, `app/create/_hooks/use-video-generation.ts`, and `app/page.tsx`.

## Confirmed named migrations already present

The current checkout already routes the Phase 1 named page-local callers through `api.*`: `app/story/page.tsx`, talent relationships/media/profile-image/LoRA/voice sections, `app/create/_components/generation-result.tsx`, `app/analytics/page.tsx`, `app/assets/page.tsx`, and `frontend/src/lib/hooks.ts`. Their existing dirty state predates this execution and was not rewritten.

## Tenant selector audit

No executable frontend caller currently contains `org_id`, `orgId`, `org-id`, or `organization_id` query selectors. The canonical transport rejects all four query-key spellings (case-insensitive) before making a request. Organization context remains server-derived from the authenticated bearer session.

## Remaining handoffs / blockers

1. Shared components require the designated frontend/integration lane; this lane must not edit them.
2. Creation hooks require the creation lane; this lane must not edit them.
3. The frontend package contains existing Vitest-style tests but does not declare/install Vitest or a test script, so the new contract test file is added for the configured repository convention but cannot run until the frontend test runner dependency is provisioned by the frontend/tooling owner.
