"""AI Studio Job Worker

A lightweight worker that polls for queued jobs, claims them, and executes
the appropriate handler. Designed for future multi-worker, multi-GPU deployment.

Usage:
    # Run from repo root
    uv run python -m backend.worker --org-id <org-uuid>

    # With custom settings
    uv run python -m backend.worker --name gpu-worker-1 --poll-interval 5 --org-id <org-uuid>

Architecture:
    - Workers poll Supabase for queued jobs (highest priority first)
    - Each job type maps to a handler via the JOB_HANDLERS registry
    - Handlers implement the BaseHandler interface
    - Workers report progress back to Supabase during execution
    - On completion, output is stored in the job record
    - On failure, error is recorded and retry logic applies

Future:
    - Replace polling with Redis/Celery queue
    - Add GPU provisioning (Vast.ai, RunPod)
    - Support distributed locking for multi-worker
    - Add health endpoint for worker monitoring
"""

from __future__ import annotations

import argparse
import math
import signal
import time
import uuid
from collections.abc import Callable
from typing import Any

from backend import cost_ledger  # noqa: F401 - compatibility for worker test hooks
from backend.database import (
    claim_next_job,
    complete_job,
    fail_job,
    update_job,
)
from backend.generation_cost_gate import execute_with_cost_gate
from backend.handlers.base import BaseHandler  # re-exported for compatibility
from backend.handlers.image_handler import ImageGenerationHandler
from backend.handlers.lora_handler import LoraTrainingHandler
from backend.handlers.video_handler import VideoGenerationHandler


