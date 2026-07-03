# Vast.ai + ComfyUI Setup Guide

## Overview

AI Studio uses Vast.ai as a GPU cloud provider to run ComfyUI workers for image and video generation. This keeps the FastAPI backend lightweight (metadata and orchestration only) while heavy compute runs on remote GPU instances.

## Architecture

```
┌─────────────────────┐       ┌───────────────────────────────┐
│  AI Studio (local)  │       │  Vast.ai GPU Instance         │
│                     │       │                               │
│  FastAPI Backend    │◄─────►│  ComfyUI (port 8188)          │
│  Job Queue          │  HTTP │  Models / LoRAs / VAEs        │
│  Worker Registry    │       │  ComfyUI Manager              │
│  Provider Health    │       │  GPU (RTX 4090, A100, etc.)   │
└─────────────────────┘       └───────────────────────────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────────┐       ┌───────────────────────────────┐
│  Supabase (DB)      │       │  Backblaze B2 (Storage)       │
│  Jobs, Workers,     │       │  Generated images/videos      │
│  Assets metadata    │       │  Model files (future)         │
└─────────────────────┘       └───────────────────────────────┘
```

## What Runs Where

| Component | Location | Purpose |
|-----------|----------|---------|
| FastAPI | Local / Cloud VM | API, orchestration, metadata |
| Supabase | Cloud | Database, auth, realtime |
| Backblaze B2 | Cloud | Asset storage |
| ComfyUI | Vast.ai GPU | Image/video generation |
| Models | Vast.ai disk | Checkpoints, LoRAs, VAEs |
| Outputs | Vast.ai → B2 | Generated media uploaded to B2 |

## Environment Variables

Add these to your `.env` (never commit this file):

```bash
VAST_API_KEY=your-key-from-cloud.vast.ai
VAST_DEFAULT_IMAGE=runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04
VAST_DEFAULT_GPU=RTX_4090
VAST_DISK_GB=80
VAST_MAX_PRICE_PER_HOUR=1.50
COMFYUI_BASE_URL=http://<instance-ip>:<port>
COMFYUI_PORT=8188
```

Get your API key from: https://cloud.vast.ai → Account → API Key

## Quick Start

### 1. Verify Authentication

```bash
python scripts/vast/check_vast_auth.py
```

### 2. Find Available GPUs

```bash
python scripts/vast/list_offers.py --gpu RTX_4090 --max-price 1.00
```

### 3. Launch a ComfyUI Worker

```bash
# Dry run (shows cost estimate, does not launch)
python scripts/vast/launch_comfy_worker.py --gpu RTX_4090

# Actually launch (requires --launch --yes)
python scripts/vast/launch_comfy_worker.py --gpu RTX_4090 --launch --yes
```

### 4. Check ComfyUI Health

```bash
python scripts/vast/check_comfy_health.py --instance 12345
# or
python scripts/vast/check_comfy_health.py --url http://1.2.3.4:8188
```

### 5. Register Worker with AI Studio

```bash
python scripts/vast/register_worker.py --instance 12345
```

### 6. Stop Worker When Done

```bash
python scripts/vast/stop_vast_worker.py --instance 12345
# or stop all:
python scripts/vast/stop_vast_worker.py --all
# permanently destroy:
python scripts/vast/stop_vast_worker.py --instance 12345 --destroy
```

## Cost Control Rules

1. **Max price cap**: `VAST_MAX_PRICE_PER_HOUR` prevents launching expensive instances
2. **Confirmation required**: Scripts require `--yes` flag to launch paid instances
3. **Dry-run by default**: `launch_comfy_worker.py` requires `--launch` flag
4. **Always stop workers**: Run `stop_vast_worker.py --all` when done for the day
5. **Monitor costs**: Check Vast.ai dashboard at https://cloud.vast.ai/instances/

### Cost Estimates (approximate)

| GPU | $/hr | $/day | Use Case |
|-----|------|-------|----------|
| RTX 4090 | $0.30-0.80 | $7-19 | Standard generation |
| A100 80GB | $1.00-2.00 | $24-48 | Large models, training |
| H100 | $2.00-4.00 | $48-96 | Maximum performance |

## Shutdown Procedure

Always shut down workers when not in use:

```bash
# Stop all running instances
python scripts/vast/stop_vast_worker.py --all --yes

# Or destroy (removes disk too):
python scripts/vast/stop_vast_worker.py --all --destroy --yes
```

Set a reminder or use the cost control script to avoid surprise charges.

## Bootstrap Script

The `scripts/vast/bootstrap_comfyui.sh` runs on the Vast.ai instance and:

1. Installs system dependencies (git, wget, ffmpeg)
2. Clones or updates ComfyUI
3. Installs ComfyUI Manager
4. Creates standard model directories
5. Starts ComfyUI on `0.0.0.0:8188`

Standard directory structure on the instance:

```
/workspace/ComfyUI/
├── models/
│   ├── checkpoints/
│   ├── loras/
│   ├── vae/
│   ├── controlnet/
│   ├── upscale_models/
│   ├── clip/
│   ├── embeddings/
│   └── hypernetworks/
├── custom_nodes/
│   └── ComfyUI-Manager/
├── input/
├── output/
└── temp/
```

## Provider Health Endpoint

Check all provider status from the API:

```bash
curl http://localhost:8000/api/v1/providers/health
```

Returns:
- Simulation provider status
- ComfyUI provider status
- Vast.ai running instances count
- Direct ComfyUI health check

## Worker Registration Flow

1. Instance launches on Vast.ai
2. Bootstrap script installs ComfyUI
3. ComfyUI starts on port 8188
4. `register_worker.py` detects the ComfyUI URL
5. Verifies ComfyUI is healthy (`/system_stats`)
6. Registers worker with AI Studio (`POST /api/v1/workers`)
7. Worker appears in AI Studio as `provider=vast, type=comfyui, status=online`

## Troubleshooting

### "VAST_API_KEY not set"
Add your key to `.env`. Get it from https://cloud.vast.ai → Account → API Key.

### "No matching offers found"
Relax filters: increase `--max-price`, remove `--gpu` filter, decrease `--min-disk`.

### "ComfyUI unreachable"
- Instance may still be starting (wait 2-3 minutes after launch)
- Check that port 8188 is mapped in the Vast.ai instance config
- Verify the public IP hasn't changed

### "Worker registration failed"
- Ensure AI Studio backend is running locally
- Check `API_BASE_URL` in `.env`

## Future Enhancements

- Auto-shutdown after idle timeout
- Auto-scale based on job queue depth
- Model pre-loading via bootstrap config
- RunPod provider adapter (same interface)
- Cost tracking per job/campaign/brand
- Automatic worker recovery on failure
