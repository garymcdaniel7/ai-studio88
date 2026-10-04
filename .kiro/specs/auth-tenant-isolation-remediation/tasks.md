# Implementation Plan: Auth and Tenant-Isolation Remediation

## Overview

This is a linear bugfix and Phase 1 implementation task list derived from `design.md`, `.kiro/specs/deep-audit-report.md`, and `.kiro/specs/phase-1-nav-auth.md`. Execute the tasks in order: establish unfixed counterexamples, observe and preserve valid behavior, implement the ordered remediation, then run the final gates. This plan intentionally has no dependency DAG.

The plan is implementation-only. It does not claim that application code, six worktree variants, staging, credentials, migrations, deployment, or tests are already complete. Do not modify `bugfix.md`, `design.md`, `.config.kiro`, secrets, or production data as part of this task-list update or its later execution.

**Ownership and safety rules:** Backend-lane work is limited to backend-owned paths. `frontend/src/components/**` is frozen for lane agents; frontend page and page-local work belongs to the lane recorded in `LANES.json`. `backend/api_v1.py` is a single-file mutex and may be edited by only one backend executor at a time, with serialized review and tests. Auth-router branch/worktree state must be verified operationally rather than inferred from this checkout. No destructive or RLS-disabled test may target production.

**Validation conventions:** Use pytest/pytest-asyncio, httpx/FastAPI TestClient, pytest-mock or `unittest.mock`, Hypothesis, pytest-cov, and the repository's frontend lint/type checks. Mark tests `@pytest.mark.unit`, `@pytest.mark.integration`, and `@pytest.mark.slow` as applicable. New code targets at least 80% line coverage; enforcement, fallback, allowlist, and error branches each target at least 80% branch coverage. `UNIT-READY` means local/mock evidence is complete. `STAGING-REQUIRED` means local preparation may be complete but acceptance remains `BLOCKED` until controlled CTO-owned staging evidence exists.

## Tasks

1. **Write the bug-condition exploration property and record counterexamples before the fix.**
   - Add a Hypothesis-based test for `Property 1: Bug Condition - Trusted Tenant Enforcement`, using the `isBugCondition(input)` and `expectedBehavior(result)` specifications in `design.md`.
   - Cover invalid/missing/expired bearer tokens on non-public routes; all `org_id`, `orgId`, `org-id`, and `organization_id` query spellings; cross-tenant A/B reads and mutations; missing Brain executor context; unscoped query operations; missing or malformed worker org/job context; protected raw frontend calls; missing story routes; invalid migration destinations; active-but-expired credentials; stale frame values; and rollout actions with missing evidence.
   - Assert the intended fixed contract in the harness: structured rejection, no handler/database call, no foreign data or mutation, successful valid preflight, inactive expired credential, valid redirect/interstitial, or `BLOCKED` gate. Include concrete native-route cases for `GET /projects`, `GET /talent`, and `POST /talent`.
   - Run against an isolated unfixed revision or explicit pre-fix fixtures. Do not weaken the test when it fails. Record minimized counterexamples in the test docstring/evidence, including the first observed executor, query, route, worker operation, or unsafe rollout state.
   - **Owned paths:** `backend/tests/unit/security/test_auth_tenant_bug_condition.py` or the established security-test location; retained evidence under `.kiro/specs/auth-tenant-isolation-remediation/` only if required. No application-code changes in this task.
   - **Validation:** `uv run pytest <exploration-test> -q -m unit`; expected outcome is at least one reproducible failure on unfixed behavior. Preserve the original failing example for the post-fix rerun.
   - _Design: Bug Condition, Expected Behavior, Correctness Property 1, Testing Strategy / Exploratory Bug-Condition Checks._
   - _Requirements: 1.1-1.17, 2.1-2.5, 2.11-2.18_

