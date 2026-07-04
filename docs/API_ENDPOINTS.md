# AI Studio API Endpoint Reference

Complete documentation of every API endpoint in AI Studio. Organized by router module with connection info and status.

**Base URL:** `http://localhost:8000` (dev) or your deployed domain.

**Interactive Docs:** `/docs` (Swagger UI) | `/redoc` (ReDoc)

---

## Status Key

| Symbol | Meaning |
|--------|---------|
| ✅ | Working — endpoint is functional with configured services |
| ⚠️ | Simulated — returns realistic fake data, no external service needed |
| 🔲 | Needs setup — requires external service configuration |

---

## 1. Root Endpoints

Health check and legacy Supabase-direct endpoints. These work immediately with just `SUPABASE_URL` + `SUPABASE_KEY`.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/` | GET | Liveness probe — returns `{"status": "ok"}` | Nothing | ✅ |
| `/projects` | GET | List all projects | Supabase | ✅ |
| `/talent` | GET | List all AI talent | Supabase | ✅ |
| `/talent` | POST | Create a new AI talent record | Supabase | ✅ |

**Example:**
```bash
curl http://localhost:8000/
# {"status": "ok"}

curl http://localhost:8000/talent
# [{"id": "...", "name": "Melissa", "persona": "luxury travel influencer", ...}]
```

---

## 2. Core V1 API (`/api/v1/`)

The main versioned API. Covers assets, jobs, workflows, creative DNA, feedback, generation, models, workers, story engine, and production.

### 2.1 Health & Projects

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/health` | GET | V1 API liveness check | Nothing | ✅ |
| `/api/v1/projects` | GET | List all projects | Supabase | ✅ |
| `/api/v1/talent` | GET | List all AI talent | Supabase | ✅ |
| `/api/v1/talent` | POST | Create talent | Supabase | ✅ |

### 2.2 Assets

Upload files to Backblaze B2, metadata stored in Supabase.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/assets` | GET | List all assets | Supabase | ✅ |
| `/api/v1/assets/{id}` | GET | Get single asset | Supabase | ✅ |
| `/api/v1/assets` | POST | Upload file (multipart) → B2 + Supabase | B2, Supabase | ✅ |
| `/api/v1/assets/{id}` | DELETE | Delete from B2 + Supabase | B2, Supabase | ✅ |

**Example — Upload:**
```bash
curl -X POST http://localhost:8000/api/v1/assets \
  -F "file=@photo.png" \
  -F "talent_id=abc123" \
  -F "asset_type=portrait" \
  -F "tags=headshot,flux"
# {"id": "...", "public_url": "https://f005.backblazeb2.com/...", ...}
```

### 2.3 Jobs

Queue-based job system for all async work (generation, training, etc.).

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/jobs` | GET | List jobs (filter by status/type) | Supabase | ✅ |
| `/api/v1/jobs/{id}` | GET | Get job details | Supabase | ✅ |
| `/api/v1/jobs` | POST | Create & queue a job | Supabase | ✅ |
| `/api/v1/jobs/{id}` | DELETE | Delete a job (not running) | Supabase | ✅ |
| `/api/v1/jobs/{id}/cancel` | POST | Cancel a queued/running job | Supabase | ✅ |
| `/api/v1/jobs/{id}/retry` | POST | Retry a failed/cancelled job | Supabase | ✅ |

**Valid job types:** `image_generation`, `video_generation`, `lora_training`, `image_upscale`, `image_edit`, `voice_generation`, `workflow_execution`, `asset_processing`, `publishing`

### 2.4 Workflows

Multi-step automation pipelines with dependency ordering.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/workflows` | GET | List workflows | Supabase | ✅ |
| `/api/v1/workflows/{id}` | GET | Get workflow with steps | Supabase | ✅ |
| `/api/v1/workflows` | POST | Create workflow | Supabase | ✅ |
| `/api/v1/workflows/{id}` | PUT | Update workflow | Supabase | ✅ |
| `/api/v1/workflows/{id}` | DELETE | Delete workflow | Supabase | ✅ |
| `/api/v1/workflows/{id}/run` | POST | Execute workflow (spawns jobs) | Supabase | ⚠️ |

### 2.5 Creative DNA

Style preferences and creative rules per talent. The system learns what works.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/creative-dna` | GET | List all creative DNA records | Supabase | ✅ |
| `/api/v1/creative-dna/{talent_id}` | GET | Get DNA for a talent | Supabase | ✅ |
| `/api/v1/creative-dna` | POST | Create creative DNA | Supabase | ✅ |
| `/api/v1/creative-dna/{id}` | PUT | Update creative DNA | Supabase | ✅ |
| `/api/v1/creative-dna/talent/{talent_id}` | GET | Talent-scoped DNA (alt route) | Supabase | ✅ |
| `/api/v1/continuity` | GET | List continuity notes | Supabase | ✅ |
| `/api/v1/continuity` | POST | Create continuity note | Supabase | ✅ |
| `/api/v1/continuity/{id}` | PUT | Update continuity note | Supabase | ✅ |
| `/api/v1/continuity/{id}` | DELETE | Delete continuity note | Supabase | ✅ |
| `/api/v1/rules` | GET | List creative rules | Supabase | ✅ |
| `/api/v1/rules` | POST | Create rule (include/avoid) | Supabase | ✅ |
| `/api/v1/rules/{id}` | DELETE | Delete rule | Supabase | ✅ |
| `/api/v1/preferences` | GET | List style preferences | Supabase | ✅ |
| `/api/v1/preferences` | POST | Save/upsert preference | Supabase | ✅ |
| `/api/v1/prompt-history` | GET | Prompt history for learning | Supabase | ✅ |

### 2.6 Feedback

