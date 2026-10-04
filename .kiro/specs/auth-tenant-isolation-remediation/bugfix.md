# Bugfix Requirements Document

## Introduction

This bugfix addresses the Stream A authentication and tenant-isolation failures identified in the sealed CTO remediation handoff. In the affected production entry point, three native routes are unprotected, the production authentication middleware and the `org_id` injection guard are not wired, authentication policy is split between independent `AUTH_REQUIRED` and `AUTH_DEV_MODE` paths, and legacy database queries rely on Supabase RLS instead of applying authenticated-organization filters in the application layer. Together these defects can expose tenant data, permit unauthenticated writes, and make the stated security posture depend on an accidental database or connection failure.

The remediation is phased: Stream C1 Frontend Auth Integration pairs with Stream A P1; Stream C4 Staging Provisioning is an explicit verification gate; Stream A P2 wires the production guards; Stream A P3 performs the tenant-query sweep; and Stream C7 supplies the auth and isolation regression suite. Stream C1 and P1 SHALL support a dark-launch path so the enforcement path can be wired, tested, and observed before frontend auth is ready, but authentication SHALL NOT be deployed permissively in production or staging. A dark launch, if required, is permitted only in an explicitly controlled non-production environment and has one documented flip trigger. Staging provisioning and dashboard-key access are owned by the platform/CTO operator; tests requiring staging credentials remain blocked until that access is granted.

The confirmed implementation decision is to use the existing `backend.auth.require_auth` dependency for `/projects` and `/talent`, register the existing production-compatible `AuthMiddleware` and `OrgIdInjectionGuard` as defense-in-depth in the production entry point, and execute them in this order: `AuthMiddleware` -> `OrgIdInjectionGuard`. Route-level `backend.auth.require_auth` SHALL remain on `GET /projects`, `GET /talent`, and `POST /talent` as explicit defense-in-depth. JWTs SHALL be enforced on every route outside one documented public-probe/preflight allow-list represented by one shared constant named `PUBLIC_PROBE_ALLOWLIST`, or by one explicitly equivalent exemption in the authoritative policy for CORS preflight. `AUTH_REQUIRED` and `AUTH_DEV_MODE` SHALL be consolidated behind one authoritative policy/configuration path; no independent dependency or middleware path may interpret those environment variables separately. CORS handling SHALL occur before authentication rejection for preflight requests.

The tenant sweep SHALL use regex/search to enumerate `.table("literal")`, `.from_()`, and dynamic table-name calls across the repository, including unscoped code outside `api_v1.py`, specifically `training/router.py`, `production_intelligence/router.py`, and `backend/worker.py`. Search results SHALL be followed by manual audit and classification of every occurrence as organization-scoped or explicitly exempt with a reason; literal-table search alone SHALL not be treated as coverage. The audit SHALL include service-role Supabase direct polls and job claim/complete/fail operations in `backend/worker.py`, because those operations bypass HTTP middleware.

The sealed handoff's planning estimates remain planning inputs: the rapid capability items are C1 Anti-Plastic Toggle (0.5 day), C2 Speed Verbs Injection (<2 hours), C4 Frame Grid Validation (0.5 day), C5 Series Bible (2–3 days), and C6 Brand Identity Template (2–3 days); the corrected identity and consistency scope is C2 Character Identity Pipeline (3–4 weeks) and C3 Character Consistency (3–4 weeks). The operational follow-ons are C9 Input Validation (0.5 day), C10 Rate Limiting (1.5 days), C11 Observability (2 days), C12 API Versioning (1 day), C13 Session Revocation (1.5 days), C14 Performance / Load Strategy (7 days), C15 Job Retry / Error Recovery (3.75 days), and C16 Generation Pipeline Reliability (4.25 days). These estimates do not change the bugfix scope or constitute implementation of those follow-ons.

Stream B competitive capabilities and the Shot Manifest are explicitly independent follow-on work. Their schemas, prompt capabilities, identity pipeline, series/brand features, and manifest storage or integration SHALL NOT be treated as implemented by this bugfix.

## Bug Analysis

