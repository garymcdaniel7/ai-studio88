# Environment Map — Story 015

**Status: DRAFT — REQUIRES GARY APPROVAL**

This document must be reviewed, corrected, and approved before any deployment or security story can reference it as the source of truth.

Items marked `⚠️ GARY CONFIRM` are inferred from config files and need explicit verification.

---

## 1. Repository

| Field | Value | Status |
|-------|-------|--------|
| GitHub URL | `https://github.com/garymcdaniel7/ai-studio88.git` | Verified |
| Canonical branch | `main` | Verified |
| Owner | @garymcdaniel7 | Verified |
| Visibility | **Public** | Confirmed by Gary |
| Branch protection | Not yet enabled (Story 003 documented rules) | Pending |

---

## 2. Environments

### Production

| Platform | ID / URL | Owner | Deployment Source |
|----------|----------|-------|-------------------|
| **Frontend** | Vercel — `https://ai-studio99.vercel.app` | Gary | Auto-deploy from `main` |
| **Backend** | Railway — project ID/URL unknown (Gary unsure) | Gary | `railway.toml` → uvicorn |
| **Database** | Supabase `vipmjgglascthwoqqqji` — `https://vipmjgglascthwoqqqji.supabase.co` | Gary | SQL migrations (docs/sql/) |
| **Storage** | Backblaze B2 — bucket: `ai-studio88`, region: `us-east-005` | Gary | Backend uploads |
| **GPU Workers** | Vast.ai (primary), RunPod (secondary) — ephemeral instances | Gary | `scripts/vast/launch_comfy_worker.py` |
| **Redis/Queue** | Unknown — may not be deployed for production | Gary | Backend + Celery workers |
| **LLM** | Ollama (local) + OpenAI/Anthropic (cloud fallback) | Gary | ENV vars |

### Staging

**No staging environment exists.** All environments share the same Supabase project, B2 bucket, and Vast.ai account.

### Development (Local)

| Platform | Config | Status |
|----------|--------|--------|
| Frontend | `localhost:3000` — Next.js dev server | Verified |
| Backend | `localhost:8000` — uvicorn --reload | Verified |
| Database | Same Supabase project (`vipmjgglascthwoqqqji`) — **shared with production** | Confirmed risk |
| Storage | Same B2 bucket (`ai-studio88`) — **shared with production** | Confirmed risk |
| GPU | Vast.ai — same account, `TRAINING_VAST_LIVE=false` by default | Verified |
| LLM | Ollama `localhost:11434` | Verified |
| Redis | `redis://localhost:6379/0` | Local only |

---

## 3. Secrets Authority

| Secret Category | Current Source | ⚠️ Production Recommendation |
|-----------------|----------------|-------------------------------|
| Supabase keys | `.env` file (local) | Secrets manager (Doppler/Railway secrets) |
| B2 credentials | `.env` file (local) | Secrets manager |
| Vast.ai API key | `.env` file (local) | Secrets manager |
| Credential encryption key | `CREDENTIAL_ENCRYPTION_KEY` env var | Secrets manager / KMS |
| JWT secret | `SUPABASE_JWT_SECRET` env var | Supabase dashboard (auto-managed) |
| OAuth tokens | DB column (encrypted via CredentialService) | DB + backend |
| SSH key (GPU) | `~/.ssh/id_ed25519` | Per-developer, not shared |

---

## 4. Data Classification

| Environment | Contains Real User Data | PII | Credentials |
|-------------|------------------------|-----|-------------|
| Production | Yes (founder's data only — single-tenant currently) | Minimal | Yes (encrypted) |
| Development | Same database as production — **shared risk** | Same as prod | Dev keys in .env |

---

## 5. Deployment Relationships

```
GitHub main
  ├── Vercel (auto-deploy) → Frontend production
  ├── Railway (auto-deploy?) → Backend production
  └── Manual → GPU workers (Vast.ai on-demand)

Supabase vipmjgglascthwoqqqji
  ├── Frontend reads (via anon key + RLS)
  └── Backend writes (via service_role key)

Backblaze B2 ai-studio88
  └── Backend uploads/downloads (signed URLs to frontend)
```

---

## 6. Open Questions for Gary

All questions answered. Remaining actions:

| # | Finding | Action |
|---|---------|--------|
| 1 | Supabase shared between dev and prod | **Accept risk for now** — single developer, no staging needed until customers onboard |
| 2 | Vercel production domain confirmed | `https://ai-studio99.vercel.app` |
| 3 | Railway project unknown | Gary to confirm if backend is deployed to Railway or only local |
| 4 | No staging environment | Accepted — will revisit when customers onboard |
| 5 | Sole access holder | Gary is only person with all credentials |
| 6 | Redis unknown | Celery/queue features may not work in production |
| 7 | Public repository | **Security implication:** secrets must never be committed; .env patterns are exposed |
| 8 | No other projects | Clean — no stale environments |

---

## 7. Confirmed Risks

| Risk | Evidence | Severity | Accepted? |
|------|----------|----------|-----------|
| **Dev/prod database shared** | Same Supabase project for both | High | Yes (single-dev, revisit at multi-tenant) |
| **Dev/prod storage shared** | Same B2 bucket | Medium | Yes (same reasoning) |
| **No staging environment** | Confirmed by Gary | Medium | Yes (pre-customer phase) |
| **Public repository** | Confirmed by Gary | Medium | Mitigated by .gitignore + gitleaks |
| **Redis not confirmed for prod** | Gary unsure | Low | Celery features degrade gracefully |
| **Sole access holder** | Only Gary has all credentials | Low (bus factor risk) | Accepted for now |

---

## Approval

- [x] Gary has reviewed and confirmed all environment details (2026-08-05)
- [x] Environment boundaries (single env — dev/prod shared) explicitly decided
- [x] Owner confirmed: Gary is sole access holder for all platforms
- [x] No stale/abandoned environments exist
- [x] This document is approved as the canonical environment map

**Approved by:** Gary McDaniel **Date:** 2026-08-05
