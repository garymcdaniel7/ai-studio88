---
inclusion: always
---

# API Design Standards

## URL structure

```
/api/v1/{resource}/{id}/{sub-resource}
```

- Lowercase, hyphen-separated path segments
- Noun plurals for collections (`/talents`, `/campaigns`, `/jobs`)
- No verbs in URLs except for actions: `/jobs/{id}/cancel`, `/talent/{id}/publish`

## HTTP methods

| Method | Action | Success code |
|---|---|---|
| GET | Read resource or list | 200 |
| POST | Create resource | 201 |
| PUT | Full replacement | 200 |
| PATCH | Partial update | 200 |
| DELETE | Delete | 204 |
| POST /cancel | Cancel async job | 200 |

## Request validation

All inputs validated via Pydantic schemas. Always use:
- `Field(min_length=1)` for required strings
- `Field(ge=0, le=100)` for bounded integers
- `UUID` type for all IDs — never raw strings
- Enum types for fixed option sets

## Response format

### Success (single resource)

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

### Success (list)

```json
{
  "items": [],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

### Error

```json
{
  "detail": "Human-readable message",
  "code": "SNAKE_CASE_ERROR_CODE"
}
```

## Pagination

All list endpoints accept:
- `?limit=20` (default 20, max 100)
- `?offset=0` (default 0)

Use `PaginationDep` from `app.core.dependencies`.

## Authentication

All endpoints (except `/health` and `/ready`) require:
```
Authorization: Bearer <supabase_jwt>
```

Use `CurrentUserIDDep` for authenticated user ID.

## Versioning

- Version prefix in URL: `/api/v1/`
- When breaking changes are needed, add `/api/v2/` routes
- Old versions deprecated for 90 days before removal
- Deprecation header: `Deprecation: true`, `Sunset: <date>`

## Async jobs

For long-running operations (generation, training):
- Submit: `POST /jobs` → returns `202 Accepted` with job ID
- Poll: `GET /jobs/{id}` → returns current status
- Subscribe: Supabase Realtime channel for live updates
- Never make the client wait synchronously for GPU work

## Rate limiting

Per-tenant rate limits (configured in Redis):
- Default: 100 req/min per org
- GPU job submission: 10 jobs/min per org
- File upload: 20 uploads/min per org
