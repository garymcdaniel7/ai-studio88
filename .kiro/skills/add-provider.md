# Skill: Add a New Provider

## Purpose

Add a new generation, video, training, or editing provider to AI Studio.

## Provider types and interfaces

| Type | Interface | Location |
|---|---|---|
| Image/Generation | `GenerationProvider` | `backend/engine/provider.py` |
| Video | `VideoProvider` | `backend/video/provider.py` |
| Training | `TrainingProvider` | `backend/training/provider.py` |
| Editing | `EditingProvider` | `backend/video/provider.py` |
| Execution | `ExecutionProvider` | `backend/execution/provider_interface.py` |
| LLM | `LLMProvider` | `backend/intelligence_engine/llm_provider.py` |

## Steps

1. Create provider file: `backend/{package}/providers/{name}.py`
2. Implement the interface (health, submit, cancel, etc.)
3. Register in the `PROVIDERS` dict in the corresponding module
4. Add env var to `.env.example` (never modify `.env`)
5. Test with `GENERATION_PROVIDER={name}` or equivalent

## Example: Adding a WAN video provider

```python
# backend/video/providers/wan.py (future)
from backend.video.provider import VideoProvider, VideoRequest, VideoResult

class WanVideoProvider(VideoProvider):
    @property
    def name(self): return "wan"

    def health(self):
        # Check if WAN model is loaded on the worker
        ...

    def capabilities(self):
        return {"models": ["wan-2.1"], "max_duration": 10, ...}

    def submit(self, request, on_progress=None):
        # Submit to ComfyUI worker running WAN workflow
        ...

    def cancel(self, job_id): ...
```

Then register:
```python
# In backend/video/provider.py
VIDEO_PROVIDERS["wan"] = WanVideoProvider
```

## Key rules

- No provider-specific code outside the provider file
- Provider never imports from other providers
- All communication through the standard interface
- Provider reads config from environment variables
- Heavy compute NEVER runs in the provider class itself — it dispatches to a worker
