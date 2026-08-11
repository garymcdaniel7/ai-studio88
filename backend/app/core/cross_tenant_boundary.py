"""Cross-Tenant Learning Boundary — R95.

Enforces zero cross-tenant creative content in Brain/Hermes context retrieval.
This module is a hard security boundary: any item from org P that appears in
org O's context retrieval is treated as a P0 security incident.

Protected content types (R95.2 — forbidden for cross-tenant retrieval):
  prompts, campaigns, stories, talent_data, creative_dna, assets,
  conversations, workflows, generated_media, brain_memory, workspace_knowledge

Permitted for Layer 4 platform learning (R95.3):
  Aggregated/de-identified signals ONLY — UX patterns, routing optimization,
  success rates, general capability improvement.

Platform Learning Gate (A2-034):
  PLATFORM_LEARNING_DISABLED = True until an approved de-identification
  pipeline exists. Layer 4 interface exists but has zero data flow.

Validates: Requirements R95.1, R95.2, R95.3, R95.4, A2-034
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, Sequence

from app.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Protected Content Types (R95.2)
# =============================================================================

PROTECTED_CONTENT_TYPES: frozenset[str] = frozenset({
    "prompts",
    "campaigns",
    "stories",
    "talent_data",
    "creative_dna",
    "assets",
    "conversations",
    "workflows",
    "generated_media",
    "brain_memory",
    "workspace_knowledge",
})
"""Content types forbidden for cross-tenant retrieval or learning.

If any item with one of these content_types belongs to org P, it must NEVER
appear in org O's context retrieval (where O != P).
"""


# =============================================================================
# Platform Learning Signals (R95.3)
# =============================================================================

PERMITTED_PLATFORM_SIGNALS: frozenset[str] = frozenset({
    "ux_patterns",
    "routing_optimization",
    "success_rates",
    "assistance_patterns",
    "performance_optimization",
    "recommendation_quality",
    "general_capability",
})
"""Signal types permitted for platform-level aggregated learning.

These are aggregated/de-identified signals that do NOT contain
proprietary creative content. They help improve the platform generally
without exposing one customer's ideas to another.
"""


# =============================================================================
# Platform Learning Gate (A2-034)
# =============================================================================

# Hard-coded to True until Founder approves a de-identification pipeline.
# The Layer 4 architecture defines the boundary — it does NOT require
# an active learning system at launch.
PLATFORM_LEARNING_DISABLED: bool = True
"""When True, no data flows through the platform learning pipeline.

This flag remains True until:
  1. A documented de-identification pipeline is approved by the Founder
  2. The pipeline is verified to be irreversible (cannot reconstruct source)
  3. Explicit activation via configuration change (not code deploy)
