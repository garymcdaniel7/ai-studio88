# Implementation Plan: AI Studio Phase 2 UI Revamp

## Overview

This plan implements the approved Phase 2 scope from [`ui-revamp-design.md`](../ui-revamp-design.md) after the remaining Phase 1 carry-forward work is complete. It is an execution plan only: do not modify this plan's source design, `.config.kiro`, secrets, `.env*`, old specs, generated media, or unrelated pre-existing changes.

Phase 2 uses the existing Next.js 16 / TypeScript frontend and Python 3.12 / FastAPI backend. Frontend work is lane-owned through `LANES.json`; `frontend/src/components/**` is frozen for lane agents and can change only through the designated frontend/integration lane. Backend work stays in backend-owned paths; `backend/api_v1.py` remains a single-file mutex and may be edited only by the backend lane in a serialized checkpoint.

The first three task groups are mandatory carry-forward work from Phase 1. They must preserve the now-passing backend authentication coverage while frontend callers are migrated through their designated lanes. Phase 2 feature work must not be marked complete when a required lane handoff, auth evidence record, tenant-isolation result, cost gate, or provider credential test is missing.

## Task Metadata

| Field | Value |
|---|---|
| Spec | `phase-2-ui-revamp` |
| Workflow | `fast-task` |
| Source design | `.kiro/specs/ui-revamp-design.md` |
| Lane registry | `LANES.json` |
| Frontend stack | Next.js 16, TypeScript, TailwindCSS, shadcn/ui |
| Backend stack | Python 3.12, FastAPI, async services, Supabase/PostgreSQL |
| Required test stack | pytest/pytest-asyncio, httpx/TestClient, pytest-mock/unittest.mock, Hypothesis where pure logic varies, Vitest/Playwright or repository frontend test commands |
| Coverage target | At least 80% line coverage for new code and at least 80% branch coverage for auth, tenant, cost, credential, provider, retry, and error paths |
| Frozen paths | `frontend/src/components/**`, unless changed by the designated frontend/integration lane |
| Serialized mutex | `backend/api_v1.py`, backend lane only |
| Explicit non-goals | Do not delete Streamlit; do not expose raw provider secrets; do not bypass `api` auth transport; do not weaken RLS/tenant gates; do not commit or deploy from this plan |

## Phase 2 Scope References

The task references below are scope identifiers for traceability to the approved design and the user's Phase 2 brief; they are not new application requirements files.

- **P2-WRITE** — Design §5.3: WRITE story/script editor, storyboard, inline prompt editing, customization, preview generation, references, and shot context.
- **P2-MAKE** — Design §5.4 and §10: MAKE Prompt Workshop, three-tier controls, simple/advanced mode, presets, queue, output review, and quality presets.
- **P2-ROUTES** — Design §§2, 4, 5 and Phase 1 route disposition: absorb `/create` and `/editor`, migrate `/production`, `/workflows`, `/models`, `/jobs`, and preserve valid deep links.
- **P2-PUBLISH** — Design §5.5 and §§15–16: library, calendar, queue, platform selector, optimal times, scheduling, auto-post, and provider reliability behavior.
- **P2-PLATFORMS** — Design §5.5: Fanvue-first connections, NSFW/SFW policy labels, disclosures, age/consent gates, and subsequent platform rollout.
- **P2-MCP** — Design §20: authenticated, org-threaded story, generation, publishing/calendar, credential, and provider tools.
- **P2-BYO** — Design §§11–12 and §15: encrypted user credentials, provider orchestration for Thunder Compute, RunComfy, Gemini, ElevenLabs, OpenAI, and Replicate, with cost and fallback controls.
- **P2-OLLAMA** — Design §12: Ollama/dolphin-llama3 free option, explicit opt-in/warning, health/configuration, and fallback behavior.
- **P2-VISUAL** — Design §3: dark near-monochrome system, sparse purple interaction accents, typography, glass overlays, whitespace, and micro-interactions.
- **P2-GATES** — Design §§7, 11, 16, 20 and the security/storage/testing standards: responsive behavior, accessibility, auth, tenant isolation, signed storage, cost evidence, secret handling, and final evidence.

## Tasks

- [ ] 1. Complete Phase 1 carry-forward: migrate frozen shared protected callers through the designated frontend/integration lane.
  - [ ] 1.1 Inventory and classify every protected caller under `frontend/src/components/**` before editing
    - Classify each raw `fetch`, `API_BASE` use, and compatibility `authFetch` as protected API, health/probe, or approved exception.
    - Include `brain-dock.tsx`, `feedback-buttons.tsx`, `topbar.tsx`, and any additional shared caller discovered by the inventory; do not assume the prior 13-call inventory is exhaustive.
    - Record the designated frontend/integration lane owner, target `api.*` method, test owner, and handoff status in the task execution record without changing frozen components from another lane.
    - **Owned paths:** inventory/test metadata only in the frontend/integration lane; `frontend/src/components/**` remains frozen to all other lanes.
    - **Validation:** repository search for `fetch(`, `API_BASE`, and `authFetch`; every protected shared caller has an owner and classification.
    - _References: P2-GATES; Design §7 and Phase 1 frontend auth migration._

  - [ ] 1.2 Migrate shared protected callers through the designated frontend/integration lane only
    - Replace protected shared calls with the canonical `api.get`, `api.post`, `api.put`, `api.patch`, `api.delete`, `api.upload`, or `api.stream` methods as applicable.
    - Preserve request payloads, response shapes, request IDs, one-refresh behavior, and the approved unauthenticated health/probe exceptions.
    - Do not edit frozen shared components from backend, talent, creation, post, platform, growth, or brain lanes; if a shared component needs an interface change, queue an explicit integration-lane handoff.
    - **Owned paths:** designated frontend/integration lane owns `frontend/src/components/**`; `frontend/src/lib/api.ts` changes remain serialized with the current API-client owner.
    - **Validation:** targeted component transport tests for valid, missing, expired, and refreshable sessions; no protected raw caller remains unclassified.
    - _References: P2-GATES; Design §7; Phase 1 §2._

  - [ ] 1.3 Verify shared-caller handoff and protect the auth contract
    - Run the frontend lint/typecheck/test commands selected by the integration lane and attach the result to the handoff.
    - Confirm no `org_id` selector is accepted from shared UI callers and no secret/token is logged or returned.
    - Keep failures or unavailable lane work explicitly `BLOCKED`; do not mark the Phase 2 feature tasks green on a partial shared migration.
    - **Validation:** `npm --prefix frontend run lint`; configured frontend typecheck/build; targeted auth transport tests; `git diff --check` on the lane diff.
    - _References: P2-GATES; Design §7 and Phase 1 preservation contract._

