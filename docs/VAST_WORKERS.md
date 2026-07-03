# AI Studio — Vast.ai Workers

> How GPU workers on Vast.ai register with and communicate to AI Studio.

---

## Overview

Workers are external GPU instances that register with AI Studio, report their
capabilities, accept jobs, and send heartbeats. AI Studio never runs inference
directly — it orchestrates workers.

---

## Worker Lifecycle

```
Start instance → Install ComfyUI → Register with AI Studio → Accept jobs → Heartbeat → Shutdown
```

---

## Registration

A worker registers itself by calling:

```bash
curl -X POST http://your-aistudio:8000/api/v1/workers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "vast-gpu-1",
    "provider": "vast_ai",
    "base_url": "http://<instance_ip>:<port>",
    "gpu_name": "RTX 4090",
    "vram_gb": 24.0,
    "available_vram_gb": 22.0,
    "cuda_version": "12.4",
    "driver_version": "550.54",
    "supported_tasks": ["txt2img", "img2img", "upscale", "video"],
    "supported_models": ["flux1-dev-fp8.safetensors", "sd_xl_base_1.0.safetensors"]
  }'
```

Returns a `worker_id` used for all subsequent communication.

---

## Heartbeat

Workers should send a heartbeat every 30 seconds:

```bash
curl -X POST http://your-aistudio:8000/api/v1/workers/{worker_id}/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "status": "online",
    "available_vram_gb": 20.0,
    "current_job_id": null
  }'
```

If heartbeat is stale (>60s), AI Studio marks the worker offline.

---

## Required Environment

On the worker instance:
- Python 3.10+
- CUDA 12.1+
- ComfyUI running on port 8188
- Models in `/workspace/ComfyUI/models/`

---

## Startup Script (Vast.ai onstart)

```bash
#!/bin/bash
cd /workspace/ComfyUI
python main.py --listen 0.0.0.0 --port 8188 &

# Wait for ComfyUI to start
sleep 10

# Register with AI Studio
curl -X POST http://<your_aistudio_url>/api/v1/workers \
  -H "Content-Type: application/json" \
  -d '{"name":"vast-'$(hostname)'","provider":"vast_ai","base_url":"http://'$(hostname -I | awk "{print \$1}")':8188","gpu_name":"'$(nvidia-smi --query-gpu=name --format=csv,noheader)'","vram_gb":'$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk "{print \$1/1024}")'}'

# Heartbeat loop
while true; do
  curl -s -X POST http://<your_aistudio_url>/api/v1/workers/{worker_id}/heartbeat \
    -H "Content-Type: application/json" \
    -d '{"status":"online","available_vram_gb":'$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | awk "{print \$1/1024}")'}'
  sleep 30
done
```

---

## Shutdown

```bash
# Mark offline (stops receiving jobs)
curl -X POST http://your-aistudio:8000/api/v1/workers/{worker_id}/offline

# Then destroy the Vast.ai instance to stop billing
```

---

## Cost-Control Checklist

- [ ] Always mark offline before destroying instance
- [ ] Use spot instances (50-70% cheaper)
- [ ] Destroy when idle for >10 minutes
- [ ] Monitor via AI Studio dashboard (Workers page)
- [ ] Set daily spending limits in Vast.ai account
- [ ] Use fp8 models to fit in smaller GPUs

---

## Recommended GPU Tiers

| Tier | GPU | VRAM | Use |
|---|---|---|---|
| Standard | RTX 4090 | 24 GB | Flux fp8, SDXL, upscale |
| Pro | A100 40GB | 40 GB | Flux fp16, WAN video |
| Ultra | A100 80GB | 80 GB | Hunyuan video, training |
