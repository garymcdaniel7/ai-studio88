# Phase 2 Task Group 3 — Authentication and Tenant Evidence

**Scope:** Task Group 3 only (`3.1`–`3.3`) from `phase-2-ui-revamp/tasks.md`.
**Execution timestamp:** `2026-10-04T16:03:25Z`.
**Repository:** `/Users/garymcdaniel/kiro/ai-studio88`.
**Result:** `BLOCKED` for the Phase 2 auth evidence gate; preserved tests were rerun unchanged and no runtime/application files were modified.

## Safety and baseline

The checkout had extensive pre-existing dirty and untracked files before this task, including backend auth/runtime files, frontend pages, `frontend/src/lib/api.ts`, and Phase 1 remediation artifacts. Those files were not edited. No `.env*`, `.config.kiro`, old spec, shared frozen component, backend application file, frontend application file, or unrelated dirty file was changed. No commit was created.

Phase 2 has no local `requirements.md`, `design.md`, or `.config.kiro`; this record follows the Phase 2 task plan and its referenced source design (`.kiro/specs/ui-revamp-design.md`) plus the Phase 1 auth/tenant remediation evidence. The Phase 1 config is `.kiro/specs/phase-1-nav-auth/.config.kiro` with `specType: build`.

## Exact commands and results

### Required Phase 2 validation command

```text
uv run pytest backend/tests/unit/security backend/tests/unit/api -q -m unit
```

**Result:** `BLOCKED`, exit `4`. `backend/tests/unit/api` does not exist (`ERROR: file or directory not found`). No test collection occurred for that nonexistent path.

### Preserved Property 2

```text
uv run pytest backend/tests/unit/security/test_auth_tenant_preservation.py -q -m unit
```

**Result:** `PASS`, exit `0`, `9 passed`.

Exact nodes:

- `tests/unit/security/test_auth_tenant_preservation.py::test_same_tenant_crud_preserves_scoped_result_shape`
- `tests/unit/security/test_auth_tenant_preservation.py::test_trusted_worker_context_preserves_lifecycle_scope`
- `tests/unit/security/test_auth_tenant_preservation.py::test_exact_public_probes_preserve_observed_responses`
- `tests/unit/security/test_auth_tenant_preservation.py::test_valid_unauthenticated_options_preflight_preserves_cors`
- `tests/unit/security/test_auth_tenant_preservation.py::test_approved_local_fallback_and_optional_auth_without_tenant_data`
- `tests/unit/security/test_auth_tenant_preservation.py::test_documented_shared_reference_data_preserves_recipe_shape`
- `tests/unit/security/test_auth_tenant_preservation.py::test_existing_mcp_authentication_preserves_credential_org`
- `tests/unit/security/test_auth_tenant_preservation.py::test_valid_frontend_session_transport_contract`
- `tests/unit/security/test_auth_tenant_preservation.py::test_streamlit_legacy_admin_entrypoint_remains_available`

### Preserved Property 1 and security suite

```text
uv run pytest backend/tests/unit/security -q -m unit
```

**Result:** `BLOCKED`, exit `1`: `99 passed`, `2 failed`.

The two exact failures are preserved, not weakened:

- `tests/unit/security/test_api_v1_tenant_isolation.py::test_direct_api_supabase_calls_are_confined_to_tenant_helpers` — static expected line numbers are `[56, 63, 72, 83]`, observed `[50, 57, 66, 77]`. This is a stale source-line assertion, not a runtime auth response failure.
- `tests/unit/security/test_auth_tenant_bug_condition.py::test_property_1_bug_condition_requires_fixed_contract` — expected preserved exploration blocker. Hypothesis minimized the counterexample to:

  ```text
  case='frontend_transport', invalid_bearer=None, selector='org_id', operation='read'
  protected raw fetch callers: frontend/src/components/topbar.tsx, frontend/src/components/feedback-buttons.tsx, frontend/src/components/brain-dock.tsx
  ```

  The original Property 1 exploration test remains unchanged. The shared callers remain frozen/integration-lane work; this is an expected Phase 1 carry-forward blocker.