Rate generation outputs to improve future results.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/feedback` | GET | List feedback | Supabase | ✅ |
| `/api/v1/feedback` | POST | Submit rating (1-5) + problem tags | Supabase | ✅ |
| `/api/v1/feedback/talent/{talent_id}` | GET | Feedback for a talent | Supabase | ✅ |

### 2.7 Generation Engine

The heart of content creation. Generates images/video, uploads to B2, registers as assets.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/generation/health` | GET | Provider health + GPU status | ComfyUI (optional) | ⚠️ |
| `/api/v1/generation/providers` | GET | List generation providers | In-memory registry | ⚠️ |
| `/api/v1/generation/models` | GET | List registered models | In-memory registry | ⚠️ |
| `/api/v1/generation/available-models` | GET | Models with workflow templates | In-memory | ⚠️ |
| `/api/v1/generation/run` | POST | **Generate content** (image/video) | ComfyUI, B2, Supabase | ⚠️ |
| `/api/v1/generation/history` | GET | Past generation outputs | Supabase | ✅ |
| `/api/v1/generation/{job_id}/status` | GET | Live progress for a generation | Supabase | ✅ |
| `/api/v1/generation/{job_id}/cancel` | POST | Cancel running generation | ComfyUI | ⚠️ |
| `/api/v1/generation/{job_id}/retry` | POST | Retry failed generation | ComfyUI, B2, Supabase | ⚠️ |
| `/api/v1/generation/validate` | POST | Validate request before running | In-memory | ⚠️ |
| `/api/v1/providers/health` | GET | Health of all providers + Vast.ai | Vast.ai, ComfyUI | 🔲 |
| `/api/v1/provider-capabilities` | GET | Provider capabilities + models | In-memory | ⚠️ |

> **To make generation real:** Set `COMFYUI_BASE_URL` to a running ComfyUI instance (local or via Vast.ai worker). The simulation provider works without it.

**Example — Generate Image:**
```bash
curl -X POST http://localhost:8000/api/v1/generation/run \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Melissa in luxury Dubai hotel lobby, golden hour lighting",
    "model": "flux-dev",
    "width": 1024,
    "height": 1024,
    "steps": 20
  }'
# {"status": "completed", "job_id": "...", "asset": {"id": "...", "public_url": "..."}}
```

### 2.8 Models & Workflow Templates

Registry of AI models and ComfyUI workflow templates.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/models` | GET | List models (checkpoints, LoRAs, etc.) | Supabase | ✅ |
| `/api/v1/models` | POST | Register a model | Supabase | ✅ |
| `/api/v1/models/{id}` | GET | Get model by ID | Supabase | ✅ |
| `/api/v1/models/{id}` | PUT | Update model | Supabase | ✅ |
| `/api/v1/models/{id}` | DELETE | Delete model | Supabase | ✅ |
| `/api/v1/workflow-templates` | GET | List workflow templates | Supabase | ✅ |
| `/api/v1/workflow-templates` | POST | Create template | Supabase | ✅ |
| `/api/v1/workflow-templates/{id}` | GET | Get template | Supabase | ✅ |
| `/api/v1/workflow-templates/{id}` | PUT | Update template | Supabase | ✅ |
| `/api/v1/workflow-templates/{id}` | DELETE | Delete template | Supabase | ✅ |

### 2.9 Workers (Persistent, DB-backed)

GPU worker registry. Workers register themselves and send heartbeats.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/workers` | GET | List registered workers | Supabase | ✅ |
| `/api/v1/workers` | POST | Register a GPU worker | Supabase | ✅ |
| `/api/v1/workers/available` | GET | Workers ready for jobs | Supabase | ✅ |
| `/api/v1/workers/health` | GET | Aggregate worker health | Supabase | ✅ |
| `/api/v1/workers/{id}` | GET | Get worker | Supabase | ✅ |
| `/api/v1/workers/{id}` | PUT | Update worker | Supabase | ✅ |
| `/api/v1/workers/{id}` | DELETE | Remove worker | Supabase | ✅ |
| `/api/v1/workers/{id}/heartbeat` | POST | Worker heartbeat | Supabase | ✅ |
| `/api/v1/workers/{id}/online` | POST | Mark worker online | Supabase | ✅ |
| `/api/v1/workers/{id}/offline` | POST | Mark worker offline | Supabase | ✅ |

### 2.10 Execution Platform

In-memory worker registry + job routing (complementary to persistent workers).

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/execution/health` | GET | Execution platform health | In-memory | ⚠️ |
| `/api/v1/execution/workers` | GET | List in-memory workers | In-memory | ⚠️ |
| `/api/v1/execution/workers/register` | POST | Register worker (in-memory) | In-memory | ⚠️ |
| `/api/v1/execution/workers/{id}/heartbeat` | POST | Worker heartbeat | In-memory | ⚠️ |
| `/api/v1/execution/workers/{id}` | DELETE | Unregister worker | In-memory | ⚠️ |
| `/api/v1/execution/providers` | GET | List execution providers | In-memory | ⚠️ |
| `/api/v1/execution/route` | POST | Route job to best worker | In-memory | ⚠️ |

### 2.11 Intelligence Engine

AI planning system — 10 specialized agents analyze context and produce optimized creative plans.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/intelligence/plan` | POST | Build full creative plan from idea | Supabase, In-memory agents | ⚠️ |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/intelligence/plan \
  -H "Content-Type: application/json" \
  -d '{"user_idea": "Melissa at Dubai Marina sunset", "talent_id": "abc123", "platform": "instagram"}'
# {"session_id": "...", "prompt": "...", "model": "flux-dev", "confidence": 0.92, ...}
```

### 2.12 Story Engine

Narrative content management — universes, characters, episodes, scenes, shots, and story memory.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/universes` | GET | List story universes | Supabase | ✅ |
| `/api/v1/universes` | POST | Create universe | Supabase | ✅ |
| `/api/v1/universes/{id}` | GET | Get universe | Supabase | ✅ |
| `/api/v1/universes/{id}` | PUT | Update universe | Supabase | ✅ |
| `/api/v1/universes/{id}` | DELETE | Delete universe | Supabase | ✅ |
| `/api/v1/universes/{id}/characters` | GET | List characters | Supabase | ✅ |
| `/api/v1/characters` | POST | Create character | Supabase | ✅ |
| `/api/v1/characters/{id}` | GET | Get character | Supabase | ✅ |
| `/api/v1/characters/{id}` | PUT | Update character | Supabase | ✅ |
| `/api/v1/universes/{id}/episodes` | GET | List episodes | Supabase | ✅ |
| `/api/v1/episodes` | POST | Create episode | Supabase | ✅ |
| `/api/v1/episodes/{id}` | GET | Get episode | Supabase | ✅ |
| `/api/v1/episodes/{id}` | PUT | Update episode | Supabase | ✅ |
| `/api/v1/episodes/{id}/scenes` | GET | List scenes | Supabase | ✅ |
| `/api/v1/scenes` | POST | Create scene | Supabase | ✅ |
| `/api/v1/scenes/{id}` | PUT | Update scene | Supabase | ✅ |
| `/api/v1/scenes/{id}/shots` | GET | List shots | Supabase | ✅ |
| `/api/v1/scenes/{id}/plan-shots` | POST | Auto-plan shots (AI) | Supabase | ⚠️ |
| `/api/v1/scenes/{id}/check-continuity` | POST | Continuity warnings | Supabase | ⚠️ |
| `/api/v1/shots/{id}/generate` | POST | Generate shot content | ComfyUI, B2, Supabase | ⚠️ |
| `/api/v1/universes/{id}/memory` | GET | List story memory | Supabase | ✅ |
| `/api/v1/memory` | POST | Record story event | Supabase | ✅ |