- [ ] 2. Complete Phase 1 carry-forward: migrate platform-owned admin/page `authFetch` callers through the platform lane.
  - [ ] 2.1 Inventory platform-owned protected calls and approved probes
    - Inspect `frontend/src/app/admin/**`, `frontend/src/app/settings/**`, `frontend/src/app/models/**`, and `frontend/src/app/workflows/**` according to the platform lane in `LANES.json`.
    - Classify each call as typed `api.*`, compatibility `authFetch`, health/probe, or an unapproved raw transport; preserve only probes with a documented public-route reason.
    - **Owned paths:** platform lane paths listed above plus platform-lane tests; do not edit `frontend/src/components/**`.
    - **Validation:** route/page caller inventory has zero unclassified protected requests and identifies all page-local owners.
    - _References: P2-ROUTES, P2-GATES; Design §§4 and 7; `LANES.json` platform lane._

  - [ ] 2.2 Migrate platform pages to the canonical authenticated transport
    - Convert admin, settings, models, and workflows protected calls to `api.*` methods where typed responses are available; retain `authFetch` only for an approved compatibility path with the same bearer/session contract.
    - Preserve governed-action confirmations, structured errors, retry behavior, `X-Request-ID`, and no-loop redirect behavior.
    - Ensure platform page code never imports `API_BASE` to call `fetch` directly and never sends a client-supplied organization selector.
    - **Owned paths:** `frontend/src/app/admin/**`, `frontend/src/app/settings/**`, `frontend/src/app/models/**`, `frontend/src/app/workflows/**`, and platform-lane tests.
    - **Validation:** page transport tests for GET/POST/PUT/DELETE/upload as applicable, expired-session refresh/redirect tests, and protected-route 401 tests.
    - _References: P2-GATES; Design §7 and Phase 1 §2._

  - [ ] 2.3 Validate the platform lane before feature absorption
    - Run platform-lane lint/typecheck/build and targeted tests; preserve all valid health/probe calls and remove no legacy admin surface.
    - Attach an explicit lane handoff stating changed paths, test commands/results, unresolved conflicts, and whether the platform lane is `UNIT-READY` or `BLOCKED`.
    - **Validation:** `npm --prefix frontend run lint`; configured typecheck/build; targeted platform tests; raw-fetch classification search.
    - _References: P2-GATES; Design §2 and Phase 1 preservation requirements._

- [ ] 3. Preserve the now-passing backend authentication coverage evidence.
  - [ ] 3.1 Capture the current passing auth/tenant evidence without changing backend behavior
    - Record the exact passing test commands and test-node IDs for auth middleware, route protection, tenant filters, worker context, Brain executor context, credential expiry, and frontend session transport evidence already present in the repository.
    - Preserve the original counterexample and preservation-test references from the Phase 1 remediation plan; do not rewrite passing tests to fit Phase 2 implementation details.
    - **Owned paths:** backend test/evidence paths already owned by the backend lane; no `.env`, `.config.kiro`, or unrelated application edits.
    - **Validation:** `uv run pytest backend/tests/unit/security backend/tests/unit/api -q -m unit` and the repository's established targeted auth test command, with the exact result retained.
    - _References: P2-GATES; Phase 1 remediation tasks 1–2 and final evidence checkpoint._

  - [ ] 3.2 Re-run preserved backend auth coverage after carry-forward handoffs
    - Confirm that shared and platform frontend migrations do not change backend 401/403/404/422 behavior, trusted `org_id` derivation, CORS preflight, or route allowlists.
    - If a regression appears, stop Phase 2 feature work and route the fix through the backend lane; do not weaken or delete the passing coverage.
    - **Owned paths:** backend auth/security tests and evidence; `backend/api_v1.py` remains a serialized mutex.
    - **Validation:** targeted security suite, tenant A/B tests, and `uv run ruff check` on any backend-owned fix.
    - _References: P2-GATES; Design §§7 and 16; Phase 1 auth/tenant contract._

  - [ ] 3.3 Establish the Phase 2 auth evidence gate
    - Require preserved passing evidence before accepting any new page, route, MCP handler, provider orchestration, or background job.
    - Require every Phase 2 lane handoff to identify its auth mechanism, tenant context source, protected API tests, and any deferred staging evidence.
    - **Validation:** evidence checklist has no missing auth/tenant test owner; unresolved auth evidence is `BLOCKED` rather than waived.
    - _References: P2-GATES; Design §§7, 11, 16, and 20._

