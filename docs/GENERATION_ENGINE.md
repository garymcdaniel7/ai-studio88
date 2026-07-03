# AI Studio — Generation Engine

> Phase A. The production-ready content generation pipeline.

---

## Overview

The Generation Engine is AI Studio's core content production system. It accepts
generation requests, routes them through pluggable providers, tracks progress,
uploads outputs to B2, and registers them as assets.

```
Creative Session → Production Plan → Generation Engine → Provider → Output → Asset
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Generation Engine                              │
│                    backend/engine/generation_engine.py            │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              Provider Interface (ABC)                        │ │
│  │  health() │ capabilities() │ submit() │ cancel() │ validate()│ │
│  └─────────┬──────────────────────────────┬────────────────────┘ │
│            │                              │                       │
│  ┌─────────▼──────────┐      ┌───────────▼──────────────┐      │
│  │ SimulationProvider  │      │    ComfyUIProvider        │      │
│  │ (development/test) │      │    (production)           │      │
│  └────────────────────┘      └──────────────────────────┘      │
│                                                                   │
│  Future:  ForgeProvider │ InvokeAIProvider │ CloudGPUProvider    │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐           ┌─────────────────┐
│  Backblaze B2   │           │    Supabase     │
│  (file storage) │           │  (asset record) │
└─────────────────┘           └─────────────────┘
```

---

## Provider Interface

```python
class GenerationProvider(ABC):
    def name(self) -> str: ...
    def health(self) -> ProviderHealth: ...
    def capabilities(self) -> ProviderCapabilities: ...
    def submit(self, request, on_progress) -> GenerationOutput: ...
    def cancel(self, job_id) -> bool: ...
    def validate_workflow(self, workflow) -> tuple[bool, str]: ...
```

To add a new provider:
1. Create `backend/engine/providers/yourprovider.py`
2. Implement `GenerationProvider`
3. Register in `PROVIDERS` dict in `generation_engine.py`
4. Set `GENERATION_PROVIDER=yourprovider` in `.env`

---

## Providers

| Provider | Status | Use case |
|---|---|---|
| `simulation` | ✅ Active | Development, testing, demos |
| `comfyui` | ✅ Implemented | Production (requires running ComfyUI instance) |
| `forge` | Planned | Alternative Stable Diffusion backend |
| `invokeai` | Planned | InvokeAI integration |
| `cloud` | Planned | Vast.ai / RunPod serverless |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/generation/health` | Provider health + GPU status |
| GET | `/api/v1/generation/providers` | List available providers |
| GET | `/api/v1/generation/models` | Model registry (checkpoints, LoRAs) |
| POST | `/api/v1/generation/run` | Execute generation (full pipeline) |

---

## Full Pipeline: What Happens on Generate

```
1. POST /api/v1/generation/run
   ↓
2. Build GenerationRequest from parameters
   ↓
3. Create job record (status=running)
   ↓
4. Dispatch to provider via submit()
   ↓
5. Provider executes with progress callbacks
   ↓
6. Progress updates written to job record
   ↓
7. Provider returns GenerationOutput (file bytes)
   ↓
8. Upload file bytes to Backblaze B2
   ↓
9. Create asset record in Supabase
   ↓
10. Mark job completed with output reference
    ↓
11. Return { job_id, asset, provider }
```

---

## Model Registry

Currently in-memory. Future: database-backed.

| Model | Type | VRAM | Capabilities |
|---|---|---|---|
| FLUX.1-dev | checkpoint | 24 GB | txt2img, img2img |
| Stable Diffusion XL | checkpoint | 12 GB | txt2img, img2img, inpainting |
| WAN Video 2.1 | checkpoint | 24 GB | txt2video, img2video |

---

## GPU Manager

Tracks GPU state (simulated currently, real metrics when ComfyUI connected):

- GPU name, VRAM total/free
- Temperature, utilization
- Queue size, current job
- Provider connection status

---

## Configuration

```env
GENERATION_PROVIDER=simulation    # simulation | comfyui
COMFYUI_BASE_URL=http://localhost:8188
COMFYUI_TIMEOUT_SECONDS=300
```

---

## Curl Examples

```bash
# Check engine health
curl http://localhost:8000/api/v1/generation/health

# List providers
curl http://localhost:8000/api/v1/generation/providers

# List models
curl http://localhost:8000/api/v1/generation/models

# Run generation (full pipeline: generate → B2 → asset)
curl -X POST http://localhost:8000/api/v1/generation/run \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "luxury portrait, golden hour, cinematic",
    "negative_prompt": "blurry, deformed",
    "steps": 20,
    "width": 1024,
    "height": 1024,
    "model": "flux-dev",
    "talent_id": "uuid-here"
  }'
```

---

## Files

| File | Purpose |
|---|---|
| `backend/engine/__init__.py` | Package |
| `backend/engine/models.py` | Internal data models (request, output, progress) |
| `backend/engine/provider.py` | Abstract provider interface |
| `backend/engine/generation_engine.py` | Engine + model registry + GPU manager |
| `backend/engine/providers/simulation.py` | Simulation provider |
| `backend/engine/providers/comfyui.py` | ComfyUI provider |
