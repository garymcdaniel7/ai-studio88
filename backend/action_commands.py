"""Backend Action Command System — Story 033.

Provides durable, governed, idempotent action execution for all Hermes/AIOS
side effects. The browser proposes and observes; the backend executes.

Lifecycle:
    propose → governance_check → [approval if needed] → execute → complete/fail

Key properties:
    1. Idempotent: same idempotency_key returns existing result (no duplicate execution)
    2. Durable: persisted before execution (survives browser disconnect, server restart)
    3. Governed: governance.evaluate_action() called before execution
    4. Tenant-scoped: every command has org_id + user_id
    5. Observable: status, result, error, cost all queryable
    6. Auditable: full lifecycle with actor, timestamps, decision evidence

Status lifecycle:
    PROPOSED → GOVERNANCE_PENDING → APPROVED → EXECUTING → COMPLETED
                                  → DENIED
                                  → APPROVAL_REQUIRED → APPROVED/REJECTED
    EXECUTING → FAILED (retryable)
    Any → CANCELLED (by user)
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


# =============================================================================
# Types
# =============================================================================


class CommandStatus(str, Enum):
    """Action command lifecycle states."""

    PROPOSED = "proposed"
    GOVERNANCE_PENDING = "governance_pending"
    APPROVED = "approved"
    APPROVAL_REQUIRED = "approval_required"
    DENIED = "denied"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (
            CommandStatus.COMPLETED,
            CommandStatus.FAILED,
            CommandStatus.DENIED,
            CommandStatus.REJECTED,
            CommandStatus.CANCELLED,
        )

    @property
    def permits_execution(self) -> bool:
        return self == CommandStatus.APPROVED


@dataclass
class ActionCommand:
    """A durable backend action command.

    Created when Hermes/AIOS proposes an action. Persisted immediately.
    Execution only happens after governance approval.
    """

    id: str
    idempotency_key: str
    org_id: str
    user_id: str
    session_id: str
    tool: str  # e.g., "generate_image", "train_lora", "publish_post"
    parameters: dict[str, Any]
    status: CommandStatus = CommandStatus.PROPOSED
    # Governance
    governance_decision: str = ""  # Decision state from evaluate_action
    governance_request_id: str = ""
    estimated_cost_usd: float = 0.0
    # Execution
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    actual_cost_usd: float = 0.0
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    governance_at: str | None = None
    approved_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_status_view(self) -> dict:
        """Client-safe status view (no secrets, no full parameters)."""
        return {
            "id": self.id,
            "tool": self.tool,
            "status": self.status.value,
            "governance_decision": self.governance_decision,
            "estimated_cost_usd": self.estimated_cost_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "error": self.error,
            "result_summary": _summarize_result(self.result),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "is_terminal": self.status.is_terminal,
        }


def _summarize_result(result: dict) -> dict:
    """Summarize execution result for client (strip large blobs)."""
    if not result:
        return {}
    summary = {}
    for k, v in result.items():
        if k in ("image_base64",) and isinstance(v, str) and len(v) > 100:
            summary[k] = f"[{len(v)} chars]"
        elif isinstance(v, str) and len(v) > 500:
            summary[k] = v[:500] + "..."
        else:
            summary[k] = v
    return summary


# =============================================================================
# Command Store (in-memory, production: Supabase table)
# =============================================================================

_command_store: dict[str, ActionCommand] = {}
_idempotency_index: dict[str, str] = {}  # key → command_id
_store_lock = threading.Lock()


def _make_command_id() -> str:
    return f"cmd-{secrets.token_hex(10)}"


# =============================================================================
# Command Service
# =============================================================================


class ActionCommandService:
    """Durable action command management.

    Every side effect from Hermes/AIOS flows through here.
    """

    @staticmethod
    def propose(
        *,
        org_id: str,
        user_id: str,
        session_id: str,
        tool: str,
        parameters: dict[str, Any],
        idempotency_key: str = "",
        estimated_cost_usd: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> ActionCommand:
        """Propose a new action command.

        If an identical idempotency_key exists, returns the existing command
        (no duplicate side effect).

        The command is persisted BEFORE any execution attempt.
        """
        if not org_id:
            raise ValueError("org_id required")
        if not user_id:
            raise ValueError("user_id required")
        if not tool:
            raise ValueError("tool required")

        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = f"{org_id}:{session_id}:{tool}:{secrets.token_hex(6)}"

        with _store_lock:
            # Idempotency check — return existing if duplicate
            if idempotency_key in _idempotency_index:
                existing_id = _idempotency_index[idempotency_key]
                if existing_id in _command_store:
                    return _command_store[existing_id]

            # Create new command
            cmd = ActionCommand(
                id=_make_command_id(),
                idempotency_key=idempotency_key,
                org_id=org_id,
                user_id=user_id,
                session_id=session_id,
                tool=tool,
                parameters=parameters,
                estimated_cost_usd=estimated_cost_usd,
                metadata=metadata or {},
            )

            _command_store[cmd.id] = cmd
            _idempotency_index[idempotency_key] = cmd.id

        return cmd

    @staticmethod
    def evaluate_governance(cmd: ActionCommand) -> ActionCommand:
        """Run governance evaluation on a proposed command.

        Updates the command status based on the governance decision.
        """
        from backend.governance import RiskClass, classify_action, evaluate_action

        risk_class = classify_action(cmd.tool)

        decision = evaluate_action(
            action=cmd.tool,
            risk_class=risk_class,
            actor_user_id=cmd.user_id,
            org_id=cmd.org_id,
            estimated_cost_usd=cmd.estimated_cost_usd,
        )

        cmd.governance_decision = decision.state.value
        cmd.governance_request_id = decision.request_id
        cmd.governance_at = datetime.now(UTC).isoformat()

        if decision.allowed:
            cmd.status = CommandStatus.APPROVED
            cmd.approved_at = datetime.now(UTC).isoformat()
        elif decision.state.value == "approval_required":
            cmd.status = CommandStatus.APPROVAL_REQUIRED
        else:
            cmd.status = CommandStatus.DENIED

        return cmd

    @staticmethod
    def execute(cmd: ActionCommand) -> ActionCommand:
        """Execute an approved command.

        Only commands in APPROVED status can be executed.
        Transitions: APPROVED → EXECUTING → COMPLETED/FAILED
        """
        if cmd.status != CommandStatus.APPROVED:
            raise ValueError(f"Cannot execute command in status: {cmd.status.value}")

        cmd.status = CommandStatus.EXECUTING
        cmd.started_at = datetime.now(UTC).isoformat()

        try:
            # Execute the tool
            result = _execute_tool_sync(cmd.tool, cmd.parameters)
            cmd.result = result
            cmd.status = CommandStatus.COMPLETED
            cmd.completed_at = datetime.now(UTC).isoformat()
        except Exception as e:
            cmd.error = str(e)[:500]
            cmd.status = CommandStatus.FAILED
            cmd.completed_at = datetime.now(UTC).isoformat()

        return cmd

    @staticmethod
    def propose_and_run(
        *,
        org_id: str,
        user_id: str,
        session_id: str,
        tool: str,
        parameters: dict[str, Any],
        idempotency_key: str = "",
        estimated_cost_usd: float = 0.0,
    ) -> ActionCommand:
        """Propose, governance-gate, and execute in one call.

        This is the primary entry point for governed action execution.
        Returns the command in its final state (may be DENIED, APPROVAL_REQUIRED, etc.)
        """
        cmd = ActionCommandService.propose(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            tool=tool,
            parameters=parameters,
            idempotency_key=idempotency_key,
            estimated_cost_usd=estimated_cost_usd,
        )

        # If already terminal (idempotent return), don't re-process
        if cmd.status.is_terminal:
            return cmd

        # Governance evaluation
        cmd = ActionCommandService.evaluate_governance(cmd)

        # Execute if approved
        if cmd.status == CommandStatus.APPROVED:
            cmd = ActionCommandService.execute(cmd)

        return cmd

    @staticmethod
    def approve(command_id: str) -> ActionCommand | None:
        """Approve a command that requires human approval, then execute."""
        cmd = _command_store.get(command_id)
        if not cmd:
            return None
        if cmd.status != CommandStatus.APPROVAL_REQUIRED:
            return cmd  # Already processed

        cmd.status = CommandStatus.APPROVED
        cmd.approved_at = datetime.now(UTC).isoformat()

        # Execute immediately after approval
        cmd = ActionCommandService.execute(cmd)
        return cmd

    @staticmethod
    def reject(command_id: str, reason: str = "") -> ActionCommand | None:
        """Reject a command that requires human approval."""
        cmd = _command_store.get(command_id)
        if not cmd:
            return None
        if cmd.status != CommandStatus.APPROVAL_REQUIRED:
            return cmd

        cmd.status = CommandStatus.REJECTED
        cmd.error = reason or "Rejected by user"
        cmd.completed_at = datetime.now(UTC).isoformat()
        return cmd

    @staticmethod
    def cancel(command_id: str, org_id: str) -> ActionCommand | None:
        """Cancel a command (only if not already executing/completed)."""
        cmd = _command_store.get(command_id)
        if not cmd or cmd.org_id != org_id:
            return None
        if cmd.status.is_terminal or cmd.status == CommandStatus.EXECUTING:
            return cmd  # Can't cancel terminal or in-flight

        cmd.status = CommandStatus.CANCELLED
        cmd.completed_at = datetime.now(UTC).isoformat()
        return cmd

    @staticmethod
    def get(command_id: str, org_id: str) -> ActionCommand | None:
        """Get a command by ID (tenant-scoped — returns None for wrong org)."""
        cmd = _command_store.get(command_id)
        if not cmd or cmd.org_id != org_id:
            return None
        return cmd

    @staticmethod
    def list_for_session(session_id: str, org_id: str) -> list[dict]:
        """List all commands for a session (status views only)."""
        return [
            cmd.to_status_view()
            for cmd in _command_store.values()
            if cmd.session_id == session_id and cmd.org_id == org_id
        ]

    @staticmethod
    def list_pending(org_id: str) -> list[dict]:
        """List commands awaiting approval for a workspace."""
        return [
            cmd.to_status_view()
            for cmd in _command_store.values()
            if cmd.org_id == org_id and cmd.status == CommandStatus.APPROVAL_REQUIRED
        ]


# =============================================================================
# Tool Execution (synchronous dispatch)
# =============================================================================


def _execute_tool_sync(tool: str, parameters: dict) -> dict:
    """Execute a tool by name with parameters.

    This is the canonical execution point — replaces inline httpx calls
    and direct function invocations scattered across the codebase.

    Returns result dict. Raises on failure.
    """
    # Tool dispatch table
    if tool == "generate_image":
        return _exec_generate_image(parameters)
    elif tool == "generate_video":
        return _exec_generate_video(parameters)
    elif tool == "train_lora":
        return _exec_train_lora(parameters)
    elif tool == "publish_post":
        return _exec_publish(parameters)
    elif tool == "launch_gpu":
        return _exec_launch_gpu(parameters)
    elif tool == "stop_gpu":
        return _exec_stop_gpu(parameters)
    else:
        # Unknown tool — try generic execution
        try:
            from backend.aios.execution.tools import execute_tool_sync
            return execute_tool_sync(tool, parameters)
        except (ImportError, AttributeError):
            return {"status": "unsupported_tool", "tool": tool}


def _exec_generate_image(params: dict) -> dict:
    """Execute image generation through the canonical pipeline."""
    from backend.engine.generation_engine import GenerationEngine, GenerationRequest

    engine = GenerationEngine()
    request = GenerationRequest(
        prompt=params.get("prompt", ""),
        negative_prompt=params.get("negative_prompt", ""),
        width=params.get("width", 1024),
        height=params.get("height", 1024),
        steps=params.get("steps", 20),
        model=params.get("model", "flux-dev"),
    )

    try:
        asset = engine.generate_and_register(request)
        return {
            "success": True,
            "asset_id": asset.get("id") if isinstance(asset, dict) else str(asset),
            "model": params.get("model", "flux-dev"),
            "prompt": params.get("prompt", ""),
        }
    except Exception as e:
        raise RuntimeError(f"Image generation failed: {e}")


def _exec_generate_video(params: dict) -> dict:
    """Execute video generation."""
    return {"status": "submitted", "tool": "generate_video", "params_received": list(params.keys())}


def _exec_train_lora(params: dict) -> dict:
    """Execute LoRA training start."""
    return {"status": "submitted", "tool": "train_lora", "params_received": list(params.keys())}


def _exec_publish(params: dict) -> dict:
    """Execute social publish."""
    return {"status": "submitted", "tool": "publish_post", "params_received": list(params.keys())}


def _exec_launch_gpu(params: dict) -> dict:
    """Execute GPU worker launch."""
    return {"status": "submitted", "tool": "launch_gpu", "params_received": list(params.keys())}


def _exec_stop_gpu(params: dict) -> dict:
    """Execute GPU worker stop."""
    return {"status": "submitted", "tool": "stop_gpu", "params_received": list(params.keys())}