### Current Behavior (Defect)

The following conditions describe the defects to be fixed:

1.1 WHEN a caller requests `GET /projects`, `GET /talent`, or `POST /talent` without a valid bearer JWT THEN the native route has no route-level authentication requirement and may read or mutate data if its downstream Supabase call succeeds.

1.2 WHEN a request enters through the production `backend/main.py` entry point THEN `AuthMiddleware` is not registered and `OrgIdInjectionGuard` is not registered; therefore the production middleware stack does not enforce the required JWT boundary and organization-parameter rejection in the required order.

1.3 WHEN a caller requests any non-probe route with a missing, invalid, or expired JWT THEN enforcement behavior can differ because `AUTH_REQUIRED` and `AUTH_DEV_MODE` are interpreted by separate authentication paths, with one path defaulting to permissive behavior instead of using one authoritative policy.

1.4 WHEN a caller supplies `org_id` as a query parameter to a tenant-scoped request THEN the unregistered `OrgIdInjectionGuard` does not reject the client-controlled organization selection at the application boundary.

1.5 WHEN an authenticated user from organization B invokes a legacy database read, update, or delete path whose query lacks an application-layer `org_id` predicate THEN the query can rely entirely on RLS and can return, modify, or delete organization A data if that backstop is disabled, bypassed, or misconfigured.

1.6 WHEN the tenant-query audit searches only literal `.table(...)` calls in `api_v1.py` THEN calls using `.from_()`, dynamic table names, or unscoped code in `training/router.py` and `production_intelligence/router.py` can remain unreviewed and tenant-scoped operations can remain unprotected.

1.7 WHEN acceptance testing requires cross-tenant or RLS-disabled verification THEN staging is not fully usable because required dashboard keys, migration application, unified enforcement configuration, and controlled test access are incomplete, so the tenant-isolation claim cannot be independently demonstrated without risking production data.

1.8 WHEN backend authentication is enforced before Stream C1 Frontend Auth Integration is shipped THEN dashboard/API-client calls that do not attach a bearer token receive authentication failures, breaking authenticated application pages rather than completing the login-and-request flow.

1.9 WHEN P1 and Stream C1 are not prepared for a controlled dark launch THEN the team must choose between breaking frontend traffic with an unready enforcement boundary or deploying a permissive rollout without a single flip trigger, verification signal, or observability evidence.

1.10 WHEN authentication or tenant-isolation behavior changes THEN the absence of a complete Stream C7 regression suite permits future changes to re-open unauthenticated access, malformed-token handling, org injection, or cross-tenant query defects without a reliable automated signal.

1.11 WHEN `backend/worker.py` performs a service-role Supabase poll or a tenant-owned job claim, complete, or fail operation outside HTTP middleware THEN the operation can bypass request authentication and execute without a trusted job-context organization predicate, including a required direct `.eq("org_id", ...)` predicate where `jobs` is directly organization-owned.

1.12 WHEN an HTTP `OPTIONS` CORS preflight request without `Authorization` enters an authentication check before CORS handling or is absent from the shared public/preflight policy THEN the preflight can be rejected with HTTP 401 and prevent the frontend login or authenticated request flow from completing.

1.13 WHEN an `optional_auth`-guarded path or a worker/service path requires tenant-scoped behavior but the validated identity, active membership, job context, or tenant context has no organization THEN the path can pass `None` to downstream validation or database access, causing a 500 or an unscoped operation instead of a canonical membership/authorization rejection.

1.14 WHEN staging or production rolls back from an enforcing release by setting `AUTH_ENFORCEMENT_FLIP` from true to false or by deploying a release without enforcement THEN the rollback can restore a permissive authentication boundary and make tenant isolation unsafe.

1.15 WHEN acceptance testing derives the unauthenticated production route set incompletely THEN an auth bootstrap route or `OPTIONS` preflight route can be omitted from the public/preflight policy, causing frontend login or CORS requests to fail even though the route inventory appears complete.

1.16 WHEN authentication changes are validated without a representative before/after auth-overhead latency benchmark THEN the change can add material request overhead without a measured baseline or regression signal.

