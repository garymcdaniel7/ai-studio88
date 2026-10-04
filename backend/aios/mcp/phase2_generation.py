"""Authenticated MCP adapters for WRITE/MAKE generation contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.aios.mcp.phase2_common import (
    MCPExecutionContext,
    MCPToolError,
    idempotent_result,
    parse_safe_id,
    reject_org_selectors,
    remember_result,
)
from backend.batch_generation import BatchError, get_batch, submit_batch
from backend.generation_jobs import (
    cancel_job,
    get_job_status,
    list_jobs_for_session,
    submit_generation,
)

_MAX_BATCH_SIZE = 50
_MAX_STEPS = 150
_MAX_DIMENSION = 4096
_ALLOWED_SAMPLERS = frozenset({"euler", "euler_cfg1", "euler_ancestral", "heun", "dpmpp_2m", "ddim"})
_ALLOWED_SCHEDULERS = frozenset({"normal", "karras", "sgm_uniform", "simple", "exponential"})


def _workflows_dir() -> Path:
    """Resolve the configured workflow directory without accepting a client path."""
    return Path(os.getenv("COMFYUI_WORKFLOWS_DIR", "./workflows/comfyui")).resolve()


def _workflow_path(workflow_id: str) -> Path:
    """Resolve one safe local workflow template."""
    if not workflow_id or Path(workflow_id).name != workflow_id or not workflow_id.endswith(".json"):
        workflow_id = f"{workflow_id}.json"
    path = (_workflows_dir() / workflow_id).resolve()
    try:
        path.relative_to(_workflows_dir())
    except ValueError as exc:
        raise MCPToolError("Workflow identifier is invalid", "INVALID_WORKFLOW", 422) from exc
    return path


def _load(workflow_id: str) -> dict[str, Any]:
    """Load and validate a local workflow template."""
    path = _workflow_path(workflow_id)
    if not path.is_file():
        raise MCPToolError("Workflow not found", "WORKFLOW_NOT_FOUND", 404)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MCPToolError("Workflow is not valid JSON", "INVALID_WORKFLOW", 422) from exc
    if not isinstance(data, dict) or not data:
        raise MCPToolError("Workflow must be a non-empty object", "INVALID_WORKFLOW", 422)
    return data


def _validate_controls(params: dict[str, Any]) -> dict[str, Any]:
    """Validate bounded KSampler and generation controls."""
    width = int(params.get("width", 1024))
    height = int(params.get("height", 1024))
    steps = int(params.get("steps", 20))
    cfg = float(params.get("cfg", params.get("cfg_scale", 3.5)))
    if not 256 <= width <= _MAX_DIMENSION or not 256 <= height <= _MAX_DIMENSION:
        raise MCPToolError("width and height must be between 256 and 4096", "INVALID_INPUT", 422)
    if not 1 <= steps <= _MAX_STEPS or not 0 <= cfg <= 30:
        raise MCPToolError("steps or cfg is outside the supported range", "INVALID_INPUT", 422)
    sampler = str(params.get("sampler", params.get("sampler_name", "euler")))
    scheduler = str(params.get("scheduler", "normal"))
    if sampler not in _ALLOWED_SAMPLERS or scheduler not in _ALLOWED_SCHEDULERS:
        raise MCPToolError("Unsupported sampler or scheduler", "INVALID_INPUT", 422)
    return {
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "sampler": sampler,
        "scheduler": scheduler,
        "seed": int(params.get("seed", -1)),
    }


def _estimate_cost(steps: int, width: int, height: int, count: int = 1) -> float:
    """Estimate provider cost before queueing a generation job."""
    pixels = (width * height) / (1024 * 1024)
    return round(max(0.005, 0.005 * (steps / 20) * pixels * count), 4)


def _prompt(params: dict[str, Any]) -> str:
    """Require a bounded prompt without returning it in status responses."""
    value = params.get("prompt")
    if not isinstance(value, str) or not value.strip() or len(value) > 10000:
        raise MCPToolError("prompt is required and must be at most 10000 characters", "INVALID_INPUT", 422)
    return value


def _check_cost(params: dict[str, Any], estimate: float) -> None:
    """Reject a request that explicitly exceeds its caller-supplied cost gate."""
    maximum = params.get("max_cost_usd")
    if maximum is not None and estimate > float(maximum):
        raise MCPToolError("Estimated cost exceeds the requested budget", "COST_GATE_REJECTED", 402)


async def generate_with_ksampler(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Queue an idempotent KSampler-style generation with provenance."""
    reject_org_selectors(params)
    controls = _validate_controls(params)
    prompt = _prompt(params)
    estimate = _estimate_cost(controls["steps"], controls["width"], controls["height"])
    _check_cost(params, estimate)
    key = params.get("idempotency_key")
    prior = idempotent_result(context, "generate_with_ksampler", key)
    if prior:
        return prior
    job = submit_generation(
        org_id=context.org_id,
        user_id=context.user_id,
        session_id=str(params.get("session_id", context.identity.credential_id)),
        prompt=prompt,
        negative_prompt=str(params.get("negative_prompt", ""))[:10000],
        model=str(params.get("model", "flux-dev")),
        width=controls["width"],
        height=controls["height"],
        steps=controls["steps"],
        cfg=controls["cfg"],
        seed=controls["seed"],
        talent_id=str(params["talent_id"]) if params.get("talent_id") else None,
        project_id=str(params["project_id"]) if params.get("project_id") else None,
        lora_ids=[str(value) for value in params.get("lora_ids", [])],
        estimated_cost_usd=estimate,
        idempotency_key=f"{context.org_id}:{key}" if key else "",
    )
    job.effective_settings = {**controls, "workflow_id": params.get("workflow_id"), "provider": "orchestrated"}
    output = {
        "status": job.state.value,
        "job_id": job.id,
        "estimated_cost_usd": estimate,
        "provenance": {"org_id": context.org_id, "model": job.model, "workflow_id": params.get("workflow_id")},
    }
    return remember_result(context, "generate_with_ksampler", key, output)


