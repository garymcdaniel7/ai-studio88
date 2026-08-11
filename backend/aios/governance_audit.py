"""Governance Audit Service — persistent audit logging for governance evaluations.

This module provides the GovernanceAuditService class that:
1. Persists governance evaluations from the in-memory buffer to Supabase
2. Provides query access for audit review (paginated, filtered by org)
3. Integrates with GovernanceBoundary's in-memory audit trail

All AI-initiated side effects MUST have a governance_evaluation record
before execution. This service ensures those records are durably stored.

Validates: Requirements R59.6, R59.7
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


# =============================================================================
# Filter schema for querying evaluations
# =============================================================================


@dataclass
class EvaluationFilters:
    """Filters for querying governance evaluations."""

    action_type: str | None = None
    decision: str | None = None
    risk_classification: str | None = None
    identity: str | None = None
    trust_domain: str | None = None
    is_degraded: bool | None = None
    since: datetime | None = None
    until: datetime | None = None


# =============================================================================
# Query result schema
# =============================================================================


@dataclass
class EvaluationPage:
    """Paginated result of governance evaluation queries."""

    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


# =============================================================================
# GovernanceAuditService
# =============================================================================


class GovernanceAuditService:
    """Persists and queries governance evaluation audit records.

    This service bridges the in-memory audit trail in GovernanceBoundary
    with durable storage in Supabase's governance_evaluations table.

    Usage:
        service = GovernanceAuditService()

        # Flush in-memory evaluations to Supabase
        persisted = await service.batch_persist()

        # Query evaluations for audit review
        page = await service.query_evaluations(org_id="...", limit=20, offset=0)
    """

    TABLE_NAME = "governance_evaluations"

    def __init__(self) -> None:
        """Initialize the audit service."""
        self._client = None

    def _get_client(self) -> Any:
        """Lazily get the Supabase client."""
        if self._client is None:
            from backend.database import get_supabase_client

            self._client = get_supabase_client()
        return self._client

    async def persist_evaluation(self, evaluation: dict[str, Any]) -> dict[str, Any] | None:
        """Persist a single governance evaluation record to Supabase.

        Args:
            evaluation: Dict from _record_evaluation() with keys:
                evaluation_id, correlation_id, timestamp, action_type,
                identity, trust_domain, org_id, role, risk_classification,
                decision, denial_reason, required_approval_type, is_degraded,
                failed_checks, estimated_cost_usd

        Returns:
            The persisted record dict, or None on failure.
        """
        try:
            client = self._get_client()
            row = self._evaluation_to_row(evaluation)
            result = (
                client.table(self.TABLE_NAME)
                .insert(row)
                .execute()
            )
            if result.data:
                logger.info(
                    "governance_evaluation_persisted",
                    extra={
                        "evaluation_id": evaluation.get("evaluation_id"),
                        "action_type": evaluation.get("action_type"),
                        "decision": evaluation.get("decision"),
                    },
                )
                return result.data[0]
            return None
        except Exception as exc:
            logger.error(
                "governance_evaluation_persist_failed",
                extra={
                    "evaluation_id": evaluation.get("evaluation_id"),
                    "error": str(exc)[:200],
                },
            )
            return None

    async def batch_persist(self, evaluations: list[dict[str, Any]] | None = None) -> int:
        """Persist multiple evaluations from the in-memory buffer to Supabase.

        If evaluations is None, reads and clears the in-memory audit trail
        from GovernanceBoundary.

        Args:
            evaluations: List of evaluation dicts to persist. If None, flushes
                         the in-memory buffer from governance_boundary module.

        Returns:
            Number of evaluations successfully persisted.
        """
        if evaluations is None:
            from backend.aios.governance_boundary import (
                get_evaluation_audit,
                clear_evaluation_audit,
            )

            evaluations = get_evaluation_audit()
            clear_evaluation_audit()

        if not evaluations:
            return 0

        persisted_count = 0
        try:
            client = self._get_client()
            rows = [self._evaluation_to_row(e) for e in evaluations]

            # Batch insert (Supabase supports batch inserts)
            result = client.table(self.TABLE_NAME).insert(rows).execute()
            persisted_count = len(result.data) if result.data else 0

            logger.info(
                "governance_evaluations_batch_persisted",
                extra={
                    "count": persisted_count,
                    "total_submitted": len(evaluations),
                },
            )
        except Exception as exc:
            logger.error(
                "governance_evaluations_batch_persist_failed",
                extra={
                    "total_submitted": len(evaluations),
                    "error": str(exc)[:200],
                },
            )
            # Fall back to individual inserts
            for evaluation in evaluations:
                result = await self.persist_evaluation(evaluation)
                if result is not None:
                    persisted_count += 1

        return persisted_count

    async def query_evaluations(
        self,
        org_id: str,
        filters: EvaluationFilters | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> EvaluationPage:
        """Query governance evaluations for a specific org (paginated).

        Args:
            org_id: Organization ID to query (tenant isolation enforced).
            filters: Optional filters for narrowing results.
            limit: Maximum records to return (1-100, default 20).
            offset: Offset for pagination (default 0).

        Returns:
            EvaluationPage with items, total count, limit, and offset.
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        try:
            client = self._get_client()

            # Build query
            query = (
                client.table(self.TABLE_NAME)
                .select("*", count="exact")
                .eq("org_id", org_id)
            )

            # Apply filters
            if filters:
                if filters.action_type:
                    query = query.eq("action_type", filters.action_type)
                if filters.decision:
                    query = query.eq("decision", filters.decision)
                if filters.risk_classification:
                    query = query.eq("risk_classification", filters.risk_classification)
                if filters.identity:
                    query = query.eq("identity", filters.identity)
                if filters.trust_domain:
                    query = query.eq("trust_domain", filters.trust_domain)
                if filters.is_degraded is not None:
                    query = query.eq("is_degraded", filters.is_degraded)
                if filters.since:
                    query = query.gte("created_at", filters.since.isoformat())
                if filters.until:
                    query = query.lte("created_at", filters.until.isoformat())

            # Order and paginate
            query = (
                query.order("created_at", desc=True)
                .limit(limit)
                .offset(offset)
            )

            result = query.execute()
            items = result.data if result.data else []
            total = result.count if result.count is not None else len(items)

            return EvaluationPage(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            logger.error(
                "governance_evaluations_query_failed",
                extra={"org_id": org_id, "error": str(exc)[:200]},
            )
            return EvaluationPage(items=[], total=0, limit=limit, offset=offset)

    def _evaluation_to_row(self, evaluation: dict[str, Any]) -> dict[str, Any]:
        """Convert an in-memory evaluation dict to a Supabase row.

        Maps the in-memory format to the governance_evaluations table schema.
        """
        row: dict[str, Any] = {
            "evaluation_id": evaluation.get("evaluation_id", ""),
            "correlation_id": evaluation.get("correlation_id"),
            "action_type": evaluation.get("action_type", "unknown"),
            "identity": evaluation.get("identity"),
            "trust_domain": evaluation.get("trust_domain"),
            "org_id": evaluation.get("org_id"),
            "role": evaluation.get("role"),
            "risk_classification": evaluation.get("risk_classification", "medium_impact"),
            "decision": evaluation.get("decision", "deny"),
            "denial_reason": evaluation.get("denial_reason"),
            "required_approval_type": evaluation.get("required_approval_type"),
            "is_degraded": evaluation.get("is_degraded", False),
            "failed_checks": evaluation.get("failed_checks", []),
            "estimated_cost_usd": evaluation.get("estimated_cost_usd"),
        }

        # Set created_at from the evaluation timestamp if available
        timestamp = evaluation.get("timestamp")
        if timestamp:
            row["created_at"] = timestamp

        return row
