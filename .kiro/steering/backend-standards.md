---
inclusion: always
---

# Backend Standards

## Stack

- **Language:** Python 3.12+
- **Framework:** FastAPI
- **Package manager:** uv
- **ORM:** SQLAlchemy 2.x (async)
- **Migrations:** Alembic
- **Validation:** Pydantic v2
- **Task queue:** Celery + Redis
- **Testing:** pytest + pytest-asyncio

## Code style

- Line length: 100 characters (Black + Ruff enforce this)
- Imports: absolute, sorted by Ruff isort rules
- Type annotations: required on all functions and methods
- Docstrings: required on all public modules, classes, and functions
- f-strings: preferred over `.format()` and `%`

## File naming

| Type | Convention | Example |
|---|---|---|
| Modules | snake_case | `talent_service.py` |
| Classes | PascalCase | `TalentService` |
| Functions | snake_case | `get_talent_by_id` |
| Constants | SCREAMING_SNAKE | `MAX_UPLOAD_SIZE_MB` |
| Variables | snake_case | `talent_id` |
| Type vars | T, PascalCase | `TModel` |

## Project structure

```
backend/
  app/
    api/v1/endpoints/   ← one file per resource (talent.py, jobs.py)
    core/               ← config.py, security.py, dependencies.py, logging.py
    db/                 ← session.py, base.py
    models/             ← SQLAlchemy ORM models (one file per model or group)
    schemas/            ← Pydantic schemas (one file per resource)
    services/           ← Business logic (one file per service)
    workers/            ← Celery tasks (one file per task group)
  alembic/
  tests/
    unit/               ← no I/O, mock everything external
    integration/        ← requires running DB/Redis
```

## Required patterns

### Every endpoint file

```python
from app.core.dependencies import CurrentUserIDDep, DBSessionDep
# Use Annotated type aliases — never repeat Depends() inline
```

### Every service

```python
class TalentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, talent_id: UUID, org_id: UUID) -> Talent:
        # Always validate org_id ownership
        ...
```

### Every model

```python
class AiTalent(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "ai_talent"
    # Always use UUIDMixin, TimestampMixin, TenantMixin
```

## Error handling

```python
# Always catch specific exceptions
try:
    result = await service.get(...)
except NoResultFound:
    raise HTTPException(status_code=404, detail="Not found")
except PermissionError:
    raise HTTPException(status_code=403, detail="Forbidden")
# Never bare except:
```

## Logging

```python
from app.core.logging import get_logger
logger = get_logger(__name__)

# Always include identifying context
logger.info("job_submitted", job_id=str(job.id), org_id=str(org.id), job_type=job.job_type)

# Never log secrets, tokens, passwords, or PII
```