- [ ] 4. Establish Phase 2 lane contracts and the dark visual foundation.
  - [ ] 4.1 Map CAST/WRITE/MAKE/PUBLISH ownership to `LANES.json` before creating new routes
    - Keep **CAST** explicit as the talent lane, currently `frontend/src/app/talent/**` and `frontend/src/app/training/**`; a new `frontend/src/app/cast/**` path requires an explicit talent-lane handoff before edits.
    - Keep **WRITE** explicit as creation-lane work for story/production plus post-lane ownership for the absorbed editor storyboard surface; a new `frontend/src/app/write/**` path requires an explicit creation/integration handoff.
    - Keep **MAKE** explicit as creation-lane work for create, post-lane work for editor generation controls, and platform-lane work for models/workflows; a new `frontend/src/app/make/**` path requires an explicit cross-lane handoff.
    - Keep **PUBLISH** explicit as growth-lane work for publish/analytics, with backend publishing and connection work in backend-owned paths.
    - Keep shared `frontend/src/components/**` frozen and route all shared component changes through the designated frontend/integration lane.
    - **Owned paths:** lane handoff metadata and page-local paths only; do not modify `LANES.json` opportunistically during feature implementation.
    - **Validation:** every planned file path has exactly one lane owner or an explicit integration handoff; overlapping ownership is resolved before implementation.
    - _References: P2-ROUTES, P2-GATES; Design §§4, 6, 16, and 17; `LANES.json`._

  - [ ] 4.2 Implement page-local dark near-monochrome tokens and interaction styling
    - Use deep slate/navy base `#0f172a`, slate surfaces `#1e293b`/`#334155`, muted `#64748b`, Inter typography, JetBrains Mono for prompts/code, and sparse purple `#7c3aed` only for actions, links, active state, and focus/selection affordances.
    - Keep decorative purple gradients out of the new pages; use restrained glass overlays, generous whitespace, and subtle transitions without making generation progress ambiguous.
    - Change shared/global styling only through the growth/integration owner of `frontend/src/app/globals.css`; page-local styling belongs beside the owning page.
    - **Owned paths:** `frontend/src/app/globals.css` through its LANES.json owner and page-local style files through their feature lanes; no direct shared-component edits.
    - **Validation:** frontend build/lint plus token/static checks for prohibited bright decorative accents and missing focus states.
    - _References: P2-VISUAL; Design §3 and §17._

  - [ ] 4.3 Create page-local primitives and API contracts without orphaned shared code
    - Define typed page-local contracts for PromptEditor, PromptPreview, GenerationQueue, FrameGrid, Storyboard, reference ordering, LoRA controls, QAGate, and platform/calendar states where each owning lane needs them.
    - Reuse existing `frontend/src/lib/api.ts` and backend schemas/services; do not create duplicate auth clients, raw fetch wrappers, or unowned shared components.
    - **Owned paths:** page-local component directories beside the owning route; backend schema/service interfaces in backend-owned paths only when required by a feature task.
    - **Validation:** TypeScript compilation catches all route/component contract mismatches before page implementation begins.
    - _References: P2-WRITE, P2-MAKE, P2-PUBLISH; Design §§6, 7, 17, and 20._

- [ ] 5. Implement WRITE as the story/script editor and customization surface.
  - [ ] 5.1 Build the lane-owned WRITE route and three-panel composition
    - Implement the authenticated WRITE page with Episodes list → visual Storyboard timeline → Shot detail panels, loading skeletons, typed recoverable errors, empty states, and retry actions.
    - Use existing story-engine contracts and tenant-scoped API methods; preserve route/auth behavior and do not make full-quality renders from WRITE.
    - Coordinate the new `/write` route with the creation lane and the editor storyboard absorption with the post lane; missing handoff evidence is `BLOCKED`.
    - **Owned paths:** `frontend/src/app/write/**` after creation/integration handoff, `frontend/src/app/story/**` and `frontend/src/app/production/**` through the creation lane, editor storyboard adapters through the post lane.
    - **Validation:** route/auth tests, loading/error/empty tests, and `npm --prefix frontend run build` after the lane handoff.
    - _References: P2-WRITE, P2-ROUTES; Design §§4, 5.3, 7, and 8._

  - [ ] 5.2 Implement script editor, inline H3 prompt editing, and shot customization
    - Support editable six-section H3 prompts with syntax-aware presentation, inline save/cancel, prompt preview, character/location/continuity context, reference-image upload, and frame thumbnail selection.
    - Provide regenerate with the same parameters and a new seed, upload/reference ordering, preview-quality generation only, and clear indication that full-quality rendering belongs in MAKE.
    - Validate all IDs and payloads through typed Pydantic/API contracts; preserve B2 signed URLs and job/asset provenance.
    - **Owned paths:** WRITE page-local TypeScript components and backend story/prompt service/schema files only where the existing contracts are insufficient; no `frontend/src/components/**` changes outside integration lane.
    - **Validation:** unit tests for prompt section editing/serialization, examples for save/cancel/regenerate/upload errors, and mocked API tests for signed reference uploads.
    - _References: P2-WRITE, P2-GATES; Design §§5.3, 7, 8, 11, and 17._

  - [ ] 5.3 Wire WRITE preview generation and continuity state
    - Connect storyboard frames to preview-quality generation using the approved Turbo 4-step/480p configuration, valid frame-grid values, selected talent/style context, and continuity metadata.
    - Display job state inline and retain job/workflow/model/seed provenance; do not duplicate the MAKE queue or create a separate `/jobs` page.
    - **Owned paths:** backend story/prompt/preview service or router files under backend lane; WRITE page files under creation lane; shared transport only through the integration lane.
    - **Validation:** mocked provider/job tests for queued/running/completed/failed states, tenant A/B isolation, and no-dispatch-without-cost-estimate behavior.
    - _References: P2-WRITE, P2-MAKE, P2-GATES; Design §§5.3, 8, 14, and 16._

  - [ ] 5.4 Test WRITE behavior and lane boundaries
    - Test keyboard and pointer editing, reference upload rejection, prompt validation, regeneration, continuity display, auth redirect, request-ID error display, and tenant isolation.
    - Test the editor split contract so storyboard features land in WRITE while generation controls are routed to MAKE.
    - **Validation:** targeted frontend unit/component tests; backend story/prompt unit tests; frontend lint/typecheck/build; no shared frozen file changed by the wrong lane.
    - _References: P2-WRITE, P2-ROUTES, P2-GATES; Design §§4, 5.3, 7, and 17._

