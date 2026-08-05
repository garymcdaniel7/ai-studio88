# Secret Remediation Report

**Date:** 2026-08-03
**Performed by:** Kiro automated audit
**Scope:** All tracked files, git history (all branches/tags), .env files, scripts, docs, CI config

---

## Executive Summary

No production credentials were found in git-tracked source files or git history.
All secrets reside exclusively in `.env` (untracked, gitignored) and `frontend/.env.local` (untracked, gitignored).
No git history rewriting is required.

---

## Credential Inventory

| # | Provider | Env Variable | Location | Classification | Rotation Required |
|---|----------|-------------|----------|----------------|-------------------|
| 1 | Supabase | `SUPABASE_ANON_KEY` | `.env`, `frontend/.env.local` | ACTIVE | Recommended (see notes) |
| 2 | Supabase | `SUPABASE_SERVICE_ROLE_KEY` | `.env` | ACTIVE | Recommended |
| 3 | Supabase | `SUPABASE_JWT_SECRET` | `.env` | ACTIVE | Recommended |
| 4 | Backblaze B2 | `B2_KEY_ID` | `.env` | ACTIVE | Recommended |
| 5 | Backblaze B2 | `B2_APPLICATION_KEY` | `.env` | ACTIVE | Recommended |
| 6 | Vast.ai | `VAST_API_KEY` / `VASTAI_API_KEY` | `.env` | ACTIVE | Recommended |
| 7 | HuggingFace | `HF_TOKEN` | `.env` | ACTIVE | Recommended |
| 8 | RunPod | `RUNPOD_API_KEY` | `.env` | ACTIVE | Recommended |
| 9 | ElevenLabs | `ELEVENLABS_API_KEY` | `.env` | ACTIVE | Recommended |
| 10 | Vercel | `VERCEL_TOKEN` | `.env` | ACTIVE | Recommended |
| 11 | Vercel | `VERCEL_PROJECT_ID` | `.env` | ACTIVE (not secret) | No |
| 12 | App | `SECRET_KEY` | `.env` | PLACEHOLDER | Generate before production |
| 13 | Database | `DATABASE_URL` | `.env` | PLACEHOLDER | N/A (contains `password` literal) |
| 14 | Stripe | `STRIPE_SECRET_KEY` | `.env` | PLACEHOLDER | N/A (not configured) |
| 15 | Stripe | `STRIPE_WEBHOOK_SECRET` | `.env` | PLACEHOLDER | N/A (not configured) |
| 16 | SMTP | `SMTP_PASSWORD` | `.env` | PLACEHOLDER | N/A (not configured) |
| 17 | OpenAI | `OPENAI_API_KEY` | `.env` | EMPTY | N/A |
| 18 | Instagram | `INSTAGRAM_ACCESS_TOKEN` | `.env` | EMPTY | N/A |
| 19 | TikTok | `TIKTOK_ACCESS_TOKEN` | `.env` | EMPTY | N/A |
| 20 | YouTube | `YOUTUBE_OAUTH_CLIENT_SECRET` | `.env` | EMPTY | N/A |
| 21 | Publishing | `PUBLISHING_WEBHOOK_SECRET` | `.env` | EMPTY | N/A |

---

## Exposure Analysis

### Git History
- **Result:** CLEAN. No credentials have ever been committed.
- `.env` was never tracked (`.gitignore` includes it from the initial commit).
- `frontend/.env.local` was never tracked.
- No history rewriting needed.

### Tracked Source Files
- **Result:** CLEAN. All secret access uses `os.getenv()`, `process.env.`, or `${VAR}` interpolation.
- No hardcoded credential values in any `.py`, `.ts`, `.tsx`, `.sh`, `.yml`, or `.json` file.

