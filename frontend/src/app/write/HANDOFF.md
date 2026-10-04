# WRITE lane handoff

The creation lane owns `/write` and its page-local components. No shared components, backend files, or post-lane `/editor` files were changed.

## Backend contract needed by the next integration checkpoint

The current authenticated legacy story API provides tenant-scoped reads and `POST /api/v1/shots/{shot_id}/generate`. The WRITE UI calls `PUT /api/v1/shots/{shot_id}` to persist the six-section prompt, preview parameters, continuity, and ordered reference asset IDs before dispatching preview generation. The current backend branch has the repository mutation but no registered shot-update route, and the existing generation route does not yet accept a preview request body.

Backend/integration should add a typed, tenant-safe shot update/preview contract (or provide an adapter) before enabling production prompt saves. The UI deliberately surfaces the canonical `ApiError` and request ID when that contract is unavailable; it does not persist a browser-only copy or bypass auth. Full-quality rendering remains a MAKE concern.

## Post-lane boundary

Storyboard/timeline behavior is implemented only in `/write`. The post lane may absorb or redirect the old `/editor` storyboard surface, but should not modify this route or shared components without an explicit integration checkpoint.

## Group 16.1 route-absorption checkpoint

WRITE is the built destination for storyboard/script/timeline responsibilities. The creation lane owns the destination implementation under `/write`; it does not duplicate or import post-owned `/editor` files. The shared `/editor` interstitial and 301/deprecation behavior remain an integration-owned proxy concern.

The current `/production` and `/story` implementations remain in place until their non-storyboard capabilities are covered: production still exposes fleet/cost/job operations, while story still creates universes and plans shots. The route contract may redirect those legacy paths only after the destination behavior is proven and the shared migration suite passes.

`frontend/src/lib/route-migration.ts`, `frontend/src/proxy.ts`, and `frontend/e2e/**` are outside this lane's registered ownership. Integration/test handoff is required for the editor interstitial, 301 status, query forwarding, auth-before-migration ordering, deprecation headers, and built deep-link checks.
