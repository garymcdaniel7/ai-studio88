# AI Studio — Model & Workflow Manager

> Priority 2. Central registry for AI models, LoRAs, and workflow templates.

---

## Overview

Tracks all AI models (checkpoints, LoRAs, VAEs, ControlNets, etc.) and
ComfyUI workflow templates. Validates generation requests before execution.

---

## Model Types

| Type | Examples |
|---|---|
| checkpoint | FLUX.1-dev, SDXL, WAN, Hunyuan, LTX, Pony |
| lora | Character LoRAs, style LoRAs |
| vae | Custom VAE decoders |
| controlnet | Pose, depth, canny, etc. |
| ipadapter | Reference image adapters |
| upscaler | 4x-UltraSharp, Real-ESRGAN |
| embedding | Textual inversions |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/models` | List (filter: type, family, status) |
| POST | `/models` | Register new model |
| GET | `/models/{id}` | Get model details |
| PUT | `/models/{id}` | Update model |
| DELETE | `/models/{id}` | Remove model |
| GET | `/workflow-templates` | List templates |
| POST | `/workflow-templates` | Create template |
| GET | `/workflow-templates/{id}` | Get template |
| PUT | `/workflow-templates/{id}` | Update template |
| DELETE | `/workflow-templates/{id}` | Remove template |
| GET | `/provider-capabilities` | Provider + model compatibility |
| POST | `/generation/validate` | Pre-validate before generating |

---

## Generation Validation

Before executing, `POST /generation/validate` checks:
- Provider exists and supports the model
- Model status is "available"
- VRAM requirements are compatible
- Workflow template exists (if specified)

---

## Seed Data (9 models + 3 templates)

Run `docs/sql/006b_seed_models.sql` after creating tables.

Includes: FLUX.1-dev (fp8/fp16), SDXL, WAN, Hunyuan, LTX, Pony,
4x-UltraSharp upscaler, and a test LoRA.

---

## Civitai Integration (Future)

Set in `.env`:
```
CIVITAI_API_KEY=your-key
CIVITAI_BASE_URL=https://civitai.com/api/v1
```

Future capabilities:
- Import model metadata from Civitai
- Sync LoRA information
- Download models to worker instances
- Track model versions and updates

See `docs/CIVITAI.md` for details.
