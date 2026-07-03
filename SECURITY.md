# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 0.x (current) | Yes |

---

## Reporting a Vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

Report security issues by emailing: **security@yourdomain.com**

Include a description, reproduction steps, potential impact, and any suggested fix.
You will receive acknowledgement within 48 hours and a resolution timeline within 5 business days.

---

## Security Practices

### Secrets Management
- All secrets stored in `.env` — never committed to version control
- Production secrets in a secrets manager (AWS Secrets Manager or Doppler)
- API keys hashed with bcrypt before database storage
- All keys rotated every 90 days

### Authentication
- Supabase JWT tokens with RS256 signing
- Access tokens expire in 30 minutes; refresh tokens in 7 days
- All endpoints require authentication unless explicitly public

### Authorisation
- Row-Level Security (RLS) enforced at PostgreSQL level
- Service-level permission checks in addition to RLS
- Principle of least privilege for all service accounts

### API Security
- Rate limiting per tenant via Redis
- Request size limits enforced at Nginx level
- Input validation via Pydantic on all endpoints
- Parameterised queries only — no raw SQL string formatting
- CORS restricted to known origins

### Data Protection
- All data encrypted at rest (Supabase / B2) and in transit (TLS 1.2+)
- No PII in logs
- Tenant data isolated via `org_id` + RLS

### Dependencies
- Dependabot enabled for Python and Node dependencies
- `pip-audit` runs in CI on every PR
- No unpinned version ranges in production dependencies

### File Uploads
- File type whitelist: jpg, png, webp (images); mp4 (video); safetensors (models)
- File size limits enforced before upload to B2
- Filenames sanitised to prevent path traversal

---

## Known Security Considerations

- GPU instances on Vast.ai run user-supplied workflows — validate all workflows before execution
- ComfyUI API must not be exposed publicly — SSH tunnel or VPN only
- Supabase service role key has full DB access — backend only, never expose to frontend
