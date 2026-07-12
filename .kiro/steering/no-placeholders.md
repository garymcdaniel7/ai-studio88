---
inclusion: auto
---

# No Placeholders Policy

## Rule

When building new features or adding capabilities:

1. **Never create simulation providers** that return fake data
2. **Never add placeholder endpoints** that return 501/404
3. **Never return fake bytes** (SHA256 hashes, random data) pretending to be real content
4. **Never silently fall back to simulation** — if a service is unavailable, fail explicitly with a clear error message telling the user what's needed

## What To Do Instead

- Connect to the real service. If the service requires a GPU worker or API key, check for it and return a clear error explaining what's missing.
- If a provider can't work without infrastructure (GPU, API key, etc.):
  - Return HTTP 503 with message: "Service unavailable. Requires: [specific thing needed]"
  - Show in the frontend: "⚠️ [Service] requires [thing]. Configure in Admin → Services."
- If the feature is genuinely not built yet, don't create the endpoint at all.

## Existing Simulators

See `docs/SIMULATORS_AUDIT.md` for the full list of 37 existing simulators/placeholders that need to be replaced with real connections over time.

## When Simulation Is Acceptable

Only in automated test suites (`tests/unit/`, `tests/integration/`) where mocking external services is standard practice. Never in production code paths.