The direct native-route exploration nodes were also run in the targeted command below and passed; only the preserved raw-caller and stale line-number blockers remain in this suite.

### Targeted backend auth, tenant, Brain, worker, credential, frame, and story command

```text
uv run pytest backend/tests/unit/test_core/test_middleware.py backend/tests/unit/security/test_auth_boundary_coverage.py backend/tests/unit/security/test_task5_auth_stack.py backend/tests/unit/security/test_brain_executor_tenant_scope.py backend/tests/unit/security/test_api_v1_tenant_isolation.py backend/tests/unit/worker/test_worker_org_context.py backend/tests/unit/test_credentials_expiry.py backend/tests/unit/story_engine/test_router.py -q -m unit
```

**Result:** `BLOCKED`, exit `1`. All selected tests passed except the same static line-number assertion:

```text
backend/tests/unit/security/test_api_v1_tenant_isolation.py::test_direct_api_supabase_calls_are_confined_to_tenant_helpers
assert [50, 57, 66, 77] == [56, 63, 72, 83]
```

The selected auth middleware, route protection, CORS, allowlist, Brain, worker, credential, and story nodes all passed. This command did not change runtime behavior.

### Remaining preserved auth/security/frame/story command

```text
uv run pytest backend/tests/unit/security/test_c7_rollout_gates.py backend/tests/unit/test_thunder_h3_adapter.py backend/tests/unit/test_auth_router.py backend/tests/unit/security/test_auth_tenant_bug_condition.py::test_native_routes_have_no_unprotected_counterexample backend/tests/unit/security/test_task5_auth_stack.py backend/tests/unit/security/test_brain_executor_tenant_scope.py backend/tests/unit/worker/test_worker_org_context.py backend/tests/unit/test_credentials_expiry.py backend/tests/unit/story_engine/test_router.py -q -m unit
```

**Result:** `PASS`, exit `0`, all collected nodes passed (output: `100%`, no failures).

This includes the native route unauthenticated cases, the C7 auth/CORS/allowlist gate, exact frame-grid validation, credentials, worker lifecycle, Brain context, and story route checks.

### Exact backend node collection

```text
uv run pytest backend/tests/unit/test_core/test_middleware.py backend/tests/unit/security/test_task5_auth_stack.py backend/tests/unit/security/test_api_v1_tenant_isolation.py backend/tests/unit/security/test_brain_executor_tenant_scope.py backend/tests/unit/worker/test_worker_org_context.py backend/tests/unit/test_credentials_expiry.py backend/tests/unit/test_thunder_h3_adapter.py backend/tests/unit/story_engine/test_router.py backend/tests/unit/security/test_auth_tenant_preservation.py --collect-only
```

**Result:** `PASS`, `127 tests collected`, exit `0`. The category nodes are:

- **Auth middleware:** `tests/unit/test_core/test_middleware.py::TestExemptPaths::{test_health_returns_200_without_auth,test_ready_returns_200_without_auth,test_root_returns_200_without_auth,test_docs_returns_200_without_auth,test_exempt_paths_include_request_id}`; `TestAuthEnforcement::{test_missing_authorization_returns_401,test_malformed_authorization_returns_401,test_empty_bearer_token_returns_401,test_expired_token_returns_401_token_expired,test_invalid_signature_returns_401,test_empty_sub_returns_401_invalid_token,test_valid_token_proceeds_with_payload,test_response_includes_request_id,test_401_response_includes_request_id}`; `TestAuthDevMode::{test_dev_mode_production_raises_runtime_error,test_dev_mode_staging_raises_runtime_error,test_dev_mode_local_does_not_raise,test_dev_mode_disabled_does_not_raise}`; `TestAuthDevModeInjection::{test_dev_mode_injects_real_user_id_from_org_members,test_dev_mode_injects_real_org_id_not_none,test_dev_mode_never_trusts_client_supplied_user_id,test_dev_mode_falls_through_when_no_org_members,test_dev_mode_blocked_at_runtime_in_production}`. **Result:** pass in targeted run.
- **Effective stack/native route protection:** `tests/unit/security/test_task5_auth_stack.py::test_active_app_registers_cors_auth_and_org_guard_in_effective_order`, `::test_sentinel_events_prove_auth_precedes_org_guard`, `::test_missing_auth_never_invokes_native_or_sentinel_handler`, `::test_org_selector_and_repeated_selector_are_rejected_before_handler[org_id]`, `[orgId]`, `[-org]`, `[organization_id]`, `::test_valid_cors_preflight_completes_without_bearer`, `::test_public_allowlist_is_exact_and_near_match_is_not_public`, `::test_native_routes_keep_explicit_require_auth_dependency`, `::test_native_routes_pass_trusted_org_to_database_helpers`, `::test_missing_native_membership_fails_before_database_access`. **Result:** pass.
- **Native exploration routes:** `tests/unit/security/test_auth_tenant_bug_condition.py::test_native_routes_have_no_unprotected_counterexample[GET-/projects]`, `[GET-/talent]`, `[POST-/talent]`. **Result:** pass in the remaining preserved command.
- **Tenant filters/A-B isolation:** `tests/unit/security/test_api_v1_tenant_isolation.py::{test_direct_helpers_never_return_foreign_tenant_rows,test_insert_overwrites_client_org_and_update_cannot_reassign,test_tenant_mutations_use_id_and_org_predicates,test_route_update_rejects_foreign_talent_without_mutation,test_authorized_client_strips_org_id_from_updates,test_inherited_parent_check_blocks_cross_tenant_scene_insert,test_tenant_repo_refuses_unfiltered_inherited_collection,test_storyboard_detail_update_delete_are_a_b_scoped,test_lora_collection_requires_owned_talent_before_child_reads,test_model_update_passes_only_trusted_org_and_rejects_foreign_row}`. **Result:** 10 pass; `test_direct_api_supabase_calls_are_confined_to_tenant_helpers` is the one stale-line assertion failure recorded above.
- **Brain executor trusted context:** `tests/unit/security/test_brain_executor_tenant_scope.py::{test_missing_trusted_org_is_rejected_before_executor_validation,test_search_talent_uses_trusted_org_and_ignores_selector,test_create_talent_inserts_only_trusted_org,test_schedule_post_requires_owned_asset_and_scopes_post_insert,test_train_lora_scopes_talent_and_assets_to_trusted_org,test_authenticated_mcp_dispatch_still_receives_org_context,test_search_knowledge_passes_trusted_org_and_ignores_selector,test_recommend_workflow_scopes_workflow_dna_to_each_trusted_org[11111111-1111-1111-1111-111111111111-22222222-2222-2222-2222-222222222222],test_recommend_workflow_scopes_workflow_dna_to_each_trusted_org[22222222-2222-2222-2222-222222222222-11111111-1111-1111-1111-111111111111],test_recommend_workflow_rejects_foreign_talent_before_query}`. **Result:** pass.
- **Worker UUID/lifecycle predicates:** `tests/unit/worker/test_worker_org_context.py::{test_worker_rejects_missing_and_malformed_org_before_database_access,test_worker_normalizes_valid_org_uuid,test_worker_cli_rejects_missing_or_malformed_org_before_startup[argv0],test_worker_cli_rejects_missing_or_malformed_org_before_startup[argv1],test_worker_cli_passes_valid_org_to_worker,test_all_worker_lifecycle_queries_bind_trusted_org,test_null_worker_context_makes_zero_database_calls[poll],test_null_worker_context_makes_zero_database_calls[claim],test_null_worker_context_makes_zero_database_calls[complete],test_null_worker_context_makes_zero_database_calls[fail],test_action_generation_receives_command_org_context,test_action_command_execute_forwards_durable_org_to_dispatch}`. **Result:** pass.
- **Credential expiry:** `tests/unit/test_credentials_expiry.py::{test_user_api_key_provider_type_is_supported,test_active_future_expiry_resolves_and_is_masked,test_null_expiry_remains_active,test_expired_credential_is_inactive,test_malformed_or_ambiguous_expiry_fails_closed[not-a-timestamp],test_malformed_or_ambiguous_expiry_fails_closed[],test_malformed_or_ambiguous_expiry_fails_closed[2027-01-01T00:00:00],test_revoked_credential_is_inactive,test_rotated_credential_is_inactive_and_new_version_resolves,test_only_active_non_expired_records_resolve,test_status_metadata_discloses_expiry_but_never_secret}`. **Result:** pass.
- **Frame grid:** `tests/unit/test_thunder_h3_adapter.py::{test_length_grid_is_exact_contract,test_snap_h3_length_exact_values_pass_through,test_snap_h3_length_rejects_unsupported_values,test_validate_h3_length_rejects_non_integer_values,test_validate_h3_length_accepts_only_exact_integer_grid_values,test_validate_h3_length_rejects_all_non_integer_inputs,test_h3_request_validation_rejects_unsupported_frame_grid_values}`. **Result:** pass; exact accepted values are `124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600`.
- **Story routes:** `tests/unit/story_engine/test_router.py::test_exactly_22_story_routes_are_registered`, `::test_all_22_story_routes_return_contract_shapes`, `::test_lists_are_paginated_and_pass_trusted_org`, all 16 `::test_viewer_cannot_write_story_resources[...]` cases, `::test_cross_tenant_detail_is_not_found_and_uses_jwt_org`, `::test_missing_auth_returns_401_before_story_service`, `::test_all_22_story_routes_require_auth`, `::test_invalid_uuid_and_body_return_422`, `::test_repository_failure_returns_structured_500`, `::test_story_router_is_mounted_in_active_registry`. **Result:** pass.
- **Property 2 frontend/session/legacy evidence:** the nine exact nodes listed in the Property 2 section above. **Result:** pass.