2. **Write preservation property tests from observations on the unfixed implementation.**
   - Add `Property 2: Preservation - Valid Existing Behavior` before implementing remediation. First observe actual outputs and response shapes for non-buggy inputs, then encode those observations rather than assuming them.
   - Cover valid same-tenant authenticated list/detail/update/delete behavior; exact public probes; valid unauthenticated `OPTIONS` preflight; approved local/test fallback; documented shared/reference data; valid optional-auth paths that do not require tenant data; worker operations with trusted context; existing MCP authentication; Streamlit legacy/admin availability; and valid frontend session transport.
   - Use Hypothesis for valid same-tenant IDs, exact allowlist routes, valid worker contexts, supported CRUD operations, and non-injection query parameters. Exclude bug-condition cases. Permit only differences required by auth headers, trusted org predicates, expiry checks, request correlation, and documented navigation migration.
   - **Owned paths:** `backend/tests/unit/security/test_auth_tenant_preservation.py`, frontend transport contract-test locations owned by the frontend lane, and no frozen shared components.
   - **Validation:** `uv run pytest <preservation-test> -q -m unit`; expected outcome is passing on unfixed behavior. Record representative observed response shapes and preserve the same test for the final rerun.
   - _Design: Preservation Requirements, Correctness Property 2, Cross-Cutting Data-Access Rules._
   - _Requirements: 3.1-3.13_

3. **Repair the Brain executor bridge with trusted organization context across workspace variants.**
   - Identify the six affected Brain executors in `backend/aios/execution/tools.py` from the verified implementation/audit; do not assume every tool in the module is affected.
   - Make the bridge require trusted `org_id`/tenant context, reject missing or null context before validation or database access, and thread that context through all six executors in the main checkout and every applicable workspace variant.
   - Add application-layer scope for talent, assets, publishing posts, and every other tenant-owned record touched by those six executors. Never derive organization from prompt text, tool arguments, or client selectors.
   - Test organization A/B isolation for talent, assets, and publishing operations, including reads, updates, deletes, and inserts where applicable. Add regression coverage proving the authenticated MCP path remains intact.
   - **Do not modify `backend/aios/mcp/server.py` authentication or org propagation.** It is the clean/current MCP boundary; this task repairs only the Brain bridge that bypasses it. Do not expand MCP.
   - **Owned paths:** `backend/aios/execution/tools.py` in the active checkout and applicable workspace variants; executor unit/integration tests; `backend/aios/mcp/server.py` is read-only regression scope, not an edit path.
   - **Validation:** targeted Hypothesis/unit tests for all six signatures and context paths; A/B tenant tests with mocked DB/external providers; `uv run ruff check` on changed backend files. Record per-variant verification without claiming branches not present.
   - _Design: Fix Implementation §1, Component Responsibilities / Brain executor bridge and MCP boundary, Correctness Properties 1-3._
   - _Requirements: 2.5, 2.9, 2.11, 2.13, 2.18, 3.4, 3.5_

4. **Inventory and repair the 19+ unscoped `backend/api_v1.py` queries under the serialized mutex.**
   - Inventory every audit occurrence, including talent, scenes, shots, `lora_versions`, assets, storyboards, and talent relationships at the audit’s listed locations. Classify direct tenant ownership, inherited ownership, or documented system/shared exemption.
   - Add trusted organization predicates or call approved scoped helpers to every applicable select/detail/update/delete/aggregate. Overwrite org on inserts and prevent organization changes on updates; validate parent ownership for inherited records. Record-only access and RLS-only justification are insufficient.
   - Update the query inventory with file/symbol/operation/table, trusted org source, predicate or parent check, exemption reason/owner, remediation, test, reviewer, and status. Include related `backend/database.py`, `backend/data_access.py`, and `backend/tenant_repo.py` findings when the audit resolves through those helpers.
   - **Mutex:** only one backend executor may edit `backend/api_v1.py` at a time. Serialize the work and review; do not stage unrelated pre-existing files or claim concurrent edits are safe.
   - **Owned paths:** `backend/api_v1.py` (single-file mutex), inventory artifact such as `docs/architecture/AUTH_TENANT_QUERY_INVENTORY.md`, affected backend repository/helper files, and targeted tenant-isolation tests.
   - **Validation:** repository searches for `.table(`, `.from_(`, dynamic table names, wrappers, and `optional_auth`; per-occurrence query-builder tests; A/B record-ID tests; `uv run pytest backend/tests/unit/ -q -m unit`; no unclassified occurrence may pass the gate.
   - _Design: Fix Implementation §2, Cross-Cutting Data-Access Rules, Repository-Wide Query Audit Method._
   - _Requirements: 2.5, 2.6, 2.9, 2.18, 3.4-3.6, 3.10_

