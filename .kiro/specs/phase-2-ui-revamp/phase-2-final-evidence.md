# Phase 2 UI Revamp — Close-Out Evidence Reconciliation

**Audit scope:** Tasks 13–14 evidence plus Close-Out Sprint Tasks 15.1–15.6.
**Checkout:** `/Users/garymcdaniel/kiro/ai-studio88` (`main`, HEAD `2d35736`).
**Decision:** **BLOCKED — Phase 2 is not complete and is not release-ready.** The close-out adds useful local/mock evidence, but mandatory frontend integration, authenticated responsive/accessibility, storage/provider staging, ownership, and no-regression gates do not have complete evidence.

This artifact is the only file updated by this reconciliation. No commit, deployment, migration, provider-secret installation, `.env*` edit, `.config.kiro` edit, old-spec edit, frozen shared-component edit, generated-media edit, or unrelated dirty-file cleanup was performed.

## 0. Close-Out Sprint Tasks 15.1–15.6

The table below reconciles the six close-out result records against the current checkout. `UNIT-READY` means local/mock evidence only; it does not authorize a staging or release decision. Counts are reported only where the result is preserved in a handoff or existing evidence; source-collected node counts are labeled as such and are not substituted for execution counts.

| Task | Close-out result | Exact command/evidence | UNIT-READY / remaining gate |
|---|---|---|---|
| **15.1 — connection namespace, revoke, and provider probe** | Connection close-out source contains **22 collected test cases**; platform connection source contains **11 collected test cases** (**33 source-collected cases total**). Coverage includes connection-ID credential namespace, successful/failed provider probes, provisional rollback, revoke failure state preservation, health lookup, Fanvue state/role/policy/tenant behavior, and secret masking. | `uv run pytest backend/tests/unit/test_connection_closeout.py backend/tests/unit/test_phase2_platform_connections.py -q -m unit` — the checked handoffs preserve the focused test scope but do **not** preserve an executed pass count; no suite was rerun in this read-back-only reconciliation. | **UNIT-READY for mocked lifecycle/probe contracts.** **STAGING-REQUIRED/BLOCKED** for live provider probes, OAuth/provider approvals, real credentials, deployment parity, and two-org staging A/B evidence. |
| **15.2 — worker cost-gate entry point** | **5 test cases** cover the real `Worker._process_job()` boundary: reserve before provider execution, hard-limit rejection before provider call, actual-cost finalization, `finally` release on provider failure, and org A/B isolation. | `uv run pytest backend/tests/unit/worker/test_worker_cost_gate.py -q -m unit` — the handoff/source preserves 5 tests and the entry-point assertions; an executed pass count was not preserved in the checked evidence. | **UNIT-READY locally** for the mocked worker boundary and tenant budget ledger. **STAGING-REQUIRED/BLOCKED** for live worker timeout/termination, provider receipt, quota/budget enforcement, and actual GPU dispatch. The legacy `GenerationEngine` direct path remains separate in `backend/api_v1.py` and `backend/action_commands.py`; it is not evidence that every generation path enters the queued worker cost gate. |
| **15.3 — Ollama environment-isolated opt-in** | `backend/tests/unit/test_byo_provider_contracts.py` contains the explicit dolphin opt-in rejection/warning contract. The broader selected command passed only with process-local opt-in while excluding the default-rejection test because the repository `.env` selects `dolphin-llama3` without opt-in; no environment file was changed. | `OLLAMA_UNCENSORED_OPT_IN=true uv run pytest backend/tests/unit/test_byo_provider_contracts.py -q -m unit -k 'not dolphin_requires_explicit_opt_in_and_exposes_warning_only'` is preserved in the prior evidence as part of the passing selected suite. The current source test names are `test_dolphin_requires_explicit_opt_in` and `test_dolphin_opt_in_exposes_warning_and_safe_capabilities`; the preserved `-k` expression does not exactly match either name, so the claimed exclusion cannot be independently verified without rerunning. The default-rejection case is **not** promoted to a green repository-wide result; its environment conflict is recorded rather than waived. | **UNIT-READY only for isolated explicit opt-in/safe metadata behavior.** **BLOCKED** for a clean repository environment-isolation result and **STAGING-REQUIRED** for managed-VPS Ollama configuration, warning/opt-in deployment parity, and fallback evidence. |
| **15.4 — C7 route inventory delta** | C7 selected checks pass when the two stale inventory assertions are excluded. The exact delta is **23 observed routes versus stale expected 22 (+1)**. The tenant-audit assertion also expects stale source lines **[56, 63, 72, 83]** while the current observed lines are **[50, 57, 66, 77]**. | `OLLAMA_UNCENSORED_OPT_IN=true uv run pytest backend/tests/unit/security/test_c7_rollout_gates.py backend/tests/unit/security/test_auth_boundary_coverage.py backend/tests/unit/security/test_task5_auth_stack.py backend/tests/unit/security/test_api_v1_tenant_isolation.py backend/tests/unit/security/test_brain_executor_tenant_scope.py backend/tests/unit/worker/test_worker_org_context.py backend/tests/unit/test_credentials_expiry.py backend/tests/unit/story_engine/test_router.py -q -m unit -k 'not test_property_5_route_and_story_inventories_are_exact and not test_direct_api_supabase_calls_are_confined_to_tenant_helpers'` — **all selected tests passed** in the preserved record; the two named assertions were excluded, not fixed. | **UNIT-READY for the selected C7 policy/auth checks only.** **BLOCKED** until the +1 route inventory and stale line-number assertion are reconciled without weakening behavior. Full auth/tenant acceptance remains **STAGING-REQUIRED** for deployment parity, live CORS/allowlist, controlled A/B users, and independent sign-off. |
| **15.5 — MCP inventory delta and authenticated tool contracts** | The current working MCP registry declares **52 tools** versus **16 at `HEAD` (+36)**, including authenticated Phase 2 story/generation/publishing/connection/credential tools. The focused MCP contract file has **10 source-declared test nodes**; its selected scenarios cover auth/org matching, selector rejection, idempotency, cost-before-dispatch, credential masking, role/provider/policy errors, and foreign-job isolation. | Preserved selected-suite command: `OLLAMA_UNCENSORED_OPT_IN=true uv run pytest backend/tests/unit/mcp/test_phase2_tools.py backend/tests/unit/test_byo_provider_contracts.py backend/tests/unit/test_byo_provider_orchestration.py backend/tests/unit/test_phase2_platform_connections.py backend/tests/unit/test_credentials_expiry.py backend/tests/unit/story_engine/test_router.py backend/tests/unit/worker/test_worker_org_context.py backend/tests/unit/test_thunder_h3_adapter.py -q -m unit -k 'not dolphin_requires_explicit_opt_in_and_exposes_warning_only'` — **all selected tests passed** in the prior record; the combined execution count is not preserved. | **UNIT-READY for the selected authenticated/mock MCP contracts.** The +36 registry delta still needs inventory ownership/review and live deployment parity; external provider/OAuth and staging tenant evidence remain **STAGING-REQUIRED/BLOCKED**. |
| **15.6 — storage signed/CDN/soft-delete/multipart contract** | **8 test cases** cover signed URL selection, CDN preference, raw B2 URL rejection, immutable tenant-scoped key shape, required metadata, multipart threshold/completion, multipart abort, fail-closed direct delete, and provider-error propagation. Asset-service evidence requires soft-delete first and pending deletion scheduling; request-path hard delete is prohibited. | `uv run pytest backend/tests/unit/test_storage.py -q -m unit` — the handoff preserves the 8-case focused scope but not an executed pass count. `backend/tests/unit/test_services/test_asset_service.py` could not collect because the pre-existing `backend.app.providers` package has a circular import involving unrelated BYO changes. | **UNIT-READY for the mocked compatibility boundary.** **STAGING-REQUIRED/BLOCKED** for live B2/CDN signed URLs, multipart behavior, durable pending-deletion worker wiring, required metadata across legacy callers, and controlled credentials. |

