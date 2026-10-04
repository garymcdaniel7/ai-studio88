# Phase 1 Task 15 — Auth Rollout Gates

**Status:** `UNIT-READY` for the local policy/tooling checks only. **Staging acceptance: `STAGING-REQUIRED` / `BLOCKED`.** This record does not claim deployment, credentials, migrations, branch parity, or production evidence.

## Authoritative policy

- `backend/app/core/auth_policy.py` is the sole policy for exact public paths, valid `OPTIONS` preflight exemption, local/test fallback, dark launch, startup validation, and enforcement.
- `PUBLIC_PROBE_ALLOWLIST` is an exact path set. It does not prefix-match near routes.
- `backend/app/core/middleware.py` emits non-sensitive `auth_policy_decision` telemetry with outcome, route, method, request ID, environment, and mode; it never logs bearer material, service-role keys, or organization selectors.
- The only enforcement flip is the `AUTH_ENFORCEMENT_FLIP=true` setting. Staging and production refuse startup without it, and the flip cannot be used to disable enforcement.
- Dark launch is permitted only in local/test controlled observation. It never qualifies as staging or production acceptance.
- Null organization identities are rejected by `require_auth` for authenticated tenant requests with `403` and `WORKSPACE_MEMBERSHIP_REQUIRED`; optional-auth paths return no tenant identity rather than passing `None` into tenant operations.
- CORS is the outermost middleware and completes valid preflight before auth; a sentinel/order test must remain part of controlled staging verification.

## Local gates

| Gate | Evidence | Result |
|---|---|---|
| Policy/allowlist/error mapping | `backend/tests/unit/security/test_c7_rollout_gates.py` | `UNIT-READY` |
| Property 1 exploration rerun | `backend/tests/unit/security/test_auth_tenant_bug_condition.py` | Run unchanged; failures are blockers, not weakened |
| Property 2 preservation rerun | `backend/tests/unit/security/test_auth_tenant_preservation.py` | Run unchanged; failures are blockers |
| C7 properties 1–5 | `backend/tests/unit/security/test_c7_rollout_gates.py` plus the unchanged Property 1/2 suites | `UNIT-READY` when targeted command passes |
| Query inventory | `backend/scripts/audit_tenant_queries.py`, `docs/architecture/AUTH_TENANT_QUERY_AUDIT.md`, `docs/architecture/AUTH_TENANT_QUERY_INVENTORY.md` | Any `BLOCKED` query keeps acceptance blocked |
| Benchmark | `backend/scripts/benchmark_auth_overhead.py` | Run `before` and `after` with identical options/environment; tool is outside runtime |
| Coverage | `backend/coverage.ini`, `backend/scripts/check_auth_coverage.py` | Per security-boundary file, line and branch floors are 80%; aggregate coverage cannot substitute |
| Secret/diff safety | `git diff --check` and repository secret scan | Required before review; no `.env` or secret changes permitted |

### Benchmark protocol

```text
uv run python backend/scripts/benchmark_auth_overhead.py --label before --iterations 25 > reports/auth-before.json
uv run python backend/scripts/benchmark_auth_overhead.py --label after --iterations 25 > reports/auth-after.json
```

Both runs must use the same base URL, valid token fixture, iteration count, request mix, and machine. The fixed mix contains public probe, valid auth, missing auth, invalid auth, organization-selector injection, and CORS preflight. A local result is not staging evidence.

### Coverage protocol

```text
uv run pytest backend/tests/unit/security -q -m unit \
  --cov-config=backend/coverage.ini --cov-report=json:reports/coverage/auth.json
uv run python backend/scripts/check_auth_coverage.py reports/coverage/auth.json
```

The category gate covers the policy, middleware, and route dependency boundary independently. The report must show at least 80% lines and branches in each required file; missing files or zero branch totals fail closed.

## Repository-wide query audit

The audit searches backend source for literal and dynamic `.table(...)`, `.from_(...)`, approved wrappers, worker service-role operations, and every `optional_auth` call site. Each row has exactly one classification: direct org predicate, inherited parent proof, approved scoped wrapper, worker lifecycle scoped, documented shared exemption, optional-auth review, or explicit unscoped remediation blocker. Unknown and RLS-only findings are not accepted.

The existing API inventory records the 19+ `api_v1.py` findings and related helper paths. The generated repository audit additionally surfaced direct query paths outside `api_v1.py`; the latest generation records **552 findings with 267 explicit `BLOCKED` findings**. Those remain `BLOCKED` until their application predicate or documented exemption is independently reviewed. This is intentional evidence, not a claim that the whole repository is already fixed.

## Controlled staging gate — `STAGING-REQUIRED` / `BLOCKED`

The following evidence is not available from this local checkout and must be supplied by the CTO/platform owner before acceptance:

- deployment parity and startup logs proving `AUTH_ENFORCEMENT_FLIP=true`, no dark launch, and fail-closed configuration;
- secret-manager/configuration evidence without exposing values;
- two controlled organization users proving A/B reads, inserts, updates, deletes, and inherited parent ownership;
- service-role worker `poll`, `claim`, `complete`, and `fail` lifecycle evidence with trusted organization predicates;
- optional-auth null-context behavior on every tenant path;
- frontend token refresh, one-retry, redirect, and no-loop evidence;
- live public-route/allowlist parity and valid CORS-before-auth preflight;
- migration and schema/RLS evidence, including approved RLS-disabled/service-role-backed checks in staging only;
- branch/worktree auth-router parity and independent reviewer/CTO sign-off;
- before/after benchmark artifacts from the same controlled staging environment.

No destructive or RLS-disabled check may target production. If an immediately prior enforcing release has not been independently verified, rollback is not an auth-disable option: restrict/shepherd traffic and fix forward.
