# Skill: Create ComfyUI Workflow Integration

## Purpose

Integrate a new ComfyUI workflow including storage, parameterisation, and API exposure.

## Steps

### 1. Export workflow

In ComfyUI: Settings → Enable Dev Mode → Save (API Format)
Save to: `workflows/{category}/{name}_v1.json`

### 2. Add parameter placeholders

```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": { "text": "__POSITIVE_PROMPT__" }
  },
  "3": {
    "class_type": "KSampler",
    "inputs": { "seed": "__SEED__", "steps": "__STEPS__" }
  }
}
```

### 3. Create schema

```python
class FluxPortraitParams(BaseSchema):
    positive_prompt: str = Field(min_length=1, max_length=2000)
    steps: int = Field(default=20, ge=1, le=50)
    seed: int = Field(default=-1)
    width: int = Field(default=1024, ge=512, le=2048)
    height: int = Field(default=1024, ge=512, le=2048)
```

### 4. Register in job system

```python
WORKFLOW_REGISTRY = {
    "flux_portrait_v1": {
        "path": "image/flux_portrait_v1.json",
        "params_schema": FluxPortraitParams,
        "gpu_vram_gb": 24,
        "estimated_minutes": 3,
    },
}
```

## Versioning rules

- Never modify a workflow used in production jobs
- New version = new filename (`_v2.json`) + new registry entry
- Old versions kept for job history reproduction
