"""Celery application configuration.

Defines the Celery app instance used by all background tasks.
Tasks are autodiscovered from backend/app/workers/tasks/.

Start worker with:
    celery -A backend.app.workers.celery_app worker --loglevel=info

Start beat (scheduler) with:
    celery -A backend.app.workers.celery_app beat --loglevel=info
"""

from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

app = Celery(
    "ai_studio",
    broker=REDIS_URL,
    backend=RESULT_BACKEND,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=14400,  # 4 hours max per task
    task_soft_time_limit=13800,  # Soft limit 3h50m (warns before hard kill)
    worker_prefetch_multiplier=1,  # One task at a time per worker
    task_acks_late=True,  # Don't ack until task completes (retry on crash)
)

# Autodiscover tasks
app.autodiscover_tasks(["backend.app.workers.tasks"])
