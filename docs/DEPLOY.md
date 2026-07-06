# Deployment Guide

Deploy AI Studio so anyone can access it from a URL.

## Architecture

```
Vercel (Frontend)  →  Railway (Backend)  →  Supabase (DB)
     ↓                     ↓                     ↓
  Next.js 16         FastAPI + Python      PostgreSQL
  Static/SSR         API + Business Logic   Data persistence
                           ↓
                    Vast.ai (GPU Worker)
                    ComfyUI + Models
```

## Step 1: Deploy Backend to Railway

1. Go to [railway.app](https://railway.app) and sign up (GitHub login works)
2. Click "New Project" → "Deploy from GitHub Repo"
3. Select `garymcdaniel7/ai-studio88`
4. Railway auto-detects Python. Set these:
   - **Root directory**: `/` (leave default)
   - **Start command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Go to **Variables** tab, add ALL your `.env` variables:
   ```
   SUPABASE_URL=https://vipmjgglascthwoqqqji.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=your_key
   B2_KEY_ID=your_key
   B2_APPLICATION_KEY=your_key
   VAST_API_KEY=your_key
   ELEVENLABS_API_KEY=your_key
   ELEVENLABS_LIVE=true
   VOICE_PROVIDER=elevenlabs
   OLLAMA_BASE_URL=http://localhost:11434
   ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:3000
   ```
6. Deploy. Note the URL (e.g., `https://ai-studio88-production.up.railway.app`)

## Step 2: Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) and sign up (GitHub login)
2. Click "Import Project" → select `garymcdaniel7/ai-studio88`
3. Set:
   - **Framework**: Next.js
   - **Root Directory**: `frontend`
4. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://ai-studio88-production.up.railway.app
   ```
   (Use the Railway URL from Step 1)
5. Deploy. You get a URL like `https://ai-studio88.vercel.app`

## Step 3: Update CORS

Go back to Railway → Variables → update:
```
ALLOWED_ORIGINS=https://ai-studio88.vercel.app,http://localhost:3000
```

## Step 4: Share

Give your friend the Vercel URL. They can use the full app:
- Create images (routes to GPU via backend)
- Use AI Brain (Ollama on GPU worker)
- Manage models, talent, assets
- Everything persists in Supabase

## Notes

- **GPU Worker**: Still needs to be launched from Admin → Fleet. The backend SSH's to Vast.ai.
- **Ollama**: Won't work remotely unless you set up Ollama on the Railway instance or keep using the GPU worker tunnel.
- **Cost**: Vercel free tier handles frontend. Railway free tier ($5 credit/mo) handles backend. Supabase free tier handles DB.
- **Custom domain**: Both Vercel and Railway support custom domains (e.g., `app.yourbrand.com`).

## Local Development (unchanged)

```bash
# Backend
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm run dev
```

The frontend reads `NEXT_PUBLIC_API_URL` from `.env.local` (defaults to localhost:8000 for dev).
