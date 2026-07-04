# Video Generation

AI Studio generates video content using WAN 2.1 via ComfyUI, with a simulation fallback for development and testing.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  API Layer  │────▶│  VideoProvider   │────▶│  ComfyUI Instance    │
│  /api/v1/   │     │  (comfyui)       │     │  (GPU worker, SSH)   │
└─────────────┘     └──────────────────┘     └──────────────────────┘
                           │                          │
                           │ fallback                  │ executes
                           ▼                          ▼
                    ┌──────────────────┐     ┌──────────────────────┐
                    │  SimulatedVideo  │     │  WAN 2.1 Workflow    │
                    │  Provider        │     │  (JSON template)     │
                    └──────────────────┘     └──────────────────────┘
```

### Flow

1. Client calls `POST /api/v1/videos/{id}/generate` with provider = `comfyui`
2. `ComfyUIVideoProvider` loads the workflow template from `workflows/comfyui/`
3. Parameters (prompt, resolution, frames) are injected into the workflow JSON
4. Workflow is submitted to ComfyUI via `POST /prompt`
5. Provider polls `/history/{prompt_id}` until completion
6. Output file (MP4/WebP) is downloaded from ComfyUI `/view` endpoint
7. Video is uploaded to B2 storage and registered as an asset

### Providers

| Provider     | Key          | Status     | Notes                              |
|-------------|-------------|------------|-------------------------------------|
| Simulation  | `simulation` | Active     | Instant fake output for dev/test   |
| ComfyUI     | `comfyui`    | Active     | Real generation via WAN 2.1        |

Set the default provider via environment variable:
```
VIDEO_GENERATION_PROVIDER=simulation|comfyui
```

## WAN 2.1 Model Requirements

| Parameter       | Value                                    |
|----------------|------------------------------------------|
| Model file     | `wan2.1_t2v_14B_bf16.safetensors`        |
| Size           | ~28 GB                                    |
| VRAM required  | 80 GB+ (A100 80GB or H100 recommended)    |
| Precision      | BF16                                      |
| HuggingFace    | `Wan-AI/Wan2.1-T2V-14B`                  |
| Generation time| 3-10 min per 2-second clip                |

### VRAM Estimates

| Resolution | Frames | VRAM Usage |
|-----------|--------|------------|
| 832x480   | 49     | ~60 GB     |
| 832x480   | 81     | ~75 GB     |
| 1280x720  | 49     | ~78 GB     |
| 1280x720  | 81     | 80+ GB     |

## ComfyUI Workflow Templates

Templates live in `workflows/comfyui/`:

### wan21_t2v_simple.json

Uses standard ComfyUI nodes (KSampler, batch latents). Works without custom node packs but produces frame-by-frame output without temporal coherence. Good for testing the pipeline end-to-end.

### wan21_t2v_native.json

Uses native WAN nodes from the [ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper) extension. Provides proper temporal video generation. Requires:

- ComfyUI-WanVideoWrapper custom nodes installed
- WAN 2.1 model files downloaded
- Adequate VRAM (80GB+)

### Placeholder System

Workflow JSON uses `__PLACEHOLDER__` syntax:

```json
{
  "class_type": "CLIPTextEncode",
  "inputs": {
    "text": "__POSITIVE_PROMPT__",
    "clip": ["1", 1]
  }
}
```

Available placeholders:
- `__POSITIVE_PROMPT__` — Generation prompt
- `__NEGATIVE_PROMPT__` — Negative prompt
- `__WIDTH__` — Output width (default: 832)
- `__HEIGHT__` — Output height (default: 480)
- `__NUM_FRAMES__` — Frame count (default: 49)
- `__STEPS__` — Sampling steps (default: 20)
- `__CFG__` — Classifier-free guidance scale (default: 6.0)
- `__SEED__` — Random seed
- `__MODEL__` — Checkpoint filename

## API Usage

### List Providers

```bash
GET /api/v1/video/providers
```

Response:
```json
{
  "providers": [
    {
      "name": "simulation",
      "health": {"healthy": true, "provider": "simulation"},
      "capabilities": {"modes": ["text_to_video", "image_to_video"], "models": ["wan-2.1"]}
    },
    {
      "name": "comfyui",
      "health": {"healthy": true, "provider": "comfyui", "gpu_name": "NVIDIA A100"},
      "capabilities": {"modes": ["text_to_video"], "models": ["wan-2.1"]}
    }
  ]
}
```

### Generate Video

```bash
POST /api/v1/videos/{video_id}/generate
Content-Type: application/json

