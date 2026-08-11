# Branch Protection & Required CI Checks

## Protected Branch: `main`

All merges to `main` must pass the required CI checks below. Direct pushes are
discouraged; use pull requests so checks run before merge.

## Required Checks (must pass to merge)

| Check Name (GitHub) | What it validates | Blocks merge on failure |
|---|---|---|
| `Backend: Tests` | `pytest tests/unit/ -v --cov --cov-fail-under=40 -x` + import check | Yes |
| `Frontend: Build` | `npm ci` + `tsc --noEmit` + `next build` | Yes |
| `Enforcement: Auth Boundary` | `pytest tests/unit/test_data_access_enforcement.py` | Yes |

## Informational Checks (do not block merge)

| Check Name | What it validates | Notes |
|---|---|---|
| `Backend: Lint` | `ruff check` | 950 pre-existing issues; informational until resolved |
| `Frontend: Build` → Lint step | `eslint` | 214 pre-existing errors being resolved; `continue-on-error: true` |
| `Schema: Control Matrix` | Schema coverage report | Advisory until gaps are closed |
| `Worker: Docker Build` | GPU worker Dockerfile builds | Advisory (not all PRs affect worker) |
| `Security: Scan` | Secret scan + dependency audit + static analysis | See `security-gate.yml` |
| `Config: Profiles` | Validates settings for `local` and `test` profiles | Advisory |

## Configuring Branch Protection (GitHub Settings)

Go to **Settings → Rules → Rulesets** (or legacy Branch Protection Rules):

1. **Branch name pattern:** `main`
2. **Require a pull request before merging:** Yes
   - Required approvals: 1 (recommended)
3. **Require status checks to pass before merging:** Yes
   - Add these required checks:
     - `Backend: Tests`
     - `Frontend: Build`
     - `Enforcement: Auth Boundary`
4. **Require branches to be up to date before merging:** Yes
5. **Do not allow bypassing the above settings:** Recommended for all contributors

## Local Parity (run before pushing)

These commands mirror exactly what CI runs:

```bash
# Backend lint
ruff check backend/ tests/ scripts/

# Backend tests (same as CI)
AUTH_DEV_MODE=true pytest tests/unit/ -v --cov=backend --cov-fail-under=40 -x --tb=short

# Backend import check
python -c "from backend.main import app; print(f'Routes: {len(app.routes)}')"

# Frontend typecheck
cd frontend && npm run typecheck

# Frontend build
cd frontend && NEXT_PUBLIC_SUPABASE_URL="https://placeholder.supabase.co" \
  NEXT_PUBLIC_SUPABASE_ANON_KEY="placeholder" \
  NEXT_PUBLIC_API_URL="http://localhost:8000" \
  npm run build
```

## Emergency Override Process

If a critical fix must merge despite a failing check:

1. Repository admin creates a bypass via Ruleset exception or temporarily disables the rule
2. PR description must document: which check failed, why override is needed, follow-up plan
3. A follow-up PR to fix the failing check must be opened within 24 hours
4. Tag the PR with `emergency-override` label

## Edge Cases

| Scenario | Handling |
|---|---|
| Docs-only PR | CI still runs (path filters removed intentionally) — build must pass regardless |
| Missing secrets (forks) | Security scan uses `continue-on-error`; other checks don't need secrets |
| Flaky tests | No known flaky tests currently. If discovered, mark `@pytest.mark.flaky` and file issue |
| Dependency cache poisoning | `npm ci` (not `npm install`) ensures lockfile integrity |
| Renamed default branch | Update ruleset branch pattern if ever changed from `main` |

## Vercel Deployment Status

Vercel deployments are triggered on push to `main` and on PR branches:
- PR previews: automatic, not blocking
- Production (`main`): deploys after merge; deployment status visible in GitHub

To make Vercel deployment status required (optional, stricter):
- Add `Vercel` as a required status check in branch protection
- This ensures the preview build succeeds before merge

## History

- **2026-08-05**: Initial branch protection documentation (Story 003)
- Lint made informational until pre-existing 214 errors are resolved
- TypeScript typecheck added as blocking step
- Coverage threshold: 40% (will increase as test coverage grows)