## Frontend transport and route evidence

### Session transport

The preserved backend static contract node `test_valid_frontend_session_transport_contract` passed. It confirms `frontend/src/lib/api.ts` contains Supabase token sourcing, bearer attachment, `X-Request-ID`, login redirect behavior, and no client organization selector in the tested contract.

The stronger frontend Vitest file exists at `frontend/src/lib/__tests__/api.test.ts` with these exact intended nodes:

- `canonical frontend API transport > sources and attaches a valid Supabase bearer token and request ID`
- `canonical frontend API transport > fails closed and redirects when no session token can be refreshed`
- `canonical frontend API transport > sends no bearer for an explicitly unauthenticated health probe`
- `canonical frontend API transport > refreshes once after a 401 and replays with the refreshed token`
- `canonical frontend API transport > clears the session and redirects after refresh failure`
- `canonical frontend API transport > does not create a redirect loop when already on /login`
- `canonical frontend API transport > rejects org_id query selectors before network access`
- `canonical frontend API transport > rejects orgId query selectors before network access`
- `canonical frontend API transport > rejects org-id query selectors before network access`
- `canonical frontend API transport > rejects organization_id query selectors before network access`
- `canonical frontend API transport > routes authFetch through canonical auth and preserves Response compatibility`

Exact command attempted:

```text
if [ -x frontend/node_modules/.bin/vitest ]; then frontend/node_modules/.bin/vitest run src/lib/__tests__/api.test.ts; else printf '%s\\n' 'vitest unavailable: frontend/node_modules/.bin/vitest is absent and frontend/package.json has no test script'; exit 127; fi
```

**Result:** `BLOCKED`, exit `127`: `frontend/node_modules/.bin/vitest` is absent and `frontend/package.json` has no test script. No frontend session test node was collected or executed.