{
  "provider": "comfyui"
}
```

This generates all planned shots in the video project. Each shot specifies its own prompt, resolution, and frame count.

### Create a Shot

```bash
POST /api/v1/videos/{video_id}/shots
Content-Type: application/json

{
  "prompt": "A cinematic shot of ocean waves at golden hour, slow motion",
  "negative_prompt": "blurry, low quality, distorted",
  "model": "wan-2.1",
  "duration_seconds": 2.0,
  "fps": 24,
  "resolution": "832x480",
  "camera_motion": "slow_pan_right"
}
```

## Model Caching Strategy

WAN 2.1 is registered in the model cache (`backend/providers/vast/model_cache.py`):

```python
KNOWN_MODELS = {
    "wan-2.1-t2v": {
        "filename": "wan2.1_t2v_14B_bf16.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "Wan-AI/Wan2.1-T2V-14B",
        "size_gb": 28.3,
    },
    "wan-2.1-i2v": {
        "filename": "wan2.1_i2v_14B_bf16.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "Wan-AI/Wan2.1-I2V-14B-720P",
        "size_gb": 28.3,
    },
}
```

Download priority:
1. Local file (already on worker)
2. Backblaze B2 cache (fast CDN download)
3. HuggingFace Hub (fallback, may be rate-limited)

For production, pre-cache the model to B2:
```bash
# Download from HF, then upload to B2
python -c "
from backend.providers.vast.model_cache import smart_download, upload_to_cache
path = smart_download('checkpoint', 'wan2.1_t2v_14B_bf16.safetensors', '/tmp/models', hf_repo='Wan-AI/Wan2.1-T2V-14B', hf_filename='diffusion_pytorch_model.safetensors')
upload_to_cache(path, 'checkpoint', 'wan2.1_t2v_14B_bf16.safetensors')
"
```

## Resolution and Frame Count Recommendations

| Use Case        | Resolution | Frames | Duration | Notes                    |
|----------------|-----------|--------|----------|--------------------------|
| Instagram Reel | 832x480   | 49     | 2.0s     | Landscape, default       |
| Portrait Reel  | 480x832   | 49     | 2.0s     | Vertical 9:16            |
| Quick test     | 512x320   | 17     | 0.7s     | Low VRAM, fast iteration |
| High quality   | 1280x720  | 81     | 3.4s     | Needs 80GB+ VRAM         |

Frame count notes:
- WAN 2.1 works best with frame counts of `4n + 1` (17, 21, 25, 33, 49, 65, 81)
- More frames = more VRAM + longer generation time
- At 24fps: 49 frames = ~2 seconds, 81 frames = ~3.4 seconds

## Configuration

Environment variables:

```bash
# ComfyUI connection
COMFYUI_BASE_URL=http://localhost:8188    # ComfyUI HTTP endpoint (via SSH tunnel)
COMFYUI_API_TIMEOUT=600                   # Max wait time for video gen (seconds)
COMFYUI_WORKFLOWS_DIR=./workflows/comfyui # Workflow template directory
COMFYUI_VIDEO_WORKFLOW=wan21_t2v_simple   # Default video workflow template

# Provider selection
VIDEO_GENERATION_PROVIDER=simulation      # Default: simulation | comfyui
```

## Current Limitations

1. **Custom nodes required** — Native WAN workflow needs ComfyUI-WanVideoWrapper extension
2. **Single GPU** — No multi-GPU batching yet; one video at a time
3. **No image-to-video** — Only text-to-video workflow implemented (i2v is planned)
4. **Frame coherence** — Simple workflow uses batch latents (no true temporal modeling)
5. **Output format** — Currently WebP (simple) or MP4 (native); no format selection yet
6. **No streaming** — Client must wait for full generation; no progressive preview