- [ ] 6. Implement MAKE as the generation studio with three-tier controls.
  - [ ] 6.1 Build the lane-owned MAKE route and Prompt Workshop
    - Implement shot-type templates for Dialogue, Action, Establishing, and Reaction; section injectors for Subject, Action, Camera, Lighting, and Sound; and toggles for Anti-Plastic, Speed Verbs, and Frame Grid.
    - Add full prompt preview, model/checkpoint/workflow selection, valid frame-grid snap, Simple mode (three-step first-render path), and Advanced mode (schema-driven inspector) without building a node graph.
    - Coordinate `/make` ownership between creation, post, and platform lanes before editing new route paths.
    - **Owned paths:** `frontend/src/app/make/**` after explicit handoff; create adapters through creation lane; editor generation controls through post lane; models/workflows adapters through platform lane.
    - **Validation:** route/auth tests, prompt assembly tests, invalid frame-grid tests, and frontend build/lint/typecheck.
    - _References: P2-MAKE, P2-ROUTES; Design §§4, 5.4, 10, 14, and 17._

  - [ ] 6.2 Implement Tier 1, Tier 2, and Tier 3 control behavior
    - Tier 1 always-visible controls: model/checkpoint, CFG, steps, sampler/scheduler, seed random/lock/manual, aspect ratio presets, and negative prompt.
    - Tier 2 collapsed Advanced controls: denoise, batch size, CLIP skip, VAE, precision, LoRA stack/strength, and ControlNet.
    - Tier 3 pipeline controls: shot sequence, motion preset, character/style locks, batch variation, upscale toggle, and Quick Preview ↔ Full Quality presets with exact sampler/step/CFG/shift behavior from Design §14 P8.
    - Keep control values typed, bounded, serialized into the job/workflow request, and attributable to the resulting asset.
    - **Owned paths:** MAKE page-local TypeScript controls; generation/workflow schemas and service contracts under backend lane; models/workflows page adapters through platform lane.
    - **Validation:** unit tests for bounds/defaults/serialization, preset round-trip examples, and mocked dispatch assertions for every tier.
    - _References: P2-MAKE, P2-GATES; Design §§5.4, 8, 10, 14, 15, and 16._

  - [ ] 6.3 Implement inline queue and output review
    - Show Queued → Running with progress → Completed/Failed inline in MAKE, including queue position/backlog messaging, cancel, retry, OOM lower-resolution retry, provider-down retry, webhook fallback, and user-visible error guidance.
    - Add completed-render grid with Approve, Reject, and Retake actions and preserve asset/job/workflow/model provenance.
    - Enforce cost estimation/reservation before every GPU/provider dispatch and terminate/clean up ephemeral workers through existing backend lifecycle contracts.
    - **Owned paths:** MAKE page-local queue/review UI; backend generation/job/provider orchestration under backend lane; no separate jobs page.
    - **Validation:** unit tests for queue state transitions/retry classification/cancel/idempotency and integration tests with mocked Thunder/RunComfy/ComfyUI adapters; tenant and cost-gate assertions.
    - _References: P2-MAKE, P2-BYO, P2-GATES; Design §§5.4, 8, 15, and 16._

  - [ ] 6.4 Test MAKE controls, failure modes, and accessibility
    - Cover Simple/Advanced modes, keyboard access to all controls, screen-reader labels, focus retention in accordions, provider/key errors, timeout/cancel/retry states, and no raw secret display.
    - **Validation:** targeted frontend tests at desktop/tablet/mobile sizes; backend provider/job tests; lint/typecheck/build; coverage targets for control validation and retry/error branches.
    - _References: P2-MAKE, P2-GATES; Design §§3, 5.4, 7, 16, and 17._

- [ ] 7. Absorb CREATE/EDITOR and complete route migration into WRITE/MAKE.
  - [ ] 7.1 Split existing editor responsibilities and preserve supported behavior
    - Move storyboard/timeline/script responsibilities to WRITE and generation controls to MAKE; preserve only compatibility adapters needed during migration.
    - Absorb `/create` into MAKE, `/production` into WRITE, `/workflows` and generative `/models` into MAKE settings, character `/models` into CAST, and `/jobs` into the inline MAKE queue.
    - Keep CAST ownership explicit through the talent lane; do not accidentally move character identity/LoRA/voice features into WRITE or MAKE.
    - **Owned paths:** `frontend/src/app/create/**`, `frontend/src/app/story/**`, `frontend/src/app/production/**` creation lane; `frontend/src/app/editor/**`, `frontend/src/app/projects/**` post lane; `frontend/src/app/models/**`, `frontend/src/app/workflows/**` platform lane; CAST adapters talent lane.
    - **Validation:** each absorbed capability has one destination route and no duplicate side-effect path.
    - _References: P2-ROUTES, P2-WRITE, P2-MAKE; Design §§4, 5, and 8; Phase 1 route disposition._

  - [ ] 7.2 Implement redirects, interstitials, query forwarding, and deep-link safety
    - Implement the approved 301/deprecation map, editor interstitial to WRITE/MAKE, `/models` character-vs-generative split, `/jobs` 60-day window, and supported query-parameter forwarding.
    - Ensure every redirect destination is a built/auth-correct V2 page or documented interstitial; preserve `/`, `/login`, `/brain`, `/pricing`, `/settings`, `/admin`, and other keep routes according to the route matrix.
    - Do not delete Streamlit legacy/admin pages or claim parity before the authenticated Next.js surface is proven.
    - **Owned paths:** approved frontend routing config/middleware through the integration/platform owner and lane-owned destination adapters; no shared component changes.
    - **Validation:** route tests cover every migrated route, status/destination, query preservation, deprecation behavior, and no-404 deep link in a built frontend.
    - _References: P2-ROUTES, P2-GATES; Design §§2, 4, 5, 8, and 13; Phase 1 §1._

  - [ ] 7.3 Run the route-absorption checkpoint
    - Confirm WRITE, MAKE, CAST, and PUBLISH have explicit owners, no path is edited by two lanes, no frozen shared component was changed outside integration, and all old route callers use the new authenticated API contracts.
    - **Validation:** `npm --prefix frontend run lint`; configured typecheck/build; complete route migration suite; unresolved lane conflicts remain `BLOCKED`.
    - _References: P2-ROUTES, P2-GATES; Design §§4, 7, 8, and 16._