def validate_worker_org_id(org_id: str | None) -> str:
    """Validate and normalize the worker's required organization UUID."""
    if not org_id:
        raise ValueError("--org-id is required; worker organization context is missing")
    try:
        return str(uuid.UUID(org_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"--org-id must be a valid UUID: {org_id!r}") from exc


def _org_id_argument(value: str) -> str:
    """Validate an argparse organization value before worker startup."""
    try:
        return validate_worker_org_id(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


# =============================================================================
# Handler Interface
# =============================================================================


# =============================================================================
# Simulation Handler (development/testing)
# =============================================================================


class SimulationHandler(BaseHandler):
    """Simulates job processing for development and testing.

    Produces fake output after a configurable delay with progress updates.
    """

    @property
    def name(self) -> str:
        return "simulation"

    def execute(self, job: dict, report_progress) -> dict:
        job_type = job.get("type", "unknown")
        input_data = job.get("input", {})
        steps = input_data.get("steps", 5)
        step_delay = input_data.get("step_delay", 1.0)

        print(f"    [sim] Processing {job_type} with {steps} steps...")

        for step in range(1, steps + 1):
            time.sleep(step_delay)
            progress = int((step / steps) * 100)
            report_progress(progress)
            print(f"    [sim] Step {step}/{steps} — {progress}%")

        # Generate simulated output based on job type
        output = {
            "handler": "simulation",
            "job_type": job_type,
            "steps_completed": steps,
            "message": f"Simulated {job_type} completed successfully",
        }

        # Add type-specific fake output
        if job_type == "image_generation":
            output["image_url"] = "https://example.com/simulated_output.png"
            output["width"] = input_data.get("width", 1024)
            output["height"] = input_data.get("height", 1024)
        elif job_type == "video_generation":
            output["video_url"] = "https://example.com/simulated_output.mp4"
            output["duration_seconds"] = input_data.get("duration", 5)
        elif job_type == "lora_training":
            output["model_path"] = "models/simulated_lora_v1.safetensors"
            output["training_steps"] = input_data.get("training_steps", 1000)

        return output


# =============================================================================
# Handler Registry
# =============================================================================
# Register new handlers here. The worker dispatches jobs based on this mapping.
# When a real handler is built, replace SimulationHandler with the real class.
#
# Example:
#   from backend.handlers.flux import FluxHandler
#   JOB_HANDLERS["image_generation"] = FluxHandler
#

# JOB_HANDLERS is defined after the simulation handler so all handler classes
# are available when the registry is constructed.

JOB_HANDLERS: dict[str, type[BaseHandler]] = {
    "image_generation": ImageGenerationHandler,
    "video_generation": VideoGenerationHandler,
    "lora_training": LoraTrainingHandler,
    "image_upscale": SimulationHandler,
    "image_edit": SimulationHandler,
    "voice_generation": SimulationHandler,
    "workflow_execution": SimulationHandler,
    "asset_processing": SimulationHandler,
    "publishing": SimulationHandler,
}


# =============================================================================
# Canonical Handler Dispatch / Cost Gate
# =============================================================================


_COST_GATED_JOB_TYPES = frozenset({
    "image_generation",
    "video_generation",
    "lora_training",
})


def _job_input(job: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized input payload for a persisted job."""
    value = job.get("input", {})
    return value if isinstance(value, dict) else {}


def _estimated_cost(job: dict[str, Any]) -> float:
    """Read and validate the provider estimate required before GPU execution."""
    input_data = _job_input(job)
    value = job.get("estimated_cost_usd")
    if value is None:
        value = input_data.get("estimated_cost_usd")
    if value is None:
        raise ValueError("estimated_cost_usd is required before provider execution")

    try:
        estimate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("estimated_cost_usd must be a finite positive number") from exc
    if not math.isfinite(estimate) or estimate <= 0:
        raise ValueError("estimated_cost_usd must be a finite positive number")
    return estimate


def _actual_cost(job: dict[str, Any], output: dict[str, Any], estimate: float) -> float:
    """Use provider-reported cost, falling back to the pre-dispatch estimate."""
    input_data = _job_input(job)
    value: Any = output.get("actual_cost_usd")
    if value is None:
        value = output.get("cost_usd")
    if value is None:
        value = job.get("actual_cost_usd")
    if value is None:
        value = input_data.get("actual_cost_usd")
    if value is None:
        return estimate

    try:
        actual = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("actual cost must be a finite non-negative number") from exc
    if not math.isfinite(actual) or actual < 0:
        raise ValueError("actual cost must be a finite non-negative number")
    return actual


def execute_handler_with_cost_gate(
    job: dict[str, Any],
    handler: BaseHandler,
    report_progress: Callable[[int], None],
    org_id: str,
) -> dict[str, Any]:
    """Execute a worker handler through the shared synchronous cost boundary.

    ``Worker._process_job``, workflow execution, and the legacy
    ``GenerationEngine`` dispatch all use the same reservation/finalization/
    release helper. Provider-backed handlers must supply a positive estimate,
    which is reserved for the trusted ``org_id`` and persisted ``job_id``
    before health checks, provisioning, or provider execution.
    """
    job_id = str(job.get("id", ""))
    if not job_id:
        raise ValueError("job id is required before provider execution")
    if not org_id:
        raise ValueError("org_id is required before provider execution")
    persisted_org_id = job.get("org_id")
    if persisted_org_id and str(persisted_org_id) != org_id:
        raise ValueError("job organization does not match worker organization")

    job_type = str(job.get("type") or handler.name)
    if job_type not in _COST_GATED_JOB_TYPES:
        return handler.execute(job, report_progress)

    estimate = _estimated_cost(job)
    input_data = _job_input(job)
    provider = str(job.get("provider") or input_data.get("provider") or handler.name)
    return execute_with_cost_gate(
        org_id=org_id,
        job_id=job_id,
        operation=f"worker:{job_type}",
        provider=provider,
        estimated_cost_usd=estimate,
        execute=lambda: handler.execute(job, report_progress),
        actual_cost=lambda output, fallback: _actual_cost(job, output, fallback),
    )


# =============================================================================
# Worker
# =============================================================================


class Worker:
    """Job worker that polls for and processes queued jobs."""

    def __init__(self, name: str = "worker", poll_interval: int = 3, org_id: str | None = None) -> None:
        self.name = name
        self.worker_id = f"{name}-{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval
        self.org_id = validate_worker_org_id(org_id)
        self.running = True

    def _report_progress(self, job_id: str, progress: int) -> None:
        """Report job progress to Supabase."""
        try:
            update_job(job_id, {"progress": min(max(progress, 0), 100)}, self.org_id)
        except Exception as e:
            print(f"  [warn] Failed to report progress: {e}")

    def _process_job(self, job: dict) -> None:
        """Process a single job using the appropriate handler."""
        job_id = job["id"]
        job_type = job.get("type", "unknown")

        print(f"  Processing job {job_id[:8]}... (type={job_type})")

        # Get handler
        handler_class = JOB_HANDLERS.get(job_type)
        if not handler_class:
            fail_job(job_id, f"No handler registered for job type: {job_type}", self.org_id)
            print(f"  [error] No handler for type: {job_type}")
            return

        handler = handler_class()

        # Execute with progress reporting
        try:
            output = execute_handler_with_cost_gate(
                job,
                handler,
                lambda progress: self._report_progress(job_id, progress),
                self.org_id,
            )
            complete_job(job_id, output, self.org_id)
            print(f"  [done] Job {job_id[:8]} completed by {handler.name}")
        except Exception as e:
            error_msg = f"{handler.name} failed: {str(e)}"
            fail_job(job_id, error_msg, self.org_id)
            print(f"  [fail] Job {job_id[:8]}: {error_msg}")

    def run(self) -> None:
        """Main worker loop. Polls for jobs until stopped."""
        print(f"Worker started: {self.worker_id}")
        print(f"  Poll interval: {self.poll_interval}s")
        print(f"  Registered handlers: {list(JOB_HANDLERS.keys())}")
        print()

        while self.running:
            try:
                job = claim_next_job(self.name, self.worker_id, self.org_id)
                if job:
                    self._process_job(job)
                else:
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"  [error] Worker loop error: {e}")
                time.sleep(self.poll_interval)

        print(f"\nWorker {self.worker_id} stopped.")

    def stop(self) -> None:
        """Signal the worker to stop after current job completes."""
        self.running = False


# =============================================================================
# CLI Entry Point
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Studio Job Worker")
    parser.add_argument("--name", default="worker", help="Worker name (default: worker)")
    parser.add_argument(
        "--poll-interval", type=int, default=3, help="Seconds between polls (default: 3)"
    )
    parser.add_argument(
        "--org-id",
        required=True,
        type=_org_id_argument,
        help="Tenant org_id UUID to scope job claiming (required)",
    )
    args = parser.parse_args()

    worker = Worker(name=args.name, poll_interval=args.poll_interval, org_id=args.org_id)

    # Handle graceful shutdown
    def signal_handler(sig, frame) -> None:
        print("\nShutdown signal received...")
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    worker.run()


if __name__ == "__main__":
    main()
