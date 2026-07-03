# Contributing to AI Studio

Thank you for contributing. This document describes the development workflow and standards expected for all contributors.

---

## Before you start

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system design.
2. Follow [SETUP.md](SETUP.md) to get your environment working.
3. Check open issues and the roadmap before opening new ones.

---

## Branching strategy

We use trunk-based development with short-lived feature branches.

| Branch | Purpose |
|---|---|
| `main` | Production-ready code only |
| `develop` | Integration branch for features |
| `feature/<ticket>-<short-description>` | New features |
| `fix/<ticket>-<short-description>` | Bug fixes |
| `chore/<description>` | Tooling, docs, refactors |
| `release/<version>` | Release preparation |

```bash
# Start a feature
git checkout develop
git pull origin develop
git checkout -b feature/AI-123-add-lora-training-endpoint
```

---

## Development workflow

1. Create a branch from `develop`
2. Write code following the standards below
3. Write or update tests
4. Verify checks pass: `pre-commit run --all-files`
5. Push and open a PR against `develop`
6. Request review from at least one engineer

---

## Code standards

### Python

- Python 3.12+
- Format with **Black** (line length 100)
- Lint with **Ruff**
- Type-annotate all functions
- Use Pydantic models for all API inputs/outputs
- Never use bare `except:` — catch specific exceptions
- Use `async def` for all FastAPI endpoints
- Never import from `app.*` in a circular way

```bash
# Format
black backend/

# Lint
ruff check backend/

# Type check
mypy backend/app
```

### API design

- All endpoints under `/api/v1/`
- Use noun plurals for resource paths (`/talents`, `/campaigns`)
- HTTP methods: GET (read), POST (create), PUT (full update), PATCH (partial), DELETE
- Return `201 Created` for successful resource creation
- Use standard error schema: `{"detail": "message", "code": "ERROR_CODE"}`
- Paginate list endpoints with `limit` / `offset` query params
- Never expose internal IDs in responses — use UUIDs

### Database

- All migrations via Alembic
- Always write a down migration
- Never rename columns in-place — add new, migrate data, drop old
- All tables must have: `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `created_at`, `updated_at`, `org_id`

---

## Commit messages

Follow Conventional Commits:

```
<type>(<scope>): <short description>

[optional body]

[optional footer: BREAKING CHANGE, Closes #issue]
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `ci`

Examples:
```
feat(talent): add LoRA training endpoint
fix(auth): correct JWT expiry calculation
docs(setup): update Supabase local dev instructions
```

---

## Pull requests

- Title must follow commit message format
- Fill in the PR template
- All CI checks must pass
- At least one approved review before merge
- Squash merge into `develop`

---

## Testing

```bash
# Run tests
pytest backend/tests/

# With coverage
pytest --cov=app --cov-report=term-missing

# Run pre-commit on all files
pre-commit run --all-files
```

- Unit tests live in `backend/tests/unit/`
- Integration tests live in `backend/tests/integration/`
- Use fixtures for database setup/teardown
- Mock external services (Vast.ai, B2) in unit tests
- Target 80%+ coverage for new code

---

## Opening issues

Use the provided issue templates. Include:
- What you expected
- What actually happened
- Steps to reproduce
- Environment info (`./verify_environment.sh` output)

---

## Security vulnerabilities

Do not open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md).
