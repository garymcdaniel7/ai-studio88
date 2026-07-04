# Skill: Generate Image

## Purpose
Generate an AI image using ComfyUI via the backend API.

## Prerequisites
- GPU worker running with ComfyUI
- Model loaded (SDXL Turbo, SD 1.5, or Flux Dev)
- SSH tunnel active (localhost:8188 → worker:8188)

## Via API
```bash
curl -X POST http://localhost:8000/api/v1/generate/image \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a luxury penthouse at sunset, photorealistic",
    "model": "flux-dev",
    "width": 1024,
    "height": 1024,
    "steps": 20,
    "seed": -1
  }'
```

## Models Available

| Model | Checkpoint | Resolution | Steps | Notes |
|-------|-----------|-----------|-------|-------|
| flux-dev | flux1-dev.safetensors | 1024x1024 | 20 | Best quality, needs DualCLIPLoader + T5 + VAE |
| sdxl-turbo | sd_xl_turbo_1.0_fp16.safetensors | 512x512 | 1 | Fastest, lower quality |
| sd15 | v1-5-pruned-emaonly.safetensors | 512x512 | 20 | Classic, versatile |

## Flux Dev Requirements
- flux1-dev.safetensors in models/diffusion_models/
- clip_l.safetensors in models/clip/
- t5xxl_fp16.safetensors in models/clip/
- ae.safetensors in models/vae/

## Response
Returns base64-encoded PNG image + metadata (filename, generation_time, seed).

## Workflow Templates
All in `workflows/comfyui/`:
- `sdxl_turbo.json`
- `sd15_standard.json`
- `flux_dev.json` (v2 — uses UNETLoader + DualCLIPLoader)