1.17 WHEN coverage acceptance checks only aggregate coverage or line coverage THEN enforcement, fallback, allowlist, and error branches can remain untested and new code can remain below the required line-coverage threshold.

### Expected Behavior (Correct)

The following clauses define the required fix and its testable acceptance behavior. Clauses 2.1–2.10 correspond in order to defects 1.1–1.10; clauses 2.11–2.17 address defects 1.11–1.17; the remaining clauses define the audit, staging, dependency, and scope gates:

2.1 WHEN a caller requests GET /projects, GET /talent, or POST /talent without a valid, non-expired bearer JWT, THEN the system SHALL return HTTP 401 and SHALL not invoke the protected route handler or perform a data read or write. WHEN the caller presents a valid, non-expired JWT, THE system SHALL retain the explicit backend.auth.require_auth dependency, invoke the existing handler, and return that route’s existing success or structured downstream response.

2.2 WHEN a request enters through backend/main.py, THE system SHALL register AuthMiddleware followed by OrgIdInjectionGuard and SHALL execute them in that order. WHEN a request targets a route outside PUBLIC_PROBE_ALLOWLIST and has missing, invalid, or expired credentials, THE middleware stack SHALL return a structured HTTP 401 response containing the applicable unauthorized or expired-token error code before invoking the route handler. PUBLIC_PROBE_ALLOWLIST SHALL be the single shared constant defining every route exempt from JWT enforcement, including any explicitly permitted preflight entries.

2.3 WHEN a request targets a route outside PUBLIC_PROBE_ALLOWLIST, THE system SHALL evaluate authentication through one authoritative policy that is the sole interpreter of AUTH_REQUIRED and AUTH_DEV_MODE. WHEN the environment is staging or production, THE policy SHALL require JWT enforcement and SHALL reject startup or deployment if that enforcement state is not explicitly configured. WHEN the environment is local or test, THE policy MAY enable only the approved development fallback; no fallback decision made outside the authoritative policy SHALL alter enforcement.

2.4 WHEN any request to a guarded surface contains one or more client-supplied org_id query parameters, THE system SHALL return HTTP 422 with code ORG_ID_INJECTION_REJECTED and SHALL not invoke the guarded handler. WHEN no client-supplied org_id query parameter is present, THE guard SHALL not reject the request for that reason, and subsequent authentication and normal validation SHALL apply.

2.5 WHEN an authenticated user from organization B performs a tenant-scoped read, update, or delete operation, THE system SHALL constrain the operation using the organization derived from the validated credentials, independently of database RLS. A record owned by organization A SHALL produce no organization-B-visible list/detail result, SHALL not be updated or deleted by organization B, and SHALL remain unchanged after the operation.

2.6 WHEN staging-dependent acceptance testing is requested, THE platform/CTO operator SHALL provide all of the following before the test may be marked complete: controlled staging ownership and access; manually retrieved staging anon and service_role keys; application of all required migrations; AUTH_REQUIRED=true resolved through the authoritative policy; and confirmed controlled staging access. IF any one of these conditions is absent, THEN code development and unit testing MAY proceed, but deployment completion, staging integration-test completion, destructive or RLS-disabled test completion, and F5 tenant-isolation verification SHALL remain marked BLOCKED. No destructive or RLS-disabled test SHALL target production.

2.7 WHEN frontend authentication is not ready and the P1 enforcement path is wired, THE team MAY deploy that path only to an explicitly controlled non-production dark-launch environment with enforcement disabled. WHILE that dark launch is active, THE system SHALL emit observable signals for middleware execution, would-be authentication failures, PUBLIC_PROBE_ALLOWLIST exemptions, and org_id injection attempts. THE implementation SHALL document exactly one flip trigger, and WHEN that trigger is satisfied, THE system SHALL enable enforcement. THE system SHALL not use the dark-launch state to mark staging or production authentication complete, and staging SHALL use enforcement before staging verification.

