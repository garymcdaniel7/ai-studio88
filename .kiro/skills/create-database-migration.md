# Skill: Create Database Migration

## Purpose

Create a safe, reversible Alembic migration for schema changes.

## Steps

```bash
# 1. Make model changes in app/models/
# 2. Generate
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "describe_the_change"
# 3. Review generated file, then apply
alembic upgrade head
# 4. Test rollback
alembic downgrade -1 && alembic upgrade head
```

## Migration checklist

- [ ] `upgrade()` complete and correct
- [ ] `downgrade()` reverses ALL changes
- [ ] New tables include `id`, `org_id`, `created_at`, `updated_at`
- [ ] Indexes added for `org_id` and foreign keys
- [ ] No column renames (add new + deprecate old)
- [ ] Data migrations separated from schema migrations

## Supabase RLS (add after every new table)

```sql
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;

CREATE POLICY "{table}_org_isolation" ON {table}
    FOR ALL TO authenticated
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY "{table}_service_role" ON {table}
    FOR ALL TO service_role USING (true) WITH CHECK (true);
```

Apply with: `supabase db push`

## Common patterns

```python
# Add column (nullable first, constrain later)
op.add_column('table', sa.Column('field', sa.String(100), nullable=True))

# Add index
op.create_index('ix_table_column', 'table', ['column'])

# Add FK
op.create_foreign_key('fk_name', 'source', 'target', ['col'], ['id'], ondelete='CASCADE')
```