### 2.13 Production Studio

Media pipeline planning, voice/music libraries, camera system, timeline building.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/production/types` | GET | List production types | In-memory | ⚠️ |
| `/api/v1/production/pipelines` | GET | List pipeline types | In-memory | ⚠️ |
| `/api/v1/production/templates` | GET | Pipeline templates | In-memory | ⚠️ |
| `/api/v1/production/plan` | POST | Build production graph | In-memory | ⚠️ |
| `/api/v1/production/timeline` | POST | Build timeline from shots | In-memory | ⚠️ |
| `/api/v1/production/camera/moves` | GET | Camera movement types | In-memory | ⚠️ |
| `/api/v1/production/camera/sizes` | GET | Shot size types | In-memory | ⚠️ |
| `/api/v1/production/editing/operations` | GET | Editing operations | In-memory | ⚠️ |
| `/api/v1/production/voices` | GET | Voice library | In-memory | ⚠️ |
| `/api/v1/production/voices` | POST | Add voice profile | In-memory | ⚠️ |
| `/api/v1/production/music` | GET | Music library | In-memory | ⚠️ |
| `/api/v1/production/music/recommend` | GET | Music recommendation | In-memory | ⚠️ |

---

## 3. AI Brain (`/api/v1/brain/`)

The conversational AI interface. Talk to the Brain in natural language and get production plans. Uses Ollama (local) or OpenAI/Anthropic.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/brain/chat` | POST | Talk to the AI Brain | Ollama/OpenAI/Anthropic | ⚠️ |
| `/api/v1/brain/plan` | POST | Create production plan (no chat) | In-memory planner | ⚠️ |
| `/api/v1/brain/sessions` | GET | List brain sessions | In-memory | ⚠️ |
| `/api/v1/brain/sessions/{id}` | GET | Get session with history | In-memory | ⚠️ |
| `/api/v1/brain/context` | GET | Brain's current context | In-memory | ⚠️ |
| `/api/v1/brain/memory` | GET | Production memory (preferences) | In-memory | ⚠️ |
| `/api/v1/brain/memory` | PUT | Update production memory | In-memory | ⚠️ |
| `/api/v1/brain/modules` | GET | List registered modules | In-memory | ⚠️ |
| `/api/v1/brain/reasoning/{plan_id}` | GET | Why these steps were chosen | In-memory | ⚠️ |
| `/api/v1/brain/health` | GET | LLM provider health | Ollama/OpenAI | 🔲 |
| `/api/v1/brain/llm/chat` | POST | Direct LLM chat (bypass planner) | Ollama/OpenAI/Anthropic | 🔲 |

> **To make Brain real:** Set `OLLAMA_BASE_URL` for local Ollama, or `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`. The planner works without LLM (rule-based). Direct `/llm/chat` requires a provider.

**Example — Brain Chat:**
```bash
curl -X POST http://localhost:8000/api/v1/brain/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a luxury travel reel with Melissa in Dubai"}'
# {"session_id": "...", "response": "I'll handle this with 4 steps...", "plan": {...}}
```

**LLM Modes:** `creative`, `prompt_engineer`, `story_assistant`, `production_advisor`, `research`, `image_analyzer`

---

## 4. Video Pipeline (`/api/v1/`)

Video project management, shot planning, generation (WAN 2.1), timeline editing, and export.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/video/providers` | GET | List video gen providers | In-memory | ⚠️ |
| `/api/v1/video/providers/{name}` | GET | Provider detail | In-memory | ⚠️ |
| `/api/v1/videos` | GET | List video projects | Supabase | ✅ |
| `/api/v1/videos` | POST | Create video project | Supabase | ✅ |
| `/api/v1/videos/{id}` | GET | Get video project | Supabase | ✅ |
| `/api/v1/videos/{id}` | PUT | Update video project | Supabase | ✅ |
| `/api/v1/videos/{id}` | DELETE | Delete video project | Supabase | ✅ |
| `/api/v1/videos/{id}/shots` | GET | List shots | Supabase | ✅ |
| `/api/v1/videos/{id}/shots` | POST | Create shot | Supabase | ✅ |
| `/api/v1/videos/{id}/generate` | POST | Generate all planned shots | ComfyUI, B2, Supabase | ⚠️ |
| `/api/v1/video/image-to-video` | POST | Image→Video (WAN 2.1 I2V) | ComfyUI, B2 | 🔲 |
| `/api/v1/videos/{id}/timeline` | GET | Get timeline | Supabase | ✅ |
| `/api/v1/videos/{id}/timeline/tracks` | POST | Create track | Supabase | ✅ |
| `/api/v1/videos/{id}/timeline/clips` | POST | Add clip | Supabase | ✅ |
| `/api/v1/videos/{id}/render` | POST | Create render job | Supabase | ⚠️ |
| `/api/v1/videos/{id}/export` | POST | Export timeline | Supabase | ⚠️ |
| `/api/v1/video-renders` | GET | List renders | Supabase | ✅ |
| `/api/v1/video-renders/{id}` | GET | Get render | Supabase | ✅ |

> **To make video generation real:** Need `COMFYUI_BASE_URL` pointing to a GPU worker with WAN 2.1 models loaded.

---

## 5. LoRA Training (`/api/v1/training/`)

Dataset management, captioning, training execution, and LoRA version management.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/training/providers` | GET | List training providers | In-memory | ⚠️ |
| `/api/v1/training/datasets` | GET | List datasets | Supabase | ✅ |
| `/api/v1/training/datasets` | POST | Create dataset | Supabase | ✅ |
| `/api/v1/training/datasets/{id}` | GET | Get dataset | Supabase | ✅ |
| `/api/v1/training/datasets/{id}` | PUT | Update dataset | Supabase | ✅ |
| `/api/v1/training/datasets/{id}` | DELETE | Delete dataset | Supabase | ✅ |
| `/api/v1/training/datasets/{id}/images` | GET | List dataset images | Supabase | ✅ |
| `/api/v1/training/datasets/{id}/images` | POST | Add image to dataset | Supabase | ✅ |
| `/api/v1/training/datasets/{id}/caption` | POST | Auto-caption all images | Supabase | ⚠️ |
| `/api/v1/training/images/{id}/caption` | PUT | Edit image caption | Supabase | ✅ |
| `/api/v1/training/jobs` | GET | List training jobs | Supabase | ✅ |
| `/api/v1/training/jobs/{id}` | GET | Get training job | Supabase | ✅ |
| `/api/v1/training/jobs` | POST | **Start LoRA training** | Vast.ai, B2, Supabase | ⚠️ |
| `/api/v1/training/jobs/{id}/cancel` | POST | Cancel training | Supabase | ✅ |
| `/api/v1/loras` | GET | List LoRA versions | Supabase | ✅ |
| `/api/v1/loras/{id}` | GET | Get LoRA | Supabase | ✅ |
| `/api/v1/loras/{id}/evaluate` | POST | Submit LoRA evaluation | Supabase | ✅ |
| `/api/v1/loras/{id}/promote` | POST | Set as talent's default LoRA | Supabase | ✅ |

