"""Authority Matrix — defines what each action requires for auto-approval.

Every tool/action is mapped to:
- required_authority: minimum AuthorityLevel needed to auto-execute
- risk_level: low | medium | high | critical
- always_approve: always require human sign-off regardless of policy
- budget_gate: only execute if estimated cost < configured threshold
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.aios.council.base import AuthorityLevel


class RiskLevel(Enum):
    LOW = "low"           # Cheap, reversible (generate image, search)
    MEDIUM = "medium"     # Moderate cost or impact (train lora, schedule post)
    HIGH = "high"         # Significant cost or external impact (GPU launch, publish)
    CRITICAL = "critical" # Irreversible or very expensive (delete talent DNA, mass delete)


@dataclass
class ActionPolicy:
    """Policy for a specific action."""
    tool: str
    required_authority: AuthorityLevel
    risk_level: RiskLevel
    always_require_approval: bool = False
    budget_gate_usd: float | None = None  # Auto-block if cost exceeds this
    description: str = ""


# =============================================================================
# Authority Matrix
# =============================================================================

AUTHORITY_MATRIX: dict[str, ActionPolicy] = {

    # ── Read / Search (no side effects) ────────────────────────────────────────
    "search_talent": ActionPolicy(
        tool="search_talent",
        required_authority=AuthorityLevel.EXECUTE_READ,
        risk_level=RiskLevel.LOW,
        description="Search talent library",
    ),
    "list_models": ActionPolicy(
        tool="list_models",
        required_authority=AuthorityLevel.EXECUTE_READ,
        risk_level=RiskLevel.LOW,
        description="List available models",
    ),
    "check_health": ActionPolicy(
        tool="check_health",
        required_authority=AuthorityLevel.EXECUTE_READ,
        risk_level=RiskLevel.LOW,
        description="Check service health",
    ),
    "worker_status": ActionPolicy(
        tool="worker_status",
        required_authority=AuthorityLevel.EXECUTE_READ,
        risk_level=RiskLevel.LOW,
        description="Check GPU worker status",
    ),
    "cost_summary": ActionPolicy(
        tool="cost_summary",
        required_authority=AuthorityLevel.EXECUTE_READ,
        risk_level=RiskLevel.LOW,
        description="View cost summary",
    ),
    "get_story": ActionPolicy(
        tool="get_story",
        required_authority=AuthorityLevel.EXECUTE_READ,
        risk_level=RiskLevel.LOW,
        description="Read story content",
    ),
    "discover_tools": ActionPolicy(
        tool="discover_tools",
        required_authority=AuthorityLevel.EXECUTE_READ,
        risk_level=RiskLevel.LOW,
        description="List available platform tools",
    ),

    # ── Creative Generation (cheap, reversible) ───────────────────────────────
    "generate_image": ActionPolicy(
        tool="generate_image",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.LOW,
        budget_gate_usd=0.10,
        description="Generate an image via ComfyUI",
    ),
    "enhance_prompt": ActionPolicy(
        tool="enhance_prompt",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.LOW,
        description="Optimize a generation prompt",
    ),
    "recommend_model": ActionPolicy(
        tool="recommend_model",
        required_authority=AuthorityLevel.RECOMMEND,
        risk_level=RiskLevel.LOW,
        description="Recommend best model for task",
    ),
    "recommend_workflow": ActionPolicy(
        tool="recommend_workflow",
        required_authority=AuthorityLevel.RECOMMEND,
        risk_level=RiskLevel.LOW,
        description="Recommend optimal workflow",
    ),

    # ── Creative Generation (medium cost) ─────────────────────────────────────
    "generate_video": ActionPolicy(
        tool="generate_video",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.MEDIUM,
        budget_gate_usd=1.00,
        description="Generate a video clip",
    ),
    "generate_voice": ActionPolicy(
        tool="generate_voice",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.LOW,
        budget_gate_usd=0.50,
        description="Generate speech via TTS",
    ),
    "generate_music": ActionPolicy(
        tool="generate_music",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.MEDIUM,
        description="Generate music",
    ),
    "clone_voice": ActionPolicy(
        tool="clone_voice",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.HIGH,
        always_require_approval=True,  # Consent always required
        description="Clone a voice from audio sample (consent required)",
    ),

    # ── Training (expensive, long-running) ────────────────────────────────────
    "train_lora": ActionPolicy(
        tool="train_lora",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.HIGH,
        always_require_approval=True,
        budget_gate_usd=10.00,
        description="Train a LoRA model on GPU",
    ),

    # ── Infrastructure (expensive, hard to reverse) ───────────────────────────
    "launch_worker": ActionPolicy(
        tool="launch_worker",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.HIGH,
        budget_gate_usd=5.00,
        description="Launch GPU worker (costs money per hour)",
    ),
    "stop_worker": ActionPolicy(
        tool="stop_worker",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.MEDIUM,
        description="Stop GPU worker",
    ),
    "download_model": ActionPolicy(
        tool="download_model",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.MEDIUM,
        description="Download model to worker",
    ),

    # ── Publishing (external impact) ──────────────────────────────────────────
    "schedule_post": ActionPolicy(
        tool="schedule_post",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.HIGH,
        always_require_approval=True,
        description="Schedule social media post",
    ),
    "publish_post": ActionPolicy(
        tool="publish_post",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.HIGH,
        always_require_approval=True,
        description="Publish to social media immediately",
    ),

    # ── Data Mutations ────────────────────────────────────────────────────────
    "create_talent": ActionPolicy(
        tool="create_talent",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.LOW,
        description="Create a new talent record",
    ),
    "update_talent": ActionPolicy(
        tool="update_talent",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.LOW,
        description="Update talent profile",
    ),
    "continue_story": ActionPolicy(
        tool="continue_story",
        required_authority=AuthorityLevel.EXECUTE_WRITE,
        risk_level=RiskLevel.LOW,
        description="Continue story narrative",
    ),

    # ── Destructive (irreversible) ────────────────────────────────────────────
    "delete_talent": ActionPolicy(
        tool="delete_talent",
        required_authority=AuthorityLevel.EXECUTE_DESTRUCTIVE,
        risk_level=RiskLevel.CRITICAL,
        always_require_approval=True,
        description="Permanently delete a talent record",
    ),
    "delete_model": ActionPolicy(
        tool="delete_model",
        required_authority=AuthorityLevel.EXECUTE_DESTRUCTIVE,
        risk_level=RiskLevel.CRITICAL,
        always_require_approval=True,
        description="Permanently delete a model from B2",
    ),
    "delete_asset": ActionPolicy(
        tool="delete_asset",
        required_authority=AuthorityLevel.EXECUTE_DESTRUCTIVE,
        risk_level=RiskLevel.HIGH,
        always_require_approval=True,
        description="Delete an asset",
    ),
    "delete_talent_dna": ActionPolicy(
        tool="delete_talent_dna",
        required_authority=AuthorityLevel.EXECUTE_DESTRUCTIVE,
        risk_level=RiskLevel.CRITICAL,
        always_require_approval=True,
        description="Delete Talent Creative DNA (irreversible)",
    ),
}


def get_policy(tool: str) -> ActionPolicy | None:
    """Get the policy for a given tool."""
    return AUTHORITY_MATRIX.get(tool)


def requires_approval(
    tool: str,
    agent_authority: AuthorityLevel,
    estimated_cost: float = 0.0,
    governance_policies: dict | None = None,
) -> tuple[bool, str]:
    """Check if an action requires human approval.

    Returns: (requires_approval: bool, reason: str)
    """
    policy = get_policy(tool)

    # Unknown tools require approval by default
    if not policy:
        return True, f"Unknown tool '{tool}' — approval required by default"

    # Check always_require_approval flag
    if policy.always_require_approval:
        return True, f"{tool} always requires human approval ({policy.description})"

    # Check agent authority level
    authority_order = [
        AuthorityLevel.OBSERVE,
        AuthorityLevel.RECOMMEND,
        AuthorityLevel.EXECUTE_READ,
        AuthorityLevel.EXECUTE_WRITE,
        AuthorityLevel.EXECUTE_DESTRUCTIVE,
    ]
    agent_level = authority_order.index(agent_authority) if agent_authority in authority_order else 0
    required_level = authority_order.index(policy.required_authority) if policy.required_authority in authority_order else 4

    if agent_level < required_level:
        return True, f"Agent authority ({agent_authority.value}) insufficient for {tool} (requires {policy.required_authority.value})"

    # Check budget gate
    if policy.budget_gate_usd is not None and estimated_cost > policy.budget_gate_usd:
        return True, f"Estimated cost ${estimated_cost:.3f} exceeds gate ${policy.budget_gate_usd:.2f} for {tool}"

    # Check governance policies
    if governance_policies:
        # User may have set require_publish_approval=true
        if tool in ("schedule_post", "publish_post") and governance_policies.get("require_publish_approval", True):
            return True, "Publishing requires approval per your settings"

        if tool in ("train_lora", "launch_worker") and governance_policies.get("require_gpu_approval", False):
            return True, "GPU operations require approval per your settings"

        # Check max auto-spend
        max_auto_usd = float(governance_policies.get("max_auto_spend_usd", 5.0))
        if estimated_cost > max_auto_usd:
            return True, f"Cost ${estimated_cost:.3f} exceeds auto-approval limit ${max_auto_usd:.2f}"

    return False, "Auto-approved"