### Route migration

```text
npm --prefix frontend exec playwright test e2e/route-migration.spec.ts --project=desktop
```

**Result:** `PASS`, exit `0`: `32 passed`, `2 skipped` (the two HTTP assertions require `ROUTE_MIGRATION_HTTP=1` and a running authenticated/local-fallback server).

The passing contract covers the exact 33 route entries, 301 destinations, `/models` character/generative split, query forwarding, 60-day `/jobs` window, keep-route public/protected status, `/editor` WRITE/MAKE interstitial, unsafe destination rejection, redirect collision safety, and protected-before-migration behavior. The skipped nodes are:

- `Phase 1 V1-to-V2 route migration contract › built frontend representative requests expose the migration status when local fallback is active`
- `Phase 1 V1-to-V2 route migration contract › built frontend editor response exposes the interstitial when local fallback is active`

### Frontend TypeScript carry-forward check

```text
npm --prefix frontend run typecheck
```

**Result:** `BLOCKED`, exit `1`, 24 errors in 3 pre-existing dirty page files:

- `src/app/admin/page.tsx`: 20 errors (`authFetch`, `API_BASE`, implicit response/data types).
- `src/app/editor/page.tsx`: 3 response-shape/type errors.
- `src/app/talent/_components/talent-generations-section.tsx`: 1 asset-shape error.

No frontend file was changed to address these errors. The platform-lane handoff records its own platform-worktree typecheck/build as passing, but the current main checkout cannot claim a clean Phase 2 frontend gate.

## Carry-forward behavior verification

The current unchanged test evidence supports preservation of the following behavior:

- **401:** missing, malformed, expired, invalid-signature, and empty-sub auth middleware paths; native routes; story routes; and missing protected Brain context reject before handler/service access.
- **403:** null trusted organization membership and viewer write-role denial remain covered by task-5/story tests.
- **404:** foreign story detail and tenant A/B detail paths remain covered without existence leakage.
- **422:** organization-selector injection/repeat rejection, invalid UUID/body validation, and exact frame-grid rejection remain covered.
- **Trusted organization derivation:** native route tests use `AuthUser.org_id`; Brain tests reject missing context and scope A/B operations; worker tests require/normalize UUID context and bind all four lifecycle operations; preservation tests verify same-tenant CRUD and worker predicates.
- **CORS preflight:** valid unauthenticated `OPTIONS` completes before auth with the expected `200 OK`, origin header, and no bearer requirement.
- **Allowlist:** exact public paths remain distinct from near matches; route migration protects every migrating source and preserves the public keep-route contract.
- **Frontend handoffs:** existing Phase 1 shared-caller inventory still marks shared raw callers as integration-lane blocked; platform handoff reports route migration and explicitly remains `BLOCKED` pending shared hardened transport synchronization. No backend result was weakened to hide these frontend blockers.

## Gate decision

**Phase 2 Task Group 3 status: `BLOCKED`, not `UNIT-READY`.**

Blocking evidence is explicit and preserved:

1. The prescribed command references a missing `backend/tests/unit/api` path.
2. Property 1 still reproduces the frozen shared raw-fetch counterexample.
3. One tenant audit test has stale expected source line numbers (`[56, 63, 72, 83]` vs `[50, 57, 66, 77]`).
4. Frontend Vitest transport tests cannot run because Vitest/test script is not installed.
5. Current main-worktree frontend typecheck fails on 24 existing errors; no source changes were made.
6. Phase 1 rollout evidence remains `STAGING-REQUIRED` / `BLOCKED` for deployment parity, secrets manager, two-org staging A/B, live CORS/allowlist, branch/worktree auth-router parity, and independent sign-off.

No application behavior was changed in this task. The original Property 1/2 tests and all observed blockers remain available for the next authorized lane; this artifact is the only file added for Phase 2 Task Group 3.