> **To make training real:** Set `VAST_API_KEY` for GPU rental. The simulation provider trains instantly and produces a fake .safetensors that goes to B2.

**Example — Start Training:**
```bash
curl -X POST http://localhost:8000/api/v1/training/jobs \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "ds_abc", "config": {"steps": 1500, "rank": 32}}'
# {"status": "completed", "training_job_id": "...", "asset_id": "...", "model_id": "..."}
```

---

## 6. Publishing Engine (`/api/v1/publishing/`)

Social media publishing, scheduling, approval workflows, analytics, and platform packaging.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/publishing/posts` | GET | List posts | Supabase | ✅ |
| `/api/v1/publishing/posts` | POST | Create a post (draft) | Supabase | ✅ |
| `/api/v1/publishing/posts/{id}` | GET | Get post | Supabase | ✅ |
| `/api/v1/publishing/posts/{id}/approve` | POST | Approve post | Supabase | ✅ |
| `/api/v1/publishing/posts/{id}/reject` | POST | Reject post | Supabase | ✅ |
| `/api/v1/publishing/posts/{id}/schedule` | POST | Schedule post | Supabase | ✅ |
| `/api/v1/publishing/posts/{id}/publish` | POST | Publish to platform | Supabase (simulated social) | ⚠️ |
| `/api/v1/publishing/analytics` | GET | List analytics snapshots | Supabase | ✅ |
| `/api/v1/publishing/analytics/simulate` | POST | Simulate fetching analytics | Supabase | ⚠️ |
| `/api/v1/publishing/analytics/summary` | GET | Aggregate analytics | Supabase | ✅ |
| `/api/v1/publishing/platforms` | GET | Platform requirements | In-memory | ⚠️ |
| `/api/v1/publishing/package` | POST | Create platform package | Supabase | ✅ |
| `/api/v1/publishing/repurpose/formats` | GET | Repurposing formats | In-memory | ⚠️ |
| `/api/v1/publishing/repurpose` | POST | Generate repurpose plan | In-memory | ⚠️ |
| `/api/v1/publishing/calendar` | GET | Publishing calendar | Supabase | ✅ |
| `/api/v1/publishing/providers/health` | GET | Provider health | In-memory (simulated) | ⚠️ |

> **To make publishing real:** Integrate real social APIs (Instagram Graph API, TikTok API, etc.). Currently uses a simulated provider that returns realistic fake responses.

---

## 7. Infrastructure (`/api/v1/infrastructure/`)

GPU worker orchestration, Connection Race Mode (Vast.ai), fleet management, cost tracking, reputation, and diagnostics.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/infrastructure/launch` | POST | Launch GPU worker (race mode) | Vast.ai | 🔲 |
| `/api/v1/infrastructure/status` | GET | Full infrastructure dashboard | In-memory | ⚠️ |
| `/api/v1/infrastructure/dashboard` | GET | Alias for /status | In-memory | ⚠️ |
| `/api/v1/infrastructure/stop` | POST | Destroy current worker | Vast.ai | 🔲 |
| `/api/v1/infrastructure/history` | GET | Connection attempt history | In-memory | ⚠️ |
| `/api/v1/infrastructure/cost` | GET | Current spend summary | In-memory | ⚠️ |
| `/api/v1/infrastructure/cost/history` | GET | Daily cost history | In-memory | ⚠️ |
| `/api/v1/infrastructure/reputation` | GET | Provider reputation scores | In-memory | ⚠️ |
| `/api/v1/infrastructure/blacklist` | GET | Blacklisted hosts | In-memory | ⚠️ |
| `/api/v1/infrastructure/blacklist` | POST | Blacklist a host | In-memory | ⚠️ |
| `/api/v1/infrastructure/fleet` | GET | Render fleet status | In-memory | ⚠️ |
| `/api/v1/infrastructure/fleet/add` | POST | Add worker to fleet | Vast.ai | 🔲 |
| `/api/v1/infrastructure/fleet/{id}` | DELETE | Remove fleet worker | Vast.ai | 🔲 |
| `/api/v1/infrastructure/fleet/stop-all` | POST | Emergency fleet shutdown | Vast.ai | 🔲 |
| `/api/v1/infrastructure/fleet/jobs` | POST | Submit job to fleet | In-memory queue | ⚠️ |
| `/api/v1/infrastructure/diagnose` | POST | Self-healing error diagnosis | In-memory | ⚠️ |
| `/api/v1/infrastructure/known-issues` | GET | Known error patterns | In-memory | ⚠️ |
| `/api/v1/infrastructure/admin/services` | GET | All service connection status | Vast.ai, B2, Supabase, ComfyUI | 🔲 |

> **To make infrastructure real:** Set `VAST_API_KEY` (or `VASTAI_API_KEY`). Launch creates real GPU instances on Vast.ai, races them, first to SSH wins.

**Example — Launch Worker:**
```bash
curl -X POST http://localhost:8000/api/v1/infrastructure/launch \
  -H "Content-Type: application/json" \
  -d '{"max_price": 1.50, "min_vram_gb": 24, "num_candidates": 3, "gpu_filter": "RTX 4090"}'
# {"status": "active", "worker_id": "...", "ssh_host": "...", "boot_time_seconds": 45}
```

