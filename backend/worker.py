"""AI Studio Job Worker

A lightweight worker that polls for queued jobs, claims them, and executes
the appropriate handler. Designed for future multi-worker, multi-GPU deployment.

Usage:
    # Run from repo root
    uv run python -m backend.worker

    # With custom settings
    uv run python -m backend.worker --name gpu-worker-1 --poll-interval 5

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
import time
import uuid
import signal
import sys
from abc import ABC, abstractmethod
from typing import Any

from backend.database import (
    claim_next_job,
    complete_job,
    fail_job,
    update_job,
)


# =============================================================================
# Handler Interface
# =============================================================================

class BaseHandler(ABC):
    """Base class for all job handlers.

    Implement this interface to add support for a new job type.
    Register the handler in JOB_HANDLERS below.
    """

    @abstractmethod
    def execute(self, job: dict, report_progress: Any) -> dict:
        """Execute the job and return output data.

        Args:
            job: Full job record from Supabase (includes input, type, etc.)
            report_progress: Callable(progress: int) to report 0-100 progress

        Returns:
            dict: Output data to store in job.output

        Raises:
            Exception: Any exception will mark the job as failed
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable handler name."""
        ...


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

JOB_HANDLERS: dict[str, type[BaseHandler]] = {
    "image_generation": SimulationHandler,
    "video_generation": SimulationHandler,
    "lora_training": SimulationHandler,
    "image_upscale": SimulationHandler,
    "image_edit": SimulationHandler,
    "voice_generation": SimulationHandler,
    "workflow_execution": SimulationHandler,
    "asset_processing": SimulationHandler,
    "publishing": SimulationHandler,
}


# =============================================================================
# Worker
# =============================================================================

class Worker:
    """Job worker that polls for and processes queued jobs."""

    def __init__(self, name: str = "worker", poll_interval: int = 3):
        self.name = name
        self.worker_id = f"{name}-{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval
        self.running = True

    def _report_progress(self, job_id: str, progress: int) -> None:
        """Report job progress to Supabase."""
        try:
            update_job(job_id, {"progress": min(max(progress, 0), 100)})
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
            fail_job(job_id, f"No handler registered for job type: {job_type}")
            print(f"  [error] No handler for type: {job_type}")
            return

        handler = handler_class()

        # Execute with progress reporting
        try:
            output = handler.execute(
                job,
                lambda progress: self._report_progress(job_id, progress),
            )
            complete_job(job_id, output)
            print(f"  [done] Job {job_id[:8]} completed by {handler.name}")
        except Exception as e:
            error_msg = f"{handler.name} failed: {str(e)}"
            fail_job(job_id, error_msg)
            print(f"  [fail] Job {job_id[:8]}: {error_msg}")

    def run(self) -> None:
        """Main worker loop. Polls for jobs until stopped."""
        print(f"Worker started: {self.worker_id}")
        print(f"  Poll interval: {self.poll_interval}s")
        print(f"  Registered handlers: {list(JOB_HANDLERS.keys())}")
        print()

        while self.running:
            try:
                job = claim_next_job(self.name, self.worker_id)
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

def main():
    parser = argparse.ArgumentParser(description="AI Studio Job Worker")
    parser.add_argument("--name", default="worker", help="Worker name (default: worker)")
    parser.add_argument("--poll-interval", type=int, default=3, help="Seconds between polls (default: 3)")
    args = parser.parse_args()

    worker = Worker(name=args.name, poll_interval=args.poll_interval)

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutdown signal received...")
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    worker.run()


if __name__ == "__main__":
    main()
