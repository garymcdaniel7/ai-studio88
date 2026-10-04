# MAKE lane handoff — Phase 2 Task Group 6

Date: 2026-08-25
Lane: creation (`/create/**` only)
Status: `UNIT-READY` for the creation-owned workshop adapter; `/make` route integration is `BLOCKED` pending explicit cross-lane ownership.

## Implemented in this lane

- `PromptWorkshop` is embedded in the existing creation-owned `/create` route. It provides Dialogue, Action, Establishing, and Reaction templates; Subject, Action, Camera, Lighting, and Sound injectors; Anti-Plastic, Speed Verbs, and Frame Grid toggles; full H3 preview; Simple/Advanced modes; three typed control tiers; exact H3 frame-grid values; quality presets; and inline queue/review UI.
- `make-contract.ts` is the page-local serialization contract. It owns bounds, frame-grid snapping, prompt assembly, quality defaults, cost estimate display, and queue error classification.
- Dispatch uses the canonical authenticated `api` client and the existing `/api/v1/generate/batch` contract. The backend batch service remains responsible for the authoritative estimate/reservation, tenant scope, async lifecycle, and provenance. The UI will not dispatch without a positive estimate and an authenticated session.

## Required integration handoffs

1. **Integration/platform lane — create `/make` route:** Add `frontend/src/app/make/page.tsx` as the canonical destination and move or re-export the creation-owned workshop without changing `frontend/src/components/**`. Preserve the `/create` compatibility surface until route-absorption validation passes.
2. **Platform lane — model/checkpoint/workflow adapters:** Replace the page-local fallback selectors with typed adapters for the existing model and workflow APIs. Keep all requests on `api.*`, preserve tenant-derived scope, and do not expose provider credentials.
3. **Post lane — editor generation controls:** Route editor generation controls to `/make`; keep storyboard/timeline behavior in WRITE/editor-owned paths. Do not import or mutate post-owned files from this lane.
4. **Backend lane — richer generation payload:** The existing batch endpoint accepts the core prompt/model/size/steps/CFG contract and performs reservation. To persist sampler, scheduler, frame grid, LoRA, ControlNet, precision, locks, motion, and workflow provenance as first-class fields, add an additive typed backend schema/service contract and return those fields in job/batch status. Do not edit `backend/api_v1.py` from this lane.
5. **Backend lane — preflight estimate:** The current batch endpoint calculates/reserves cost at submission but does not expose a standalone image-generation estimate endpoint. Add an authenticated tenant-scoped preflight estimate endpoint if the product requires a separately displayed server-authoritative estimate before POST `/generate/batch`; retain the reservation gate as the final authority.
6. **Test/integration lane:** Move the page-local contract assertions into the configured Playwright test directory and add authenticated browser fixtures for `/make`, tenant A/B API fixtures, 401/403/422 cases, provider-down/OOM/timeout responses, and no-secret assertions. This lane could not edit `frontend/e2e/**` because it is not listed in the creation lane's `LANES.json` ownership.

No `/make`, post-owned editor, platform-owned model/workflow, backend, shared component, env, secret, or unrelated dirty file was edited by this lane.

## Validation note

The creation-owned unit contract suite passed with `node --experimental-strip-types --test src/app/create/_lib/make-contract.test.mjs`. The page-local browser spec is present at `create-workshop.spec.ts`, but `npx playwright test src/app/create/create-workshop.spec.ts --project=desktop --reporter=line` returns `No tests found` because the repository Playwright config is fixed to `testDir: ./e2e`; moving it into `frontend/e2e/**` requires the integration/test owner.

## Group 16.1 route-absorption checkpoint

The creation lane did not remove `/create` or its implementation. The canonical `/make` destination is not registered as a creation-owned path and is not built in this worktree; removing `/create` would leave the approved 301 destination without a behavior-complete page. The Prompt Workshop remains the `/create` compatibility implementation until the integration/platform lane lands `/make` and proves the migrated controls, authenticated deep links, query forwarding, and queue/error behavior.

`/production` is also retained in this lane: its existing queue/fleet/cost surface is not behavior-equivalent to the current `/write` storyboard destination. `/story` remains the legacy story-management surface because universe creation and shot planning are not yet covered by `/write`. The route-migration owner must keep the approved `/production → /write` contract and `/story` keep-route behavior until those capabilities are explicitly absorbed and covered.

Shared route contract files were intentionally not edited here. `frontend/src/lib/route-migration.ts`, `frontend/src/proxy.ts`, and `frontend/e2e/route-migration.spec.ts` are outside the creation lane's `LANES.json` ownership. Integration handoff: update the shared contract/proxy only after `/make` is built, execute 301/deprecation/query/auth/deep-link checks, then remove the compatibility implementation in a serialized checkpoint.

### Test-lane handoff

The creation lane cannot own `frontend/e2e/**`, and the package has no frontend test script. The integration/test owner should run the route-migration Playwright suite against a production build with representative `/create`, `/production`, `/story`, `/make`, and `/write` requests, including unauthenticated redirect, authenticated query forwarding, `Deprecation`/`Sunset`, and no-404 deep-link assertions. No route was marked removed without that evidence.
