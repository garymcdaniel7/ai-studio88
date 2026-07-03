---
inclusion: always
---

# Security Standards

## Secrets

- **Never hardcode secrets** — all secrets via `.env` / environment variables
- **Never log secrets** — no tokens, API keys, passwords in log output
- **Never return secrets** — API keys shown once on creation, never again
- **Never commit `.env`** — `.gitignore` must include `.env`
- Production secrets: use a secrets manager (Doppler, AWS Secrets Manager)

## Authentication

- All endpoints require `Authorization: Bearer <supabase_jwt>` except `/health`, `/ready`
- Validate JWT with `decode_supabase_jwt()` from `app.core.security`
- Never trust user-supplied `user_id` — always extract from validated JWT
- JWT expiry checked on every request

## Authorisation

- Tenant isolation: always filter queries by `org_id` derived from JWT
- Role checks: `owner > admin > editor > viewer` — enforce in service layer
- Supabase RLS: second line of defence at DB level
- Never use `SUPABASE_SERVICE_ROLE_KEY` in client-facing code — backend only

## Input validation

- All API inputs validated via Pydantic schemas — no exceptions
- File uploads: validate MIME type AND magic bytes (not just extension)
- File size limits enforced before reading content
- UUID type for all IDs — never raw strings in query parameters
- SQL: always use parameterised queries via SQLAlchemy — never string interpolation

## Webhook verification

```python
# Always verify HMAC signature before processing webhooks
from app.core.security import verify_webhook_signature

body = await request.body()
sig = request.headers.get("X-Signature-256", "")
if not verify_webhook_signature(body, sig, settings.webhook_secret):
    raise HTTPException(401, "Invalid webhook signature")
```

## CORS

- `allow_origins` restricted to known frontend origins
- Never use `allow_origins=["*"]` in production
- Set from `settings.allowed_origins` (comma-separated env var)

## Dependency security

- `pip-audit` runs in CI on every PR
- Bandit static analysis runs in CI
- Dependabot enabled for weekly dependency updates
- Pin all dependencies to exact versions in `pyproject.toml`

## GPU instances

- ComfyUI API never exposed publicly — SSH tunnel or VPN only
- GPU instances use temporary credentials — never long-lived API keys on instances
- Validate all ComfyUI workflow JSON before dispatching — prevent code injection
- Sanitise all user-supplied prompt strings