### Close-out test-count and availability reconciliation

- Preserved exact execution counts from the earlier evidence remain: **9 passed** auth-preservation tests; **98 passed** local publishing/disclosure/platform/preflight/lifecycle/preset-cost tests; **32 passed, 2 skipped** route migration Playwright tests; **4 passed** settings-provider Playwright tests; and **2 passed, 6 failed** WRITE Playwright tests (authenticated fixture/route state unavailable).
- The close-out handoffs preserve commands and focused scopes for Tasks 15.1, 15.2, 15.5, and 15.6, but not their executed pytest totals. This reconciliation intentionally records the exact source-collected counts where available and marks execution totals unavailable rather than converting source counts into false pass claims.
- No test runner was added or assumed: frontend `package.json` has no Vitest/Jest test script; the publish contract Node test is blocked by its extensionless import; the growth `publish-audit.spec.ts` is unavailable; and the required authenticated browser fixtures are absent.
- `gitleaks` is unavailable (exit 127), so no full repository secret-scan result is claimed. Broader/stale suites remain unavailable or blocked: the prescribed `backend/tests/unit/api` path is missing, Stripe-dependent credit tests cannot collect because `stripe` is absent, and the C7 route/line-number assertions remain stale.
- This section does not claim that a local green subset closes the Phase 2 gate. The final decision remains **BLOCKED** until ownership, frontend integration/authenticated browser evidence, live provider/B2 staging, stale inventory reconciliation, and independent release evidence exist.

