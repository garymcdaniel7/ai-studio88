# AI Studio — LoRA Training Manager

> Priority 4. Full LoRA lifecycle from dataset to deployed model.

---

## Overview

Manages the complete LoRA training pipeline:
Dataset → Captions → Training Job → LoRA Version → Evaluation → Deployment

Training always runs on external GPU workers (never inside FastAPI).

---

## Pipeline

```
1. Create Dataset (select talent)
2. Add images from Assets
3. Auto-caption (simulated, future: BLIP/Florence/JoyCaption)
4. Review/edit captions
5. Start training job
6. Job routes to GPU worker via Worker Manager
7. Training executes (simulated or real Kohya/OneTrainer)
8. Output LoRA uploaded to B2
9. Asset + Model + LoRA Version records created
10. Evaluate LoRA quality
11. Promote as talent default
```

---

## API Endpoints (16)

| Method | Path | Description |
|---|---|---|
| GET | `/training/datasets` | List datasets |
| POST | `/training/datasets` | Create dataset |
| GET | `/training/datasets/{id}` | Get dataset |
| PUT | `/training/datasets/{id}` | Update dataset |
| DELETE | `/training/datasets/{id}` | Delete dataset |
| GET | `/training/datasets/{id}/images` | List dataset images |
| POST | `/training/datasets/{id}/images` | Add image to dataset |
| POST | `/training/datasets/{id}/caption` | Auto-caption all images |
| PUT | `/training/images/{id}/caption` | Edit image caption |
| GET | `/training/jobs` | List training jobs |
| GET | `/training/jobs/{id}` | Get training job |
| POST | `/training/jobs` | Start training |
| POST | `/training/jobs/{id}/cancel` | Cancel training |
| GET | `/loras` | List LoRA versions |
| GET | `/loras/{id}` | Get LoRA details |
| POST | `/loras/{id}/evaluate` | Submit evaluation |
| POST | `/loras/{id}/promote` | Promote as talent default |

---

## Training Config

```json
{
  "base_model": "flux1-dev-fp8.safetensors",
  "resolution": 512,
  "rank": 16,
  "alpha": 16,
  "learning_rate": 0.0001,
  "steps": 1000,
  "optimizer": "adamw",
  "scheduler": "cosine",
  "trigger_words": ["melissa_character"],
  "sample_prompts": ["melissa_character, portrait, studio"]
}
```

---

## Training Providers

| Provider | Status |
|---|---|
| simulation | ✅ Active |
| vast | ✅ Active (simulated by default, live with `TRAINING_VAST_LIVE=true`) |
| kohya | Planned |
| onetrainer | Planned |
| fluxgym | Planned |
| civitai | Planned |
| replicate | Planned |

---

## Vast.ai Training Workflow

The `vast` provider executes LoRA training on Vast.ai GPU workers using the
Infrastructure module's Worker Orchestrator and Connection Race Mode.

### Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  API Router │────▶│ VastTrainingProv  │────▶│ Worker Orchestrator │
│  POST /jobs │     │  vast_provider.py │     │  connection_race.py │
└─────────────┘     └──────────────────┘     └─────────────────────┘
                            │                          │
                            │ SSH/SCP                   │ Vast.ai API
                            ▼                          ▼
                    ┌──────────────┐           ┌──────────────┐
                    │  GPU Worker  │           │  Vast.ai     │
                    │  train_lora  │           │  Marketplace │
                    └──────────────┘           └──────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  B2 Storage  │
                    │  models/loras│
                    └──────────────┘
```

### Execution Steps

1. **Provision** — Launch a 24GB+ VRAM worker via Connection Race Mode
2. **Install** — SSH in, install diffusers/accelerate/peft/safetensors
3. **Upload** — SCP training images to `/workspace/training/dataset/`
4. **Configure** — Write `config.json` with training params
5. **Train** — Launch `train_lora.py --config config.json` as background process
6. **Monitor** — Poll `training.log` for step progress
7. **Download** — SCP the output `.safetensors` file back
8. **Store** — Upload to B2 under `models/loras/`
9. **Register** — Create Asset + Model + LoRA Version records

### Environment Variables

```bash
TRAINING_PROVIDER=simulation         # Default provider for new jobs
TRAINING_WORKER_MIN_VRAM=24          # Minimum VRAM in GB
TRAINING_VAST_LIVE=false             # Set true for real GPU provisioning
VAST_MAX_PRICE_PER_HOUR=1.50        # Safety cap for hourly cost
VASTAI_SSH_KEY_PATH=~/.ssh/id_ed25519
```

### Usage

```bash
# Start a training job with the vast provider
curl -X POST http://localhost:8000/api/v1/training/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "<uuid>",
    "provider": "vast",
    "config": {
      "base_model": "flux1-dev-fp8.safetensors",
      "steps": 1500,
      "rank": 16,
      "resolution": 512,
      "trigger_words": ["character_name"]
    }
  }'

# List available providers
curl http://localhost:8000/api/v1/training/providers
```

---

## On Completion

When training completes:
1. LoRA file → Backblaze B2
2. Asset record created (type=model)
3. Model record created (type=lora)
4. LoRA Version record created
5. Linked to talent via `talent_id`
6. Optionally promoted as talent default

---

## Captioning Providers (Future)

| Provider | Description |
|---|---|
| BLIP | General image captioning |
| Florence | Microsoft foundation model |
| JoyCaption | Anime/character-focused |
| WD14 Tagger | Tag-based (Danbooru) |
| LLaVA | Multi-modal LLM |
| GPT Vision | OpenAI vision API |

---

## Database Tables (5 new)

`training_datasets`, `training_images`, `training_jobs`, `lora_versions`, `lora_evaluations`

See `docs/sql/008_lora_training.sql` for full schema.