5. **Register and verify production authentication in `backend/main.py` and protect native routes.**
   - Register the production `AuthMiddleware -> OrgIdInjectionGuard` stack in the active app, with CORS/transport handling and valid `OPTIONS` completion before auth rejection. Prove effective Starlette middleware order with sentinel events rather than source order alone.
   - Use one authoritative policy and exact `PUBLIC_PROBE_ALLOWLIST` for health/readiness/docs/auth bootstrap/root probes and valid preflight. Reject all four organization-selector spellings and repeats with HTTP 422 / `ORG_ID_INJECTION_REJECTED` before handler/database execution. Preserve the auth router registration and public-route matrix; do not create a second policy.
   - Add route-level `Depends(require_auth)` defense in depth to `GET /projects`, `GET /talent`, and `POST /talent`. Extract trusted `AuthUser.org_id` and pass it to `get_projects`, `get_talent`, and `create_talent`; eliminate the current missing-argument `TypeError` without changing valid response shapes. Missing membership/null org must fail with the canonical structured authorization error before validation/DB access.
   - Verify the equivalent app factory/security registration where applicable, and preserve exact public routes `/`, `/login`, OAuth bootstrap/callback/logout, `/pricing`, health/readiness, docs/probes while protecting `/start`, `/cast`, `/write`, `/make`, `/publish`, settings/admin/brain, `/api/v1/*`, and `/aios/*` as specified.
   - **Owned paths:** `backend/main.py`, `backend/app/main.py`, `backend/auth.py`, `backend/auth_router.py` only for registered-route preservation, `backend/app/core/**`, and backend auth/middleware/native-route tests. Do not edit frontend shared components.
   - **Validation:** middleware-order, CORS/OPTIONS, policy/allowlist, injection, native-route 401/valid/null-org/TypeError tests; `uv run pytest backend/tests/unit/security backend/tests/unit/api -q -m unit`; `uv run ruff check` on changed backend paths. Assert rejected requests do not invoke handlers/helpers.
   - _Design: Architecture, Component Responsibilities, Expected Behavior / Security Contract Preservation, Route/Auth Matrix._
   - _Requirements: 2.1-2.4, 2.7, 2.9, 2.12, 2.14-2.15, 3.1-3.3, 3.6, 3.11_

6. **Attach bearer authentication to every `dashboard/api_client.py` request while retaining Streamlit legacy/admin status.**
   - Update all GET, POST, PUT, PATCH, DELETE, upload, and helper request paths to use the current session token as `Authorization: Bearer <token>`. Do not read unsafe raw storage, fabricate org IDs, expose service-role credentials, or change the structured error/request-ID contract.
   - Test missing, valid, expired, and refreshed tokens for every request method. Missing/expired sessions must follow the approved 401 refresh-or-login behavior without loops; valid sessions must preserve existing response handling.
   - Keep Streamlit available as a legacy/admin surface until authenticated parity is demonstrated. Do not delete it or claim feature parity from this transport change.
   - **Owned paths:** `dashboard/api_client.py`, dashboard transport tests and fixtures, and only directly related dashboard-owned scripts.
   - **Validation:** unit tests with mocked token/session provider for every method; `uv run pytest <dashboard-tests> -q -m unit`; lint/type checks used by the dashboard; secret scan confirms no credential is logged or returned.
   - _Design: Fix Implementation §4, Navigation and Transport Contract, Preservation Requirements._
   - _Requirements: 2.7-2.10, 3.7, 3.12_