## 1. Evidence sources and repository state

- Phase 2 has no local `requirements.md`, `design.md`, or `.config.kiro`; the task plan references `.kiro/specs/ui-revamp-design.md` as the source design.
- `LANES.json` registers `talent`, `creation`, `post`, `platform`, `growth`, `brain`, and `backend`. It does **not** register the required `frontend/integration` lane.
- Registered worktrees found: `ai-studio88-brain`, `ai-studio88-creation`, `ai-studio88-growth`, `ai-studio88-platform`, `ai-studio88-post`, and `ai-studio88-talent`.
- Main checkout had extensive pre-existing dirty and untracked application/test/evidence paths before this checkpoint. Existing `.config.kiro` files under old/Phase 1 specs were present and untouched.
- `git diff --check`: **PASS** in main.
- `git diff --check`: **PASS** in all six registered lane worktrees.
- No direct `main` push or commit was made.

## 2. Lane ownership and handoff evidence

| Surface | Owner from `LANES.json` / handoff | Evidence | Status |
|---|---|---|---|
| Shared protected callers and shared transport | `frontend/integration` required, but lane is absent | `task-group-1-shared-callers-handoff.md` inventories five callers and explicitly blocks migration | **BLOCKED** |
| CAST | `talent`: `src/app/talent/**`, `src/app/training/**` | No new CAST route or Phase 2 frontend handoff in talent worktree | **BLOCKED for final Phase 2 evidence** |
| WRITE | Creation owns story/production; post owns editor storyboard; new `/write` needs explicit integration handoff | Creation `frontend/src/app/write/HANDOFF.md` exists; it identifies missing authenticated shot-update/preview backend contract | **UNIT-READY locally; BLOCKED integration** |
| MAKE | Creation owns `/create`; post owns editor generation controls; platform owns models/workflows; new `/make` needs cross-lane handoff | Creation `MAKE_HANDOFF.md` says page-local workshop is `UNIT-READY`, `/make` integration is blocked, richer backend payload/preflight are deferred | **UNIT-READY locally; BLOCKED integration** |
| PUBLISH | Growth owns `src/app/publish/**` and analytics; backend owns publishing/connection services | Growth `task-group-4-lane-ownership-handoff.md` is `UNIT-READY`; `backend-publishing-handoff.md` records durable cancel/idempotency/optimal-time/async-job/server-policy gaps | **UNIT-READY locally; BLOCKED production** |
| Platform/provider settings | Platform owns admin/settings/models/workflows | `platform-lane-handoff.md` records page migration complete but transport synchronization and focused frontend tests blocked | **BLOCKED** |
| Brain | Brain owns `src/app/brain/**` | No Phase 2 frontend handoff artifact found; only unrelated/pre-existing backend execution-tool dirt exists | **BLOCKED / missing evidence** |
| Post | Post owns editor/assets/projects | No Phase 2 frontend handoff artifact found | **BLOCKED / missing evidence** |
| Backend | `backend/**`; `backend/api_v1.py` mutex remains | Backend tests and implementation lint were run; no backend application file was changed by this checkpoint | **Partial local evidence** |

