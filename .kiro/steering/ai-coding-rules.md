---
inclusion: always
---

# AI Coding Rules

Rules for all AI-assisted code generation in this repository.

## Always do

- Read the relevant existing code before writing new code
- Follow the layered architecture: router → service → repository
- Use existing patterns — copy the style of adjacent files
- Add type annotations to every function signature
- Use the existing `get_logger(__name__)` pattern for logging
- Use `CurrentUserIDDep` and `DBSessionDep` in all authenticated endpoints
- Return appropriate HTTP status codes (201 for create, 204 for delete, 202 for async)
- Include docstrings on all public functions and classes
- Validate org_id ownership in every service mutation

## Never do

- Never expose the `SUPABASE_SERVICE_ROLE_KEY` in client-facing code
- Never log secrets, tokens, or PII
- Never use bare `except:` — always catch specific exceptions
- Never skip the Pydantic schema layer — all API inputs/outputs go through schemas
- Never write raw SQL — use SQLAlchemy ORM or `text()` with bound params
- Never hardcode secrets, URLs, or configuration values
- Never create database sessions outside `get_db_session()`
- Never block the event loop — use `asyncio.run_in_executor` for blocking calls
- Never modify existing migrations — create new ones
- Never push directly to `main`

## Code generation guidelines

When asked to create a new feature:
1. Create the Pydantic schema first (`app/schemas/{resource}.py`)
2. Create the SQLAlchemy model (`app/models/{resource}.py`)
3. Create the Alembic migration
4. Create the service class (`app/services/{resource}_service.py`)
5. Create the endpoint file (`app/api/v1/endpoints/{resource}.py`)
6. Register the router in `app/api/v1/__init__.py`
7. Write unit tests for the service

When asked to add a database table:
- Always include: `id UUID PK`, `org_id UUID NOT NULL`, `created_at`, `updated_at`
- Always add RLS policy in a Supabase migration
- Always add an index on `org_id`

When asked to add a GPU job type:
- Add a new Celery task in `app/workers/tasks/`
- Register the task in `app/workers/celery_app.py`
- Add job type to the `JobType` enum
- Always add instance cleanup in a `finally` block

## File size limit

If a file exceeds 300 lines, split it. Prefer multiple focused files over one large one.

## Imports

Maintain this import order (enforced by Ruff):
1. Standard library
2. Third-party packages
3. Local application imports (`app.*`)

Always use absolute imports. Never relative imports (`from . import ...`).
