---
inclusion: always
---

# Database Standards

## Stack

- **Database:** PostgreSQL 15+ via Supabase
- **ORM:** SQLAlchemy 2.x async
- **Migrations:** Alembic
- **Connection pooling:** asyncpg + SQLAlchemy pool

## Schema conventions

### Every table must have

```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
org_id      UUID NOT NULL                        -- multi-tenancy
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```

### Naming

| Object | Convention | Example |
|---|---|---|
| Tables | snake_case, plural | `ai_talent`, `content_jobs` |
| Columns | snake_case | `talent_id`, `is_active` |
| Indexes | `ix_{table}_{column}` | `ix_content_jobs_org_id` |
| FK constraints | `fk_{table}_{column}_{ref_table}` | `fk_campaigns_talent_id_ai_talent` |
| Unique constraints | `uq_{table}_{column}` | `uq_organizations_slug` |

### Always index

- `org_id` on every tenant-scoped table
- Foreign keys used in JOINs
- Status/type columns used in frequent WHERE clauses
- `created_at` on time-series heavy tables

## SQLAlchemy ORM patterns

### Always inherit base mixins

```python
class AiTalent(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "ai_talent"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### Relationships

```python
# Always use lazy="select" or lazy="raise" — never implicit loading
campaigns: Mapped[list["Campaign"]] = relationship(
    "Campaign",
    back_populates="talent",
    lazy="raise",
)
```

### Queries

```python
# Always scope queries to org_id
stmt = select(AiTalent).where(
    AiTalent.org_id == org_id,
    AiTalent.id == talent_id,
    AiTalent.deleted_at.is_(None),  # soft delete filter
)
result = await db.execute(stmt)
talent = result.scalar_one_or_none()
```

## Migrations

```bash
# Create migration
alembic revision --autogenerate -m "add_ai_talent_table"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Show current state
alembic current
```

### Migration rules

1. Always write a `downgrade()` function
2. Never rename columns in-place — add new, copy data, drop old
3. Never drop columns without a deprecation migration cycle
4. Data migrations go in a separate migration file from schema changes
5. All migrations must be reversible

## Supabase RLS

Every table must have RLS policies. Example:

```sql
ALTER TABLE ai_talent ENABLE ROW LEVEL SECURITY;

-- Users can only see talent in their org
CREATE POLICY "talent_org_isolation" ON ai_talent
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid);
```

## Query patterns

### Paginated list

```python
async def list_talent(
    db: AsyncSession,
    org_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[AiTalent], int]:
    count_stmt = select(func.count()).select_from(AiTalent).where(
        AiTalent.org_id == org_id,
        AiTalent.deleted_at.is_(None),
    )
    total = await db.scalar(count_stmt) or 0

    stmt = (
        select(AiTalent)
        .where(AiTalent.org_id == org_id, AiTalent.deleted_at.is_(None))
        .order_by(AiTalent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return items, total
```
