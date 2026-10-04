# Group 16.2 — Authenticated Browser Fixture Handoff

**Scope:** Phase 2 Close-Out Sprint, Group 16.2 only: reusable Playwright authenticated browser state for WRITE/MAKE flows.

**Status:** **BLOCKED — no registered owner for `frontend/e2e/**`, `frontend/playwright.config.ts`, or the shared frontend auth transport.** This artifact is evidence/handoff only; no unowned application or test path was edited.

**Checkout:** `/Users/garymcdaniel/kiro/ai-studio88`

## Ownership decision

`LANES.json` registers `talent`, `creation`, `post`, `platform`, `growth`, `brain`, and `backend`. It does not register a `frontend/integration` lane, and none of the registered lanes owns `frontend/e2e/**`, `frontend/playwright.config.ts`, or `frontend/src/lib/**`.

Required owner when provisioned:

- **Fixture/config/test owner:** designated `frontend/integration` lane (currently absent).
- **WRITE browser consumers:** creation lane for `frontend/src/app/write/**` and page-local WRITE tests, with post-lane coordination for absorbed editor/storyboard behavior.
- **MAKE browser consumers:** creation lane for `frontend/src/app/make/**`, with post/platform coordination for editor generation controls and model/workflow adapters.
- **Application auth files:** no changes are authorized by this handoff. Any test-only auth seam must be separately assigned and must remain local/test-only.

The existing Phase 2 evidence records the same gap: authenticated WRITE checks had **2 passed, 6 failed** because authenticated route/session state was unavailable, and no authenticated browser fixture was configured.

## Inspected contract

The following local files were inspected without reading any environment/secrets files:

- `LANES.json` — no owner for browser fixtures, Playwright config, or shared auth libraries.
- `frontend/playwright.config.ts` — `./e2e` test directory; desktop and mobile projects only; `BASE_URL` defaults to `http://localhost:3000`; no `globalSetup`, `storageState`, or authenticated project.
- `frontend/src/proxy.ts` — protected requests call Supabase SSR `getUser()`; invalid/missing sessions redirect to `/login` with a safe `redirect` parameter; valid sessions preserve refreshed cookies.
- `frontend/src/app/auth/callback/route.ts` — OAuth callback exchanges a code and writes session cookies to the returned redirect response; no-code/error paths redirect to `/login`.
- `frontend/src/lib/auth-context.tsx` — browser auth state comes from Supabase `getSession()`/`onAuthStateChange`; workspace comes from validated user metadata, with a current fallback to the user ID when metadata is absent.
- `frontend/src/lib/api.ts` and `frontend/src/lib/__tests__/api.test.ts` — canonical API transport attaches bearer auth, performs one refresh/replay on 401, signs out and redirects to `/login` after refresh failure, and rejects client organization selectors.
- `frontend/e2e/proxy-auth.spec.ts`, `frontend/e2e/proxy-unit.spec.ts`, `frontend/e2e/uat-joint-audit.spec.ts`, and `frontend/e2e/pages.ts` — unauthenticated proxy coverage exists; authenticated tests currently depend on direct `TEST_EMAIL`/`TEST_PASSWORD` login or skip when credentials are absent; no reusable storage-state fixture exists.
- `frontend/e2e/publish-audit.spec.ts` and `frontend/e2e/publish-fullflow.spec.ts` — direct credential login patterns exist, but they must not be reused for a non-local `BASE_URL`.

No `frontend/e2e/write.spec.ts` or `make.spec.ts` exists in this checkout. Existing references to WRITE authenticated failures are from lane-worktree evidence, not local test files.

## Smallest fixture contract for the integration owner

Add, under the integration lane only:

```text
frontend/e2e/fixtures/authenticated.ts
frontend/e2e/authenticated-browser.spec.ts
```

The fixture should export a Playwright extended `test` with:

```text
- authenticatedPage: Page
- authenticatedContext: BrowserContext
- testTenant: { orgId: string, userId: string }
```

Use one setup login per worker and Playwright `storageState` for reuse. A generated state file may live under the ignored `frontend/test-results/` tree, for example:

```text
frontend/test-results/.auth/{project}-{worker}.json
```

Do not commit storage state, cookies, access tokens, refresh tokens, credentials, or tenant data. Do not add a fixture path to source control that contains a real session.

### Safe authentication modes

The fixture must support exactly one of these local/test-only modes, selected explicitly by the test harness:

1. **Loopback test-user login (preferred):** use `PLAYWRIGHT_TEST_EMAIL` and `PLAYWRIGHT_TEST_PASSWORD`, supplied by the test runner and belonging only to a local/test Supabase project. Log in through the existing `/login` UI, wait for the callback/session cookie, then save `context.storageState()`.
2. **Explicit mocked auth state:** use a test-only auth seam or local auth emulator that makes the server-side `proxy.ts` validation and browser `auth-context.tsx` resolve a deterministic test user/workspace. The seam must be disabled unless `PLAYWRIGHT_AUTH_MODE=mock` and must not exist in a production/staging build.