"""


# =============================================================================
# Exceptions
# =============================================================================


class CrossTenantViolationError(Exception):
    """Raised when a cross-tenant content leak is detected.

    This is a P0 security incident equivalent to a tenant isolation breach.
    """

    def __init__(
        self,
        item_org_id: str,
        requesting_org_id: str,
        content_type: str,
        item_id: str = "",
    ) -> None:
        self.item_org_id = item_org_id
        self.requesting_org_id = requesting_org_id
        self.content_type = content_type
        self.item_id = item_id
        super().__init__(
            f"P0 CROSS-TENANT VIOLATION: org={item_org_id} content_type={content_type} "
            f"item_id={item_id} appeared in context for org={requesting_org_id}"
        )


class PlatformLearningDisabledError(Exception):
    """Raised when platform learning is attempted while disabled.

    Per A2-034, platform learning is disabled until an approved
    de-identification pipeline exists.
    """

    def __init__(self, message: str = "Platform learning is disabled (A2-034)") -> None:
        super().__init__(message)


# =============================================================================
# Item Protocol — what context items must expose
# =============================================================================


class ContextItem(Protocol):
    """Protocol for items in Brain/Hermes context retrieval.

    Any item that flows through the context retrieval pipeline must
    expose org_id and content_type for boundary enforcement.
    """

    @property
    def org_id(self) -> str: ...

    @property
    def content_type(self) -> str: ...

    @property
    def id(self) -> str: ...


# =============================================================================
# Cross-Tenant Boundary Enforcement
# =============================================================================


class CrossTenantBoundary:
    """Enforces zero cross-tenant creative content in context retrieval.

    This class is the primary enforcement point for R95.1/R95.2/R95.5:
      - validate_context_retrieval() filters items, excluding any from another org
        whose content_type is in PROTECTED_CONTENT_TYPES
      - is_cross_tenant_violation() checks whether a single item would violate the boundary
      - log_violation() records a P0 security incident for audit

    Usage:
        boundary = CrossTenantBoundary()
        safe_items = boundary.validate_context_retrieval(items, requesting_org_id="org-123")
    """

    def __init__(self) -> None:
        self._violations: list[dict[str, Any]] = []
        self._max_violations: int = 1000

    def validate_context_retrieval(
        self,
        items: Sequence[Any],
        requesting_org_id: str,
    ) -> list[Any]:
        """Filter context items, excluding cross-tenant protected content.

        Items from the same org are always included.
        Items from a different org with a content_type in PROTECTED_CONTENT_TYPES
        are EXCLUDED and logged as P0 violations.
        Items from a different org with a content_type NOT in PROTECTED_CONTENT_TYPES
        are also excluded (defense in depth).

        Args:
            items: Sequence of context items (must have org_id, content_type, id attributes).
            requesting_org_id: The org_id of the requesting user/session.

        Returns:
            Filtered list containing only items belonging to the requesting org.
        """
        if not requesting_org_id:
            logger.error(
                "cross_tenant_boundary_empty_org_id",
                detail="validate_context_retrieval called with empty requesting_org_id",
            )
            return []

        safe_items: list[Any] = []

        for item in items:
            item_org_id = getattr(item, "org_id", None) or ""
            item_content_type = getattr(item, "content_type", None) or ""
            item_id = getattr(item, "id", None) or ""

            if not item_org_id:
                # Items without org_id are excluded (deny by default)
                logger.warning(
                    "cross_tenant_boundary_missing_org_id",
                    item_id=str(item_id),
                    content_type=item_content_type,
                )
                continue

            if item_org_id == requesting_org_id:
                # Same org — safe to include
                safe_items.append(item)
            else:
                # Different org — this is a cross-tenant item
                if item_content_type in PROTECTED_CONTENT_TYPES:
                    # P0 violation: protected content from another org was in retrieval
                    self.log_violation(
                        item_org_id=item_org_id,
                        requesting_org_id=requesting_org_id,
                        content_type=item_content_type,
                        item_id=str(item_id),
                    )
                else:
                    # Non-protected content from another org — still excluded
                    # (defense in depth: no cross-tenant content at all)
                    logger.info(
                        "cross_tenant_boundary_excluded_non_protected",
                        item_org_id=item_org_id,
                        requesting_org_id=requesting_org_id,
                        content_type=item_content_type,
                        item_id=str(item_id),
                    )

        return safe_items

    def is_cross_tenant_violation(
        self,
        item_org_id: str,
        requesting_org_id: str,
        content_type: str,
    ) -> bool:
        """Check if this would be a cross-tenant learning boundary violation.

        Returns True if:
          - item_org_id != requesting_org_id AND
          - content_type is in PROTECTED_CONTENT_TYPES

        Args:
            item_org_id: The org that owns the item.
            requesting_org_id: The org requesting context.
            content_type: The type of content.

        Returns:
            True if this combination constitutes a cross-tenant violation.
        """
        if not item_org_id or not requesting_org_id:
            return False

        if item_org_id == requesting_org_id:
            return False

        return content_type in PROTECTED_CONTENT_TYPES

    def log_violation(
        self,
        item_org_id: str,
        requesting_org_id: str,
        content_type: str,
        item_id: str = "",
    ) -> None:
        """Log a P0 security incident for cross-tenant content violation.

        Per R95.5: Cross-tenant retrieval of protected creative content
        SHALL be treated as a P0 security incident equivalent to a tenant
        isolation breach.

        Args:
            item_org_id: The org that owns the leaked item.
            requesting_org_id: The org that would have received the item.
            content_type: The type of protected content.
            item_id: Identifier of the specific item.
        """
        violation_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "P0_CROSS_TENANT_VIOLATION",
            "severity": "P0",
            "item_org_id": item_org_id,
            "requesting_org_id": requesting_org_id,
            "content_type": content_type,
            "item_id": item_id,
            "description": (
                f"Protected content type '{content_type}' from org '{item_org_id}' "
                f"was present in context retrieval for org '{requesting_org_id}'. "
                f"This is a P0 security incident (R95.5)."
            ),
        }

        # Log at CRITICAL level — this is a P0 incident
        logger.critical(
            "P0_CROSS_TENANT_VIOLATION",
            item_org_id=item_org_id,
            requesting_org_id=requesting_org_id,
            content_type=content_type,
            item_id=item_id,
            severity="P0",
        )

        # Store for audit retrieval
        self._violations.append(violation_record)
        if len(self._violations) > self._max_violations:
            self._violations.pop(0)

    def get_violations(
        self,
        limit: int = 50,
        org_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve recorded violations for audit purposes.

        Args:
            limit: Maximum number of violations to return.
            org_id: If provided, filter to violations involving this org.

        Returns:
            List of violation records, most recent first.
        """
        if org_id:
            filtered = [
                v for v in self._violations
                if v.get("item_org_id") == org_id
                or v.get("requesting_org_id") == org_id
            ]
        else:
            filtered = self._violations

        return list(reversed(filtered[-limit:]))

    def clear_violations(self) -> None:
        """Clear recorded violations (for testing only)."""
        self._violations.clear()