---

## 8. Direct Generation (`/api/v1/generate/`)

The fast-path generation endpoint. Builds a ComfyUI workflow, submits it, polls for results. Used by the frontend Create page.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/generate/image` | POST | Generate image via ComfyUI | ComfyUI (direct) | 🔲 |

> **Requires:** `COMFYUI_BASE_URL` pointing to a running ComfyUI instance. Returns base64 image or error.

**Supported models:** `flux-dev`, `sdxl-turbo`, `sd15`

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/generate/image \
  -H "Content-Type: application/json" \
  -d '{"prompt": "beautiful sunset over ocean", "model": "sdxl-turbo", "steps": 1}'
# {"success": true, "image_base64": "iVBOR...", "generation_time": 2.3, "seed": 42}
```

---

## 9. Object Intelligence (`/api/v1/object-intelligence/`)

Physical object understanding — Object DNA, Product DNA, Digital Twins, Virtual Try-On, 360° renders, Scene Composer, Material Intelligence.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/object-intelligence/object-dna` | GET | List Object DNA profiles | Supabase | ✅ |
| `/api/v1/object-intelligence/object-dna` | POST | Create Object DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/object-dna/{id}` | GET | Get Object DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/object-dna/{id}` | PUT | Update Object DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/object-dna/{id}` | DELETE | Delete Object DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/product-dna` | GET | List Product DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/product-dna` | POST | Create Product DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/product-dna/{id}` | GET | Get Product DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/product-dna/{id}` | PUT | Update Product DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/product-dna/{id}` | DELETE | Delete Product DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/digital-twins` | GET | List Digital Twins | Supabase | ✅ |
| `/api/v1/object-intelligence/digital-twins` | POST | Create Digital Twin | Supabase | ✅ |
| `/api/v1/object-intelligence/digital-twins/{id}` | GET | Get Digital Twin | Supabase | ✅ |
| `/api/v1/object-intelligence/digital-twins/{id}` | PUT | Update Digital Twin | Supabase | ✅ |
| `/api/v1/object-intelligence/digital-twins/{id}/versions` | POST | Version a twin | Supabase | ✅ |
| `/api/v1/object-intelligence/virtual-try-on` | GET | List try-on jobs | Supabase | ✅ |
| `/api/v1/object-intelligence/virtual-try-on` | POST | Create try-on job | Supabase | ✅ |
| `/api/v1/object-intelligence/virtual-try-on/{id}` | GET | Get try-on job | Supabase | ✅ |
| `/api/v1/object-intelligence/virtual-try-on/{id}/complete` | POST | Mark completed | Supabase | ✅ |
| `/api/v1/object-intelligence/360-renders` | GET | List 360° renders | Supabase | ✅ |
| `/api/v1/object-intelligence/360-renders` | POST | Create 360° render | Supabase | ✅ |
| `/api/v1/object-intelligence/360-renders/{id}` | GET | Get 360° render | Supabase | ✅ |
| `/api/v1/object-intelligence/360-renders/{id}` | PUT | Update 360° render | Supabase | ✅ |
| `/api/v1/object-intelligence/scene-dna` | GET | List Scene DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/scene-dna` | POST | Create Scene DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/scene-dna/{id}` | GET | Get Scene DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/scene-dna/{id}` | PUT | Update Scene DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/scene-dna/{id}` | DELETE | Delete Scene DNA | Supabase | ✅ |
| `/api/v1/object-intelligence/scene-composer/compose` | POST | Compose scene from assets | Supabase | ✅ |
| `/api/v1/object-intelligence/materials` | GET | List material profiles | Supabase | ✅ |
| `/api/v1/object-intelligence/materials` | POST | Create material profile | Supabase | ✅ |
| `/api/v1/object-intelligence/materials/{id}` | GET | Get material | Supabase | ✅ |
| `/api/v1/object-intelligence/materials/{id}/recommendations` | GET | AI material recs | Supabase | ⚠️ |
| `/api/v1/object-intelligence/product-commercials/types` | GET | Commercial types | In-memory | ⚠️ |
| `/api/v1/object-intelligence/product-commercials/generate` | POST | Generate commercial plan | Supabase | ⚠️ |
| `/api/v1/object-intelligence/categories` | GET | Object categories | In-memory | ⚠️ |
| `/api/v1/object-intelligence/material-types` | GET | Material types | In-memory | ⚠️ |
| `/api/v1/object-intelligence/recommend/{id}` | GET | AI recommendations | Supabase | ⚠️ |

---

## 10. Asset Intelligence (`/api/v1/asset-intelligence/`)