7. **Make worker organization context mandatory and audit all lifecycle predicates.**
   - Require `--org-id` in `backend/worker.py`; parse and UUID-validate it before startup, validation, or database access. Remove the historical hardcoded UUID and unsafe `WORKER_ORG_ID`/other fallback; malformed or missing input must fail clearly and fail closed.
   - Audit `backend/database.py` helper calls and separately repair/test service-role `poll`, `claim`, `complete`, and `fail` operations. Derive `trusted_job_org_id` from validated job context and apply `.eq("org_id", trusted_job_org_id)` or an equivalent bound predicate to every directly organization-owned jobs query.
   - Clean related script references, including `backend/scripts/reprobe_video.py`, `backend/scripts/aios_scale_test.py`, and applicable workspace variants, without claiming a variant is fixed until verified. Never log service-role keys or other secrets.
   - **Owned paths:** `backend/worker.py`, affected worker/database helpers, related scripts, worker unit tests, and worker entries in the query inventory.
   - **Validation:** CLI tests for missing/malformed/valid UUID; mocked Supabase query-builder assertions for all four lifecycle operations; null job-context tests assert zero DB calls; `uv run pytest backend/tests/unit/worker -q -m unit`; static search proves the historical UUID and unsafe fallback are absent from owned scope.
   - _Design: Fix Implementation §5, Cross-Cutting Data-Access Rules, Testing Strategy / Worker Checks._
   - _Requirements: 2.11, 2.13, 2.18, 3.10_

8. **Coordinate `auth_router` registration across all six worktree variants as an operational task.**
   - Verify/re-include `auth_router` in each of the six agent worktree/branch variants named by the Phase 1 source, and run the branch-specific auth registration tests.
   - Record branch/worktree identity, commit or review evidence, test command/result, and unresolved conflicts for each variant. The main checkout is not evidence that six branches exist or are synchronized; do not claim branch state from this checkout.
   - Keep active main-entrypoint registration independently covered by Task 5. Coordinate cherry-picks/conflict resolution through the orchestrator and respect lane ownership.
   - **Owned paths:** operational worktree/branch records and branch-local `backend/main.py`/auth registration only under the assigned lane; no edits to unrelated worktree files from this checkout.
   - **Validation:** six explicit branch/worktree verification records, branch-local auth endpoint tests, and route matrix checks. Missing branch, conflict, or test evidence remains `BLOCKED`; do not infer completion.
   - _Design: Fix Implementation §6, Hypothesized Root Cause / Workspace Divergence, Dependencies and Gates P1._
   - _Requirements: 2.6, 2.10, 2.17_

9. **Build and mount exactly the 22 story-engine endpoints from the verified 0/22 baseline.**
   - Add a typed, authenticated, org-scoped router using existing story models and domain logic. Do not claim the rejected “50+ endpoints” inventory and do not build CAST/WRITE feature behavior.
   - Implement exactly these 22 contracts: `GET/POST /api/v1/story/universes`; `GET/PATCH/DELETE /api/v1/story/universes/{universe_id}`; `GET/POST /api/v1/story/universes/{universe_id}/characters`; `PATCH/DELETE /api/v1/story/characters/{character_id}`; `GET/POST /api/v1/story/universes/{universe_id}/episodes`; `GET/PATCH/DELETE /api/v1/story/episodes/{episode_id}`; `GET/POST /api/v1/story/episodes/{episode_id}/scenes`; `PATCH/DELETE /api/v1/story/scenes/{scene_id}`; `GET/POST /api/v1/story/scenes/{scene_id}/shots`; and `PATCH/DELETE /api/v1/story/shots/{shot_id}`.
   - Add Pydantic request/response schemas, UUID and bounded input validation, `{items,total,limit,offset}` pagination for lists, editor-role checks for writes, inherited parent-org checks, soft-delete/204 behavior, and structured 401/403/404/422/500 cases without existence leakage. Preserve `scene_builder`, duration estimation, and continuity services behind the router.
   - **Owned paths:** `backend/story_engine/router.py`, typed story schemas/services selected by the backend lane, router registration in the active app, and story unit/integration tests. Do not rewrite unrelated story domain logic.
   - **Validation:** enumerate all 22 routes in route tests; test unauthenticated 401, role 403, foreign-parent/detail 404 or canonical denial, invalid UUID/input 422, valid 201/200/204, pagination, and A/B isolation; `uv run pytest <story-tests> -q -m unit` plus controlled integration later.
   - _Design: Fix Implementation §7, exact 22-route table, Dependencies and Gates / Story API._
   - _Requirements: 2.5, 2.9, 2.16, 2.18, 3.1, 3.4-3.6_