async def generate_with_workflow(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Validate a workflow template/JSON and queue an asynchronous generation."""
    reject_org_selectors(params)
    workflow_id = str(params.get("workflow_id", ""))
    workflow = params.get("workflow")
    if workflow is None:
        if not workflow_id:
            raise MCPToolError("workflow_id or workflow is required", "INVALID_INPUT", 422)
        workflow = _load(workflow_id)
    if not isinstance(workflow, dict) or not workflow:
        raise MCPToolError("workflow must be a non-empty object", "INVALID_WORKFLOW", 422)
    serialized = json.dumps(workflow)
    if any(marker in serialized.lower() for marker in ("__import__", "eval(", "exec(")):
        raise MCPToolError("Workflow contains a prohibited expression", "INVALID_WORKFLOW", 422)
    controls = _validate_controls(params)
    estimate = _estimate_cost(controls["steps"], controls["width"], controls["height"])
    _check_cost(params, estimate)
    nested = {**params, **controls, "workflow_id": workflow_id or "inline"}
    result = await generate_with_ksampler(nested, context)
    result["workflow_validated"] = True
    return result


async def preview_generation(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Queue the fixed quick-preview contract used by WRITE."""
    return await generate_with_ksampler(
        {**params, "steps": 4, "height": 480, "width": int(params.get("width", 768)), "cfg": 1.0, "scheduler": "simple"},
        context,
    )


async def get_generation_status(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Read one generation status through the job store's tenant predicate."""
    reject_org_selectors(params)
    job_id = parse_safe_id(params.get("job_id"), "job_id")
    result = get_job_status(job_id, context.org_id)
    if result is None:
        raise MCPToolError("Generation job not found", "GENERATION_NOT_FOUND", 404)
    return result


async def get_generation_queue(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """List queue jobs for the authenticated MCP session and tenant."""
    reject_org_selectors(params)
    session_id = str(params.get("session_id", context.identity.credential_id))
    rows = list_jobs_for_session(session_id, context.org_id)
    return {"items": rows, "total": len(rows), "session_id": session_id}


async def list_workflows(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """List local workflow templates without exposing filesystem paths."""
    reject_org_selectors(params)
    directory = _workflows_dir()
    if not directory.is_dir():
        return {"items": [], "total": 0}
    items = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = data.get("_meta", {}) if isinstance(data, dict) else {}
        items.append({"id": path.stem, "name": meta.get("name", path.stem), "description": meta.get("description", ""), "node_count": max(len(data) - 1, 0) if isinstance(data, dict) else 0})
    return {"items": items, "total": len(items)}


async def get_workflow_schema(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Return a workflow's node/input schema after safe local validation."""
    reject_org_selectors(params)
    workflow_id = str(params.get("workflow_id", ""))
    data = _load(workflow_id)
    return {"workflow_id": Path(workflow_id).stem, "schema": data}


async def switch_workflow(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Validate a workflow switch and optionally apply it to an owned active job."""
    reject_org_selectors(params)
    workflow_id = str(params.get("workflow_id", ""))
    _load(workflow_id)
    job_id = params.get("job_id")
    if job_id:
        job_key = parse_safe_id(job_id, "job_id")
        status = get_job_status(job_key, context.org_id)
        if status is None:
            raise MCPToolError("Generation job not found", "GENERATION_NOT_FOUND", 404)
        if status["state"] not in {"queued", "claimed", "running"}:
            raise MCPToolError("Workflow cannot be switched after completion", "INVALID_STATE", 409)
    return {"status": "selected", "workflow_id": Path(workflow_id).stem, "job_id": job_id}


async def generate_batch(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Queue a tenant-scoped, idempotent generation batch."""
    reject_org_selectors(params)
    prompt = _prompt(params)
    count = int(params.get("variation_count", params.get("count", 1)))
    if not 1 <= count <= _MAX_BATCH_SIZE:
        raise MCPToolError("variation_count must be between 1 and 50", "INVALID_INPUT", 422)
    controls = _validate_controls(params)
    estimate = _estimate_cost(controls["steps"], controls["width"], controls["height"], count)
    _check_cost(params, estimate)
    key = params.get("idempotency_key")
    prior = idempotent_result(context, "generate_batch", key)
    if prior:
        return prior
    try:
        batch = submit_batch(
            org_id=context.org_id,
            user_id=context.user_id,
            variation_count=count,
            model=str(params.get("model", "flux-dev")),
            prompt=prompt,
            negative_prompt=str(params.get("negative_prompt", ""))[:10000],
            width=controls["width"],
            height=controls["height"],
            steps=controls["steps"],
            cfg_scale=controls["cfg"],
            seeds=params.get("seeds"),
            cost_per_variation_usd=round(estimate / count, 4),
            idempotency_key=f"{context.org_id}:{key}" if key else "",
        )
    except BatchError as exc:
        raise MCPToolError(exc.message, exc.code, 422) from exc
    output = {"status": batch.state.value, "batch": batch.to_dict()}
    return remember_result(context, "generate_batch", key, output)


async def cancel_generation(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Cancel an owned generation job or batch idempotently."""
    reject_org_selectors(params)
    job_id = parse_safe_id(params.get("job_id", params.get("batch_id")), "job_id")
    if job_id.startswith("batch-"):
        from backend.batch_generation import cancel_batch

        batch = get_batch(job_id)
        if batch is None or batch.org_id != context.org_id:
            raise MCPToolError("Generation batch not found", "GENERATION_NOT_FOUND", 404)
        result = cancel_batch(job_id)
        return {"status": result.state.value, "batch": result.to_dict()}
    result = cancel_job(job_id, context.org_id)
    if result is None:
        raise MCPToolError("Generation job not found", "GENERATION_NOT_FOUND", 404)
    return {"status": result.state.value, **result.to_status()}
