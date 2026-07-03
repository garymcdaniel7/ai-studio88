# AI Studio — Execution Platform

> Phase C. Workers, providers, GPU discovery, job routing, and health monitoring.

---

## Overview

The Intelligence Layer decides WHAT should happen.
The Execution Platform makes it happen — on external GPU workers.

AI Studio never runs heavy compute internally. It orchestrates external workers.

```
Intelligence Engine → Execution Platform → External Workers
                                           ├── ComfyUI (local/cloud)
                                           ├── Shadow PC
                                           ├── Vast.ai
                                           ├── RunPod
                                           └── Future providers
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Execution Platform                            │
│                 backend/execution/                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Provider Registry                          │   │
│  │  simulation │ comfyui │ wan │ hunyuan │ forge         │   │
│  │  invokeai │ elevenlabs │ xtts │ openvoice            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Worker Manager                             │   │
│  │  register │ heartbeat │ status │ assign │ shutdown    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Job Router                                 │   │
│  │  VRAM match │ model support │ priority │ queue aware  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Provider Interfaces

```python
ExecutionProvider (base)
  ├── ImageProvider  (Flux, SDXL, ComfyUI, Forge)
  ├── VideoProvider  (WAN, Hunyuan, LTX)
  ├── TrainingProvider (LoRA, DreamBooth)
  ├── AudioProvider  (ElevenLabs, XTTS, OpenVoice)
  └── EditingProvider (upscale, face swap, lip sync)
```

Each provider implements: `info()`, `health()`, `execute()`, `cancel()`, `supports()`

---

## Registered Providers (9)

| Provider | Type | Status | Models |
|---|---|---|---|
| simulation | image | ✅ Active | any |
| comfyui | image | ⚪ Placeholder | flux-dev, sdxl, sd1.5, pony |
| wan | video | ⚪ Placeholder | wan-2.1 |
| hunyuan | video | ⚪ Placeholder | hunyuan-video |
| forge | image | ⚪ Placeholder | sdxl, sd1.5, flux-dev |
| invokeai | image | ⚪ Placeholder | sdxl, flux-dev |
| elevenlabs | audio | ⚪ Placeholder | eleven-turbo |
| xtts | audio | ⚪ Placeholder | xtts-v2 |
| openvoice | audio | ⚪ Placeholder | openvoice-v2 |

---

## Worker System

Workers are external GPU processes that register with AI Studio.

### Worker Lifecycle

```
Register → Online → Receive Jobs → Busy → Complete → Online → ...
                                              ↓
                                         Heartbeat timeout → Offline
```

### GPU Discovery

Each worker reports:
- GPU model, VRAM total/free
- CUDA version, driver version
- Temperature, utilization
- Supported models
- Current job, queue size

---

## Job Router

Automatically assigns jobs based on:
1. VRAM requirement (model-specific)
2. Provider compatibility
3. Model support on worker
4. Queue length (prefer shorter)
5. Free VRAM (prefer more)

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/execution/health` | System health summary |
| GET | `/api/v1/execution/workers` | List all workers with GPU info |
| POST | `/api/v1/execution/workers/register` | Register a new worker |
| POST | `/api/v1/execution/workers/{id}/heartbeat` | Worker keepalive |
| DELETE | `/api/v1/execution/workers/{id}` | Unregister worker |
| GET | `/api/v1/execution/providers` | List all providers with health |
| POST | `/api/v1/execution/route` | Route a job to best worker |

---

## Adding a New Provider

1. Create `backend/execution/providers/yourprovider.py`
2. Implement `ExecutionProvider` (or `ImageProvider`, `VideoProvider`, etc.)
3. Register in `PROVIDER_REGISTRY` in `provider_registry.py`
4. Workers using that provider will be automatically discoverable

No changes needed to the core platform.

---

## Curl Examples

```bash
# System health
curl http://localhost:8000/api/v1/execution/health

# List workers
curl http://localhost:8000/api/v1/execution/workers

# Register a worker
curl -X POST http://localhost:8000/api/v1/execution/workers/register \
  -H "Content-Type: application/json" \
  -d '{"name":"gpu-1","provider":"comfyui","url":"http://192.168.1.100:8188",
       "gpu":{"model":"RTX 4090","vram_total_gb":24,"cuda_version":"12.4"}}'

# Route a job
curl -X POST http://localhost:8000/api/v1/execution/route \
  -H "Content-Type: application/json" \
  -d '{"type":"image","model":"flux-dev","priority":8}'

# Worker heartbeat
curl -X POST http://localhost:8000/api/v1/execution/workers/{id}/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"gpu":{"vram_free_gb":18,"temperature_c":65,"utilization_pct":80}}'
```

---

## Files

| File | Purpose |
|---|---|
| `backend/execution/__init__.py` | Package |
| `backend/execution/provider_interface.py` | Abstract provider interfaces |
| `backend/execution/provider_registry.py` | Registry + simulation + placeholders |
| `backend/execution/worker_manager.py` | Worker lifecycle management |
| `backend/execution/job_router.py` | Job → worker routing logic |
| `backend/execution/providers/` | Future provider implementations |
| `dashboard/pages/11_Execution.py` | Execution dashboard page |