10. **Implement and test the complete 33-route V1-to-V2 migration layer.**
    - Use the exact 33-route inventory in `design.md` §8 / `phase-1-nav-auth.md`, including `/home`, `/create`, `/editor`, `/production`, `/training`, `/talent`, `/workflows`, `/analytics`, `/projects`, `/models`, `/jobs`, `/assets`, `/admin/fleet`, `/admin/ise`, `/admin/keys`, `/admin/knowledge`, `/admin/downloads`, `/generate`, `/video`, `/audio`, `/campaigns`, `/calendar`, `/brands`, `/teams`, `/company`, and the keep routes `/`, `/brain`, `/login`, `/pricing`, `/story`, `/settings`, `/admin`, `/publish`.
    - Implement HTTP 301/deprecation behavior with the specified 90-day window (60 days for `/jobs`), forward all supported query parameters, and reject any destination that is not a valid V2 page/contract. `/editor` must remain an interstitial linking to WRITE/MAKE during Phase 1; `/models` must split character-model requests to `/cast?section=models` and generative-model requests to `/admin/models?section=generative`; do not flatten either special case.
    - Test every route status/destination, query preservation, deprecation observation, interstitial content, model-type split, kept routes, and no broken deep links/404 destinations in a built frontend environment.
    - **Owned paths:** `frontend/next.config.ts` or the approved frontend middleware/redirect map, migration tests, and only lane-owned destination adapters. Do not edit `frontend/src/components/**`; coordinate route/page changes with frontend lanes.
    - **Validation:** frontend build/lint/type checks and route tests for all 33 entries; browser/http assertions for representative deep links and query forwarding. A redirect to an unbuilt page fails acceptance.
    - _Design: Fix Implementation §8, Route/Auth Matrix, Correctness Property 6; Phase 1 §1._
    - _Requirements: 2.12, 2.15-2.16, 3.1-3.3, 3.11_

11. **Centralize protected frontend requests through `frontend/src/lib/api.ts` and migrate the 13+ confirmed raw callers.**
    - Make `api.ts` the single protected transport for typed `get`, `post`, `put`, `patch`, `delete`, `upload`, and `stream` calls. Preserve the Supabase session-token source, attach the current bearer token, avoid client `org_id` selectors, preserve structured errors/request IDs, and perform one refresh attempt on 401 before clearing session and redirecting to `/login`.
    - Migrate the confirmed callers: `components/brain-dock.tsx`, `components/feedback-buttons.tsx`, `components/topbar.tsx`, `app/story/page.tsx`, talent relationships/media/LoRA/voice page-local sections, `app/create/_components/generation-result.tsx`, `app/analytics/page.tsx`, `app/assets/page.tsx`, relevant `frontend/src/lib/hooks.ts`, and every other protected caller found by inventory. Do not blindly remove legitimate health/probe transports.
    - Classify every raw fetch as protected caller, API-client internal, compatibility `authFetch`, health/probe, or other approved exception. No unclassified protected caller may remain; explicitly document why probes are safe. Respect frontend lane ownership and do not modify frozen shared components from the backend lane.
    - **Owned paths:** `frontend/src/lib/api.ts`, `frontend/src/lib/hooks.ts`, page-local callers owned by their frontend lanes, caller inventory, and frontend auth contract tests. Shared `frontend/src/components/**` changes require the appropriate frontend/integration lane, not backend-lane edits.
    - **Validation:** raw-fetch inventory and classification; tests for missing/valid/expired/refreshed tokens, 401 refresh success/failure, redirect/no-loop, no `org_id` selector, and probe behavior; `npm --prefix frontend run lint`, configured typecheck/build, and targeted frontend tests.
    - _Design: Fix Implementation §9, Correctness Property 5, Navigation and Transport Contract; Phase 1 §2._
    - _Requirements: 2.7-2.10, 2.15, 3.7, 3.11_

