---
inclusion: always
---

# GPU Worker Architecture

## Overview

GPU jobs are dispatched to ephemeral cloud instances on Vast.ai (primary) or RunPod (secondary). Workers are not persistent servers — they are created per-job and destroyed on completion.

## Job lifecycle

```
Client POST /api/v1/jobs
  → JobService creates job record (status=queued)
  → Celery task enqueued
  → Worker task picks up job
    → Provisions Vast.ai instance
    → Waits for instance ready
    → Uploads workflow + inputs to instance
    → Executes ComfyUI or training script
    → Monitors progress
    → Downloads output
    → Uploads output to B2
    → Updates job record (status=completed, output_asset_ids=[...])
    → Terminates GPU instance
  → Client polls GET /api/v1/jobs/{id} or subscribes to Realtime
```

## Celery task structure

```
app/workers/
  celery_app.py          ← Celery application instance
  tasks/
    generation.py        ← image_generation, video_generation
    training.py          ← lora_training
    upload.py            ← b2_upload, b2_download
```

## Key rules

1. **Always terminate** GPU instances after job completion or failure
2. **Always set a timeout** — default 30 min for generation, 4 hrs for training
3. **Always retry on transient failures** — network errors, instance startup failures (max 3 retries)
4. **Never retry on content failures** — bad workflow, missing model (fail fast)
5. **Cost gate** — reject jobs that exceed org cost limits before provisioning
6. **Idempotency** — checking job status before provisioning prevents double-billing

## Error handling

```python
try:
    result = await run_generation_job(job)
except VastAiProvisionError as exc:
    # Retry — transient infrastructure failure
    raise self.retry(exc=exc, countdown=60, max_retries=3)
except ComfyUIWorkflowError as exc:
    # Don't retry — bad workflow
    await update_job_status(job.id, "failed", error=str(exc))
    raise
finally:
    # ALWAYS clean up GPU instance
    await terminate_instance_if_running(instance_id)
```

## Cost tracking

- Record `cost_usd` on every completed job
- Log `gpu_provider`, `gpu_type`, `instance_id`, `runtime_seconds`
- Aggregate daily/monthly costs per org for billing