- [ ] 8. Implement PUBLISH library, calendar, queue, platform selector, optimal times, and auto-post.
  - [ ] 8.1 Build PUBLISH library and calendar views
    - Extend the growth-owned PUBLISH page with episode gallery, asset library, share links, month/week/day calendar modes, drag/drop scheduling, loading/error/empty states, and clear SFW/NSFW labeling.
    - Merge analytics entry points into PUBLISH without exposing cross-tenant engagement or asset data.
    - **Owned paths:** `frontend/src/app/publish/**` and related growth-lane page-local components; backend publishing/calendar service paths under backend lane.
    - **Validation:** frontend route/auth/tenant tests, drag/drop scheduling examples, keyboard alternative to drag/drop, and signed-URL-only media assertions.
    - _References: P2-PUBLISH, P2-PLATFORMS, P2-GATES; Design §§4, 5.5, 7, 8, and 11._

  - [ ] 8.2 Implement per-post platform selection and optimal-time suggestions
    - Support one or more platform targets per post, timezone-aware suggested posting times, explicit explanation/source for each suggestion, manual override, and validation for platform capability/content-policy conflicts.
    - Keep platform availability capability-driven so unsupported or not-yet-rolled-out platforms display a truthful disabled/Coming Soon state rather than a fake success path.
    - **Owned paths:** PUBLISH page-local UI through growth lane; scheduling/optimal-time service, schemas, and provider capability registry through backend lane.
    - **Validation:** deterministic unit tests across timezones/platforms/content classes; 401/403/422 cases; tenant A/B calendar isolation.
    - _References: P2-PUBLISH, P2-PLATFORMS; Design §§5.5, 8, 15, 16, and 20._

  - [ ] 8.3 Implement queue lifecycle and scheduled auto-post job
    - Add idempotent schedule/cancel/list operations and a background publishing job that transitions Queued → Published or Failed, records provider response/error, retries only transient failures, and pauses for reauthorization or policy blocks.
    - Require explicit user confirmation before first publish, preserve post/asset/job/platform provenance, and never publish content without the applicable disclosure/consent/moderation checks.
    - **Owned paths:** backend publishing router/service/repository/worker/job files; PUBLISH page-local queue UI; do not edit `backend/api_v1.py` without the backend mutex.
    - **Validation:** mocked provider integration tests for success, 401/403/409/422/429/500, idempotency, cancel, retry, reauth, tenant isolation, and durable job status.
    - _References: P2-PUBLISH, P2-PLATFORMS, P2-GATES; Design §§5.5, 8, 15, 16, and 20._

  - [ ] 8.4 Test PUBLISH calendar and queue end to end with mocked providers
    - Cover month/week/day rendering, platform selector, optimal-time override, queue filtering, failure recovery, share links, media authorization, accessibility, and responsive layouts.
    - **Validation:** frontend targeted tests plus backend integration tests with external APIs mocked; `npm --prefix frontend run build`; `uv run pytest` for publishing/calendar services.
    - _References: P2-PUBLISH, P2-GATES; Design §§5.5, 7, 11, 15, and 16._

- [ ] 9. Deliver Fanvue-first platform connections and controlled subsequent rollout.
  - [ ] 9.1 Implement authenticated connection lifecycle with Fanvue as the first-class target
    - Use the existing Connections/CredentialService patterns for encrypted OAuth/API-key references, health state, capability discovery, ownership, allowed roles, tool policy, disconnect/revoke, and reauthorization.
    - Add Fanvue-specific AI disclosure/watermark/caption, 18+ verification, consent/identity checks, reasonable-person moderation, and explicit publish confirmation gates.
    - Never store raw tokens in UI state/logs or return them after creation; derive `org_id` only from validated auth/MCP context.
    - **Owned paths:** backend connections/provider services and schemas; growth-owned PUBLISH connection UI; platform settings UI through platform lane where applicable.
    - **Validation:** mocked OAuth/API tests for connect, callback, health, expiry, revoke, role denial, policy denial, and tenant A/B isolation; secret-scan assertions.
    - _References: P2-PLATFORMS, P2-BYO, P2-GATES; Design §§5.5, 11, 13, 15, and 20._

  - [ ] 9.2 Add subsequent platform rollout behind capability and policy gates
    - Add adapters/configuration for OnlyFans and LoyalFans after Fanvue, then SFW platforms in the approved sequence (Instagram, X/Twitter, YouTube, Facebook, TikTok, Threads, Snapchat) without enabling unverified integrations by default.
    - Represent AI-label, NSFW, age, consent, verified-creator, and platform-specific content rules as provider capabilities/policies; do not infer policy approval from connection existence.
    - Roll out one provider at a time with adapter contract tests, feature flags, health checks, and truthful disabled/Coming Soon UI.
    - **Owned paths:** backend provider/connection adapters; growth PUBLISH UI; platform config/settings lane; no shared components outside integration lane.
    - **Validation:** one mocked contract suite per provider, capability/policy matrix tests, disabled-state tests, and no provider enabled without credential/configuration evidence.
    - _References: P2-PLATFORMS, P2-GATES; Design §§5.5, 8, 13, 15, and 20._

  - [ ] 9.3 Validate connection governance and publishing safety
    - Confirm every publish invocation passes authentication, tenant scope, role/tool policy, consent/moderation, cost/usage policy where applicable, and explicit confirmation requirements.
    - **Validation:** backend unit/integration tests for 401/403/404/409/422/429/500, cross-tenant IDs, expired credentials, policy blocks, and audit records; no raw platform secret in responses/logs.
    - _References: P2-PLATFORMS, P2-MCP, P2-GATES; Design §§7, 11, 15, 16, and 20._