12. **Implement the lane-owned AppShell/navigation and START route as explicit frontend handoffs.**
    - Coordinate frontend lanes through `LANES.json` for `START → CAST → WRITE → MAKE → PUBLISH`, route guards, active/completed/future states, and the route/auth matrix. Backend-lane work must not edit frozen `frontend/src/components/**`; shared `AppShell`, `AuthGate`, `TopBar`, `StepIndicator`, and `NavDropdown` changes are frontend/integration-lane work.
    - Implement responsive behavior: full horizontal nav at `>=1024px`, scrollable tabs at `768–1023px`, and hamburger/current-step control below `768px`. Keep `/` public landing distinct from protected `/start`; protect `/cast`, `/write`, `/make`, `/publish`, `/settings`, `/admin`, `/brain`, and protected APIs.
    - Build `/start` as an authenticated project dashboard only: scoped project/status summaries, existing create/open entry points, loading skeleton, recoverable typed error with retry and `X-Request-ID`, and empty state with first-project CTA. Do not build CAST/WRITE/MAKE/PUBLISH features, pipeline controls, or unrelated aggregates.
    - Record explicit handoff owner/path for each lane-owned page and shared-component integration, including unresolved lane conflicts. Do not claim frontend implementation from backend checkout state.
    - **Owned paths:** lane-owned `frontend/src/app/**` page/adapters and frontend navigation tests; shared components only by the designated frontend/integration lane; backend lane owns no frozen shared component edits.
    - **Validation:** responsive route/auth tests at all three breakpoints; loading/error/empty state tests; route matrix and 401 redirect tests; frontend lint/typecheck/build. Missing lane handoff or shared-component evidence remains `BLOCKED`.
    - _Design: Fix Implementation §§10-11, Navigation and Transport Contract, Route/Auth Matrix, Preservation Requirements; Phase 1 §§3-4 and §7._
    - _Requirements: 2.8, 2.12, 2.15-2.16, 3.1-3.3, 3.7_

13. **Add credential expiry and `ProviderType.USER_API_KEY` without persistence migration or rotation automation.**
    - Add `CredentialRecord.expires_at: str | None = None`, add `ProviderType.USER_API_KEY = "user_api_key"`, and make `_find_active()` require active status plus null/future expiry. Malformed expiry fails closed as inactive.
    - Test active, expired, revoked, rotated, null-expiry, malformed-expiry, masked metadata, and secret non-disclosure behavior. Do not expose secrets through the new field or enum.
    - Explicitly defer persistence migration (including migration 034) and rotation automation to later phases. Do not expand BYO credential management; BYO remains orchestration-layer provider credentials/pricing, not GPU resale.
    - **Owned paths:** `backend/credentials.py` and credential unit tests in the applicable workspace variants; no migration files, `.env` files, or rotation worker changes in Phase 1.
    - **Validation:** `uv run pytest <credential-tests> -q -m unit`; Hypothesis status/expiry combinations assert only non-expired active records resolve; static review confirms deferred migration/rotation is not claimed.
    - _Design: Fix Implementation §12, Preservation Requirements, Explicit Non-Goals; Phase 1 §6._
    - _Requirements: 2.17, 3.1, 3.13_