2.8 WHEN backend authentication is enabled for application traffic, THE enforcement rollout SHALL be blocked unless Stream C1 is already shipped or is shipped in the same rollout and the dashboard/API client attaches a valid bearer token to every authenticated call. WHEN an authenticated call receives an expired-session or HTTP 401 response, THE client SHALL perform the refresh or redirect behavior defined by its existing contract and SHALL preserve the existing success and error states after authentication is established.

2.9 WHEN authentication or tenant-isolation behavior changes, THE Stream C7 regression suite SHALL cover unauthenticated access; valid, invalid, and expired JWTs; every route in PUBLIC_PROBE_ALLOWLIST; AuthMiddleware-before-OrgIdInjectionGuard ordering; org_id injection; tenant-scoped reads and mutations; the permitted local/test fallback; authenticated frontend requests; service-role worker polls and job claim/complete/fail operations; all optional_auth-guarded tenant paths; and HTTP OPTIONS/CORS preflight behavior. RLS-disabled cross-tenant integration tests SHALL run only in controlled staging, and external services used by those tests SHALL be mocked where applicable.

2.10 WHEN P1, P2, P3, C1, C4, and C7 are planned or accepted, THE implementation SHALL preserve these gates and estimates: Stream C1 with Stream A P1 before enforcement rollout; Stream C4 before staging-dependent verification; Stream A P2 before Stream A P3 tenant-query acceptance; and Stream C7 before the final regression gate. The planning estimates SHALL remain C1 Anti-Plastic Toggle (0.5 day), C2 Speed Verbs Injection (<2 hours), C4 Frame Grid Validation (0.5 day), C5 Series Bible (2–3 days), C6 Brand Identity Template (2–3 days), C2 Character Identity Pipeline (3–4 weeks), C3 Character Consistency (3–4 weeks), C9 Input Validation (0.5 day), C10 Rate Limiting (1.5 days), C11 Observability (2 days), C12 API Versioning (1 day), C13 Session Revocation (1.5 days), C14 Performance / Load Strategy (7 days), C15 Job Retry / Error Recovery (3.75 days), and C16 Generation Pipeline Reliability (4.25 days). Stream C6 Settings API / Project Config SHALL remain a separately tracked prerequisite and SHALL not be treated as implemented by this bugfix.

2.11 WHEN `backend/worker.py` performs a service-role Supabase direct poll or a job claim, complete, or fail operation for a tenant-owned job, THE system SHALL derive the trusted organization from the validated job context and SHALL apply an application-layer organization predicate to every tenant-owned operation. For a directly organization-owned `jobs` table, THE operation SHALL include `.eq("org_id", trusted_job_org_id)` or an equivalent bound organization predicate on every applicable read or mutation. IF any worker operation is missing its trusted organization context or application-layer predicate, THEN Stream A P3 acceptance SHALL remain BLOCKED.

2.12 WHEN an HTTP OPTIONS CORS preflight request is received, THE system SHALL process CORS handling before authentication rejection and SHALL not require an Authorization header for the preflight. OPTIONS SHALL be represented in PUBLIC_PROBE_ALLOWLIST or be explicitly exempted by the authoritative middleware policy, with the exemption covered by the same shared policy tests. A preflight with valid CORS headers SHALL receive the existing successful preflight response and SHALL not invoke protected route business logic.

2.13 WHEN any `optional_auth`-guarded path or worker/service path requires tenant-scoped behavior and the validated identity, active membership, job context, or tenant context has no organization, THE system SHALL return the canonical structured membership/authorization error before downstream validation or database access. THE system SHALL never pass `None` as an organization or tenant scope, produce a 500 because the scope is missing, or execute an unscoped tenant query. The tenant-query sweep and regression suite SHALL enumerate and test every `optional_auth`-guarded path.

2.14 WHEN a staging or production deployment is enforcing authentication, THE system SHALL never set `AUTH_ENFORCEMENT_FLIP` from true to false and SHALL not roll back to a release that does not enforce authentication. A release without enforcement SHALL not be considered a safe or valid rollback target. IF the immediately prior release also enforces authentication, THEN it is the only safe rollback target; OTHERWISE the operator SHALL restrict or shepherd traffic while fixing forward or use another release that is independently verified to enforce authentication. Staging and production SHALL remain fail-closed throughout rollback.