- [ ] 10. Expand the authenticated MCP surface for story, publishing/calendar, credentials, and generation.
  - [ ] 10.1 Add story and storyboard MCP tools
    - Implement org-threaded handlers for `create_episode`, `create_scene`, `create_shot`, `update_shot_prompt`, `get_storyboard`, `list_episodes`, and `upload_shot_reference` using existing story services rather than duplicating DB queries.
    - Validate all IDs against the MCP identity's `org_id`; never accept organization selectors from tool arguments; preserve role checks and structured errors.
    - **Owned paths:** `backend/aios/mcp/**`, story service interfaces, and backend MCP tests; do not alter existing MCP auth semantics except through reviewed additive contracts.
    - **Validation:** mocked handler tests for authenticated success, missing/expired/revoked MCP keys, role denial, cross-tenant 404/403, invalid input 422, signed upload URL, and provenance.
    - _References: P2-MCP, P2-WRITE, P2-GATES; Design §§8, 17, and 20._

  - [ ] 10.2 Add publishing, calendar, and platform-connection MCP tools
    - Implement authenticated tools for `connect_platform`, `disconnect_platform`, `list_connected_platforms`, `schedule_post`, `list_scheduled_posts`, `cancel_scheduled_post`, `get_publishing_calendar`, and `list_platforms`.
    - Route mutations through publishing/connection services and Governance Boundary approval; require explicit confirmation for actual publish and enforce Fanvue/platform policy gates.
    - **Owned paths:** `backend/aios/mcp/**`, backend publishing/connection services, and MCP tests.
    - **Validation:** tool registry/handler tests, tenant A/B isolation, role/tool-policy denial, queue idempotency/cancel, platform capability filtering, and audit events.
    - _References: P2-MCP, P2-PUBLISH, P2-PLATFORMS, P2-GATES; Design §§5.5, 15, 16, and 20._

  - [ ] 10.3 Add credential and provider-configuration MCP tools
    - Implement `add_api_key`, `list_api_keys`, `remove_api_key`, `test_api_key`, and `get_default_provider` with masked metadata only, user/workspace ownership rules, expiry/revocation/rotation behavior, and audit records.
    - Return provider status and capability metadata without returning decrypted secrets; require role and Governance Boundary checks for mutations.
    - **Owned paths:** `backend/aios/mcp/**`, `backend/credentials.py`/credential services, provider registry, and tests; no `.env` or secret-file edits.
    - **Validation:** secret non-disclosure, expiry, revoke, rotate, wrong-org, wrong-role, invalid-provider, and provider-health tests.
    - _References: P2-MCP, P2-BYO, P2-GATES; Design §§11, 12, 15, and 20._

  - [ ] 10.4 Add full generation-control MCP tools
    - Implement `generate_with_ksampler`, `generate_with_workflow`, `list_workflows`, `switch_workflow`, `get_workflow_schema`, `generate_batch`, and `cancel_generation` using GenerationService/provider orchestration.
    - Validate workflow JSON/placeholders, model/control bounds, cost estimate, tenant-owned inputs, idempotency, and approval thresholds before dispatch.
    - **Owned paths:** `backend/aios/mcp/**`, backend generation/workflow services, and tests; preserve existing authenticated MCP server/router ownership.
    - **Validation:** mocked provider tests for valid/invalid workflows, cost rejection, batch limits, cancel/idempotency, provider fallback, and no cross-tenant assets/jobs.
    - _References: P2-MCP, P2-MAKE, P2-BYO, P2-GATES; Design §§5.4, 8, 14, 15, 16, and 20._

  - [ ] 10.5 Verify MCP registry, governance, and test coverage
    - Ensure discovery never grants execution permission, every tool carries provider/capability/risk/role/approval metadata, and every mutation creates the required audit/governance record.
    - **Validation:** `uv run pytest` targeted MCP suites; branch coverage for auth, tenant rejection, role/tool policy, approval, cost gate, provider failure, and secret masking meets 80%; no unauthenticated MCP read remains.
    - _References: P2-MCP, P2-GATES; Design §20 and production design Connections/MCP registry constraints._

- [ ] 11. Implement BYO API credentials and provider orchestration.
  - [ ] 11.1 Complete encrypted customer credential lifecycle
    - Extend the existing `CredentialService` with `ProviderType.USER_API_KEY` and provider metadata for customer-owned keys; enforce active/non-expired resolution, 90-day default expiry where configured, revoke, rotate with overlap rules, masking, and audit.
    - Keep platform fallback behavior explicit: user key → organization pool key → platform default only when policy permits; never return decrypted secrets to frontend, MCP, logs, or error payloads.
    - **Owned paths:** `backend/credentials.py`, backend credential schemas/services/repositories, and unit tests; never edit `.env*` or migration files unless a separately approved migration task exists.
    - **Validation:** unit/Hypothesis tests for status/expiry/rotation combinations, wrong-org access, ownership/role checks, fallback policy, masking, and secret non-disclosure.
    - _References: P2-BYO, P2-MCP, P2-GATES; Design §11 and Phase 1 credential-expiry contract._

  - [ ] 11.2 Implement provider adapters and registry for the requested BYO providers
    - Add capability-aware adapters/configuration for Thunder Compute and RunComfy GPU execution; Gemini and OpenAI LLM; ElevenLabs voice; and Replicate model execution.
    - Keep provider-neutral interfaces in services/ports and provider-specific code in adapters; use Settings/configuration rather than direct `os.environ` access in application logic.
    - Expose health, supported operations, estimated cost, timeout, retry, rate-limit, and credential requirements for each provider; preserve Thunder batch and RunComfy reliability/webhook capabilities from the design.
    - **Owned paths:** backend provider interfaces/registry/adapters, backend Settings, and provider unit tests; UI provider configuration remains platform/settings lane.
    - **Validation:** mocked contract tests per provider for health, auth failure, rate limit, timeout, success, unsupported capability, and cost estimation; no network calls in unit tests.
    - _References: P2-BYO, P2-MAKE, P2-PUBLISH, P2-GATES; Design §§8, 11, 13, 15, and 16._

  - [ ] 11.3 Wire GenerationService and Brain/provider routing to BYO orchestration
    - Resolve authenticated user/org/workload provider, apply privacy and denied-provider policies, check cost estimate/reservation before dispatch, select user/org/platform credential according to policy, and record provider/model/key-reference provenance without secret values.
    - Implement deterministic fallback behavior for provider down, 401, 429, timeout, OOM, webhook miss, and content/workflow failures; retry only the classes permitted by the design.
    - Ensure all GPU workers are ephemeral, time-bounded, cleaned up in `finally`, and all outputs are attributable to job/workflow/model/provider/version.
    - **Owned paths:** `backend/app/services/generation_service.py`, provider routing/orchestration, job/cost services, and tests; do not use the non-existent `backend/infrastructure/generate.py` as the orchestration location.
    - **Validation:** service tests for routing/fallback/privacy/cost/cleanup; mocked end-to-end generation lifecycle; tenant isolation; no dispatch when estimate or credential policy fails.
    - _References: P2-BYO, P2-MAKE, P2-GATES; Design §§8, 11, 15, and 16._

  - [ ] 11.4 Add platform/settings BYO provider configuration UI
    - Add a platform-lane Settings surface for adding, testing, masking, revoking, and selecting provider keys without redisplaying secrets; show health/capability/expiry and fallback mode.
    - Provide clear cost/ownership copy and link provider-specific configuration to the correct workload lane; do not allow client-side provider or org spoofing.
    - **Owned paths:** `frontend/src/app/settings/**` platform lane; backend credential/provider APIs backend lane; no shared frozen component changes outside integration lane.
    - **Validation:** frontend form/validation/auth tests, secret non-disclosure snapshots, 401/403/422/409 cases, and backend contract tests.
    - _References: P2-BYO, P2-GATES; Design §§11, 12, 13, and 17._

  - [ ] 11.5 Validate provider cost, tenant, and security gates
    - Verify every provider path has cost estimate evidence, org-scoped credential resolution, request timeout, retry classification, audit record, and structured error mapping.
    - **Validation:** targeted backend suites with coverage report; `uv run ruff check` on changed backend files; secret scan and `git diff --check`; any missing external credential remains `STAGING-REQUIRED` rather than simulated as success.
    - _References: P2-BYO, P2-GATES; Design §§8, 11, 15, 16, and 20._

