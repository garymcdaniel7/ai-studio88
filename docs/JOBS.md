# AI Studio — Job Engine

> Sprint 2 implementation. The backbone for all async AI generation work.

---

## Overview

The Job Engine handles all asynchronous processing in AI Studio — image generation, video generation, LoRA training, and any future workload. It is deliberately model-agnostic and provider-agnostic.

---

## Job Lifecycle

```
                    ┌─────────┐
         POST /jobs │ queued  │
                    └────┬────┘
                         │ worker claims
                    ┌────▼────┐
                    │ running │ ← progress updates (0-100%)
                    └────┬────┘
                   ╱     │     ╲
           success │     │      │ failure
          ┌────────▼┐    │   ┌──▼─────┐
          │completed│    │   │ failed │
          └─────────┘    │   └──┬─────┘
                         │      │ POST /retry
                    ┌────▼────┐ │
                    │cancelled│◄┘ (if retries remain)
                    └─────────┘
```

### Status transitions

| From | To | Trigger |
|---|---|---|
| queued | running | Worker claims the job |
| queued | cancelled | User cancels |
| running | completed | Handler finishes successfully |
| running | failed | Handler throws exception |
| running | cancelled | User cancels |
| failed | queued | User retries (if attempts < max_attempts) |
| cancelled | queued | User retries |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/jobs` | Create and queue a new job |
| GET | `/api/v1/jobs` | List jobs (filter by `?status=` and `?type=`) |
| GET | `/api/v1/jobs/{id}` | Get single job with full detail |
| DELETE | `/api/v1/jobs/{id}` | Delete a non-running job |
| POST | `/api/v1/jobs/{id}/cancel` | Cancel a queued or running job |
| POST | `/api/v1/jobs/{id}/retry` | Reset a failed/cancelled job to queued |

---

## Curl Examples

```bash
# Create an image generation job
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "type": "image_generation",
    "priority": 8,
    "input": {
      "prompt": "luxury portrait of AI influencer",
      "width": 1024,
      "height": 1024,
      "steps": 20
    },
    "talent_id": "d2349ed1-afb5-4b6b-858f-4b91c1de25cb"
  }'

# Create a video generation job
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "type": "video_generation",
    "priority": 5,
    "input": {"prompt": "cinematic b-roll", "duration": 5}
  }'

# List all queued jobs
curl http://localhost:8000/api/v1/jobs?status=queued

# List only image generation jobs
curl http://localhost:8000/api/v1/jobs?type=image_generation

# Get job details
curl http://localhost:8000/api/v1/jobs/{job_id}

# Cancel a job
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/cancel

# Retry a failed job
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/retry

# Delete a job
curl -X DELETE http://localhost:8000/api/v1/jobs/{job_id}
```

---

## Supported Job Types

| Type | Description | Handler (current) |
|---|---|---|
| `image_generation` | Generate images (Flux, SDXL) | SimulationHandler |
| `video_generation` | Generate video (WAN, LTX) | SimulationHandler |
| `lora_training` | Fine-tune LoRA models | SimulationHandler |
| `image_upscale` | Upscale existing images | SimulationHandler |
| `image_edit` | Edit/inpaint images | SimulationHandler |
| `voice_generation` | Generate voice audio | SimulationHandler |
| `workflow_execution` | Run arbitrary ComfyUI workflow | SimulationHandler |
| `asset_processing` | Post-process assets | SimulationHandler |
| `publishing` | Publish content to platforms | SimulationHandler |

All handlers currently use `SimulationHandler` for development. Real handlers will be plugged in as GPU integration is built.

---

## Worker Architecture

### Running the worker

```bash
# From repo root
uv run python -m backend.worker

# With custom name (for multi-worker setups)
uv run python -m backend.worker --name gpu-worker-1 --poll-interval 5
```

### Worker loop

1. Poll Supabase for the highest-priority queued job
2. Claim it atomically (optimistic lock via status check)
3. Instantiate the appropriate handler from `JOB_HANDLERS`
4. Execute with progress reporting
5. On success: store output, mark completed
6. On failure: store error, mark failed
7. Repeat

### Handler Registry

```python
# backend/worker.py

JOB_HANDLERS = {
    "image_generation": SimulationHandler,  # → FluxHandler (future)
    "video_generation": SimulationHandler,  # → WanHandler (future)
    "lora_training":    SimulationHandler,  # → LoraTrainer (future)
    ...
}
```

To add a new handler:
1. Create a class inheriting from `BaseHandler`
2. Implement `execute(job, report_progress) → dict`
3. Register it in `JOB_HANDLERS`

### BaseHandler Interface

```python
class BaseHandler(ABC):
    @abstractmethod
    def execute(self, job: dict, report_progress) -> dict:
        """Execute the job.
        
        Args:
            job: Full job record (includes input, type, etc.)
            report_progress: Callable(int) for 0-100 progress updates
            
        Returns:
            Output dict stored in job.output
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable handler name."""
        ...
```

---

## Future GPU Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Job Queue (Supabase)                   │
│        Priority-sorted, status=queued, optimistic lock   │
└──────────────┬─────────────────────────┬────────────────┘
               │                         │
    ┌──────────▼──────────┐   ┌──────────▼──────────┐
    │  Local Worker       │   │  GPU Worker (Vast.ai)│
    │  (development)      │   │                      │
    │  SimulationHandler  │   │  FluxHandler         │
    │                     │   │  WanHandler          │
    │                     │   │  LoraTrainer         │
    └─────────────────────┘   └──────────▲───────────┘
                                         │
                              ┌──────────┴──────────┐
                              │  GPU Instance        │
                              │  - ComfyUI           │
                              │  - Model weights     │
                              │  - Ephemeral (per-job)│
                              └─────────────────────┘
```

### Multi-worker design

- Workers identify themselves with `worker_name` + unique `worker_id`
- Claiming uses optimistic locking (UPDATE WHERE status='queued')
- Multiple workers can run in parallel safely
- Future: Redis-backed queue for guaranteed delivery

### GPU provider support (planned)

| Provider | Status | Use case |
|---|---|---|
| Local GPU | Planned | Development, small jobs |
| Vast.ai | Planned | Spot instances, cost-efficient |
| RunPod | Planned | Serverless, fast cold-start |
| Lambda Labs | Future | A100 training jobs |

---

## Priority System

Jobs are processed highest-priority first (10 = urgent, 1 = background).

| Priority | Use case |
|---|---|
| 9-10 | User-initiated, waiting for result |
| 6-8 | Campaign scheduled content |
| 4-5 | Background batch processing |
| 1-3 | Low-priority archival/cleanup |

Within the same priority level, oldest jobs are processed first (FIFO).

---

## Retry Logic

| Field | Purpose |
|---|---|
| `attempts` | How many times this job has been tried |
| `max_attempts` | Maximum tries before permanent failure (default: 3) |
| `error` | Last error message |

Retry is manual via `POST /jobs/{id}/retry`. Automatic retry on transient failures will be added with the GPU worker integration.