Visual DNA, wardrobes/outfits, collections, relationships, scene templates, camera/lighting/pose presets, and smart recommendations.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/asset-intelligence/visual-dna` | GET | List Visual DNA | Supabase | ✅ |
| `/api/v1/asset-intelligence/visual-dna` | POST | Create Visual DNA | Supabase | ✅ |
| `/api/v1/asset-intelligence/visual-dna/{asset_id}` | GET | Get Visual DNA for asset | Supabase | ✅ |
| `/api/v1/asset-intelligence/visual-dna/{id}` | PUT | Update Visual DNA | Supabase | ✅ |
| `/api/v1/asset-intelligence/collections` | GET | List asset collections | Supabase | ✅ |
| `/api/v1/asset-intelligence/collections` | POST | Create collection | Supabase | ✅ |
| `/api/v1/asset-intelligence/collections/{id}/items` | GET | List items in collection | Supabase | ✅ |
| `/api/v1/asset-intelligence/collections/{id}/items` | POST | Add item to collection | Supabase | ✅ |
| `/api/v1/asset-intelligence/relationships/{asset_id}` | GET | Get asset relationships | Supabase | ✅ |
| `/api/v1/asset-intelligence/relationships` | POST | Create relationship | Supabase | ✅ |
| `/api/v1/asset-intelligence/wardrobes` | GET | List wardrobes | Supabase | ✅ |
| `/api/v1/asset-intelligence/wardrobes` | POST | Create wardrobe | Supabase | ✅ |
| `/api/v1/asset-intelligence/wardrobes/{id}/outfits` | GET | List outfits | Supabase | ✅ |
| `/api/v1/asset-intelligence/outfits` | POST | Create outfit | Supabase | ✅ |
| `/api/v1/asset-intelligence/scene-templates` | GET | List scene templates | Supabase | ✅ |
| `/api/v1/asset-intelligence/scene-templates` | POST | Create scene template | Supabase | ✅ |
| `/api/v1/asset-intelligence/scene-templates/{id}` | GET | Get template | Supabase | ✅ |
| `/api/v1/asset-intelligence/camera-presets` | GET | Camera presets | Supabase | ✅ |
| `/api/v1/asset-intelligence/camera-presets` | POST | Create camera preset | Supabase | ✅ |
| `/api/v1/asset-intelligence/lighting-presets` | GET | Lighting presets | Supabase | ✅ |
| `/api/v1/asset-intelligence/lighting-presets` | POST | Create lighting preset | Supabase | ✅ |
| `/api/v1/asset-intelligence/pose-presets` | GET | Pose presets | Supabase | ✅ |
| `/api/v1/asset-intelligence/pose-presets` | POST | Create pose preset | Supabase | ✅ |
| `/api/v1/asset-intelligence/recommend/{asset_id}` | GET | Smart recommendations | Supabase | ⚠️ |
| `/api/v1/asset-intelligence/categories` | GET | Asset categories | In-memory | ⚠️ |
| `/api/v1/asset-intelligence/search` | GET | Visual search (simulated) | In-memory | ⚠️ |

---

## 11. Audio & Voice (`/api/v1/`)

Voice profiles, TTS, dialogue, narration, lip sync, music, and sound effects.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/voice-profiles` | GET | List voice profiles | Supabase | ✅ |
| `/api/v1/voice-profiles` | POST | Create voice profile | Supabase | ✅ |
| `/api/v1/voice-profiles/{id}` | GET | Get voice profile | Supabase | ✅ |
| `/api/v1/voice-profiles/{id}` | PUT | Update voice profile | Supabase | ✅ |
| `/api/v1/voice-profiles/{id}` | DELETE | Delete voice profile | Supabase | ✅ |
| `/api/v1/voice-profiles/{id}/samples` | GET | List voice samples | Supabase | ✅ |
| `/api/v1/voice-profiles/{id}/samples` | POST | Add voice sample | Supabase | ✅ |
| `/api/v1/audio/tts` | POST | Generate text-to-speech | B2, Supabase (simulated) | ⚠️ |
| `/api/v1/audio/dialogue` | POST | Generate character dialogue | B2, Supabase (simulated) | ⚠️ |
| `/api/v1/audio/narration` | POST | Generate narration | B2, Supabase (simulated) | ⚠️ |
| `/api/v1/audio/clips` | GET | List audio clips | Supabase | ✅ |
| `/api/v1/audio/clips/{id}` | GET | Get audio clip | Supabase | ✅ |
| `/api/v1/lip-sync` | POST | Create lip sync job | B2, Supabase (simulated) | ⚠️ |
| `/api/v1/lip-sync/jobs` | GET | List lip sync jobs | Supabase | ✅ |
| `/api/v1/lip-sync/jobs/{id}` | GET | Get lip sync job | Supabase | ✅ |
| `/api/v1/music` | GET | List music tracks | Supabase | ✅ |
| `/api/v1/music` | POST | Create music track | Supabase | ✅ |
| `/api/v1/sfx` | GET | List sound effects | Supabase | ✅ |
| `/api/v1/sfx` | POST | Create sound effect | Supabase | ✅ |
| `/api/v1/audio/providers/health` | GET | Audio provider health | In-memory | ⚠️ |

> **To make audio real:** Integrate ElevenLabs (`ELEVENLABS_API_KEY`), or other TTS provider. Lip sync needs Wav2Lip/SadTalker on GPU worker.

---

## 12. Creator OS (`/api/v1/`)

Business layer — campaigns, content calendar, analytics, brands, team, notifications, search, and AI ops assistant.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/calendar` | GET | Content calendar entries | In-memory | ⚠️ |
| `/api/v1/calendar` | POST | Schedule content | In-memory | ⚠️ |
| `/api/v1/calendar/{id}` | PUT | Update calendar entry | In-memory | ⚠️ |
| `/api/v1/calendar/{id}` | DELETE | Remove calendar entry | In-memory | ⚠️ |
| `/api/v1/campaigns` | GET | List campaigns | In-memory | ⚠️ |
| `/api/v1/campaigns` | POST | Create campaign | In-memory | ⚠️ |
| `/api/v1/campaigns/{id}` | GET | Get campaign | In-memory | ⚠️ |
| `/api/v1/campaigns/{id}` | PUT | Update campaign | In-memory | ⚠️ |
| `/api/v1/analytics` | GET | Analytics data | In-memory | ⚠️ |
| `/api/v1/analytics` | POST | Record analytics snapshot | In-memory | ⚠️ |
| `/api/v1/analytics/summary` | GET | Aggregate summary | In-memory | ⚠️ |
| `/api/v1/brands` | GET | List brands | In-memory | ⚠️ |
| `/api/v1/brands` | POST | Create brand | In-memory | ⚠️ |
| `/api/v1/team` | GET | List team members | In-memory | ⚠️ |
| `/api/v1/team` | POST | Add team member | In-memory | ⚠️ |
| `/api/v1/team/roles` | GET | Available roles | In-memory | ⚠️ |
| `/api/v1/notifications` | GET | List notifications | In-memory | ⚠️ |
| `/api/v1/notifications` | POST | Create notification | In-memory | ⚠️ |
| `/api/v1/notifications/types` | GET | Notification types | In-memory | ⚠️ |
| `/api/v1/repurpose/formats` | GET | Repurposing formats | In-memory | ⚠️ |
| `/api/v1/repurpose` | POST | Create repurpose plan | In-memory | ⚠️ |
| `/api/v1/platforms` | GET | Supported social platforms | In-memory | ⚠️ |
| `/api/v1/search` | GET | Unified search | In-memory | ⚠️ |
| `/api/v1/ops/recommendations` | GET | AI ops recommendations | In-memory | ⚠️ |
| `/api/v1/hub/summary` | GET | Creator hub dashboard | In-memory | ⚠️ |

> **Note:** Creator OS stores data in-memory (resets on restart). Future: migrate to Supabase tables for persistence.

---

## 13. Autonomous Studio (`/api/v1/studio/`)

Multi-agent AI system. Departments analyze studio state and provide recommendations. You approve/reject them.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/studio/briefing` | GET | Daily briefing with AI recommendations | In-memory agents | ⚠️ |
| `/api/v1/studio/recommendations` | GET | All current recommendations | In-memory agents | ⚠️ |
| `/api/v1/studio/recommendations/{idx}/decide` | POST | Approve/reject recommendation | In-memory | ⚠️ |
| `/api/v1/studio/departments` | GET | List AI departments | In-memory | ⚠️ |
| `/api/v1/studio/departments/{name}/analyze` | GET | Run department analysis | In-memory | ⚠️ |
| `/api/v1/studio/discuss` | POST | Multi-agent discussion on topic | In-memory | ⚠️ |
| `/api/v1/studio/memory` | GET | Studio learning memory | In-memory | ⚠️ |
| `/api/v1/studio/health` | GET | Overall studio health | In-memory | ⚠️ |

