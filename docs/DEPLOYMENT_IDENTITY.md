# Source-to-Deployment Identity Mapping (Story 065)

## Canonical Identifiers

| Layer | Identifier | Authority |
|-------|-----------|-----------|
| **Repository** | `garymcdaniel7/ai-studio88` | GitHub |
| **Branch (production)** | `main` | GitHub |
| **Frontend project** | `ai-studio99` | Vercel |
| **Frontend root directory** | `frontend/` | Vercel project settings |
| **Frontend framework** | Next.js 16 (auto-detected) | Vercel |
| **Backend deployment** | TBD (Railway/Render) | DECISION-REQUIRED |
| **Database** | `vipmjgglascthwoqqqji` | Supabase project ref |
| **Storage** | `ai-studio88` bucket | Backblaze B2 |
| **GPU Workers** | `garymcdaniel7/ai-studio-worker` | GHCR / Docker Hub |

## Historical Name Explanation

The repository is named `ai-studio88` (GitHub) while the Vercel project is named `ai-studio99`.
This naming divergence occurred during project setup. They are the SAME product — different names
for the source repository vs the frontend hosting project.

**Canonical product name:** AI Studio  
**Source of truth:** `garymcdaniel7/ai-studio88` on GitHub  
**Deployment project:** `ai-studio99` on Vercel (linked to the same repo)

## Environment Mapping

| Environment | Frontend URL | API URL | Database | Branch |
|-------------|-------------|---------|----------|--------|
| Production | `ai-studio99.vercel.app` (+ custom domain TBD) | TBD | `vipmjgglascthwoqqqji` | `main` |
| Preview | `ai-studio99-*.vercel.app` | TBD | Same Supabase project | PR branches |
| Development | `localhost:3000` | `localhost:8000` | Same Supabase project | any |

## Build & Deploy Configuration

### Frontend (Vercel)

```
Repository:     garymcdaniel7/ai-studio88
Branch:         main
Root Directory: frontend/
Build Command:  next build (default)
Output:         .next (default)
Framework:      Next.js (auto-detected via vercel.json)
Node.js:        20.x
```

### Backend (TBD — DECISION-REQUIRED)

```
Repository:     garymcdaniel7/ai-studio88
Branch:         main
Root Directory: ./ (repo root — backend/ is a Python package)
Entry Point:    uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### GPU Worker

```
Repository:     garymcdaniel7/ai-studio88
Path:           docker/comfyui-worker/
Dockerfile:     Dockerfile.hardened (production target)
Registry:       ghcr.io/garymcdaniel7/ai-studio88/worker
Tags:           :latest, :<commit-sha>
```

## Environment Variables Required Per Target

### Frontend (Vercel)

| Variable | Scope | Required |
|----------|-------|:--------:|
| `NEXT_PUBLIC_SUPABASE_URL` | All | ✅ |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | All | ✅ |
| `NEXT_PUBLIC_API_URL` | All | ✅ |
| `NEXT_PUBLIC_CLARITY_PROJECT_ID` | Production | Optional |

### Backend

| Variable | Required |
|----------|:--------:|
| `SUPABASE_URL` | ✅ |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ |
| `SUPABASE_JWT_SECRET` | ✅ |
| `B2_KEY_ID` | ✅ |
| `B2_APPLICATION_KEY` | ✅ |
| `B2_BUCKET_NAME` | ✅ |
| `CREDENTIAL_ENCRYPTION_KEY` | ✅ (Story 023) |
| `SECRET_KEY` | ✅ |
| `ALLOWED_ORIGINS` | ✅ |
| `AUTH_DEV_MODE` | Dev only |

## Release Manifest References

Every release manifest (Story 062) includes:

```json
{
  "source": {
    "repository": "garymcdaniel7/ai-studio88",
    "branch": "main",
    "commit_sha": "<full SHA>",
    "commit_message": "<first line>"
  },
  "targets": {
    "frontend": {
      "project": "ai-studio99",
      "platform": "vercel",
      "url": "<deployment URL>"
    },
    "api": {
      "platform": "<TBD>",
      "url": "<API URL>"
    },
    "worker": {
      "registry": "ghcr.io/garymcdaniel7/ai-studio88/worker",
      "tag": "<commit SHA>"
    }
  },
  "database": {
    "project_ref": "vipmjgglascthwoqqqji",
    "platform": "supabase"
  }
}
```

## GARY-ACTION Items (Console-Only)

These cannot be automated and require manual Vercel/GitHub console access:

1. **Verify Vercel project linkage** — Confirm `ai-studio99` is linked to `garymcdaniel7/ai-studio88` repo with `frontend/` root directory.

2. **Consider renaming Vercel project** (optional) — If desired, rename `ai-studio99` to `ai-studio88` for consistency. This changes the default `.vercel.app` URL but custom domains are unaffected.

3. **Add deployment webhook** (future) — When backend is deployed, add a webhook that confirms deployment to the release gate.

## Validation Checklist

- [ ] GitHub repo accessible at `github.com/garymcdaniel7/ai-studio88`
- [ ] Vercel project `ai-studio99` builds from `frontend/` directory
- [ ] Vercel env vars set: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL
- [ ] Supabase project `vipmjgglascthwoqqqji` accessible
- [ ] Worker image builds from `docker/comfyui-worker/Dockerfile.hardened`
- [ ] CI workflow validates all targets (Story 061)
- [ ] Release gate consumes correct target identifiers (Story 063)

## Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Repo/project name confusion during incidents | Medium | This document is the canonical reference |
| Preview deploys may use stale env vars | Low | Vercel scopes vars by environment |
| Worker image tag not linked to release manifest | Medium | CI pins to commit SHA |
| Backend deployment platform not yet chosen | High | DECISION-REQUIRED before production |