- [ ] 12. Configure Ollama and the dolphin-llama3 free LLM option.
  - [ ] 12.1 Add provider configuration and health contracts for Ollama/dolphin-llama3
    - Extend the LLM provider registry with configured local/shared Ollama endpoint, model name, health timeout, privacy mode, token/latency limits, and explicit managed-VPS versus local mode.
    - Keep dolphin-llama3 opt-in with a clear uncensored-content warning and safety/policy setting; never hardcode endpoint credentials or model secrets.
    - **Owned paths:** backend LLM provider/config/service files and unit tests; use Settings/env configuration only.
    - **Validation:** mocked health/routing tests, startup validation for safe/missing configuration, provider capability tests, and no-secret logging assertions.
    - _References: P2-OLLAMA, P2-BYO, P2-GATES; Design §§8, 12, 13, and 20._

  - [ ] 12.2 Wire Ollama into Brain fallback and platform settings
    - Make Ollama the preferred free option only when enabled and healthy; route to user BYO providers or approved cloud fallback according to privacy, cost, and workspace fallback mode (AUTO/ASK/STRICT).
    - Add platform settings to select model/mode, inspect health, disable uncensored mode, and understand when a cloud/provider fallback incurs cost.
    - **Owned paths:** backend LLM routing; `frontend/src/app/settings/**` platform lane; `frontend/src/app/brain/**` brain lane for any Brain-specific controls; no shared frozen component changes outside integration lane.
    - **Validation:** routing tests for healthy/unhealthy/local/cloud/BYO combinations, privacy-denied provider, ASK confirmation, STRICT queue/failure, and visible cost notice.
    - _References: P2-OLLAMA, P2-BYO, P2-GATES; Design §§8, 12, 13, and 20._

  - [ ] 12.3 Test Ollama operational and tenant boundaries
    - Confirm model selection and conversation context are org/user scoped, provider credentials remain private, local endpoint failure does not hang requests, and fallback is observable/audited.
    - **Validation:** backend unit/integration tests with Ollama mocked; frontend settings/Brain tests; timeout and 401/429/500 cases; coverage for fallback branches.
    - _References: P2-OLLAMA, P2-GATES; Design §§7, 12, 16, and 20._

- [ ] 13. Apply cross-cutting responsive, accessibility, security, cost, and tenant-isolation gates.
  - [ ] 13.1 Validate responsive behavior across all Phase 2 pages
    - Verify `>=1024px` full horizontal step nav, `768–1023px` scrollable tabs, and `<768px` hamburger/current-step dropdown without horizontal overflow or inaccessible hidden controls.
    - Test WRITE, MAKE, PUBLISH, Settings/provider surfaces, and CAST handoff surfaces at desktop/tablet/mobile dimensions; keep `/brain` and protected pages consistent with the route matrix.
    - **Validation:** frontend viewport/component/browser tests, screenshot or DOM assertions where configured, and production build.
    - _References: P2-WRITE, P2-MAKE, P2-PUBLISH, P2-VISUAL, P2-GATES; Design §§3, 4, 5, and 17._

  - [ ] 13.2 Validate accessibility and interaction semantics
    - Require keyboard navigation, visible focus, semantic headings/landmarks, labels/descriptions for controls, dialog focus management, reduced-motion support, sufficient contrast, accessible drag/drop alternatives, and non-color-only status indicators.
    - **Owned paths:** each feature lane tests its page; shared remediation through frontend/integration lane only.
    - **Validation:** automated accessibility tests plus keyboard interaction tests for editor, controls, calendar, queue, dialogs, and provider forms; no unresolved critical violations.
    - _References: P2-VISUAL, P2-GATES; Design §§3, 5, 6, 7, and 17._

  - [ ] 13.3 Run security, tenant-isolation, storage, and secret-handling gates
    - Test unauthenticated 401, role 403, foreign-resource 404/denial, invalid input 422, structured 500, pagination, tenant A/B reads/mutations, MCP org threading, platform connection ownership, and no client `org_id` selectors.
    - Verify B2/S3 outputs use signed/CDN URLs, soft-delete semantics remain intact, object metadata includes org/job/content type, uploads validate MIME/magic bytes/size, and large files use multipart behavior.
    - Verify no raw provider/API secret appears in response, logs, frontend state, test fixtures, or staged files; run dependency/security checks applicable to changed code.
    - **Validation:** `uv run pytest backend/tests/unit/ -q -m unit`; targeted integration tests with real DB and mocked external APIs; `npm --prefix frontend run lint`; configured typecheck/build; secret scan; `git diff --check`.
    - _References: P2-BYO, P2-MCP, P2-PUBLISH, P2-GATES; Design §§7, 8, 11, 15, 16, and 20._

  - [ ] 13.4 Run cost and operational readiness gates
    - Confirm every GPU/generation/training dispatch has a pre-dispatch estimate/reservation, per-org quota/budget check, provider/runtime/instance evidence, timeout, retry policy, and cleanup path.
    - Confirm publishing/LLM provider usage has usage caps or auditable cost classification, and no provider fallback silently converts paid work to untracked platform spend.
    - **Validation:** unit tests for budget rejection, reservation release/reconciliation, provider fallback cost records, queue timeout/cleanup; coverage report separates new-code and branch targets.
    - _References: P2-MAKE, P2-PUBLISH, P2-BYO, P2-GATES; Design §§8, 14, 15, and 16._

