# AI Studio — Service Activation Checklist

Last verified: July 5, 2026

## Quick Start (Development)

```bash
# 1. Start backend
cd /Users/garymcdaniel/kiro/ai-studio88
uv run uvicorn backend.main:app --reload

# 2. Start frontend
cd frontend && npm run dev

# 3. (Optional) Start Celery worker for background jobs
uv run celery -A backend.app.workers.celery_app worker --loglevel=info

# 4. (Optional) Start Ollama for AI Brain
ollama serve
```

---

## Service Status

| Service | Status | How to Activate |
|---------|--------|-----------------|
| **ComfyUI (Image Gen)** | ✅ LIVE | SSH tunnel to Vast.ai worker. Auto-starts on worker launch. |
| **Supabase (Database)** | ✅ LIVE | Always connected via SUPABASE_URL + SERVICE_ROLE_KEY |
| **Backblaze B2 (Storage)** | ✅ LIVE | Connected. Models + assets upload/download working. |
| **Vast.ai (GPU)** | ✅ LIVE | $18.65 balance. 2 RTX 3090 instances running. |
| **RunPod (GPU alt)** | ⚠️ Key invalid | Update RUNPOD_API_KEY in .env with valid key |
| **Redis (Job Queue)** | ✅ LIVE | Running on localhost:6379 |
| **Celery (Workers)** | ✅ READY | Start with: `uv run celery -A backend.app.workers.celery_app worker` |
| **Ollama (AI Brain)** | ✅ LOCAL | Run `ollama serve` for Brain chat |
| **ElevenLabs (Voice)** | ⚠️ Free tier | Key works but requires paid plan for API voice generation |
| **SimpleTuner (Training)** | ✅ READY | Set SIMPLETUNER_LIVE=true + TRAINING_PROVIDER=simpletuner |
| **Auth (JWT)** | ✅ READY | Set AUTH_REQUIRED=true for production |
| **KLING (Video)** | 🔧 Needs key | Add KLING_API_KEY in .env |
| **Publishing (Social)** | 🔧 Needs keys | Add Instagram/TikTok/YouTube tokens in .env |

---

## Activation Steps (Development → Production)

### Step 1: GPU Worker (Already Done ✅)
```bash
# Worker is running. Verify:
curl http://localhost:8188/system_stats

# If tunnel is down, restart:
ssh -N -L 8188:127.0.0.1:8188 -p 31482 root@ssh9.vast.ai -i ~/.ssh/id_ed25519
```

### Step 2: Generate Real Images (Already Done ✅)
```bash
curl -X POST http://localhost:8000/api/v1/generate/image \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a cat on a windowsill","model":"sdxl-turbo"}'
```

### Step 3: Enable Auth (When Ready for Users)
```env
# In .env:
AUTH_REQUIRED=true
```
- Frontend already sends Supabase JWT tokens
- All endpoints will require valid Bearer token
- Health endpoints remain public

### Step 4: Enable Live Training (When Ready)
```env
# In .env:
SIMPLETUNER_LIVE=true
TRAINING_PROVIDER=simpletuner
```
- Requires active GPU worker with 24GB+ VRAM (RTX 3090 ✓)
- SimpleTuner auto-installs on first training job
- On RunPod with persistent volume: installs once, persists

### Step 5: Start Background Workers
```bash
# Terminal 1: Celery worker
uv run celery -A backend.app.workers.celery_app worker --loglevel=info

# Terminal 2: (Optional) Celery beat for scheduled tasks
uv run celery -A backend.app.workers.celery_app beat --loglevel=info
```

### Step 6: Upgrade ElevenLabs
- Current: Free tier (can't use library voices via API)
- Needed: Starter plan ($5/mo) or higher
- URL: https://elevenlabs.io/pricing

### Step 7: Add Social Publishing Keys
```env
# Instagram (requires Meta Business account)
INSTAGRAM_ACCESS_TOKEN=your_token
INSTAGRAM_BUSINESS_ACCOUNT_ID=your_id

# TikTok (requires approved developer app)
TIKTOK_ACCESS_TOKEN=your_token
TIKTOK_CLIENT_KEY=your_key

# YouTube (requires Google Cloud project)
YOUTUBE_REFRESH_TOKEN=your_token
YOUTUBE_OAUTH_CLIENT_ID=your_id
YOUTUBE_OAUTH_CLIENT_SECRET=your_secret

# Enable publishing
PUBLISHING_ENABLED=true
```

### Step 8: Add KLING API Key (Optional — for cloud video gen)
```env
KLING_API_KEY=your_kling_key
```
- Get from: https://klingai.com → Developer → API Keys
- Enables text-to-video and image-to-video via KLING 3.0

---

## Verification Script

Run: `uv run python scripts/verify_services.py`

---

## Architecture Notes

### How Image Generation Works (Real Mode)
```
Browser → POST /api/v1/generate/image
       → Backend loads SDXL Turbo workflow template
       → Injects prompt + params into __PLACEHOLDER__ fields
       → Submits to ComfyUI at localhost:8188 (via SSH tunnel)
       → ComfyUI renders on RTX 3090 (4.1s for SDXL Turbo)
       → Backend downloads output PNG
       → Returns base64 to browser
```

### How Training Works (Live Mode)
```
Browser → POST /api/v1/training/jobs
       → Backend starts background thread
       → SSH to GPU worker
       → Check if SimpleTuner installed (persistent volume)
       → Upload training images
       → Run SimpleTuner training script
       → Download output .safetensors
       → Upload to B2
       → Register in model registry
       → Update job status → completed
```

### Cost Awareness
- Vast.ai RTX 3090: ~$0.15/hr ($3.60/day if running 24/7)
- SDXL Turbo generation: ~$0.0002 per image (4s GPU time)
- FLUX Dev generation: ~$0.001 per image (20s GPU time)
- LoRA training (1000 steps): ~$0.25-0.50
- Always stop instances when not in use: POST /api/v1/infrastructure/stop