2.15 WHEN integration acceptance derives the complete unauthenticated production route set, THE test SHALL verify that every route in that set is represented by PUBLIC_PROBE_ALLOWLIST or the authoritative explicit preflight exemption, including health/readiness probes, documentation routes, auth bootstrap routes, and OPTIONS. THE test SHALL also verify that an unlisted near-match or protected application route requires authentication, so a missed bootstrap route cannot break frontend login without detection.

2.16 WHEN authentication middleware is changed, THE validation SHALL record a representative before/after auth-overhead load or latency benchmark using the same representative request mix and environment. THE benchmark SHALL report the measured difference and SHALL be treated as a validation measurement, not as a new production runtime dependency or a reason to weaken enforcement.

2.17 WHEN authentication middleware and policy changes are accepted, THE new code SHALL achieve at least 80% line coverage, and enforcement, fallback, allowlist, and error paths SHALL each achieve at least 80% branch coverage. Aggregate coverage SHALL not satisfy acceptance when any required branch category or new-code line coverage is below its threshold.

2.18 WHEN reviewing legacy database-query coverage, THE implementation SHALL enumerate every repository occurrence of .table() with literal or non-literal names, .from_(), and dynamic table-name construction, including occurrences in api_v1.py, training/router.py, production_intelligence/router.py, and backend/worker.py, using regex/search followed by manual inspection. The resulting audit SHALL record exactly one classification for every discovered occurrence: organization-scoped with an application-layer predicate using the validated organization, or explicitly exempt with a documented reason. The audit SHALL include worker service-role polls and job claim/complete/fail operations. IF any discovered occurrence is unclassified, any tenant-scoped occurrence lacks that predicate or trusted inherited-context check, any optional_auth path is omitted, or literal-table search is the only discovery method used, THEN the audit SHALL be incomplete and P3 acceptance SHALL remain BLOCKED.

2.19 WHEN Stream B competitive-capability work or Shot Manifest work is planned, implemented, or verified, THE work SHALL continue under its own specification and acceptance gates. This bugfix SHALL not be accepted as delivering or verifying Stream B/Shot Manifest behavior, schemas, prompt capabilities, identity pipeline, series or brand features, manifest storage, or integrations.

**Fix-checking property.** Let `C(X)` be true when `X` is a request or legacy query operation that lacks valid authentication, supplies a client-controlled `org_id`, uses an invalid or expired credential, targets data owned by an organization different from the authenticated organization, invokes an unreviewed tenant-scoped query, runs a worker/service operation without trusted tenant context or its required organization predicate, omits an `optional_auth` tenant path from the sweep, sends an unauthenticated preflight that is incorrectly subject to auth rejection, attempts an unsafe rollback, fails to represent an unauthenticated production route in the shared policy, lacks the required validation benchmark or coverage evidence, or attempts to mark a staging-dependent gate complete before its prerequisites are satisfied. For every `X` where `C(X)` is true, the fixed system `F'(X)` SHALL reject the request with the specified structured error, perform no foreign-organization read or mutation, preserve successful CORS preflight behavior, reject or block the unsafe rollout action, fail the audit or validation gate, or retain the affected staging criterion as `BLOCKED`.

```pascal
FOR ALL X WHERE isBugCondition(X) DO
  result <- F'(X)
  ASSERT unauthorized_or_rejected(result)
      OR (result.contains_no_foreign_org_data
          AND result.performed_no_foreign_mutation)
      OR result.preflight_remains_usable_without_user_auth
      OR result.rollback_remains_enforcing
      OR result.audit_or_validation_gate_fails
      OR result.staging_gate_remains_blocked
END FOR
```

### Unchanged Behavior (Regression Prevention)

The following behavior is outside the bug condition and SHALL remain unchanged:

3.1 WHEN an authenticated caller presents a valid, non-expired JWT for an organization and requests a protected native route without a client-supplied `org_id` THEN the system SHALL CONTINUE to invoke the route's existing business behavior and return its normal success or structured downstream response after both middleware and route-level defense-in-depth checks pass.

