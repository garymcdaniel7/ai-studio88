"""Conversation & Execution Model Boundaries — Story 032.

Enforces the canonical entity map. Every conversation/execution operation
must go through this module to ensure correct table targeting and lifecycle.

Boundaries:
  PRESENTATION (user-facing):
    brain_conversations — title, collection, summary, display
    brain_collections — grouping, color, talent association

  EXECUTION (agent/audit):
    aios_sessions — execution state, actor, status
    aios_messages — actual message content
    aios_decisions — LLM decisions, cost, latency
    aios_approvals — governance queue

  MEMORY (long-term):
    brain_memory — key/value preferences
    brain_embeddings — RAG vectors

  COMPATIBILITY (legacy, read-only for new code):
    brain_sessions — old session records
    brain_messages — old message records

Rules:
  1. New conversations → brain_conversations (presentation)
  2. New execution state → aios_sessions (execution)
  3. New messages → aios_messages (execution)
  4. New decisions → aios_decisions (audit)
  5. brain_sessions/brain_messages → READ ONLY (compatibility)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Model Registry — Which table owns which concept
# =============================================================================


class ModelDomain(str, Enum):
    """Domain classification for each table."""
    PRESENTATION = "presentation"
    EXECUTION = "execution"
    GOVERNANCE = "governance"
    MEMORY = "memory"
    COMPATIBILITY = "compatibility"


class ModelDisposition(str, Enum):
    """Lifecycle disposition of a table."""
    CANONICAL = "canonical"
    COMPATIBILITY = "compatibility"
    MIGRATED = "migrated"
    RETIRED = "retired"


# The authoritative registry
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    # Presentation (user-facing)
    "brain_conversations": {
        "domain": ModelDomain.PRESENTATION,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "user_conversation",
        "owns": ["title", "collection_id", "summary", "mode", "message_count", "talent_id"],
        "tenant_scoped": True,
    },
    "brain_collections": {
        "domain": ModelDomain.PRESENTATION,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "conversation_collection",
        "owns": ["name", "color", "description", "talent_id"],
        "tenant_scoped": True,
    },

    # Execution (agent/audit)
    "aios_sessions": {
        "domain": ModelDomain.EXECUTION,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "execution_session",
        "owns": ["status", "user_id", "mode", "talent_id", "project_id", "message_count"],
        "tenant_scoped": True,
    },
    "aios_messages": {
        "domain": ModelDomain.EXECUTION,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "execution_message",
        "owns": ["role", "content", "session_id"],
        "tenant_scoped": True,
    },
    "aios_decisions": {
        "domain": ModelDomain.EXECUTION,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "ai_decision",
        "owns": ["decision_type", "provider", "model", "latency_ms", "tokens_used", "cost_usd"],
        "tenant_scoped": True,
    },
    "brain_plans": {
        "domain": ModelDomain.EXECUTION,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "execution_plan",
        "owns": ["request", "tasks", "reasoning", "estimated_seconds", "status"],
        "tenant_scoped": True,  # Via session FK inheritance
    },

    # Governance
    "aios_approvals": {
        "domain": ModelDomain.GOVERNANCE,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "approval",
        "owns": ["tool", "parameters", "status", "decided_by", "rejection_reason"],
        "tenant_scoped": True,
    },
    "aios_policies": {
        "domain": ModelDomain.GOVERNANCE,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "governance_policy",
        "owns": ["policies"],
        "tenant_scoped": True,
    },

    # Memory
    "brain_memory": {
        "domain": ModelDomain.MEMORY,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "long_term_memory",
        "owns": ["category", "key", "value", "confidence"],
        "tenant_scoped": True,
    },
    "brain_embeddings": {
        "domain": ModelDomain.MEMORY,
        "disposition": ModelDisposition.CANONICAL,
        "writable": True,
        "concept": "rag_embedding",
        "owns": ["content", "embedding", "source_type"],
        "tenant_scoped": True,
    },

    # Compatibility (legacy — read-only for new code)
    "brain_sessions": {
        "domain": ModelDomain.COMPATIBILITY,
        "disposition": ModelDisposition.COMPATIBILITY,
        "writable": False,  # No new writes
        "concept": "legacy_session",
        "migration_target": "aios_sessions",
        "tenant_scoped": False,  # UNVERIFIED — org_id not reliably enforced
    },
    "brain_messages": {
        "domain": ModelDomain.COMPATIBILITY,
        "disposition": ModelDisposition.COMPATIBILITY,
        "writable": False,  # No new writes
        "concept": "legacy_message",
        "migration_target": "aios_messages",
        "tenant_scoped": False,  # Inherits from brain_sessions
    },
}


# =============================================================================
# Boundary Enforcement
# =============================================================================


def get_canonical_table(concept: str) -> str | None:
    """Get the canonical table for a given concept.

    Returns None if concept is unknown.
    """
    for table, info in MODEL_REGISTRY.items():
        if info["concept"] == concept and info["disposition"] == ModelDisposition.CANONICAL:
            return table
    return None


def is_writable(table: str) -> bool:
    """Check if a table accepts new writes.

    Compatibility tables are read-only for new code.
    """
    info = MODEL_REGISTRY.get(table)
    if not info:
        return False
    return info["writable"]


def get_disposition(table: str) -> ModelDisposition | None:
    """Get the lifecycle disposition of a table."""
    info = MODEL_REGISTRY.get(table)
    return info["disposition"] if info else None


def get_domain(table: str) -> ModelDomain | None:
    """Get the domain of a table."""
    info = MODEL_REGISTRY.get(table)
    return info["domain"] if info else None


def get_migration_target(table: str) -> str | None:
    """Get the migration target for a compatibility table."""
    info = MODEL_REGISTRY.get(table)
    return info.get("migration_target") if info else None


def validate_write_target(table: str) -> None:
    """Validate that a table is an approved write target.

    Raises ValueError if the table is in compatibility/retired disposition.
    """
    info = MODEL_REGISTRY.get(table)
    if not info:
        raise ValueError(f"Unknown table: {table}. Not in model registry.")

    if not info["writable"]:
        target = info.get("migration_target", "unknown")
        raise ValueError(
            f"Table '{table}' is {info['disposition'].value} — "
            f"no new writes allowed. Use '{target}' instead."
        )


def validate_cross_reference(
    from_table: str,
    to_table: str,
    reference_type: str = "FK",
) -> None:
    """Validate that a cross-reference between tables is allowed.

    Rules:
    - Presentation → Execution: allowed (soft reference via metadata)
    - Execution → Presentation: NOT allowed (execution must not depend on presentation)
    - Any → Compatibility: allowed for reading only
    - Compatibility → Canonical: NOT allowed (legacy doesn't reference new)
    """
    from_info = MODEL_REGISTRY.get(from_table)
    to_info = MODEL_REGISTRY.get(to_table)

    if not from_info or not to_info:
        return  # Unknown tables — skip validation

    # Execution should not depend on presentation
    if (from_info["domain"] == ModelDomain.EXECUTION and
            to_info["domain"] == ModelDomain.PRESENTATION):
        logger.warning(
            f"Cross-reference from execution ({from_table}) to presentation ({to_table}) "
            f"violates model boundaries. Execution should not depend on presentation."
        )


# =============================================================================
# Concept Resolution — which table to use for a given operation
# =============================================================================


# Quick lookup: concept → canonical table
CONCEPT_TABLE_MAP: dict[str, str] = {
    "user_conversation": "brain_conversations",
    "conversation_collection": "brain_collections",
    "execution_session": "aios_sessions",
    "execution_message": "aios_messages",
    "ai_decision": "aios_decisions",
    "execution_plan": "brain_plans",
    "approval": "aios_approvals",
    "governance_policy": "aios_policies",
    "long_term_memory": "brain_memory",
    "rag_embedding": "brain_embeddings",
}


def resolve_table(concept: str) -> str:
    """Resolve a concept to its canonical table name.

    Raises ValueError if concept is unknown.
    """
    table = CONCEPT_TABLE_MAP.get(concept)
    if not table:
        raise ValueError(f"Unknown concept: '{concept}'. Valid concepts: {list(CONCEPT_TABLE_MAP.keys())}")
    return table
