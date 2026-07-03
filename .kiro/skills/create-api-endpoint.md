# Skill: Create API Endpoint

## Purpose

Create a complete, production-ready FastAPI endpoint for a new resource, following AI Studio architecture conventions.

## Inputs

- `resource_name`: The resource name (e.g., `brand`, `product`, `lora_model`)
- `operations`: Which CRUD operations to implement (list, get, create, update, delete)
- `requires_gpu`: Whether this resource triggers GPU jobs

## Outputs

- `app/schemas/{resource}.py` — Pydantic Create/Update/Response schemas
- `app/models/{resource}.py` — SQLAlchemy ORM model
- `app/services/{resource}_service.py` — Business logic
- `app/api/v1/endpoints/{resource}.py` — Route handlers
- `backend/alembic/versions/{timestamp}_add_{resource}_table.py` — Migration
- Update `app/api/v1/__init__.py` to register router

## Steps

1. **Schema first** — `TalentCreate`, `TalentUpdate`, `TalentResponse` in `app/schemas/`
2. **Model** — inherit `Base, UUIDMixin, TimestampMixin, TenantMixin`, add `__tablename__`
3. **Migration** — `alembic revision --autogenerate -m "add_{resource}_table"`
4. **Service** — `{Resource}Service(db: AsyncSession)` with list/get/create/update/delete
5. **Router** — use `CurrentUserIDDep`, `DBSessionDep`, `PaginationDep`
6. **Register** in `app/api/v1/__init__.py`

## Best practices

- All list endpoints paginated
- Soft deletes for user-visible resources
- Always validate org ownership before mutations
- Correct status codes: 201 (create), 204 (delete), 200 (read/update)
