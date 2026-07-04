# Model Cache Strategy

## Problem

Vast.ai workers start fresh every time. Downloading 6-12GB model files from HuggingFace on every boot is:
- Slow (3-30 minutes depending on host bandwidth)
- Rate-limited (HuggingFace throttles unauthenticated requests)
- Expensive (GPU charges while waiting for downloads)

## Solution: Two-Tier Model Cache

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Vast.ai Worker │ ──► │  Backblaze B2 Cache   │ ──► │  HuggingFace    │
│  (needs model)  │     │  (fast, no limits)    │     │  (fallback)     │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
        │                         │
        ▼                         ▼
   Check local disk         Check B2 bucket
   (already downloaded?)    (models/ prefix)
```

**Priority order:**
1. Local disk (already exists from previous run)
2. Backblaze B2 model cache (fast, no rate limits, our infrastructure)
3. HuggingFace Hub (slow, rate-limited, last resort)

## Setup

### 1. Environment Variables

Add to `.env`:

```bash
# HuggingFace (get from huggingface.co/settings/tokens)
HF_TOKEN=hf_xxxxxxxxxxxxx

# Model cache
MODEL_CACHE_BUCKET=ai-studio-models    # Or use your existing B2_BUCKET_NAME
MODEL_CACHE_PREFIX=models/
MODEL_CACHE_ENABLED=true
```

### 2. Seed the Cache (One-Time)

Download models locally, then upload to B2:

```bash
# Option A: Upload a known model (downloads from HF, uploads to B2)
python scripts/vast/upload_model.py --known sdxl-turbo

# Option B: Upload a local file
python scripts/vast/upload_model.py --file ./sd_xl_turbo_1.0_fp16.safetensors --type checkpoint

# Option C: Upload from any HF repo
python scripts/vast/upload_model.py --hf stabilityai/sdxl-turbo --hf-file sd_xl_turbo_1.0_fp16.safetensors --type checkpoint
```

### 3. Verify Cache Contents

```bash
python scripts/vast/upload_model.py --list
python scripts/vast/download_model.py --list-known
```

## Usage

### On a Vast.ai Worker (via bootstrap)

The `bootstrap_comfyui.sh` script automatically:
1. Checks B2 cache for each model in `MODELS_TO_DOWNLOAD`
2. Falls back to HuggingFace if not cached
3. Respects `HF_TOKEN` for authenticated downloads

Set models when launching:
```bash
export MODELS_TO_DOWNLOAD="sdxl-turbo"
# or multiple:
export MODELS_TO_DOWNLOAD="sdxl-turbo,sdxl-vae"
```

### Download Locally or on a Worker

```bash
# Smart download (checks local → B2 → HF)
python scripts/vast/download_model.py --known sdxl-turbo --dest ./models/checkpoints

# For ComfyUI directory structure
python scripts/vast/download_model.py --known sdxl-turbo --comfyui-dir /workspace/ComfyUI

# Cache-only (skip HuggingFace)
python scripts/vast/download_model.py --known sdxl-turbo --cache-only
```

## Known Models

| Name | Type | Size | Description |
|------|------|------|-------------|
| sdxl-turbo | checkpoint | 6.5 GB | SDXL Turbo — 1-step generation, fastest for testing |
| sdxl-base | checkpoint | 6.9 GB | SDXL Base 1.0 — production quality |
| flux-dev | checkpoint | 12.0 GB | Flux Dev — highest quality, needs 24GB+ VRAM |
| sdxl-vae | vae | 0.3 GB | SDXL VAE — required for SDXL models |

## B2 Storage Layout

```
ai-studio-models/
└── models/
    ├── checkpoints/
    │   ├── sd_xl_turbo_1.0_fp16.safetensors
    │   ├── sd_xl_base_1.0.safetensors
    │   └── flux1-dev.safetensors
    ├── loras/
    │   └── (your LoRAs)
    ├── vae/
    │   └── sdxl_vae.safetensors
    ├── controlnet/
    ├── upscale_models/
    ├── clip/
    └── embeddings/
```

## Recommended Smoke Test Workflow

### Pre-requisites (one-time, from your local machine)

```bash
# 1. Set up HF token in .env
echo "HF_TOKEN=hf_your_token_here" >> .env

# 2. Upload SDXL Turbo to B2 cache
python scripts/vast/upload_model.py --known sdxl-turbo

# 3. Verify it's in the cache
python scripts/vast/upload_model.py --list
```

### Running a Smoke Test

```bash
# 1. Find a compatible GPU (RTX 4090/3090/A100 — NOT RTX 50 series)
python scripts/vast/list_offers.py --gpu RTX_4090 --max-price 0.50

# 2. Launch with model cache env vars
#    (the bootstrap will pull from B2 cache automatically)
python scripts/vast/launch_comfy_worker.py --offer-id <ID> --launch --yes

# 3. Wait for boot, then check health
python scripts/vast/check_comfy_health.py --instance <INSTANCE_ID>

# 4. Register worker
python scripts/vast/register_worker.py --instance <INSTANCE_ID>

# 5. Run test generation (via ComfyUI API)
# 6. Destroy instance when done
python scripts/vast/stop_vast_worker.py --instance <INSTANCE_ID> --destroy --yes
```

## Cost Analysis

| Approach | Time to First Generation | GPU Cost Wasted |
|----------|-------------------------|-----------------|
| HuggingFace (unauth) | 10-30 min | $0.02-0.15 |
| HuggingFace (HF_TOKEN) | 3-10 min | $0.01-0.05 |
| Backblaze B2 cache | 30-90 sec | $0.001-0.004 |

B2 storage cost: ~$0.005/GB/month = $0.03/month for SDXL Turbo

## GPU Compatibility Notes

**Supported (Ada/Ampere architecture):**
- RTX 4090, RTX 4080, RTX 4070
- RTX 3090, RTX 3080, RTX 3070
- A100, A6000, A5000
- V100 (Volta — older but works)

**NOT supported yet (Blackwell architecture):**
- RTX 5090, RTX 5080, RTX 5070 Ti
- RTX PRO 6000 S

PyTorch stable releases don't yet include compiled CUDA kernels for Blackwell GPUs. Avoid these until PyTorch officially supports compute capability 12.0+.

## Architecture

```
backend/providers/vast/model_cache.py   — Core cache logic (B2 + HF + smart_download)
scripts/vast/upload_model.py            — Upload models to B2 cache
scripts/vast/download_model.py          — Download models (B2 → HF fallback)
scripts/vast/bootstrap_comfyui.sh       — Worker bootstrap (uses model cache)
```

## Adding New Models

1. Add to `KNOWN_MODELS` in `backend/providers/vast/model_cache.py`
2. Upload to cache: `python scripts/vast/upload_model.py --known <name>`
3. Workers will automatically pick it up via `MODELS_TO_DOWNLOAD`
