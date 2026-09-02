"""Context Disclosure Gate — Story 085.

Ensures every context source reports truthful status before generation.
Required failures BLOCK generation by default. Optional failures are disclosed.
Any allowed override is recorded with actor, reason, policy, and affected sources.

This module sits between the context assembler (Story 081) and generation
execution. It evaluates the assembled context and produces a gate decision:

    PROCEED   — All required sources loaded; generation may begin
    BLOCKED   — One or more required sources failed; generation halted
    OVERRIDE  — Required failure(s) present but authorized override applied

Every decision, omission, and override is persisted for generation audit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Gate Decision
# =============================================================================


class GateDecision(StrEnum):
    PROCEED = "proceed"         # All required sources OK
    BLOCKED = "blocked"         # Required failure(s), generation halted
    OVERRIDE = "override"       # Override applied, generation proceeds with risk


# =============================================================================
# Source Status (aligned with Story 081)
# =============================================================================


class SourceStatus(StrEnum):
    LOADED = "loaded"
    ABSENT = "absent"
    FILTERED = "filtered"
    STALE = "stale"
    ERROR = "error"
    UNAUTHORIZED = "unauthorized"


class SourceRequirement(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


# Statuses that count as "failed" for blocking purposes
FAILURE_STATUSES: set[SourceStatus] = {
    SourceStatus.ABSENT,
    SourceStatus.ERROR,
    SourceStatus.UNAUTHORIZED,
}

# Statuses that produce warnings but don't block
WARNING_STATUSES: set[SourceStatus] = {
    SourceStatus.FILTERED,
    SourceStatus.STALE,
}


# =============================================================================
# Source Disclosure
# =============================================================================


@dataclass
class SourceDisclosure:
    """Per-source status disclosure for generation review."""

    source_name: str
    status: SourceStatus
    requirement: SourceRequirement
    is_blocking: bool = False       # True if this source blocks generation
    warning: str | None = None      # User-visible, non-sensitive warning
    error: str | None = None        # Technical detail (not exposed to UI)
    record_count: int = 0
    versions: list[int] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "status": self.status.value,
            "requirement": self.requirement.value,
            "is_blocking": self.is_blocking,
            "warning": self.warning,
            "record_count": self.record_count,
            "versions": self.versions,
            "timestamp": self.timestamp,
        }

    def to_user_warning(self) -> str | None:
        """User-visible warning (no technical details or cross-tenant info)."""
        if self.status == SourceStatus.LOADED:
            return None
        if self.status == SourceStatus.ABSENT:
            return f"{self.source_name}: no data available"
        if self.status == SourceStatus.STALE:
            return f"{self.source_name}: data may be outdated"
        if self.status == SourceStatus.FILTERED:
            return f"{self.source_name}: some records excluded (unapproved/archived)"
        if self.status == SourceStatus.ERROR:
            return f"{self.source_name}: failed to load"
        if self.status == SourceStatus.UNAUTHORIZED:
            return f"{self.source_name}: access denied"
        return None


# =============================================================================
# Override Record
# =============================================================================


@dataclass
class OverrideRecord:
    """Evidence of an authorized override of a blocking condition."""

    override_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actor_id: str = ""
    actor_role: str = ""
    reason: str = ""
    policy: str = "manual_override"     # manual_override, emergency, testing
    affected_sources: list[str] = field(default_factory=list)
    org_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str | None = None       # Time-bound override

    def to_dict(self) -> dict:
        return {
            "override_id": self.override_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "reason": self.reason,
            "policy": self.policy,
            "affected_sources": self.affected_sources,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


# Roles permitted to override required failures
OVERRIDE_ALLOWED_ROLES: set[str] = {"owner", "admin"}

# Minimum reason length for overrides
OVERRIDE_MIN_REASON_LENGTH: int = 10


# =============================================================================
# Disclosure Gate Result
# =============================================================================


@dataclass
class DisclosureGateResult:
    """The complete disclosure gate evaluation."""

    # Identity
    gate_id: str = field(default_factory=lambda: f"gate-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""
    talent_id: str = ""
    context_package_id: str = ""

    # Decision
    decision: GateDecision = GateDecision.BLOCKED
    decision_reason: str = ""

    # Per-source disclosures
    disclosures: list[SourceDisclosure] = field(default_factory=list)

    # Summary
    total_sources: int = 0
    loaded_count: int = 0
    failed_count: int = 0
    warning_count: int = 0
    blocking_count: int = 0

    # Override (if applied)
    override: OverrideRecord | None = None

    # User-visible warnings (safe to display)
    user_warnings: list[str] = field(default_factory=list)

    # Timing
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "org_id": self.org_id,
            "decision": self.decision.value,
            "decision_reason": self.decision_reason,
            "total_sources": self.total_sources,
            "loaded_count": self.loaded_count,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "blocking_count": self.blocking_count,
            "user_warnings": self.user_warnings,
            "override": self.override.to_dict() if self.override else None,
            "disclosures": [d.to_dict() for d in self.disclosures],
            "evaluated_at": self.evaluated_at,
        }


# =============================================================================
# Gate Evaluation
# =============================================================================


@dataclass
class SourceInput:
    """Input for a single source evaluation (from context assembler)."""

    source_name: str
    status: SourceStatus
    requirement: SourceRequirement
    record_count: int = 0
    versions: list[int] = field(default_factory=list)
    error: str | None = None


def evaluate_gate(
    *,
    org_id: str,
    user_id: str,
    talent_id: str = "",
    context_package_id: str = "",
    sources: list[SourceInput],
    override: OverrideRecord | None = None,
) -> DisclosureGateResult:
    """Evaluate the context disclosure gate.

    Rules:
    1. Required source with FAILURE status → BLOCKED (unless override)
    2. Recommended source with FAILURE status → WARNING (non-blocking)
    3. Optional source with FAILURE status → disclosed but non-blocking
    4. Override with valid role + reason → OVERRIDE decision
    5. All required loaded → PROCEED
    """
    result = DisclosureGateResult(
        org_id=org_id,
        user_id=user_id,
        talent_id=talent_id,
        context_package_id=context_package_id,
        total_sources=len(sources),
    )

    blocking_sources: list[str] = []

    for src in sources:
        is_failure = src.status in FAILURE_STATUSES
        is_warning = src.status in WARNING_STATUSES
        is_blocking = is_failure and src.requirement == SourceRequirement.REQUIRED

        disclosure = SourceDisclosure(
            source_name=src.source_name,
            status=src.status,
            requirement=src.requirement,
            is_blocking=is_blocking,
            error=src.error,
            record_count=src.record_count,
            versions=src.versions,
        )

        # Generate user-visible warning
        warning_text = disclosure.to_user_warning()
        if warning_text:
            disclosure.warning = warning_text
            result.user_warnings.append(warning_text)
            result.warning_count += 1

        if src.status == SourceStatus.LOADED:
            result.loaded_count += 1
        elif is_failure:
            result.failed_count += 1
            if is_blocking:
                result.blocking_count += 1
                blocking_sources.append(src.source_name)

        result.disclosures.append(disclosure)

    # Determine decision
    if not blocking_sources:
        result.decision = GateDecision.PROCEED
        result.decision_reason = f"All {result.loaded_count} required sources loaded"
    elif override is not None:
        # Validate override
        validation = validate_override(override, blocking_sources)
        if validation is None:
            result.decision = GateDecision.OVERRIDE
            result.override = override
            result.decision_reason = (
                f"Override by {override.actor_id}: {override.reason} "
                f"(blocking: {', '.join(blocking_sources)})"
            )
        else:
            result.decision = GateDecision.BLOCKED
            result.decision_reason = f"Override rejected: {validation}"
    else:
        result.decision = GateDecision.BLOCKED
        result.decision_reason = (
            f"Required source(s) failed: {', '.join(blocking_sources)}"
        )

    return result


# =============================================================================
# Override Validation
# =============================================================================


def validate_override(
    override: OverrideRecord,
    blocking_sources: list[str],
) -> str | None:
    """Validate an override request.

    Returns None if valid, or error message if rejected.
    """
    if override.actor_role not in OVERRIDE_ALLOWED_ROLES:
        return f"Role '{override.actor_role}' not permitted to override (need: {OVERRIDE_ALLOWED_ROLES})"

    if not override.reason or len(override.reason) < OVERRIDE_MIN_REASON_LENGTH:
        return f"Override reason must be at least {OVERRIDE_MIN_REASON_LENGTH} characters"

    if not override.actor_id:
        return "Override requires actor_id"

    return None  # Valid


# =============================================================================
# Generation Audit Record
# =============================================================================


@dataclass
class GenerationAuditEntry:
    """Persisted record of context disclosure for a generation."""

    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    user_id: str = ""
    talent_id: str = ""
    job_id: str = ""
    context_package_id: str = ""
    gate_id: str = ""

    # Decision snapshot
    decision: GateDecision = GateDecision.BLOCKED
    decision_reason: str = ""

    # Omissions
    omitted_sources: list[dict] = field(default_factory=list)
    # Each: {"source": "...", "status": "...", "requirement": "...", "reason": "..."}

    # Override evidence (if any)
    override_evidence: dict | None = None

    # Warnings shown to user
    warnings_shown: list[str] = field(default_factory=list)

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "org_id": self.org_id,
            "job_id": self.job_id,
            "context_package_id": self.context_package_id,
            "gate_id": self.gate_id,
            "decision": self.decision.value,
            "decision_reason": self.decision_reason,
            "omitted_sources": self.omitted_sources,
            "override_evidence": self.override_evidence,
            "warnings_shown": self.warnings_shown,
            "created_at": self.created_at,
        }


# =============================================================================
# Audit Persistence
# =============================================================================

_audit_store: list[GenerationAuditEntry] = []


def clear_audit_store() -> None:
    """Clear store (testing only)."""
    _audit_store.clear()


def persist_audit(gate_result: DisclosureGateResult, job_id: str = "") -> GenerationAuditEntry:
    """Persist the gate decision as a generation audit record.

    Records ALL omissions, warnings, and override evidence.
    """
    omitted = [
        {
            "source": d.source_name,
            "status": d.status.value,
            "requirement": d.requirement.value,
            "reason": d.error or d.warning or "",
        }
        for d in gate_result.disclosures
        if d.status != SourceStatus.LOADED
    ]

    entry = GenerationAuditEntry(
        org_id=gate_result.org_id,
        user_id=gate_result.user_id,
        talent_id=gate_result.talent_id,
        job_id=job_id,
        context_package_id=gate_result.context_package_id,
        gate_id=gate_result.gate_id,
        decision=gate_result.decision,
        decision_reason=gate_result.decision_reason,
        omitted_sources=omitted,
        override_evidence=gate_result.override.to_dict() if gate_result.override else None,
        warnings_shown=gate_result.user_warnings,
    )

    _audit_store.append(entry)
    return entry


def get_audit_for_job(job_id: str) -> GenerationAuditEntry | None:
    """Retrieve audit entry for a generation job."""
    for entry in _audit_store:
        if entry.job_id == job_id:
            return entry
    return None


def get_audits_for_org(org_id: str) -> list[GenerationAuditEntry]:
    """Retrieve all audit entries for an org (tenant-scoped)."""
    return [e for e in _audit_store if e.org_id == org_id]
