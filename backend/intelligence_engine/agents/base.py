"""Base agent interface — all agents implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.intelligence_engine.context import IntelligenceContext


@dataclass
class AgentOutput:
    """Output from an agent's reasoning."""

    agent: str
    recommendations: list[dict] = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.8
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base for all intelligence agents.

    Each agent:
    - Reads from IntelligenceContext (never mutates it)
    - Produces AgentOutput with recommendations + reasoning
    - Operates independently (no agent calls another directly)
    - Can optionally use an LLM provider for reasoning
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier."""
        ...

    @property
    @abstractmethod
    def role(self) -> str:
        """One-line description of this agent's responsibility."""
        ...

    @abstractmethod
    def think(self, context: IntelligenceContext) -> AgentOutput:
        """Reason over the context and produce recommendations.

        Args:
            context: Full intelligence context (read-only)

        Returns:
            AgentOutput with recommendations and reasoning
        """
        ...
