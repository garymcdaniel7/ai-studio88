"""AI Studio Workflow Engine

Orchestrates multi-step workflows by spawning child jobs in dependency order.

A workflow definition contains steps, each of which maps to a job type
from the JOB_HANDLERS registry. Steps declare dependencies via `depends_on`
(list of step indices). The engine:

1. Creates a workflow_run record
2. Spawns jobs for steps whose dependencies are met
3. Polls until all steps complete (or one fails)
4. Aggregates outputs

Usage:
    from backend.workflow_engine import execute_workflow
    result = execute_workflow(workflow_id, input_data)

Step schema (inside workflow.steps JSONB array):
    {
        "name": "Generate Portrait",
        "handler": "image_generation",
        "config": {"prompt": "luxury portrait", "width": 1024, "height": 1024},
        "depends_on": []       # indices of steps that must complete first
    }
"""
from __future__ import annotations

import time
from typing import Any

from backend.database import (
    get_workflow_by_id,
    create_workflow_run,
    update_workflow_run,
    get_workflow_run,
    create_job,
    get_job_by_id,
    update_job,
    complete_job,
    fail_job,
)
from backend.worker import JOB_HANDLERS, SimulationHandler


def execute_workflow(workflow_id: str, run_input: dict | None = None) -> dict:
    """Execute a workflow synchronously (for testing/development).

    In production, this would be async with the worker handling each step.

    Args:
        workflow_id: UUID of the workflow to execute
        run_input: Optional input data to pass to the workflow run

    Returns:
        dict with run_id, status, and aggregated outputs
    """
    # Load workflow definition
    workflow = get_workflow_by_id(workflow_id).data
    steps = workflow.get("steps", [])

    if not steps:
        raise ValueError("Workflow has no steps defined")

    total_steps = len(steps)

    # Create a workflow run
    run_result = create_workflow_run({
        "workflow_id": workflow_id,
        "status": "running",
        "input": run_input or {},
        "total_steps": total_steps,
        "current_step": 0,
    })
    run = run_result.data[0]
    run_id = run["id"]

    print(f"Workflow run started: {run_id}")
    print(f"  Workflow: {workflow['name']} (v{workflow['version']})")
    print(f"  Steps: {total_steps}")
    print()

    # Track step results
    step_results: list[dict | None] = [None] * total_steps
    step_job_ids: list[str | None] = [None] * total_steps
    step_statuses: list[str] = ["pending"] * total_steps

    try:
        # Execute steps respecting dependencies
        completed_count = 0
        while completed_count < total_steps:
            made_progress = False

            for i, step in enumerate(steps):
                # Skip already completed/failed/running steps
                if step_statuses[i] in ("completed", "failed", "running"):
                    continue

                # Check if dependencies are met
                depends_on = step.get("depends_on", [])
                deps_met = all(
                    step_statuses[dep] == "completed" for dep in depends_on
                )

                if not deps_met:
                    continue

                # Execute this step
                step_name = step.get("name", f"Step {i + 1}")
                handler_type = step.get("handler", "image_generation")
                config = step.get("config", {})

                # Merge outputs from dependencies into this step's input
                merged_input = {**config}
                for dep_idx in depends_on:
                    if step_results[dep_idx]:
                        merged_input[f"step_{dep_idx}_output"] = step_results[dep_idx]

                print(f"  [{i + 1}/{total_steps}] Running: {step_name} ({handler_type})")

                # Create a child job
                job_data = create_job({
                    "type": handler_type,
                    "status": "queued",
                    "priority": 7,
                    "input": merged_input,
                    "workflow_id": workflow_id,
                }).data[0]
                job_id = job_data["id"]
                step_job_ids[i] = job_id
                step_statuses[i] = "running"

                # Execute via handler (synchronous for now)
                handler_class = JOB_HANDLERS.get(handler_type, SimulationHandler)
                handler = handler_class()

                # Mark job as running
                update_job(job_id, {
                    "status": "running",
                    "worker_name": "workflow-engine",
                    "worker_id": f"wf-{run_id[:8]}",
                    "started_at": "now()",
                })

                try:
                    output = handler.execute(
                        {**job_data, "input": merged_input},
                        lambda p: update_job(job_id, {"progress": p}),
                    )
                    complete_job(job_id, output)
                    step_results[i] = output
                    step_statuses[i] = "completed"
                    completed_count += 1
                    made_progress = True
                    print(f"  [{i + 1}/{total_steps}] Completed: {step_name}")
                except Exception as e:
                    fail_job(job_id, str(e))
                    step_statuses[i] = "failed"
                    print(f"  [{i + 1}/{total_steps}] Failed: {step_name} — {e}")
                    # Fail the entire run
                    update_workflow_run(run_id, {
                        "status": "failed",
                        "current_step": i + 1,
                        "error": f"Step '{step_name}' failed: {e}",
                        "output": {"step_results": step_results, "step_statuses": step_statuses},
                    })
                    return {
                        "run_id": run_id,
                        "status": "failed",
                        "failed_step": i,
                        "error": str(e),
                        "step_results": step_results,
                    }

                # Update run progress
                update_workflow_run(run_id, {
                    "current_step": completed_count,
                })

            # Safety: if no progress was made and we're not done, there's a dependency cycle
            if not made_progress and completed_count < total_steps:
                error = "Dependency cycle detected or unresolvable dependencies"
                update_workflow_run(run_id, {
                    "status": "failed",
                    "error": error,
                    "output": {"step_statuses": step_statuses},
                })
                return {
                    "run_id": run_id,
                    "status": "failed",
                    "error": error,
                    "step_statuses": step_statuses,
                }

        # All steps completed
        aggregated_output = {
            "step_results": step_results,
            "step_job_ids": step_job_ids,
            "total_steps": total_steps,
            "completed_steps": completed_count,
        }

        update_workflow_run(run_id, {
            "status": "completed",
            "current_step": total_steps,
            "output": aggregated_output,
            "completed_at": "now()",
        })

        print(f"\n  Workflow run completed: {run_id}")
        return {
            "run_id": run_id,
            "status": "completed",
            "output": aggregated_output,
        }

    except Exception as e:
        update_workflow_run(run_id, {
            "status": "failed",
            "error": str(e),
        })
        raise
