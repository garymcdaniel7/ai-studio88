---
inclusion: always
---

# ComfyUI Integration Standards

## Overview

ComfyUI is the primary generation engine. Workflows are JSON files stored in `/workflows/`. They are dispatched to GPU instances running ComfyUI and executed via the ComfyUI API.

## Workflow storage

```
workflows/
  image/
    flux_portrait_v1.json
    sdxl_landscape_v1.json
  video/
    wan_short_clip_v1.json
    ltx_video_v1.json
  training/
    lora_flux_v1.json
```

## Workflow parameterisation

Mark user-configurable nodes with `__PLACEHOLDER__` strings:

```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "__POSITIVE_PROMPT__",
      "clip": ["4", 1]
    }
  }
}
```

Replace before submission:

```python
def inject_parameters(workflow: dict, params: dict) -> dict:
    workflow_str = json.dumps(workflow)
    for key, value in params.items():
        workflow_str = workflow_str.replace(f"__{key.upper()}__", str(value))
    return json.loads(workflow_str)
```

## Supported models

| Model | Workflow prefix | Notes |
|---|---|---|
| FLUX.1-dev | `flux_` | Primary image model |
| SDXL | `sdxl_` | Fallback, faster |
| WAN | `wan_` | Video generation |
| LTX Video | `ltx_` | Fast video generation |

## Error handling

```python
class ComfyUIError(Exception):
    """Base ComfyUI exception."""

class ComfyUIWorkflowError(ComfyUIError):
    """Workflow validation or execution error — do not retry."""

class ComfyUIConnectionError(ComfyUIError):
    """Connection failure — retry with backoff."""
```

## GPU instance requirements

- ComfyUI installed at `/workspace/ComfyUI`
- Models at `/workspace/ComfyUI/models/`
- VRAM: minimum 12 GB for FLUX, 8 GB for SDXL
- Storage: 50 GB minimum
- CUDA 11.8+