The fixture must fail before navigation when `BASE_URL` is not loopback (`localhost`, `127.0.0.1`, or `::1`) unless a separately approved non-production test host is explicitly supplied by the integration owner. It must never default to or contact `ai-studio*.vercel.app`, Supabase production, or any external provider. It must not read `.env`, `.env.*`, editor settings, or arbitrary environment values as credential fallbacks; only the named test variables are permitted.

`PLAYWRIGHT_TEST_ORG_ID` may identify the deterministic test tenant for assertions, but it is assertion metadata only. The browser must not send it as `org_id`, `orgId`, `org-id`, or `organization_id` in a request. Tenant identity must come from the validated test JWT/workspace and server response.

## Required focused tests

The integration owner must add focused tests using the fixture; these are the minimum contract, not permission to edit from this checkout:

1. **Protected route access**
   - Unauthenticated `GET /write` and `GET /make` redirect to `/login?redirect=...`.
   - `authenticatedPage.goto("/write")` and `authenticatedPage.goto("/make")` do not land on `/login`.
   - The first protected API request includes `Authorization: Bearer ...`; no access/refresh token is logged or displayed.

2. **Tenant context / selector safety**
   - The authenticated response identifies the deterministic test tenant expected by `testTenant.orgId` through a local mocked/test API response or a local test backend.
   - Requests contain no client organization selector in URL or body. Assert all four forbidden names (`org_id`, `orgId`, `org-id`, `organization_id`) are absent from fixture-generated requests.
   - A second test tenant cannot be reached by changing a browser query/body selector; cross-tenant detail/write responses remain the local test backend’s structured denial/no-data result.
   - The fixture must not infer tenant identity from prompt text, page URL, or a client-controlled field.

3. **Refresh and redirect behavior**
   - With a local/test expired access session and valid test refresh path, the first protected API response is 401, exactly one refresh occurs, the replay uses the replacement session, and the page remains on WRITE/MAKE.
   - With refresh failure/invalid session, the page signs out and redirects once to `/login?redirect=/write` or `/make`; there is no redirect loop.
   - With a local/test callback code, `/auth/callback?code=...&next=/write` writes session state and redirects to `/write`; invalid/missing code redirects to `/login` and rejects unsafe `next` targets. The test must use a local auth emulator or test project only.
   - Assert refreshed cookies/state are persisted in the generated worker state and never printed.

4. **Storage-state reuse**
   - A second test using the same worker state reaches a protected route without performing another UI login.
   - State is isolated per worker/tenant and deleted with test results; no shared cross-tenant state is reused.

## Required Playwright configuration change (integration owner only)

The owner may add a setup project and authenticated project to `frontend/playwright.config.ts`, preserving the current desktop/mobile projects. The configuration must:

- keep `BASE_URL` loopback-only for this fixture suite;
- place generated state under ignored `frontend/test-results/`;
- avoid putting credentials in `playwright.config.ts`, source, reports, traces, screenshots, or console output;
- leave current unauthenticated proxy tests runnable without authenticated state;
- add a tablet project separately if responsive close-out evidence requires the 768–1023px breakpoint; this fixture handoff does not claim that breakpoint is covered.

## Validation commands for the owner

Run only against a local/test server and record exact node counts:

```bash
BASE_URL=http://127.0.0.1:3000 \
  npx playwright test --list e2e/authenticated-browser.spec.ts

BASE_URL=http://127.0.0.1:3000 \
  npx playwright test e2e/authenticated-browser.spec.ts \
  --project=desktop --project=mobile --reporter=line
```

Do not substitute an external deployment URL. If the local auth emulator/test project or credentials are unavailable, mark the fixture tests **BLOCKED** rather than switching to a production URL or weakening the assertions.

## Current validation performed in this checkout

- **Static/collection inspection:** existing config, auth implementation, callback, proxy, API contract tests, and e2e inventory inspected.
- **Playwright collection PASS:** from `frontend/`, `BASE_URL=http://127.0.0.1:3000 npx playwright test --list e2e/proxy-auth.spec.ts e2e/proxy-unit.spec.ts e2e/uat-joint-audit.spec.ts` collected **142 tests in 3 files** across the existing desktop/mobile projects. This did not start a server or contact an external target.
- **Artifact diagnostics PASS:** the handoff markdown has no diagnostics; `git diff --check` against the new artifact reported no whitespace errors.
- **Not run:** authenticated browser execution; no local test credentials/auth emulator were provided, and running existing direct-login specs would risk an external/default target.
- **Expected status until owner is provisioned:** fixture implementation and WRITE/MAKE authenticated browser evidence remain **BLOCKED**.

## Handoff acceptance

The integration owner may close Group 16.2 only after attaching:

1. owner/lane identity and changed paths;
2. exact `storageState` setup and cleanup behavior;
3. exact test-only auth mode and loopback guard evidence;
4. exact Playwright collection and execution commands/results;
5. protected route, tenant-context, refresh, callback, and redirect-loop test node IDs;
6. confirmation that no `.env*`, production endpoint, shared component, backend route, migration, old spec, or secret was changed.
