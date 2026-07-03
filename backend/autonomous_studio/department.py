"""Department Interface — common contract for all AI departments.

Every department implements analyze/recommend/review/improve/summarize.
Departments communicate only through StudioContext (never directly).
Each department explains its reasoning and can be independently replaced.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Recommendation:
    """A single recommendation from a department."""
    department: str
    title: str
    description: str
    reasoning: str
    confidence: float = 0.8  # 0.0 to 1.0
    evidence: list[str] = field(default_factory=list)
    expected_benefit: str = ""
    estimated_cost: str = ""
    estimated_runtime: str = ""
    potential_risks: list[str] = field(default_factory=list)
    action: str = ""  # What to do if approved
    priority: str = "medium"  # low, medium, high, critical
    status: str = "pending"  # pending, approved, rejected, modified, executed
    metadata: dict = field(default_factory=dict)


@dataclass
class DepartmentOutput:
    """Output from a department's analysis."""
    department: str
    recommendations: list[Recommendation] = field(default_factory=list)
    summary: str = ""
    health: str = "good"  # good, warning, critical
    metadata: dict = field(default_factory=dict)


class Department(ABC):
    """Abstract base for all AI departments."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Department name."""
        ...

    @property
    @abstractmethod
    def role(self) -> str:
        """One-line description of this department's responsibility."""
        ...

    @abstractmethod
    def analyze(self, context: dict) -> DepartmentOutput:
        """Analyze the current studio state and produce recommendations."""
        ...

    def recommend(self, context: dict) -> list[Recommendation]:
        """Shorthand: analyze and return just recommendations."""
        return self.analyze(context).recommendations

    def review(self, item: dict, context: dict) -> dict:
        """Review a specific item (asset, campaign, etc.) and give feedback."""
        return {"approved": True, "notes": "Looks good", "department": self.name}

    def improve(self, item: dict, context: dict) -> dict:
        """Suggest improvements to a specific item."""
        return {"suggestions": [], "department": self.name}

    def summarize(self, context: dict) -> str:
        """Produce a one-sentence summary of department status."""
        return f"{self.name}: Operating normally."