### Ownership exceptions requiring integration review

- Creation has `frontend/e2e/write.spec.ts` outside its registered page ownership; its own handoff says moving browser tests into `frontend/e2e/**` needs the integration/test owner.
- Platform has `frontend/e2e/settings-provider.spec.ts` outside its registered page ownership.
- Each registered lane worktree contains a dirty `backend/aios/execution/tools.py`, which is outside the frontend lane ownership and was preserved as pre-existing work; it is not attributed to this checkpoint.
- No `frontend/src/components/**` file was changed by this checkpoint. Shared components remain frozen.

## 3. Exact validation commands and results

### 3.1 Preserved Phase 1 auth/tenant evidence

```bash
uv run pytest backend/tests/unit/security/test_auth_tenant_preservation.py -q -m unit
```

**PASS — 9 passed.** Preserved same-tenant CRUD, trusted worker scope, public probes, CORS preflight, local fallback, shared reference data, MCP credential org, frontend session transport, and Streamlit availability nodes passed.

```bash
uv run pytest backend/tests/unit/security/test_auth_tenant_bug_condition.py -q -m unit
```

**EXPECTED BLOCKER reproduced.** Hypothesis minimized the unchanged property counterexample to:

```text
case='frontend_transport', invalid_bearer=None, selector='org_id', operation='read'
protected raw fetch callers:
  frontend/src/components/topbar.tsx
  frontend/src/components/feedback-buttons.tsx
  frontend/src/components/brain-dock.tsx
```

The native-route property cases passed when the backend was run with the required local process opt-in; the overall property file remains failing because the shared callers are still frozen/integration-lane work.

```bash
uv run pytest backend/tests/unit/security backend/tests/unit/api -q -m unit
```

**BLOCKED — exit 4.** The prescribed `backend/tests/unit/api` path does not exist; no collection occurred. This is also recorded in `task-group-3-auth-evidence.md`.

### 3.2 Phase 2 backend/provider/MCP/story/tenant evidence

```bash
OLLAMA_UNCENSORED_OPT_IN=true uv run pytest \
  backend/tests/unit/mcp/test_phase2_tools.py \
  backend/tests/unit/test_byo_provider_contracts.py \
  backend/tests/unit/test_byo_provider_orchestration.py \
  backend/tests/unit/test_phase2_platform_connections.py \
  backend/tests/unit/test_credentials_expiry.py \
  backend/tests/unit/story_engine/test_router.py \
  backend/tests/unit/worker/test_worker_org_context.py \
  backend/tests/unit/test_thunder_h3_adapter.py -q -m unit \
  -k 'not dolphin_requires_explicit_opt_in_and_exposes_warning_only'
```

**PASS — all selected tests passed.** This covers authenticated MCP org threading, selector rejection, credential masking/expiry/rotation, BYO provider registry and failure classes, cost-before-dispatch, fallback policy, tenant A/B credential isolation, Fanvue connection/policy ownership, 401/403/404/422 policy cases, story route/auth/tenant behavior, worker org context/lifecycle, and exact frame-grid values.

The excluded Ollama test is itself a configuration evidence problem: without a process-local opt-in, imports fail because the current `.env` selects `dolphin-llama3` without opt-in; with `OLLAMA_UNCENSORED_OPT_IN=true`, the test that expects default settings to reject that model cannot pass. No environment file was changed.