---

## 14. Production Intelligence (`/api/v1/intelligence/`)

AI agents for quality scoring, self-healing, learning system, and production reports.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/intelligence/production-insights` | GET | Run all agents, get insights | In-memory | ⚠️ |
| `/api/v1/intelligence/production-insights/agents` | GET | List intelligence agents | In-memory | ⚠️ |
| `/api/v1/intelligence/quality-score` | POST | Score asset quality | In-memory | ⚠️ |
| `/api/v1/intelligence/quality-scores` | GET | Recent quality scores | In-memory | ⚠️ |
| `/api/v1/intelligence/quality-scores/summary` | GET | Quality summary | In-memory | ⚠️ |
| `/api/v1/intelligence/learning/event` | POST | Record learning event | In-memory | ⚠️ |
| `/api/v1/intelligence/learning/events` | GET | List learning events | In-memory | ⚠️ |
| `/api/v1/intelligence/learning/summary` | GET | Learning summary | In-memory | ⚠️ |
| `/api/v1/intelligence/reports/production` | GET | Production report | In-memory, Supabase | ⚠️ |
| `/api/v1/intelligence/reports/recommendations` | GET | Top recommendations | In-memory | ⚠️ |

---

## 15. Performance Engine (`/api/v1/`)

Voice training, song studio, performance memory, performance DNA, series, and soundtrack cues.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/voice-training/datasets` | GET | List voice datasets | Supabase | ✅ |
| `/api/v1/voice-training/datasets` | POST | Create voice dataset | Supabase | ✅ |
| `/api/v1/voice-training/jobs` | POST | Start voice training (simulated) | Supabase | ⚠️ |
| `/api/v1/voice-training/jobs` | GET | List voice training jobs | Supabase | ✅ |
| `/api/v1/voice-versions` | GET | List voice versions | Supabase | ✅ |
| `/api/v1/voice-dna` | GET | List Voice DNA | Supabase | ✅ |
| `/api/v1/voice-dna` | POST | Create Voice DNA | Supabase | ✅ |
| `/api/v1/voice-dna/{id}` | PUT | Update Voice DNA | Supabase | ✅ |
| `/api/v1/songs` | GET | List songs | Supabase | ✅ |
| `/api/v1/songs` | POST | Create song | Supabase | ✅ |
| `/api/v1/songs/{id}` | GET | Get song | Supabase | ✅ |
| `/api/v1/songs/{id}` | PUT | Update song | Supabase | ✅ |
| `/api/v1/songs/{id}/generate` | POST | Generate song (simulated) | B2, Supabase | ⚠️ |
| `/api/v1/performance-memory` | GET | Performance continuity memory | Supabase | ✅ |
| `/api/v1/performance-memory` | POST | Record performance state | Supabase | ✅ |
| `/api/v1/performance-memory/latest/{char_id}` | GET | Latest performance for character | Supabase | ✅ |
| `/api/v1/performance-dna` | GET | List Performance DNA | Supabase | ✅ |
| `/api/v1/performance-dna` | POST | Create Performance DNA | Supabase | ✅ |
| `/api/v1/performance-dna/{id}` | PUT | Update Performance DNA | Supabase | ✅ |
| `/api/v1/series` | GET | List series | Supabase | ✅ |
| `/api/v1/series` | POST | Create series | Supabase | ✅ |
| `/api/v1/series/{id}` | GET | Get series | Supabase | ✅ |
| `/api/v1/soundtrack-cues` | GET | List soundtrack cues | Supabase | ✅ |
| `/api/v1/soundtrack-cues` | POST | Create soundtrack cue | Supabase | ✅ |

---

## 16. Cinematic Studio (`/api/v1/cinematic/`)