3.2 WHEN a request targets a documented public probe route such as `/health`, `/ready`, `/docs`, `/redoc`, `/openapi.json`, or the explicitly allowed root/probe surface THEN the system SHALL CONTINUE to respond without requiring a user JWT, subject to the shared `PUBLIC_PROBE_ALLOWLIST` and existing probe semantics.

3.3 WHEN a local or test request uses the approved development fallback through the unified policy in an environment where that fallback is permitted THEN the system SHALL CONTINUE to resolve the test/development identity according to the existing policy, without allowing that fallback in staging or production.

3.4 WHEN a legacy query is public reference data or another occurrence explicitly documented by the manual audit as not tenant-scoped THEN the system SHALL CONTINUE to execute its existing behavior without an unjustified organization filter, while retaining the audit evidence and exemption reason.

3.5 WHEN an authenticated organization B user accesses organization B data through a legacy v1 list, detail, update, or delete path THEN the system SHALL CONTINUE to return or mutate only the records that the existing endpoint contract permits for organization B.

3.6 WHEN an authenticated request omits `org_id` and otherwise supplies valid credentials and valid input THEN the system SHALL CONTINUE through normal validation, authorization, and handler processing; the guard SHALL not reject the absence of a client-supplied organization parameter.

3.7 WHEN the frontend session holds a valid, unexpired token THEN the dashboard SHALL CONTINUE to make its existing API calls and present their existing success/error states after the token is attached, with token refresh or login redirect occurring only when required by expiry or a 401 response.

3.8 WHEN an explicitly controlled non-production dark-launch environment is used before the frontend-auth readiness gate passes THEN the system SHALL CONTINUE to emit the defined enforcement, would-be rejection, probe-exemption, and injection-attempt signals without treating the dark launch as production or staging completion; once the single flip trigger is satisfied, enforcement SHALL activate without changing the documented public-probe behavior.

3.9 WHEN Stream B competitive capability work or Shot Manifest work is performed independently after this remediation THEN those efforts SHALL CONTINUE to be tracked, tested, and delivered under their own specifications and acceptance gates; this bugfix SHALL not claim their behavior, schemas, or integrations as preserved or complete.

3.10 WHEN a valid authenticated organization, active membership, trusted job context, or other required tenant context is present THEN every `optional_auth`-guarded tenant path and every worker/service operation SHALL CONTINUE to process its existing valid same-tenant behavior after applying the required organization predicate, without changing its response shape or job lifecycle semantics.

3.11 WHEN an HTTP OPTIONS CORS preflight request contains valid CORS headers but no Authorization header THEN the system SHALL CONTINUE to return the existing successful preflight response before protected route handling, without requiring user authentication or changing the documented public route behavior.

3.12 WHEN an enforcing release is rolled back after a verified incident THEN the system SHALL CONTINUE to use only an immediately prior release that also enforces authentication, or restrict/shepherd traffic while fixing forward; staging and production SHALL not be made permissive as a rollback side effect.

3.13 WHEN the representative authentication benchmark is run with the same request mix before and after the change THEN the system SHALL CONTINUE to measure application behavior without changing functional response semantics or introducing a runtime dependency on the benchmark tooling.

**Preservation-checking property.** Let `¬C(X)` be true when the request has valid credentials, no client-controlled `org_id`, accesses only the authenticated organization's data or an explicitly exempt public reference surface, has a valid required tenant context, runs in an allowed environment, uses a preflight that satisfies the CORS contract, targets an enforcing release, and does not attempt to bypass an audit, coverage, benchmark, or staging gate. For every `X` where `¬C(X)` is true, the fixed system SHALL preserve the observable behavior of the original system apart from the newly required middleware/route authentication checks, authenticated request headers, unified policy evaluation, CORS-before-auth preflight handling, application-layer tenant predicates, required null-context rejection, and validation evidence.

```pascal
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT observable_behavior(F(X)) = observable_behavior(F'(X))
      OR difference_is_limited_to_required_authentication_enforcement(X)
END FOR
```
