"""Pydantic schemas for Independent Verification API.

Defines request/response models for verification evidence recording,
automated verification runs, and coverage status reporting.

Each verification evidence record links:
    - requirement_id: which requirement was verified
    - method: how it was verified (automated_test, human_review, hermes_inspection, adversarial_test)
    - evidence_location: where proof lives (test file, CI run, sign-off doc)
    - verified_at: when verification occurred
    - verifier_identity: who/what performed verification
    - passed: whether verification succeeded

Key invariant: developer assertion alone is insufficient for PRODUCTION
classification — at least one non-developer verification method required.

Validates: Requirements R82.1, R82.2, R82.3, R82.4, R82.5, R82.6
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


class VerificationMethod(str, Enum):
    """Method used to verify a requirement.

    At least one non-developer method is required for PRODUCTION classification.
    """

    AUTOMATED_TEST = "automated_test"
    HUMAN_REVIEW = "human_review"
    HERMES_INSPECTION = "hermes_inspection"
    ADVERSARIAL_TEST = "adversarial_test"


class VerificationAspect(str, Enum):
    """Aspects that independent verification must validate (R82.2)."""

    COVERAGE = "coverage"
    CORRECTNESS = "correctness"
    SCHEMA_INTEGRITY = "schema_integrity"
    DEPLOYMENT_SUCCESS = "deployment_success"
    LOG_INTEGRITY = "log_integrity"
    SECURITY_POSTURE = "security_posture"
    TENANT_ISOLATION = "tenant_isolation"
    RUNTIME_CAPABILITY = "runtime_capability"
    COMPLETION_EVIDENCE = "completion_evidence"


class FeatureClassification(str, Enum):
    """Feature readiness classification.

    PRODUCTION requires independent evidence beyond developer assertion.
    """

    PRODUCTION = "PRODUCTION"
    PARTIAL = "PARTIAL"
    SIMULATED = "SIMULATED"
    UNVERIFIED = "UNVERIFIED"


# =============================================================================
# Request Schemas
# =============================================================================


class VerificationEvidenceCreateRequest(BaseSchema):
    """Request to record a manual verification evidence entry."""

    requirement_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Requirement identifier (e.g. 'R82.1', 'R2.14')",
    )
    feature_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Feature name being verified (e.g. 'tenant_isolation', 'auth_enforcement')",
    )
    method: VerificationMethod = Field(
        ...,
        description="Verification method used",
    )
    evidence_location: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Location of evidence (test file path, CI URL, sign-off document)",
    )
    evidence_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of evidence (test_suite, ci_run, manual_sign_off, red_team_report)",
    )
    passed: bool = Field(
        ...,
        description="Whether the verification passed",
    )
    verifier_identity: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Identity of verifier (user email, 'hermes', 'red_team', system name)",
    )
    notes: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional notes about the verification",
    )


class RunAutomatedVerificationRequest(BaseSchema):
    """Request to trigger automated verification suite."""

    feature_name: str | None = Field(
        default=None,
        max_length=200,
        description="Optional: restrict to a specific feature. If None, verifies all.",
    )
    aspects: list[VerificationAspect] | None = Field(
        default=None,
        description="Optional: restrict to specific verification aspects",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class VerificationEvidenceResponse(BaseSchema):
    """Single verification evidence record."""

    id: UUID
    requirement_id: str
    feature_name: str
    method: str
    evidence_location: str
    evidence_type: str
    passed: bool
    verified_at: datetime
    verifier_identity: str
    notes: str | None = None
    created_at: datetime


class VerificationRunResponse(BaseSchema):
    """Response from an automated verification run."""

    run_id: UUID
    feature_name: str | None = None
    total_requirements: int = Field(ge=0)
    verified_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    evidence_records_created: int = Field(ge=0)
    started_at: datetime
    status: str = Field(
        ...,
        description="Status: 'running', 'completed', 'failed'",
    )


class RequirementCoverageItem(BaseSchema):
    """Coverage status for a single requirement."""

    requirement_id: str
    feature_name: str
    has_automated_test: bool = False
    has_human_review: bool = False
    has_hermes_inspection: bool = False
    has_adversarial_test: bool = False
    all_passed: bool = False
    meets_independence_requirement: bool = False
    classification: str = Field(
        default="UNVERIFIED",
        description="Derived classification based on evidence",
    )
    evidence_count: int = Field(ge=0, default=0)
    last_verified_at: datetime | None = None


class VerificationStatusResponse(BaseSchema):
    """Overall verification coverage summary."""

    total_requirements: int = Field(ge=0)
    verified_requirements: int = Field(ge=0)
    production_ready_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    unverified_count: int = Field(ge=0)
    coverage_percentage: float = Field(ge=0.0, le=100.0)
    requirements: list[RequirementCoverageItem] = Field(default_factory=list)


class VerificationEvidenceListResponse(BaseSchema):
    """Paginated list of verification evidence records."""

    items: list[VerificationEvidenceResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
