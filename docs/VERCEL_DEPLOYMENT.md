# Vercel Deployment Guide

## Project Configuration

| Setting | Value |
|---------|-------|
| Repository | `garymcdaniel7/ai-studio88` |
| Branch | `main` |
| Root Directory | `frontend/` |
| Framework | Next.js (auto-detected via `vercel.json`) |
| Build Command | `next build` (default) |
| Output Directory | `.next` (default) |
| Node.js Version | 20.x (LTS) |

## Environment Variables

### Required for All Environments

| Variable | Scope | Description |
|----------|-------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Production, Preview, Development | Supabase project URL (`https://PROJECT_REF.supabase.co`) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Production, Preview, Development | Supabase anonymous/public key (RLS-protected) |
| `NEXT_PUBLIC_API_URL` | Production, Preview, Development | Backend API base URL |

### Optional

| Variable | Scope | Description |
|----------|-------|-------------|
| `NEXT_PUBLIC_CLARITY_PROJECT_ID` | Production | Microsoft Clarity analytics project ID |

### Environment Separation

| Environment | `NEXT_PUBLIC_API_URL` | `NEXT_PUBLIC_SUPABASE_URL` | Notes |
|-------------|----------------------|----------------------------|-------|
| Production | Production backend URL | Production Supabase project | Live users |
| Preview | Staging backend URL or production | Same Supabase project (or staging) | PR previews |
| Development | `http://localhost:8000` | Same Supabase project | Local dev |

### Security Constraints

These variables must NEVER be added to Vercel environment variables with `NEXT_PUBLIC_` prefix:

- `SUPABASE_SERVICE_ROLE_KEY` — Full database access, bypasses RLS
- `SUPABASE_JWT_SECRET` — Token signing key
- `B2_KEY_ID` / `B2_APPLICATION_KEY` — Storage credentials
- `VAST_AI_API_KEY` — GPU provider credentials
- `DATABASE_URL` — Direct database connection string
- Any webhook or signing secrets

> All `NEXT_PUBLIC_` prefixed variables are embedded in the JavaScript bundle and visible to any browser user. The Supabase anon key is safe because Row Level Security (RLS) policies enforce tenant isolation at the database level.

## Setup Steps (Vercel Dashboard)

### 1. Import Project

1. Go to [vercel.com/new](https://vercel.com/new)
2. Select **Import Git Repository**
3. Choose `garymcdaniel7/ai-studio88`
4. Set **Root Directory** to `frontend/`
5. Framework will auto-detect as **Next.js**

### 2. Configure Environment Variables

In **Settings → Environment Variables**, add:

```
NEXT_PUBLIC_SUPABASE_URL = https://vipmjgglascthwoqqqji.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY = <anon key from Supabase dashboard>
NEXT_PUBLIC_API_URL = <production backend URL>
```

Set scope to: Production + Preview + Development (or separate per environment).

### 3. Deploy

Click **Deploy**. Vercel will:
1. Clone the repo
2. Enter `frontend/` directory
3. Run `npm install`
4. Run `next build` (env vars are injected at build time)
5. Deploy the `.next` output

### 4. Verify

After deployment:
- Visit the production URL → should render the app
- Visit `/login` → should show the login form
- Open browser DevTools → Network tab → verify Supabase URL is correct
- Open DevTools → Console → no "NEXT_PUBLIC_SUPABASE_URL not set" warning

## Build Verification Checklist

```bash
# Local build test (from frontend/ directory):
cd frontend
npm run build

# Expected output includes:
# ✓ Compiled successfully
# Route (app)         Size
# /login              ...
# /                   ...
```

## Troubleshooting

### Build fails with "missing Supabase configuration"

The Supabase client (`src/lib/supabase.ts`) logs a warning if vars are missing but does not hard-fail the build. If auth doesn't work at runtime, check:

1. Vars are set in Vercel dashboard (not just locally)
2. Vars have correct scope (Production/Preview/Development)
3. A redeployment was triggered AFTER adding the vars

### Preview deployments use wrong API URL

Each preview deployment bakes in the env vars at build time. If preview should point to a staging backend, set a Preview-scoped `NEXT_PUBLIC_API_URL` override.

### "Invalid API key" at runtime

The anon key must match the Supabase project referenced by `NEXT_PUBLIC_SUPABASE_URL`. Keys are project-specific. Verify in Supabase Dashboard → Settings → API.

## Monorepo Notes

This repository has both `backend/` and `frontend/` at the root. Vercel only builds and deploys the frontend. The backend is deployed separately (e.g., Railway, Render, or self-hosted).

The `frontend/vercel.json` file specifies:
```json
{
  "framework": "nextjs"
}
```

This confirms framework detection. No rewrites or redirects are needed since the frontend calls the backend via `NEXT_PUBLIC_API_URL`.
