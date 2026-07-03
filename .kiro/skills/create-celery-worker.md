# Skill: Create Celery Worker Task

## Purpose

Create a new Celery task for GPU job processing or background work.

## File location

`backend/app/workers/tasks/{category}.py`

Categories: `generation.py`, `training.py`, `upload.py`, `analytics.py`

## Task template

```python
from celery import shared_task
from celery.utils.log import get_task_logger
import asyncio

logger = get_task_logger(__name__)

@shared_task(
    bind=True,
    name="generation.image_generation",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def image_generation_task(self, job_id: str, **kwargs):
    instance_id = None
    try:
        result = asyncio.run(_run_image_generation(job_id, kwargs))
        return result
    except VastAiProvisionError as exc:
        raise self.retry(exc=exc, countdown=60)   # transient — retry
    except (ComfyUIWorkflowError, ValueError) as exc:
        asyncio.run(_mark_job_failed(job_id, str(exc)))
        raise                                       # content error — don't retry
    finally:
        if instance_id:                             # ALWAYS clean up
            asyncio.run(_terminate_instance(instance_id))
```

## Registering tasks

```python
# app/workers/celery_app.py
celery_app.autodiscover_tasks([
    "app.workers.tasks.generation",
    "app.workers.tasks.training",
    "app.workers.tasks.upload",
])
```

## Submitting from API

```python
result = image_generation_task.apply_async(
    kwargs={"job_id": str(job.id)},
    queue="gpu",
    priority=job.priority,
)
# Store result.id as job.celery_task_id
```

## Best practices

- `acks_late=True` prevents task loss on worker crash
- `reject_on_worker_lost=True` re-queues on crash
- `max_retries=3` for transient errors only
- `finally` block MUST terminate GPU instance