```bash
OLLAMA_UNCENSORED_OPT_IN=true uv run pytest \
  backend/tests/unit/security/test_c7_rollout_gates.py \
  backend/tests/unit/security/test_auth_boundary_coverage.py \
  backend/tests/unit/security/test_task5_auth_stack.py \
  backend/tests/unit/security/test_api_v1_tenant_isolation.py \
  backend/tests/unit/security/test_brain_executor_tenant_scope.py \
  backend/tests/unit/worker/test_worker_org_context.py \
  backend/tests/unit/test_credentials_expiry.py \
  backend/tests/unit/story_engine/test_router.py -q -m unit \
  -k 'not test_property_5_route_and_story_inventories_are_exact and not test_direct_api_supabase_calls_are_confined_to_tenant_helpers'
```

**PASS — all selected tests passed.** The excluded failures are:

- `test_property_5_route_and_story_inventories_are_exact`: observed 23 routes versus stale expected 22.
- `test_direct_api_supabase_calls_are_confined_to_tenant_helpers`: observed source lines `[50, 57, 66, 77]` versus stale expected `[56, 63, 72, 83]`.

These assertions were not edited or weakened.

```bash
OLLAMA_UNCENSORED_OPT_IN=true uv run pytest \
  tests/unit/test_publishing_service.py \
  tests/unit/test_publishing_preflight.py \
  tests/unit/test_publishing_jobs.py \
  tests/unit/test_services/test_publishing_dispatch_disclosure.py \
  tests/unit/test_core/test_multi_platform_publish.py \
  backend/tests/billing/test_credit_costs.py -q -m unit
```

**PASS — 98 passed** in the local publishing, disclosure, platform, preflight, lifecycle, and preset-cost subset. The separate Stripe-dependent credit test could not collect because `stripe` is not installed.

```bash
OLLAMA_UNCENSORED_OPT_IN=true uv run ruff check \
  backend/aios/mcp/phase2_common.py backend/aios/mcp/phase2_credentials.py \
  backend/aios/mcp/phase2_generation.py backend/aios/mcp/phase2_publish.py \
  backend/aios/mcp/phase2_story.py backend/app/providers/byo.py \
  backend/app/providers/byo_adapters.py backend/app/providers/byo_contracts.py \
  backend/app/services/platform_registry.py backend/app/services/provider_orchestration.py \
  backend/app/services/provider_orchestration_contracts.py \
  backend/app/services/provider_orchestration_support.py \
  backend/app/services/publishing_policy_service.py backend/publishing/service.py
```

**PASS — all checks passed.** Ruff emitted only a configuration warning that removed rules `ANN101` and `ANN102` are ignored.

### 3.3 Frontend typecheck/lint/build

For each registered lane, the exact command below exited 0:

```bash
npm run typecheck && npm run lint && npm run build
```

**PASS:** `ai-studio88-creation/frontend`, `ai-studio88-growth/frontend`, `ai-studio88-platform/frontend`, `ai-studio88-brain/frontend`, `ai-studio88-post/frontend`, and `ai-studio88-talent/frontend`.

The platform handoff records 0 lint errors (warnings only) and a successful Next.js 16.2.10 build. Growth and creation handoffs independently record successful typecheck/build; creation also records its page-local MAKE contract pass.

Active main checkout:

```bash
npm run typecheck && npm run lint && npm run build
```

**BLOCKED at typecheck — 24 errors in three pre-existing dirty files; lint/build were not reached because of `&&`:**

- `frontend/src/app/admin/page.tsx`: 20 `authFetch`/`API_BASE`/implicit response type errors.
- `frontend/src/app/editor/page.tsx`: 3 response-shape/type errors.
- `frontend/src/app/talent/_components/talent-generations-section.tsx`: 1 asset-shape error.

This matches the preserved Phase 1 evidence and was not fixed in this checkpoint.

### 3.4 Frontend contract/browser evidence

```bash
node --experimental-strip-types --test \
  src/app/create/_lib/make-contract.test.mjs
```

**PASS — 4 passed.** Covers exact frame-grid values, prompt assembly, bounded tier serialization, no client org selector/secret, and queue error classification.

```bash
node --experimental-strip-types --test \
  src/app/publish/_lib/contracts.test.ts
```

**BLOCKED — test file cannot resolve its extensionless `./contracts` import under the available Node runner.** No Vitest/Jest test runner is declared in `frontend/package.json`; the package only has `dev`, `build`, `start`, `lint`, and `typecheck` scripts.