### Informational Findings (Non-Secret)
| Finding | Files | Risk | Action |
|---------|-------|------|--------|
| Supabase project URL hardcoded | `backend/aios/hermes/agent.py`, `.kiro/steering/project-status.md`, `docs/DEPLOY.md` | LOW — public endpoint, not a secret | Optional: parameterize via `SUPABASE_URL` env var |
| Supabase anon key in `frontend/.env.local` | Untracked file | LOW — anon keys are designed for client-side use per Supabase docs | No action needed |

### `.env.example` Assessment
- Contains only placeholder values (`your-xxx`, `placeholder`, descriptive hints).
- No real secrets present.
- One cosmetic improvement: some placeholder patterns could be more uniform (addressed below).

---

## Rotation Procedures

### Priority 1: Service Role Keys (highest privilege)

**Supabase Service Role Key + JWT Secret:**
1. Go to https://supabase.com/dashboard → Project Settings → API
2. Regenerate the service role key
3. Update `SUPABASE_SERVICE_ROLE_KEY` in `.env`
4. Regenerate JWT secret under Settings → Auth → JWT Settings
5. Update `SUPABASE_JWT_SECRET` in `.env`
6. Restart backend: `uv run uvicorn backend.main:app --reload`
7. Verify: `curl http://localhost:8000/api/v1/health`

### Priority 2: Storage & GPU Provider Keys

**Backblaze B2:**
1. Go to https://secure.backblazeb2.com → App Keys
2. Create new application key (same bucket permissions)
3. Delete old key
4. Update `B2_KEY_ID` and `B2_APPLICATION_KEY` in `.env`
5. Verify: backend storage health check

**Vast.ai:**
1. Go to https://cloud.vast.ai → Account → API Key
2. Regenerate key
3. Update `VAST_API_KEY` and `VASTAI_API_KEY` in `.env`
4. Verify: `vastai show instances`

**RunPod:**
1. Go to https://www.runpod.io → Settings → API Keys
2. Create new key, delete old
3. Update `RUNPOD_API_KEY` in `.env`

### Priority 3: Model & Voice Provider Keys

**HuggingFace:**
1. Go to https://huggingface.co/settings/tokens
2. Delete old token, create new with same permissions
3. Update `HF_TOKEN` in `.env`

**ElevenLabs:**
1. Go to https://elevenlabs.io → Profile → API Keys
2. Create new key, delete old
3. Update `ELEVENLABS_API_KEY` in `.env`

### Priority 4: Deployment Token

**Vercel:**
1. Go to https://vercel.com → Settings → Tokens
2. Create new token, revoke old
3. Update `VERCEL_TOKEN` in `.env`
4. Update Vercel project environment variables if needed

---

## Automated Scanning Added

- **Pre-commit hook:** `detect-secrets` runs on every commit attempt
- **CI integration:** GitHub Actions workflow runs `detect-secrets` on all PRs
- **Baseline:** `.secrets.baseline` tracks known false positives

---

## Deployment Refresh Required After Rotation

| Environment | Action |
|-------------|--------|
| Local dev | Restart backend (`uv run uvicorn ...`) |
| Vercel (frontend) | Redeploy after updating env vars in Vercel dashboard |
| GPU workers | No action (keys passed at runtime via SSH env) |

---

## Residual Risks

1. **Supabase anon key** is by design exposed to browsers — ensure RLS policies are correctly configured (separate verification).
2. **`SECRET_KEY=change_me_generate_with_openssl_rand_hex_32`** is a placeholder — must be replaced with a real random value before any production deployment.
3. **`AUTH_REQUIRED=false`** in `.env` — acceptable for local dev but must be `true` in production.

---

## Conclusion

The repository is in good shape regarding secret hygiene. No credentials were ever committed to version control. The primary action items are:
1. **Rotate credentials** as a precautionary best practice (especially if `.env` was ever shared via insecure channels).
2. **Add automated scanning** to prevent future accidental commits (implemented in this PR).
3. **Generate a real `SECRET_KEY`** before production deployment.
