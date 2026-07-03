---
inclusion: always
---

# Testing Standards

## Stack

- **Framework:** pytest + pytest-asyncio
- **HTTP testing:** httpx TestClient
- **Mocking:** pytest-mock + unittest.mock
- **Factories:** factory-boy
- **Coverage:** pytest-cov (target: 80%+ for new code)

## Test categories

| Category | Location | Rules |
|---|---|---|
| Unit | `tests/unit/` | No I/O, no DB, mock all external deps |
| Integration | `tests/integration/` | Real DB, mock external APIs (B2, Vast.ai) |
| E2E | (future) | Full stack, staging env only |

Mark tests: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`

## File structure

```
tests/
  unit/
    test_services/
      test_talent_service.py
    test_core/
      test_security.py
  integration/
    test_api/
      test_talent_endpoints.py
  conftest.py
  factories.py
```

## What to test

- All happy paths
- All error cases (404, 403, 422, 500)
- Auth: unauthenticated request returns 401
- Tenant isolation: user cannot access another org's resources
- Input validation: invalid data returns 422 with clear message
- Pagination: limit/offset work correctly

## Running tests

```bash
pytest tests/unit/ -v
pytest tests/ --cov=app --cov-report=term-missing
pytest -m "unit" -v
pytest -k "test_talent" -v
```
