---
inclusion: manual
---

# Skill: Run UAT Tests

Run the Ise Playwright E2E test suite against the AI Studio frontend. Interpret results, update the steering knowledge, and feed findings to Hermes.

## Prerequisites

- Frontend running on `localhost:3000` (`cd frontend && npm run dev`)
- Backend running on `localhost:8000` (`uv run uvicorn backend.main:app --reload`)
- Playwright installed (`cd frontend && npx playwright install chromium`)

## Steps

### 1. Run tests (choose scope)

```bash
# Full suite (recommended — ~3min)
cd frontend && npx playwright test --project=desktop --timeout=20000 --workers=1 --reporter=list

# Single page (fast — ~20s)
cd frontend && npx playwright test e2e/{page}.spec.ts --project=desktop --workers=1

# Via Ise API (background, stores results)
curl -X POST http://localhost:8000/aios/v1/ise/uat/run -H "Content-Type: application/json" -d '{"filter":"brain"}'
```

### 2. Interpret results

For each test file, record:
- **Pass count** and **fail count**
- For failures: the test name, error message, and which locator/assertion failed
- Whether the failure is a **test issue** (bad selector, timing) or a **real UI bug**

### 3. Classify failures

| Pattern | Diagnosis | Action |
|---------|-----------|--------|
| `locator('h1').first()` timeout | Page gates h1 behind loading | Fix: render h1 unconditionally |
| `networkidle` timeout | Page has API polling | Fix: use `domcontentloaded` |
| `isAttached is not a function` | Playwright API changed | Fix: use `count() > 0` |
| Element not found after navigation | Parallel worker race condition | Fix: use `--workers=1` |
| API endpoint returns 500 | Backend bug | File bug, not a test issue |
| API endpoint returns 404 | Route missing or changed | Check backend router mounts |

### 4. Update steering

After each run, update `.kiro/steering/uat-system.md`:
- Update the **Page Health Map** with current results
- Update **Last run** date
- Add new failures to **Known Patterns** if they represent new learnings
- Mark resolved patterns when fixes are confirmed

### 5. Feed to Hermes

Send a summary to the Brain so Hermes learns:

```bash
curl -X POST http://localhost:8000/aios/v1/hermes/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "UAT run complete: {passed}/{total} pass. Failures: {list}. Pages affected: {list}.",
    "mode": "production_advisor"
  }'
```

Or via the Ise UAT API:
```bash
# Get latest results
curl http://localhost:8000/aios/v1/ise/uat/latest

# Get alerts (failed tests)
curl http://localhost:8000/aios/v1/ise/uat/alerts
```

### 6. Fix and re-run

For test failures:
1. Read the failing test file
2. Read the corresponding page component
3. Determine if it's a test selector issue or a real UI problem
4. Apply the fix
5. Re-run just the affected test file to confirm
6. Commit with message: `fix(uat): {description}`

## Quick Reference

| Command | Purpose |
|---------|---------|
| `npx playwright test --project=desktop` | Full desktop suite |
| `npx playwright test --project=mobile` | Full mobile suite |
| `npx playwright test --grep="Brain"` | Filter by name |
| `npx playwright show-trace trace.zip` | Debug with trace viewer |
| `npx playwright test --debug` | Step-through mode |
| `npx playwright test --ui` | Interactive UI mode |

## Expected Baseline

When all services are healthy, the expected result is:
- **104/104** core tests pass (home through settings)
- **22/22** fleet tests pass (requires live backend + API routes)
- **35/35** responsive tests pass (mobile viewport checks)
- Total: **~161 tests** when everything is green

## Output Format for Hermes

When reporting to Hermes, use this format:
```
UAT Run: {date}
Result: {passed}/{total} ({percentage}%)
Status: {GREEN if 100% | YELLOW if >90% | RED if <90%}
Failures:
- {test_name}: {one-line error} → {diagnosis}
Action needed: {yes/no} — {description if yes}
```
