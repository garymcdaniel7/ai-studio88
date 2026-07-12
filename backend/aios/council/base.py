"""CouncilAgent — unified interface for all AIOS agents.

Replaces both:
- backend/intelligence_engine/agents/base.py (BaseAgent)
- backend/autonomous_studio/department.py (Department)

Every council agent:
- Has a defined authority level (what it can do autonomously)
- Reasons over AIOSContext (shared state, never mutated directly)
- Produces AgentDecision with confidence, reasoning, and proposed actions
- Can execute approved actions within its authority
- Declares its capabilities for discovery
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthorityLevel(Enum):
    """What an agent is authorized to do without human approval."""

    OBSERVE = "observe"          # Can only read state, no side effects
    RECOMMEND = "recommend"      # Can propose actions, human decides
    EXECUTE_READ = "execute_read"  # Can invoke read-only tools (queries, health checks)
    EXECUTE_WRITE = "execute_write"  # Can invoke write tools (create, update) within scope
    EXECUTE_DESTRUCTIVE = "execute_destructive"  # Can delete, spend money (requires approval config)


@dataclass
class Capability:
    """A declared capability of an agent."""

    name: str               # "generate_image", "plan_campaign", "check_health"
    description: str        # Human-readable description
    authority_required: AuthorityLevel = AuthorityLevel.RECOMMEND
    parameters: dict = field(default_factory=dict)  # Expected input parameters


@dataclass
class ProposedAction:
    """An action an agent wants to take."""

    tool: str                   # Tool/endpoint to invoke
    parameters: dict = field(default_factory=dict)
    reasoning: str = ""         # Why this action
    confidence: float = 0.8     # 0.0-1.0
    requires_approval: bool = False  # Set by governance layer
    estimated_cost_usd: float = 0.0
    estimated_time_seconds: float = 0.0


@dataclass
class AgentDecision:
    """Output from a council agent's reasoning."""

    agent: str                  # Agent name
    summary: str = ""           # One-line summary of the decision
    reasoning: str = ""         # Detailed reasoning chain
    confidence: float = 0.8    # Overall confidence
    proposed_actions: list[ProposedAction] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    context_updates: dict = field(default_factory=dict)  # Suggested context mutations
    metadata: dict = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of executing an approved action."""

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AIOSContext:
    """Shared context passed to all council agents.

    Agents READ from this. They never mutate it directly.
    Instead they propose context_updates in their AgentDecision.
    """

    # Request
    user_message: str = ""
    mode: str = "creative"
    session_id: str = ""

    # User/Tenant
    user_id: str | None = None
    org_id: str | None = None

    # Creative Context
    talent_id: str | None = None
    talent_name: str = ""
    talent_dna: dict = field(default_factory=dict)
    project_id: str | None = None
    project_name: str = ""

    # History
    conversation_history: list[dict] = field(default_factory=list)
    recent_generations: list[dict] = field(default_factory=list)

    # Infrastructure
    gpu_worker_active: bool = False
    available_models: list[str] = field(default_factory=list)
    budget_remaining_usd: float = 100.0

    # Memory
    relevant_memories: list[dict] = field(default_factory=list)

    # Platform State
    services: dict = field(default_factory=dict)  # {comfyui: True, ollama: True, ...}


class CouncilAgent(ABC):
    """Abstract base for all AIOS council agents.

    Implement this to create a new agent. Register in the council registry.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier (e.g., 'èṣù', 'òrúnmìlà')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""
        ...

    @property
    @abstractmethod
    def domain(self) -> str:
        """One-line domain description."""
        ...

    @property
    @abstractmethod
    def authority(self) -> AuthorityLevel:
        """Maximum authority level this agent has."""
        ...

    @abstractmethod
    def capabilities(self) -> list[Capability]:
        """Declare what this agent can do."""
        ...

    @abstractmethod
    async def reason(self, context: AIOSContext) -> AgentDecision:
        """Reason over context and produce a decision.

        This is the agent's main thinking function. It should:
        1. Analyze the context
        2. Determine if it has relevant input
        3. Produce recommendations and/or proposed actions
        4. Include confidence and reasoning

        Agents should return quickly if they have nothing to contribute.
        """
        ...

    async def execute(self, action: ProposedAction) -> ActionResult:
        """Execute an approved action.

        Only called if:
        - The action's authority_required <= this agent's authority
        - The governance layer approved it (or it's pre-approved)

        Default implementation raises NotImplementedError.
        Override in agents that can execute actions.
        """
        raise NotImplementedError(f"{self.name} cannot execute actions")

    def relevance_score(self, context: AIOSContext) -> float:
        """Quick check: how relevant is this agent to the current request?

        Returns 0.0-1.0. Used by the coordinator to skip irrelevant agents.
        Override for faster agent selection.
        """
        return 0.5  # Default: moderately relevant to everything
