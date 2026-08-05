"""Async Governance Enforcement — Story 038.

Correctly awaited governance evaluation for async route handlers.
Replaces the broken `asyncio.get_event_loop().run_until_complete()` pattern
with properly awaited governance checks that produce explicit outcomes.

Outcomes:
    ALLOWED — action may proceed (within policy)
    BLOCKED — action denied by policy (response tells user why)
    PENDING_APPROVAL — action queued for human approval
    DEGRADED — governance unavailable, side effects blocked, read-only continues

Rules:
    1. Governance is awaited ONCE (no nested event-loop calls)
    2. Exceptions are NEVER silently swallowed — they produce DEGRADED outcome
    3. Side effects CANNOT execute without a successful governance result
    4. Read-only chat continues during degradation (explicit policy)
    5. Timeout produces DEGRADED (not silent pass-through)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Governance evaluation timeout
GOVERNANCE_TIMEOUT_SECONDS = 5.0


# =============================================================================
# Governance Outcome
# =============================================================================


class ChatGovernanceOutcome(str, Enum):
    """Possible outcomes of governance evaluation in the chat path."""
    ALLOWED = "allowed"                    # Actions may execute
    BLOCKED = "blocked"                    # Actions denied by policy
    PENDING_APPROVAL = "pending_approval"  # Queued for human review
    DEGRADED = "degraded"                  # Governance unavailable — read-only only
    NO_ACTIONS = "no_actions"              # No side effects detected (pure chat)


@dataclass
class ChatGovernanceResult:
    """The authoritative result of governance evaluation for a chat message.

    This result GATES execution — no side effect proceeds without it.
    """
    outcome: ChatGovernanceOutcome
    proposed_actions: list[dict] = field(default_factory=list)
    governance_detail: dict = field(default_factory=dict)
    reason: str = ""
    error: str | None = None  # Non-None means degraded/failed
    evaluation_ms: int = 0

    @property
    def allows_execution(self) -> bool:
        """Whether side effects may proceed."""
        return self.outcome == ChatGovernanceOutcome.ALLOWED

    @property
    def is_degraded(self) -> bool:
        """Whether governance failed (read-only mode only)."""
        return self.outcome == ChatGovernanceOutcome.DEGRADED

    def to_response_fields(self) -> dict[str, Any]:
        """Fields to include in the chat response."""
        result: dict[str, Any] = {
            "actions": self.proposed_actions,
            "governance": self.governance_detail,
            "governance_outcome": self.outcome.value,
        }
        if self.error:
            result["governance_error"] = self.error
        if self.outcome == ChatGovernanceOutcome.PENDING_APPROVAL:
            result["approval_required"] = True
            result["approval_message"] = self.reason
        if self.outcome == ChatGovernanceOutcome.BLOCKED:
            result["action_blocked"] = True
            result["blocked_reason"] = self.reason
        if self.outcome == ChatGovernanceOutcome.DEGRADED:
            result["governance_degraded"] = True
            result["degraded_message"] = (
                "Action execution is temporarily unavailable. "
                "Your chat response is read-only. Please try again shortly."
            )
        return result


# =============================================================================
# Async Governance Evaluation
# =============================================================================


async def evaluate_governance_async(
    message: str,
    mode: str,
    session_id: str,
    talent_id: str | None = None,
    project_id: str | None = None,
) -> ChatGovernanceResult:
    """Evaluate governance for a chat message — correctly awaited.

    This REPLACES the broken `get_event_loop().run_until_complete()` pattern.

    Steps:
    1. Import council (may fail if not configured — DEGRADED)
    2. Build context
    3. Await council evaluation with timeout
    4. Interpret result into explicit outcome
    5. Log the evaluation (never swallow)

    Returns:
        ChatGovernanceResult with explicit outcome and execution gate.
    """
    start = time.time()

    try:
        from backend.aios.council.base import AIOSContext
        from backend.aios.council.orchestrator import run_council
    except ImportError as e:
        # Council not available — degraded mode
        elapsed_ms = int((time.time() - start) * 1000)
        logger.warning(f"Governance council not available: {e}")
        return ChatGovernanceResult(
            outcome=ChatGovernanceOutcome.DEGRADED,
            reason="Governance council not available",
            error=f"ImportError: {str(e)[:100]}",
            evaluation_ms=elapsed_ms,
        )

    # Build council context
    ctx = AIOSContext(
        user_message=message,
        mode=mode,
        session_id=session_id,
        talent_id=talent_id,
        project_id=project_id,
    )

    # Await with timeout — governance must respond quickly
    try:
        council_result = await asyncio.wait_for(
            run_council(ctx),
            timeout=GOVERNANCE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error(
            f"Governance evaluation TIMED OUT after {GOVERNANCE_TIMEOUT_SECONDS}s "
            f"for session={session_id}"
        )
        return ChatGovernanceResult(
            outcome=ChatGovernanceOutcome.DEGRADED,
            reason="Governance evaluation timed out",
            error=f"Timeout after {GOVERNANCE_TIMEOUT_SECONDS}s",
            evaluation_ms=elapsed_ms,
        )
    except asyncio.CancelledError:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.warning(f"Governance evaluation cancelled for session={session_id}")
        return ChatGovernanceResult(
            outcome=ChatGovernanceOutcome.DEGRADED,
            reason="Governance evaluation was cancelled",
            error="CancelledError",
            evaluation_ms=elapsed_ms,
        )
    except Exception as e:
        # Any other failure → DEGRADED (never silent pass)
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error(
            f"Governance evaluation FAILED for session={session_id}: {type(e).__name__}: {e}"
        )
        return ChatGovernanceResult(
            outcome=ChatGovernanceOutcome.DEGRADED,
            reason=f"Governance evaluation failed: {type(e).__name__}",
            error=str(e)[:200],
            evaluation_ms=elapsed_ms,
        )

    elapsed_ms = int((time.time() - start) * 1000)

    # Interpret council result into explicit outcome
    return _interpret_council_result(council_result, elapsed_ms)


def _interpret_council_result(
    council_result: dict[str, Any],
    elapsed_ms: int,
) -> ChatGovernanceResult:
    """Interpret raw council result into a typed governance outcome."""
    proposed_actions = council_result.get("proposed_actions", [])
    governance = council_result.get("governance", {})

    # No actions proposed — pure conversational response
    if not proposed_actions:
        return ChatGovernanceResult(
            outcome=ChatGovernanceOutcome.NO_ACTIONS,
            proposed_actions=[],
            governance_detail=governance,
            evaluation_ms=elapsed_ms,
        )

    # Check governance decision
    gov_decision = governance.get("decision", "allow")
    gov_reason = governance.get("reason", "")

    if gov_decision == "block" or gov_decision == "deny":
        return ChatGovernanceResult(
            outcome=ChatGovernanceOutcome.BLOCKED,
            proposed_actions=proposed_actions,
            governance_detail=governance,
            reason=gov_reason or "Action blocked by workspace policy",
            evaluation_ms=elapsed_ms,
        )

    if gov_decision == "require_approval" or gov_decision == "pending":
        return ChatGovernanceResult(
            outcome=ChatGovernanceOutcome.PENDING_APPROVAL,
            proposed_actions=proposed_actions,
            governance_detail=governance,
            reason=gov_reason or "This action requires human approval",
            evaluation_ms=elapsed_ms,
        )

    # Default: allowed
    return ChatGovernanceResult(
        outcome=ChatGovernanceOutcome.ALLOWED,
        proposed_actions=proposed_actions,
        governance_detail=governance,
        reason=gov_reason,
        evaluation_ms=elapsed_ms,
    )
