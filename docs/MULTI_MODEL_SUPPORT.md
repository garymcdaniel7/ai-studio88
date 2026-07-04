# Multi-Model Workflow Support

The Generation Engine automatically selects the correct ComfyUI workflow template and parameters based on the requested model. This enables seamless switching between different checkpoints without manual workflow configuration.

## How It Works

1. User requests generation with a model name (e.g. `sdxl-turbo`, `sd15`, `flux-dev`)
2. The **Workflow Selector** (`backend/engine/workflow_selector.py`) maps that model to:
   - A ComfyUI workflow template (JSON file in `workflows/comfyui/`)
   - Default generation parameters (steps, CFG, resolution, sampler)
   - The required checkpoint filename
3. The ComfyUI provider loads the template, injects parameters into `__PLACEHOLDER__` fields, and submits to ComfyUI

## Supported Models

| Model ID | Workflow Template | Checkpoint | Resolution | Steps | CFG | Sampler | B2 Cached |
|----------|------------------|------------|------------|-------|-----|---------|-----------|
| `sdxl-turbo` | `sdxl_turbo.json` | `sd_xl_turbo_1.0_fp16.safetensors` | 512x512 | 1 | 1.0 | euler | Yes |
| `sd15` | `sd15_standard.json` | `v1-5-pruned-emaonly.safetensors` | 512x512 | 20 | 7.5 | euler_a | Yes |
| `flux-dev` | `flux_dev.json` | `flux1-dev.safetensors` | 1024x1024 | 20 | 3.5 | euler | No |

## API Endpoint

```
GET /api/v1/generation/available-models
```

Returns all models with configured workflow templates, their defaults, and B2 cache status.

**Response example:**
```json
[
  {
    "id": "sdxl-turbo",
    "workflow_template": "sdxl_turbo",
    "description": "SDXL Turbo — single-step fast generation at 512x512",
    "defaults": {"steps": 1, "cfg": 1.0, "width": 512, "height": 512, "sampler": "euler"},
    "checkpoint": "sd_xl_turbo_1.0_fp16.safetensors",
    "capabilities": ["txt2img"],
    "required_vram_gb": 8.0,
    "cached_in_b2": true
  }
]
```

## Workflow Template Format

Templates are ComfyUI API-format JSON files in `workflows/comfyui/`. They use placeholder strings that get replaced at runtime:

- `__POSITIVE_PROMPT__` — Main generation prompt
- `__NEGATIVE_PROMPT__` — Negative prompt
- `__WIDTH__` — Output width in pixels
- `__HEIGHT__` — Output height in pixels
- `__STEPS__` — Number of sampling steps
- `__CFG__` — Classifier-free guidance scale
- `__SEED__` — Random seed (use -1 for random)

Each template includes a `_meta` key with documentation (stripped before sending to ComfyUI).

## Adding a New Model

1. **Create the workflow template** in `workflows/comfyui/<name>.json`
   - Use an existing template as reference
   - Include the `_meta` documentation block
   - Use placeholder strings for configurable parameters

2. **Register in the workflow map** (`backend/engine/workflow_selector.py`):
   ```python
   WORKFLOW_MAP["new-model"] = {
       "workflow": "template_filename",  # without .json
       "defaults": {"steps": 20, "cfg": 7.0, "width": 1024, "height": 1024, "sampler": "euler"},
       "checkpoint": "model_checkpoint.safetensors",
       "description": "Description of the model",
       "capabilities": ["txt2img", "img2img"],
       "required_vram_gb": 12.0,
   }
   ```

3. **If the checkpoint is in B2**, add it to `B2_CACHED_CHECKPOINTS`:
   ```python
   B2_CACHED_CHECKPOINTS.add("model_checkpoint.safetensors")
   ```

4. **Test** by hitting `GET /api/v1/generation/available-models` to confirm it appears.

## Architecture

```
backend/engine/
├── workflow_selector.py      # Model -> workflow mapping + defaults
├── generation_engine.py      # Orchestrates generation through providers
├── providers/
│   ├── comfyui.py           # Loads templates, injects params, submits to ComfyUI
│   └── simulation.py       # Mock provider for testing
│
workflows/comfyui/
├── sdxl_turbo.json          # SDXL Turbo single-step workflow
├── sd15_standard.json       # SD 1.5 standard workflow
├── flux_dev.json            # Flux Dev workflow
├── flux_text_to_image_basic.json  # Flux basic (legacy)
├── wan21_t2v_native.json    # WAN 2.1 text-to-video
└── wan21_t2v_simple.json    # WAN 2.1 simple video
```