14. **Replace the stale four-value frame grid with the exact eleven-value contract.**
    - Accept exactly `124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600`; reject stale values such as `216` and `280`, zero, negative, non-integer, and unsupported values at API/schema/UI boundaries.
    - Update the owning validation/schema/selector and focused tests without changing unrelated generation or video behavior.
    - **Owned paths:** the backend/frontend frame-grid validation and selector files identified by inventory, plus focused tests; coordinate page changes with the owning frontend lane and do not edit frozen shared components from the backend lane.
    - **Validation:** unit and Hypothesis tests prove exactly the eleven values pass and all other values fail; run affected backend and frontend lint/type checks.
    - _Design: Fix Implementation §13, Glossary / Frame grid, Correctness Property 6; Phase 1 §15._
    - _Requirements: 2.16, 3.1, 3.13_

15. **Add rollout safety, audit completeness, benchmark, coverage, property, and controlled-staging gates.**
    - Implement/test one authoritative auth policy and exact route-derived allowlist, CORS-before-auth, stable error mapping, null-org rejection, dark-launch telemetry, and exactly one enforcement flip: `AUTH_ENFORCEMENT_FLIP=true`. Dark launch is controlled non-production observation only; staging/production start enforcing and rollback may not disable enforcement. Only an independently verified immediately prior enforcing release is a safe rollback target; otherwise restrict/shepherd traffic and fix forward.
    - Complete the repository-wide audit for `.table(`, `.from_(`, dynamic table names, wrappers, worker service-role operations, all `optional_auth` tenant paths, and the 19+ `api_v1.py` findings. Every occurrence needs one classification, predicate/parent proof, or documented system/shared exemption; unknown or RLS-only findings fail acceptance.
    - Add the C7 Hypothesis/regression suite covering Properties 1-5, 401/403/404/422/500 error cases, pagination, tenant A/B CRUD, six executor context propagation, worker four-operation predicates, route/story inventories, credential expiry, and exact frame grid. Rerun the same tests from Tasks 1 and 2; do not replace them with weakened tests.
    - Capture a representative before/after auth-overhead benchmark with the same request mix/environment, including probes, valid/invalid auth, injection rejection, and preflight. Keep benchmark tooling out of runtime.
    - Enforce >=80% new-code line coverage and >=80% branch coverage for enforcement, fallback, allowlist/preflight, and error/rejection categories; aggregate coverage cannot hide an under-covered category.
    - Run controlled staging only after local gates: two organization users, real A/B isolation, inherited ownership, service-role worker lifecycle, optional-auth null contexts, frontend refresh/redirect, startup fail-closed configuration, live route/allowlist parity, and approved RLS-disabled/service-role-backed checks. Never run destructive or RLS-disabled checks against production.
    - **Owned paths:** policy/audit/test/benchmark/coverage configuration and evidence under assigned backend/platform/frontend lanes; deployment policy records; no secrets, `.env`, `.config.kiro`, or production data.
    - **Validation:** targeted unit/property suites; `uv run pytest backend/tests/unit/ --cov=backend --cov-report=term-missing --cov-branch`; `uv run pytest backend/tests/integration/ -q -m integration` only in controlled staging; frontend lint/typecheck/build; benchmark marked `@pytest.mark.slow`; secret scan and `git diff --check`.
    - **Gate:** Local evidence may be `UNIT-READY`. Any missing staging access, secret-manager evidence, migrations, controlled users, deployment parity, or independent sign-off is explicitly `STAGING-REQUIRED` and remains `BLOCKED`; dark-launch or local green status never substitutes for staging acceptance.
    - _Design: Dependencies, Ordering, and Gates; Rollback; Testing Strategy; Coverage and Acceptance Gates; Explicit Non-Goals._
    - _Requirements: 2.1-2.19, 3.1-3.13_