# =============================================================================
# Platform Learning Gate (A2-034)
# =============================================================================


class PlatformLearningGate:
    """Controls whether platform-level learning is active.

    Per A2-034: If no approved platform-learning pipeline exists at MVP,
    the valid implementation is PLATFORM_LEARNING_DISABLED.

    Rules:
      - Raw protected content NEVER crosses the de-identification boundary
      - De-identification must be irreversible
      - Platform learning activation requires explicit Founder approval
      - Until activated: Layer 4 exists as interface only, zero data flow

    Usage:
        gate = PlatformLearningGate()
        if gate.is_enabled():
            gate.submit_for_aggregation(signal_data)
        # Currently always disabled — submit_for_aggregation() raises
    """

    def is_enabled(self) -> bool:
        """Check if platform learning is currently enabled.

        Returns False until an approved de-identification pipeline exists.
        This is a hard constraint per A2-034.
        """
        return not PLATFORM_LEARNING_DISABLED

    def submit_for_aggregation(self, data: dict[str, Any]) -> None:
        """Submit data for platform-level aggregated learning.

        Raises PlatformLearningDisabledError when the gate is disabled.
        When enabled (future), validates that only permitted signal types
        are submitted and that no protected content is present.

        Args:
            data: Signal data to submit. Must include 'signal_type' key.

        Raises:
            PlatformLearningDisabledError: When platform learning is disabled.
            ValueError: When signal_type is not in PERMITTED_PLATFORM_SIGNALS.
        """
        if not self.is_enabled():
            raise PlatformLearningDisabledError(
                "Platform learning is disabled until an approved "
                "de-identification pipeline is deployed (A2-034). "
                "PLATFORM_LEARNING_DISABLED=True."
            )

        # If we ever enable this, validate signal type
        signal_type = data.get("signal_type", "")
        if signal_type not in PERMITTED_PLATFORM_SIGNALS:
            raise ValueError(
                f"Signal type '{signal_type}' is not permitted for platform learning. "
                f"Permitted types: {sorted(PERMITTED_PLATFORM_SIGNALS)}"
            )

        # Future: submit to aggregation pipeline
        logger.info(
            "platform_learning_signal_submitted",
            signal_type=signal_type,
        )

    def validate_signal_type(self, signal_type: str) -> bool:
        """Check if a signal type is permitted for platform learning.

        Args:
            signal_type: The signal type to validate.

        Returns:
            True if the signal type is in PERMITTED_PLATFORM_SIGNALS.
        """
        return signal_type in PERMITTED_PLATFORM_SIGNALS


# =============================================================================
# Module-level singleton for convenience
# =============================================================================

# Singleton instances for use across the application
cross_tenant_boundary = CrossTenantBoundary()
platform_learning_gate = PlatformLearningGate()
