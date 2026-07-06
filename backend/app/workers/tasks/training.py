"""Training tasks — LoRA training dispatched to GPU workers."""
from __future__ import annotations

from backend.app.workers.celery_app import app


@app.task(bind=True, name="training.lora", max_retries=1, time_limit=14400)
def train_lora_task(self, dataset_id: str, config: dict, job_id: str = ""):
    """Train a LoRA model on a GPU worker.

    This is the production replacement for the threading approach.
    When Celery+Redis are running, training jobs route here instead.

    Time limit: 4 hours.
    """
    return {
        "status": "celery_task_placeholder",
        "dataset_id": dataset_id,
        "job_id": job_id,
        "message": "Celery worker not running. Training falls back to thread mode.",
    }