```bash
npm --prefix frontend exec playwright test \
  e2e/route-migration.spec.ts --project=desktop --project=mobile --reporter=line
```

**PASS — 32 passed, 2 skipped.** The two skipped cases require `ROUTE_MIGRATION_HTTP=1` and a running authenticated/local-fallback server. The passing contract covers route destinations, 301 migration, query forwarding, `/models` split, `/jobs` deprecation, keep routes, editor interstitial, unsafe destination rejection, collision safety, and protected-before-migration behavior.

```bash
npx playwright test e2e/settings-provider.spec.ts \
  --project=desktop --project=mobile --reporter=line
```

**PASS — 4 passed.** Platform BYO provider browser checks covered no secret redisplay and provider fallback/health controls. The dev server emitted hydration warnings; no test failed on them.

```bash
npx playwright test e2e/write.spec.ts \
  --project=desktop --project=mobile --reporter=line
```

**BLOCKED — 2 passed, 6 failed.** The unauthenticated redirect checks passed, but authenticated WRITE rendering/edit/upload/regenerate checks could not establish the required session/route state and failed to find the expected `Story and storyboard` surface. The same result occurred against a dedicated creation dev server; no authenticated browser fixture is configured.

```bash
npx playwright test e2e/publish-audit.spec.ts \
  --project=desktop --project=mobile --reporter=line
```

**BLOCKED / unavailable in growth lane:** the growth worktree has no configured `publish-audit.spec.ts`; Playwright reported `No tests found`. Existing publish handoff documents backend gaps rather than claiming browser acceptance.

No configured axe/accessibility runner, Vitest runner, or frontend test script is present. Therefore keyboard/focus/contrast/reduced-motion/drag-drop alternative and authenticated desktop/tablet/mobile overflow evidence is incomplete. Existing page-local assertions are not equivalent to an accessibility audit.

## 4. Cross-cutting gate results

### Responsive and accessibility — **BLOCKED**

- Build/typecheck evidence exists in all six lane worktrees, and the route contract runs desktop/mobile.
- There is no authenticated WRITE browser fixture, no growth PUBLISH browser spec in the growth worktree, no tablet-specific browser project, and no automated accessibility runner.
- The required `>=1024px`, `768–1023px`, and `<768px` step-navigation/overflow evidence is not proven for all WRITE, MAKE, PUBLISH, Settings/provider, CAST, Brain, and protected surfaces.

### Auth, tenant isolation, and client selectors — **BLOCKED pending shared integration**

- Preserved auth/tenant suite: **9 passed**.
- Targeted native/auth/Brain/worker/story/credential/security suite: selected tests pass when run with the documented local Ollama opt-in, but stale route-count/line-number assertions remain.
- Unchanged property exploration still finds the three shared raw protected callers.
- Platform handoff reports page migrations, but the platform worktree's shared API client is not the hardened main transport and lacks proven one-refresh/no-loop behavior; synchronization is explicitly blocked.
- Static frontend scan found legacy `API_BASE`/`authFetch`/raw `fetch` callers in the changed creation/admin page trees. The required owner is the absent `frontend/integration` lane; this checkpoint did not edit those files.
- No client organization selector was found in the new MAKE contract or PUBLISH contract. `frontend/src/app/admin/connections/page.tsx` contains an `org_id` response field; it requires contract review to ensure it is display-only and never a client selector.

### Storage — **BLOCKED**

- PUBLISH page-local contract rejects raw object URLs and accepts signed/CDN URLs, but its Node test is blocked by the import-resolution issue.
- `backend/storage.py` remains non-compliant with the mandatory storage gate: `upload_file()` constructs and returns a raw `B2_ENDPOINT_URL/bucket/key` public URL; upload metadata only sets `ContentType`; `delete_file()` directly deletes instead of soft-delete-first; no multipart path or required org/job metadata is evidenced; storage keys use project/asset/filename rather than the mandated org/asset/talent/job/filename structure.
- No Phase 2 storage fix was authorized or made. Live B2/CDN behavior and large-file multipart evidence are **STAGING-REQUIRED**.

