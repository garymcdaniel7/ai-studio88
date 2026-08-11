"""Pydantic schemas for Production Gate API.

Defines request/response models for gate evaluation, approval, and status.

Each check result includes:
    - check_name: identifier for the specific gate check
    - passed: whether it succeeded
    - evidence_url: optional link to evidence artifact
    - message: human-readable status message
    - checked_at: ISO timestamp of when the check ran

Validates: Requirements R83.1, R83.2, R83.6, R83.7, R83.8, R83.9
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class GateType(str, Enum):
    """Gate evaluation type — full or emergency (hotfix)."""

    FULL = "full"
    EMERGENCY = "emergency"


class GateCheckName(str, Enum):
    """All defined gate check types per R83.2."""

    FRONTEND_BUILD = "frontend_build"
    BACKEND_BUILD = "backend_build"
    CI_GREEN = "ci_green"
    FRONTEND_DEPLOY = "frontend_deploy"
    BACKEND_DEPLOY = "backend_deploy"
    SCHEMA_MIGRATION_MATCH = "schema_migration_match"
    TENANT_ISOLATION_TESTS = "tenant_isolation_tests"
    PRODUCTION_CAPABILITIES = "production_capabilities"
    SECURITY_EVIDENCE = "security_evidence"
    ROLLBACK_DOCUMENTED = "rollback_documented"
    DB_RESTORE_REHEARSED = "db_restore_rehearsed"
    MONITORING_ACTIVE = "monitoring_active"
    DEPLOYMENT_REPEATABLE = "deployment_repeatable"
    NO_SUPPRESSED_ERRORS = "no_suppressed_errors"


# Emergency path requires only a subset of checks (R83.7)
EMERGENCY_REQUIRED_CHECKS: set[GateCheckName] = {
    GateCheckName.FRONTEND_BUILD,
    GateCheckName.BACKEND_BUILD,
    GateCheckName.CI_GREEN,
    GateCheckName.TENANT_ISOLATION_TESTS,
    GateCheckName.SECURITY_EVIDENCE,
}

# Full gate requires ALL checks
FULL_REQUIRED_CHECKS: set[GateCheckName] = set(GateCheckName)


# =============================================================================
# Check Result Schema
# =============================================================================


class GateCheckResult(BaseSchema):
    """Result of a single gate check execution."""

    check_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identifier of the gate check",
    )
    passed: bool = Field(
        ...,
        description="Whether this check passed",
    )
    evidence_url: str | None = Field(
        default=None,
        max_length=2000,
        description="URL to evidence artifact (CI run, deployment log, etc.)",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Human-readable status message",
    )
    checked_at: datetime = Field(
        ...,
        description="When this check was executed",
    )


# =============================================================================
# Request Schemas
# =============================================================================


class ProductionGateRunRequest(BaseSchema):
    """Request to run gate checks for a release identity."""

    release_identity_id: UUID = Field(
        ...,
        description="UUID of the Release Identity to evaluate",
    )
    gate_type: GateType = Field(
        default=GateType.FULL,
        description="Gate type: 'full' (all checks) or 'emergency' (reduced subset)",
    )
    check_overrides: dict[str, bool] | None = Field(
        default=None,
        description="Optional manual check result overrides (admin only)",
    )


class ProductionGateApproveRequest(BaseSchema):
    """Request to approve a gate that has all required checks passing."""

    evidence_links: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of check_name to evidence URL for the approval record",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ProductionGateResponse(BaseSchema):
    """Full response for a production gate evaluation."""

    id: UUID
    release_identity_id: UUID
    gate_type: str
    checks: list[GateCheckResult] = Field(default_factory=list)
    all_passed: bool
    evidence_links: dict[str, str] = Field(default_factory=dict)
    approving_actor: UUID | None = None
    approved_at: datetime | None = None
    emergency_verification_due: datetime | None = None
    emergency_verified: bool = False
    failure_summary: str | None = None
    created_at: datetime


class ProductionGateStatusResponse(BaseSchema):
    """Compact gate status — for dashboard views and quick checks."""

    id: UUID
    release_identity_id: UUID
    gate_type: str
    all_passed: bool
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    failed_checks: int = Field(ge=0)
    approved_at: datetime | None = None
    emergency_verification_due: datetime | None = None
    failure_summary: str | None = None
    created_at: datetime


class ProductionGateListResponse(BaseSchema):
    """Paginated list of production gate evaluations."""

    items: list[ProductionGateResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