- [ ] 14. Final Phase 2 evidence checkpoint.
  - [ ] 14.1 Assemble implementation, lane, and validation evidence
    - Re-run the unchanged Phase 1 auth exploration/preservation suites and prove the now-passing backend auth evidence remains passing.
    - Verify shared protected callers went only through the designated frontend/integration lane, platform `authFetch` callers went through the platform lane, and CAST/WRITE/MAKE/PUBLISH ownership matches `LANES.json` or has an explicit handoff.
    - Verify WRITE editor/customization, MAKE three-tier controls/queue, route absorption, PUBLISH calendar/queue, Fanvue-first rollout, MCP tools, BYO providers, and Ollama configuration have targeted tests and no orphaned code.
    - **Validation:** retain exact commands/results for backend unit/integration suites, frontend lint/typecheck/build/tests, provider contract tests, accessibility checks, secret scan, and `git diff --check`.
    - _References: P2-WRITE, P2-MAKE, P2-ROUTES, P2-PUBLISH, P2-PLATFORMS, P2-MCP, P2-BYO, P2-OLLAMA, P2-GATES; Design §§2–20._

  - [ ] 14.2 Resolve or explicitly record every blocked/deferred gate
    - Mark missing staging credentials, provider approvals, OAuth registrations, external API evidence, deployment parity, lane conflicts, or unavailable real-service checks as `STAGING-REQUIRED`/`BLOCKED` with an owner and next action; never replace missing evidence with a simulation claim.
    - Confirm no `.env*`, `.config.kiro`, old spec, secret, generated media, frozen shared component from the wrong lane, unrelated pre-existing file, or direct `main` push was changed by this plan.
    - **Validation:** scoped `git status --short`, changed-path ownership review, evidence checklist, and no commit creation.
    - _References: P2-GATES; Design §§13, 16, and 20; repository AGENTS.md lane and git-safety rules._

  - [ ] 14.3 Final no-regression and release-readiness gate
    - Confirm all required tests pass, coverage meets the 80% targets for new/auth/provider/cost/error branches, route destinations build, and all protected operations remain authenticated and tenant-scoped.
    - Confirm the final state is review-ready but not deployed: this task plan does not authorize production rollout, migration execution, provider secret installation, or commit creation.
    - **Validation:** `uv run pytest backend/tests/unit/ -q -m unit`; controlled `-m integration` only with approved staging; `npm --prefix frontend run lint`; configured frontend typecheck/build/test commands; security/secret scan; `git diff --check`.
    - _References: P2-GATES and all Phase 2 scope identifiers._

## Notes

- Tasks marked with `*` would be optional in this workflow, but no test task is marked optional here because the requested Phase 2 gates are release-blocking. A coding executor must implement all unchecked tasks unless the task is explicitly marked `BLOCKED` by a lane or staging dependency.
- `frontend/src/components/**` is frozen. Shared protected callers and any shared AppShell/auth/transport changes must be executed by the designated frontend/integration lane; page-local components belong beside their owning page.
- `LANES.json` currently names talent, creation, post, platform, growth, brain, and backend lanes. New `/cast`, `/write`, and `/make` paths are not automatically owned merely because an adjacent legacy path exists; each requires an explicit handoff before editing.
- `backend/api_v1.py` is a single-file mutex. If a Phase 2 endpoint cannot use an existing router/service, queue the backend edit and serialize it with backend review; never bundle unrelated dirty changes.
- Use real external API calls only in controlled integration/staging tests. Unit tests mock B2, Supabase, Thunder Compute, RunComfy, Gemini, ElevenLabs, OpenAI, Replicate, Fanvue, and other external providers.
- This plan does not create `.config.kiro`; existing metadata and old specs are read-only as requested. No commit is authorized.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "3.2", "4.2"] },
    { "id": 2, "tasks": ["1.3", "2.3", "3.3", "4.3"] },
    { "id": 3, "tasks": ["5.1", "6.1", "8.1", "9.1", "10.1", "11.1", "12.1"] },
    { "id": 4, "tasks": ["5.2", "6.2", "8.2", "9.2", "10.2", "11.2", "12.2"] },
    { "id": 5, "tasks": ["5.3", "6.3", "8.3", "9.3", "10.3", "11.3", "12.3"] },
    { "id": 6, "tasks": ["5.4", "6.4", "7.1", "8.4", "10.4", "11.4", "13.1"] },
    { "id": 7, "tasks": ["7.2", "10.5", "11.5", "13.2"] },
    { "id": 8, "tasks": ["7.3", "13.3"] },
    { "id": 9, "tasks": ["13.4", "14.1"] },
    { "id": 10, "tasks": ["14.2"] },
    { "id": 11, "tasks": ["14.3"] }
  ]
}
```