### Cost and operational readiness — **UNIT-READY locally; STAGING-REQUIRED operationally**

- `ProviderOrchestrationSupport._estimate()` runs before dispatch, `_reserve()` runs before provider health/execute, and failure releases are covered by local orchestration tests.
- Local mocked tests cover budget rejection, provider fallback classification, idempotency, credential expiry, and cost provenance.
- No live Thunder/RunComfy/provider runtime, worker timeout, instance termination, webhook fallback, provider receipt, or production quota/budget evidence was run. External-provider acceptance remains **STAGING-REQUIRED**.
- Stripe-dependent billing tests cannot collect because `stripe` is absent.

### Secrets and dependency security — **BLOCKED for complete evidence**

- Targeted static scan found no literal provider secret material or raw B2 URL in the Phase 2 implementation paths. Admin key pages contain labels/environment-variable names only; no secret values were found.
- Test modules intentionally contain sentinel `sk-...` strings to assert masking; these are fixtures, not production credentials, but remain a secret-scan review item.
- `gitleaks` is unavailable (`gitleaks unavailable`, exit 127), so the required repository secret scan was not completed. No replacement full scanner result is claimed.
- Targeted Ruff passed. No real external APIs or staging credentials were used.

### Fanvue/platform policy, MCP, BYO, Ollama — **Local evidence partial; rollout BLOCKED**

- Fanvue policy/connection tests pass locally with mocked persistence/provider calls; they cover OAuth state, masking, expiry/reauthorization, revoke, role denial, policy 422, cross-tenant 404, and missing bearer 401.
- Platform registry keeps OnlyFans, LoyalFans, Instagram, TikTok, and YouTube disabled/Coming Soon until verified.
- MCP Phase 2 tests cover authenticated dispatch, org mismatch, selector rejection, credential masking, generation cost gate, and idempotency.
- BYO provider tests cover Thunder Compute, RunComfy, Gemini, ElevenLabs, OpenAI, Replicate, and Ollama metadata/fallback contracts; no real provider approval or credential evidence exists.
- Ollama/dolphin-llama3 test setup is contradictory with the current environment as documented above; staging managed-VPS configuration and explicit warning/opt-in evidence are missing.
- OAuth registrations, provider approvals, two-org staging A/B, live policy enforcement, and deployment parity are **STAGING-REQUIRED**.

## 5. Required next actions and owners

1. **Frontend/integration owner (not registered):** provision the lane; migrate the five shared protected callers; synchronize the hardened canonical transport; add focused transport/component tests; update the shared-caller handoff.
2. **Platform owner:** resolve shared transport synchronization, prove refresh/no-loop and tenant-selector rejection, and retain the passing platform lint/typecheck/build evidence.
3. **Creation + backend + integration owners:** add/register the typed authenticated WRITE shot-update/preview contract; move browser tests to the permitted test owner; provide authenticated desktop/tablet/mobile fixtures.
4. **Creation/post/platform integration owners:** provision and validate `/make`, editor split, model/workflow adapters, rich generation payload, and server-authoritative preflight estimate.
5. **Growth + backend owners:** close durable cancel, idempotent scheduling, multi-destination policy, timezone-aware optimal-time, async durable auto-post, server-side consent/disclosure/moderation, and 401/403/404/409/422/429/500/provider retry tests.
6. **Backend/storage owner:** replace raw B2 URLs with signed/CDN outputs, implement soft-delete-first semantics, required object metadata, mandated immutable key structure, MIME/magic-byte/size checks, and multipart uploads; add mocked and controlled integration evidence.
7. **Backend/test owner:** reconcile the stale 22-vs-23 route assertion and stale tenant-audit line numbers without weakening behavior; install or explicitly provision the missing Stripe/test dependencies and frontend test runner/import configuration.
8. **Security/release owner:** run gitleaks or an approved replacement, dependency audit, coverage with branch reporting, controlled two-tenant staging A/B, live auth/CORS/allowlist, provider/OAuth approvals, and independent release sign-off.

Until these actions have exact passing evidence, leave Tasks 13–14 and Phase 2 **BLOCKED**.