16. **Final checkpoint: assemble evidence and record blocked/deferred work.**
    - Re-run the unchanged Property 1 exploration test and verify every original counterexample now satisfies the fixed behavior. Re-run the unchanged Property 2 preservation tests and verify valid same-tenant, public-probe, preflight, fallback, MCP, Streamlit, worker, and frontend behaviors remain preserved.
    - Verify evidence for all six Brain executors, all 19+ `api_v1.py` queries, native-route auth/TypeError repairs, dashboard methods, worker UUID/lifecycle predicates, six worktree auth-router records, exactly 22 story routes, all 33 migrations, frontend caller classification, AppShell/START lane handoffs, credential expiry/provider enum, exact frame grid, allowlist/rollout/benchmark/coverage/property/staging gates.
    - Confirm only owned implementation/test/evidence paths changed; confirm no `bugfix.md`, `design.md`, `.config.kiro`, secrets, generated media, frozen shared components from the wrong lane, or unrelated pre-existing files were changed.
    - Explicitly list any `STAGING-REQUIRED` item that remains `BLOCKED`, including missing CTO/platform access, migration evidence, controlled A/B users, live route parity, service-role/RLS-disabled checks, benchmark sign-off, branch/worktree verification, or independent tenant-isolation sign-off. Also list deferred work: credential persistence migration, rotation automation, CAST/WRITE/MAKE/PUBLISH feature builds, pipeline controls P1-P11, BYO credential management beyond expiry/enum, MCP expansion, publishing integrations, LoRA training, self-service deployment, and later monetization/GPU-resale work.
    - **Owned paths:** final test/evidence report and task status only; no application code, spec source, config, secrets, or production state changes.
    - **Validation:** full applicable unit/property suite, controlled integration suite if unblocked, coverage report, benchmark report, route/query inventories, `git status --short`, `git diff --check`, and secret scan. Final result is `ACCEPTED` only with all required evidence; otherwise record `BLOCKED` rather than claiming completion.
    - _Design: Correctness Properties 1-6, Dependencies and Gates, Coverage and Acceptance Gates, Explicit Non-Goals._
    - _Requirements: 2.1-2.19, 3.1-3.13_

## Notes

- This remains a linear bugfix/implementation plan: exploration first, preservation second, ordered remediation third, final checkpoint last. It intentionally contains no dependency DAG.
- `backend/api_v1.py` is a serialized single-file mutex. `frontend/src/components/**` is frozen for lane agents. Frontend page/shared-component changes must be handed to the appropriate `LANES.json` owner; backend work must not silently edit those paths.
- `backend/aios/mcp/server.py` is explicitly clean/current. The Brain leak is `backend/aios/execution/tools.py`; MCP auth must not be modified or expanded by this Phase 1 plan.
- The six worktree auth-router result is an operational record, not a claim about this checkout. Missing branch/worktree evidence is `BLOCKED`.
- CORS/valid `OPTIONS` handling precedes auth rejection. Client organization selectors are rejected; trusted org context comes only from validated membership/JWT, validated worker job context, or an explicitly authorized system context.
- Staging/production are fail-closed. Dark launch is non-production observation, `AUTH_ENFORCEMENT_FLIP=true` is the only flip trigger, and rollback cannot disable tenant enforcement. No production destructive or RLS-disabled test is permitted.
- Phase 1 is limited to navigation, auth, tenant-scoping plumbing, the exact story API surface, credential expiry/provider enum compatibility, and the exact frame grid. CAST/WRITE/MAKE/PUBLISH feature builds beyond plumbing, pipeline controls P1-P11, BYO credential management beyond expiry/enum, MCP expansion, publishing integrations, LoRA training, self-service deployment, and related monetization/GPU-resale work remain out of scope or deferred.
