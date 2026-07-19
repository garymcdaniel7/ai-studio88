"""Agent Learning System — unified feedback loop for all Creative Team agents.

Every agent learns from user feedback. The system:
1. Collects ratings on agent outputs (👍/👎 or 1-5★)
2. Tracks patterns (what worked, what didn't)
3. After N positive signals, updates agent preferences ("DNA")
4. Agent DNA influences future decisions

Agents that learn:
- Akose (Recipes): which generation params produce the best results
- Oya (Storyboard): which shot sequences, transitions, pacing users prefer
- Araye (Prompts): which prompt patterns get highest ratings
- Osun (Aesthetic): which styles, lighting, colors resonate
- Ogun (Infrastructure): which GPUs/providers are most reliable
- Aroko (Publishing): which posting times and formats perform best
- Obatala (Identity): which LoRA strengths maintain identity best

Usage:
    from backend.aios.learning import get_learning_engine, record_feedback
    
    # Record a thumbs-up on a storyboard shot
    record_feedback("oya", "storyboard_shot", shot_data, rating=5)
    
    # Get learned preferences for an agent
    prefs = get_learning_engine().get_agent_preferences("oya")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Learning thresholds
CONFIDENCE_THRESHOLD = 10  # Need N ratings before a pattern is "learned"
UPDATE_THRESHOLD = 5  # After N consecutive positive signals, update DNA


@dataclass
class FeedbackEntry:
    """A single feedback signal from a user."""

    agent: str  # which agent produced this output
    output_type: str  # storyboard_shot, generation, voice, publish_time, etc
    rating: int  # 1-5 (or 0/1 for thumbs down/up)
    context: dict = field(default_factory=dict)  # what was the input/output
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class LearnedPattern:
    """A pattern the agent has learned from feedback."""

    agent: str
    pattern_type: str  # e.g. "shot_sequence", "prompt_style", "lighting_preference"
    description: str
    confidence: float = 0.0  # 0-1, based on number of positive signals
    positive_count: int = 0
    negative_count: int = 0
    context: dict = field(default_factory=dict)  # specific params/settings


class AgentLearning:
    """Unified learning engine for all Creative Team agents."""

    def __init__(self) -> None:
        self._feedback: list[FeedbackEntry] = []
        self._patterns: dict[str, list[LearnedPattern]] = {}  # agent → patterns
        self._agent_dna: dict[str, dict[str, Any]] = {}  # agent → learned preferences

    def record_feedback(
        self,
        agent: str,
        output_type: str,
        context: dict,
        rating: int,
    ) -> dict:
        """Record feedback on an agent's output.

        Returns the updated learning state for that agent.
        """
        entry = FeedbackEntry(
            agent=agent,
            output_type=output_type,
            rating=rating,
            context=context,
        )
        self._feedback.append(entry)

        # Update pattern tracking
        pattern_key = f"{agent}:{output_type}"
        if pattern_key not in self._patterns:
            self._patterns[pattern_key] = []

        # Check if this matches an existing pattern
        matched = False
        for pattern in self._patterns[pattern_key]:
            if self._context_matches(pattern.context, context):
                if rating >= 4:
                    pattern.positive_count += 1
                else:
                    pattern.negative_count += 1
                total = pattern.positive_count + pattern.negative_count
                pattern.confidence = pattern.positive_count / max(total, 1)
                matched = True

                # If pattern reaches confidence threshold, update agent DNA
                if pattern.positive_count >= UPDATE_THRESHOLD and pattern.confidence >= 0.7:
                    self._update_agent_dna(agent, pattern)
                break

        if not matched:
            # New pattern
            new_pattern = LearnedPattern(
                agent=agent,
                pattern_type=output_type,
                description=f"Pattern from {output_type}",
                positive_count=1 if rating >= 4 else 0,
                negative_count=0 if rating >= 4 else 1,
                confidence=1.0 if rating >= 4 else 0.0,
                context=context,
            )
            self._patterns[pattern_key].append(new_pattern)

        logger.info(
            f"[LEARN] {agent}/{output_type}: rating={rating}, "
            f"total_feedback={len(self._feedback)}"
        )

        return {
            "agent": agent,
            "output_type": output_type,
            "rating": rating,
            "total_feedback_for_agent": len([f for f in self._feedback if f.agent == agent]),
            "patterns_learned": len(self._patterns.get(pattern_key, [])),
        }

    def get_agent_preferences(self, agent: str) -> dict:
        """Get the learned preferences (DNA) for an agent.

        This is what the agent uses to make better decisions over time.
        """
        return {
            "agent": agent,
            "dna": self._agent_dna.get(agent, {}),
            "total_feedback": len([f for f in self._feedback if f.agent == agent]),
            "patterns": {
                key: [
                    {
                        "type": p.pattern_type,
                        "confidence": round(p.confidence, 2),
                        "positive": p.positive_count,
                        "negative": p.negative_count,
                        "description": p.description,
                    }
                    for p in patterns
                    if p.confidence >= 0.5
                ]
                for key, patterns in self._patterns.items()
                if key.startswith(agent)
            },
        }

    def get_all_agent_stats(self) -> dict:
        """Get learning stats for all agents."""
        agents = set(f.agent for f in self._feedback)
        stats = {}
        for agent in agents:
            agent_feedback = [f for f in self._feedback if f.agent == agent]
            ratings = [f.rating for f in agent_feedback]
            stats[agent] = {
                "total_feedback": len(agent_feedback),
                "avg_rating": round(sum(ratings) / max(len(ratings), 1), 2),
                "patterns_learned": sum(
                    1 for key, patterns in self._patterns.items()
                    if key.startswith(agent)
                    for p in patterns if p.confidence >= 0.7
                ),
                "has_dna": agent in self._agent_dna,
            }
        return stats

    def _update_agent_dna(self, agent: str, pattern: LearnedPattern) -> None:
        """Update an agent's DNA when a pattern reaches confidence threshold."""
        if agent not in self._agent_dna:
            self._agent_dna[agent] = {}

        # Store the learned preference
        key = f"{pattern.pattern_type}_{pattern.positive_count}"
        self._agent_dna[agent][key] = {
            "type": pattern.pattern_type,
            "context": pattern.context,
            "confidence": pattern.confidence,
            "learned_at": datetime.now(UTC).isoformat(),
            "based_on": pattern.positive_count + pattern.negative_count,
        }

        logger.info(
            f"[LEARN DNA] {agent} updated: {pattern.pattern_type} "
            f"(confidence: {pattern.confidence:.2f}, based on {pattern.positive_count} positive signals)"
        )

    def _context_matches(self, stored: dict, incoming: dict) -> bool:
        """Check if incoming context matches a stored pattern (fuzzy)."""
        if not stored:
            return False
        # Match on key fields present in both
        match_keys = set(stored.keys()) & set(incoming.keys())
        if not match_keys:
            return False
        matches = sum(1 for k in match_keys if stored.get(k) == incoming.get(k))
        return matches / max(len(match_keys), 1) >= 0.6


# Module-level singleton
_learning_engine: AgentLearning | None = None


def get_learning_engine() -> AgentLearning:
    """Get or create the global learning engine."""
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = AgentLearning()
    return _learning_engine


def record_feedback(agent: str, output_type: str, context: dict, rating: int) -> dict:
    """Convenience function to record feedback."""
    return get_learning_engine().record_feedback(agent, output_type, context, rating)