Professional NLE-style timeline, storyboard, editing operations, continuity checks, render & export.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/cinematic/timelines` | GET | List timelines | Supabase | ✅ |
| `/api/v1/cinematic/timelines` | POST | Create timeline | Supabase | ✅ |
| `/api/v1/cinematic/timelines/{id}` | GET | Get timeline with tracks/items | Supabase | ✅ |
| `/api/v1/cinematic/timelines/{id}` | PUT | Update timeline | Supabase | ✅ |
| `/api/v1/cinematic/timelines/{id}/tracks` | POST | Create track | Supabase | ✅ |
| `/api/v1/cinematic/timelines/{id}/tracks` | GET | List tracks | Supabase | ✅ |
| `/api/v1/cinematic/tracks/{id}/items` | POST | Add clip to track | Supabase | ✅ |
| `/api/v1/cinematic/tracks/{id}/items` | GET | List clips in track | Supabase | ✅ |
| `/api/v1/cinematic/items/{id}` | PUT | Update clip | Supabase | ✅ |
| `/api/v1/cinematic/items/{id}` | DELETE | Delete clip | Supabase | ✅ |
| `/api/v1/cinematic/storyboard` | GET | List storyboard panels | Supabase | ✅ |
| `/api/v1/cinematic/storyboard` | POST | Create panel | Supabase | ✅ |
| `/api/v1/cinematic/editing/operations` | GET | Available edit operations | In-memory | ⚠️ |
| `/api/v1/cinematic/editing/transitions` | GET | Available transitions | In-memory | ⚠️ |
| `/api/v1/cinematic/editing/color-grades` | GET | Color grade presets | In-memory | ⚠️ |
| `/api/v1/cinematic/editing/apply` | POST | Apply edit operation | Supabase | ✅ |
| `/api/v1/cinematic/export/formats` | GET | Export format list | In-memory | ⚠️ |
| `/api/v1/cinematic/render` | POST | Create render job | Supabase | ⚠️ |
| `/api/v1/cinematic/renders` | GET | List renders | Supabase | ✅ |
| `/api/v1/cinematic/sequences` | GET | List sequences | Supabase | ✅ |
| `/api/v1/cinematic/sequences` | POST | Create sequence | Supabase | ✅ |
| `/api/v1/cinematic/continuity/check` | POST | Check continuity | In-memory logic | ⚠️ |

---

## 17. Company OS (`/api/v1/company/`)

Multi-tenant production company management — organizations, studios, brands, campaigns, team, approvals, clients, licenses.

| Endpoint | Method | What it does | Connects to | Status |
|----------|--------|-------------|-------------|--------|
| `/api/v1/company/organizations` | GET | List organizations | Supabase | ✅ |
| `/api/v1/company/organizations` | POST | Create organization | Supabase | ✅ |
| `/api/v1/company/organizations/{id}` | GET | Get organization | Supabase | ✅ |
| `/api/v1/company/studios` | GET | List studios | Supabase | ✅ |
| `/api/v1/company/studios` | POST | Create studio | Supabase | ✅ |
| `/api/v1/company/brands` | GET | List brands | Supabase | ✅ |
| `/api/v1/company/brands` | POST | Create brand | Supabase | ✅ |
| `/api/v1/company/brands/{id}` | GET | Get brand | Supabase | ✅ |
| `/api/v1/company/brands/{id}` | PUT | Update brand | Supabase | ✅ |
| `/api/v1/company/brands/{id}` | DELETE | Delete brand | Supabase | ✅ |
| `/api/v1/company/campaigns` | GET | List brand campaigns | Supabase | ✅ |
| `/api/v1/company/campaigns` | POST | Create campaign | Supabase | ✅ |
| `/api/v1/company/campaigns/{id}` | GET | Get campaign | Supabase | ✅ |
| `/api/v1/company/campaigns/{id}` | PUT | Update campaign | Supabase | ✅ |
| `/api/v1/company/team` | GET | List team members | Supabase | ✅ |
| `/api/v1/company/team` | POST | Add team member | Supabase | ✅ |
| `/api/v1/company/team/roles` | GET | Available roles | In-memory | ⚠️ |
| `/api/v1/company/team/{id}` | PUT | Update member | Supabase | ✅ |
| `/api/v1/company/team/{id}` | DELETE | Remove member | Supabase | ✅ |
| `/api/v1/company/approvals` | GET | List approval requests | Supabase | ✅ |
| `/api/v1/company/approvals` | POST | Create approval request | Supabase | ✅ |
| `/api/v1/company/approvals/{id}/decide` | POST | Approve/reject | Supabase | ✅ |
| `/api/v1/company/clients` | GET | List clients | Supabase | ✅ |
| `/api/v1/company/clients` | POST | Create client | Supabase | ✅ |
| `/api/v1/company/licenses` | GET | List licenses | Supabase | ✅ |
| `/api/v1/company/licenses` | POST | Create license | Supabase | ✅ |

---

## Service Dependencies Summary

| Service | Env Variable | What uses it | Required? |
|---------|-------------|-------------|-----------|
| **Supabase** | `SUPABASE_URL`, `SUPABASE_KEY` | All persistent data (talent, assets, jobs, etc.) | Yes — core requirement |
| **Backblaze B2** | `B2_KEY_ID`, `B2_APP_KEY`, `B2_BUCKET_NAME` | File storage (images, videos, models, audio) | Yes — for asset upload |
| **ComfyUI** | `COMFYUI_BASE_URL` | Image/video generation | No — simulation works without |
| **Vast.ai** | `VAST_API_KEY` | GPU worker rental (infrastructure, training) | No — simulation works without |
| **Ollama** | `OLLAMA_BASE_URL` | AI Brain LLM chat | No — planner works without |
| **OpenAI** | `OPENAI_API_KEY` | AI Brain LLM (alternative) | No — optional |
| **Anthropic** | `ANTHROPIC_API_KEY` | AI Brain LLM (alternative) | No — optional |
| **ElevenLabs** | `ELEVENLABS_API_KEY` | Real voice generation | No — simulation works without |

---

## Quick Start: What Works Out of the Box

With just `SUPABASE_URL` + `SUPABASE_KEY` + `B2_*` credentials configured:

1. **All CRUD endpoints** — talent, projects, assets, jobs, creative DNA, training datasets, video projects, etc.
2. **Asset upload/download** — files go to B2, metadata to Supabase
3. **Job queue** — create, track, cancel, retry
4. **Simulated generation** — the simulation provider produces fake results instantly (useful for UI development)
5. **Publishing workflow** — draft → approve → schedule → publish (simulated)
6. **All intelligence tables** — object DNA, visual DNA, wardrobes, etc.

## What Needs External Services

| Feature | Service Needed | How to Enable |
|---------|---------------|---------------|
| Real image generation | ComfyUI on GPU | Set `COMFYUI_BASE_URL`, launch worker |
| Real video generation (WAN 2.1) | ComfyUI on GPU | Set `COMFYUI_BASE_URL`, load WAN models |
| GPU worker orchestration | Vast.ai | Set `VAST_API_KEY` |
| Real LoRA training | Vast.ai GPU | Set `VAST_API_KEY` |
| AI Brain conversations | Ollama or OpenAI | Set `OLLAMA_BASE_URL` or `OPENAI_API_KEY` |
| Real voice generation | ElevenLabs | Set `ELEVENLABS_API_KEY` |
| Real social publishing | Platform APIs | Implement real provider (Instagram, TikTok) |
| Lip sync | GPU worker + Wav2Lip | Deploy model on ComfyUI worker |

---

## Total Endpoint Count

| Module | Endpoints |
|--------|-----------|
| Root | 4 |
| Core V1 (assets, jobs, workflows, DNA, feedback, generation, models, workers, execution, intelligence, story, production) | ~120 |
| Brain | 11 |
| Video | 17 |
| Training | 17 |
| Publishing | 16 |
| Infrastructure | 17 |
| Direct Generate | 1 |
| Object Intelligence | 35 |
| Asset Intelligence | 26 |
| Audio & Voice | 19 |
| Creator OS | 24 |
| Autonomous Studio | 8 |
| Production Intelligence | 10 |
| Performance | 24 |
| Cinematic | 21 |
| Company OS | 26 |
| **Total** | **~396** |
