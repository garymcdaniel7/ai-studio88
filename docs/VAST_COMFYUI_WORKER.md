# AI Studio — Vast.ai ComfyUI Worker Setup Guide

> How to run a remote ComfyUI worker on Vast.ai that AI Studio can control.

---

## Overview

AI Studio's backend is lightweight — it orchestrates but never runs inference.
The actual generation happens on a Vast.ai GPU instance running ComfyUI.

```
AI Studio (macOS)  ──HTTP──→  Vast.ai GPU Instance (ComfyUI API :8188)
                                        │
                                        ├── /prompt     (submit workflow)
                                        ├── /history    (check status)
                                        ├── /view       (download output)
                                        └── /system_stats (health check)
```

---

## Recommended GPU Specs

| Use Case | GPU | VRAM | Cost/hr |
|---|---|---|---|
| FLUX.1-dev (fp8) | RTX 4090 | 24 GB | ~$0.35-0.50 |
| FLUX.1-dev (fp16) | A100 40GB | 40 GB | ~$0.80-1.20 |
| SDXL | RTX 3090/4090 | 24 GB | ~$0.30-0.50 |
| WAN Video | A100 80GB | 80 GB | ~$1.00-1.50 |
| LoRA Training | A100 40GB+ | 40+ GB | ~$0.80-1.20 |

Minimum: 24 GB VRAM, 50 GB disk, CUDA 12.1+

---

## Docker Image Strategy

### Option A: Use a pre-built ComfyUI image (fastest start)

```bash
# On Vast.ai, search for templates with:
# - pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime base
# - Or use a community ComfyUI template

# Recommended search filters:
#   GPU: RTX 4090
#   VRAM: 24 GB
#   Disk: 50 GB
#   Image: pytorch/pytorch (or comfyui community)
```

### Option B: Custom setup script (more control)

Use the onstart script below.

---

## ComfyUI Install (onstart script for Vast.ai)

```bash
#!/bin/bash
# Vast.ai onstart script — installs ComfyUI and exposes API

cd /workspace

# Install ComfyUI if not present
if [ ! -d "ComfyUI" ]; then
    git clone https://github.com/comfyanonymous/ComfyUI.git
    cd ComfyUI
    pip install -r requirements.txt
    pip install comfy-cli
else
    cd ComfyUI
fi

# Install ComfyUI Manager
if [ ! -d "custom_nodes/ComfyUI-Manager" ]; then
    cd custom_nodes
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git
    cd ..
fi

# Start ComfyUI (listen on all interfaces for remote access)
python main.py --listen 0.0.0.0 --port 8188 &
```

---

## Model Folder Layout

```
/workspace/ComfyUI/models/
├── checkpoints/
│   ├── flux1-dev-fp8.safetensors        ← Primary model
│   └── sd_xl_base_1.0.safetensors       ← Fallback
├── loras/
│   └── (your trained LoRAs)
├── vae/
│   └── (VAE models if needed)
├── controlnet/
│   └── (ControlNet models)
├── clip/
│   └── (CLIP models for Flux)
├── upscale_models/
│   └── 4x-UltraSharp.pth
└── embeddings/
    └── (textual inversions)
```

### Downloading models on the instance:

```bash
cd /workspace/ComfyUI/models/checkpoints

# Flux.1-dev fp8 (~17 GB)
wget https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors

# Or use comfy-cli:
comfy model download --url <model_url> --dest checkpoints/
```

---

## Exposing ComfyUI API Safely

### Option 1: Direct port exposure (simple, less secure)

On Vast.ai, the instance exposes ports. Use the assigned public IP:port.

```
COMFYUI_BASE_URL=http://<vast_ip>:<mapped_port>
```

### Option 2: SSH tunnel (more secure)

```bash
# From your local machine:
ssh -L 8188:localhost:8188 root@<vast_ip> -p <ssh_port>

# Then use:
COMFYUI_BASE_URL=http://localhost:8188
```

### Option 3: Tailscale/WireGuard VPN (production)

Install Tailscale on both machines for a private network.

---

## How AI Studio Connects

1. Set in `.env`:
   ```
   COMFYUI_BASE_URL=http://<vast_instance_ip>:<port>
   GENERATION_PROVIDER=comfyui
   ```

2. AI Studio calls:
   - `GET /system_stats` → health check
   - `POST /prompt` → submit workflow
   - `GET /history/{id}` → poll progress
   - `GET /view?filename=...` → download output

3. Output flow:
   ```
   ComfyUI generates → AI Studio downloads → uploads to B2 → registers as Asset
   ```

---

## Startup Commands

```bash
# 1. Create a Vast.ai instance (via web UI or API)
# GPU: RTX 4090, Disk: 50GB, Image: pytorch/pytorch:2.1.0-cuda12.1

# 2. SSH into the instance
ssh root@<ip> -p <port>

# 3. Install ComfyUI
cd /workspace
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt

# 4. Download models
cd models/checkpoints
wget <model_url>

# 5. Start ComfyUI
cd /workspace/ComfyUI
python main.py --listen 0.0.0.0 --port 8188

# 6. Update your .env
# COMFYUI_BASE_URL=http://<instance_ip>:<port>
# GENERATION_PROVIDER=comfyui
```

---

## Shutdown Commands

```bash
# Graceful shutdown
pkill -f "python main.py"

# Or just destroy the Vast.ai instance (stops billing)
# Via Vast.ai web UI: Instances → Destroy
```

---

## Cost-Control Checklist

- [ ] Use spot instances when possible (50-70% cheaper)
- [ ] Destroy instances when not generating (billing stops)
- [ ] Use fp8 models to fit in smaller GPU (cheaper instances)
- [ ] Set `COMFYUI_API_TIMEOUT=300` to prevent runaway jobs
- [ ] Monitor via AI Studio dashboard (worker status page)
- [ ] Use the smallest GPU that fits your model (RTX 4090 for most)
- [ ] Pre-download models to a Vast.ai template (saves startup time)
- [ ] Set daily spending limits in Vast.ai account settings

---

## Verifying the Connection

```bash
# From your local machine (after setting COMFYUI_BASE_URL):
curl http://<vast_ip>:<port>/system_stats

# Should return:
# {"system": {...}, "devices": [{"name": "NVIDIA RTX 4090", "vram_total": ...}]}

# Then in AI Studio:
curl http://localhost:8000/api/v1/providers/health
# Should show ComfyUI as "healthy: true"
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Connection refused | Check port mapping in Vast.ai, ensure ComfyUI is running |
| Timeout during generation | Increase COMFYUI_API_TIMEOUT, check GPU isn't OOM |
| Model not found | Verify model is in /workspace/ComfyUI/models/checkpoints/ |
| VRAM OOM | Use fp8 model, reduce resolution, or upgrade GPU |
| Slow download | Models download once; subsequent runs use cached files |

---

## Future: RunPod Support

The same ComfyUI worker setup works on RunPod. Only the provisioning changes:
- RunPod uses Pods instead of Vast.ai instances
- Same ComfyUI install, same API, same connection method
- AI Studio's provider interface handles both identically
