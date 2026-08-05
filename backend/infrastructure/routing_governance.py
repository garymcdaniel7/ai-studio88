"""Provider Routing Governance — Story 060.

Durable evidence-based routing decisions, scoped reputation, and
blacklist/suppression lifecycle with expiry, review, and reinstatement.

Evidence hierarchy (scoped reputation):
    provider → region → gpu_type → host → template/image → account

Failure taxonomy:
    provider_rejection  — provider API refused the request
    capacity_shortage   — no available instances/GPUs
    credential_failure  — auth/key issue
    startup_timeout     — instance didn't become reachable
    health_failure      — instance alive but service unhealthy
    job_failure         — job failed after successful start
    cleanup_failure     — termination/destroy failed
    customer_cancel     — user cancelled (not a fault)

Blacklist/Suppression lifecycle:
    create → active → (expires | reviewed → reinstated | extended)

DECISION-REQUIRED:
    - Minimum evidence count before reputation affects routing
    - Confidence decay rate for stale evidence
    - Auto-suppression threshold (failure rate % over N attempts)
    - Review cadence for active suppressions
    - Retention period for historical evidence
    - Authority levels for manual blacklist
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Evidence Scope
# =============================================================================


class EvidenceScope(str, Enum):
    PROVIDER = "provider"        # e.g., "vast", "runpod"
    REGION = "region"            # e.g., "us-east-1"
    GPU_TYPE = "gpu_type"        # e.g., "RTX 4090", "A100"
    HOST = "host"                # Specific machine/host ID
    TEMPLATE = "template"        # Docker image/template
    ACCOUNT = "account"          # Provider account/credential


class FailureCategory(str, Enum):
    PROVIDER_REJECTION = "provider_rejection"
    CAPACITY_SHORTAGE = "capacity_shortage"
    CREDENTIAL_FAILURE = "credential_failure"
    STARTUP_TIMEOUT = "startup_timeout"
    HEALTH_FAILURE = "health_failure"
    JOB_FAILURE = "job_failure"
    CLEANUP_FAILURE = "cleanup_failure"
    CUSTOMER_CANCEL = "customer_cancel"
    SUCCESS = "success"


class SuppressionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REINSTATED = "reinstated"
    EXTENDED = "extended"


# =============================================================================
# Evidence Record
# =============================================================================


@dataclass
class RoutingEvidence:
    """A single piece of provider-routing evidence."""
    evidence_id: str = field(default_factory=lambda: f"ev-{uuid.uuid4().hex[:12]}")
    org_id: str = ""

    # Scope identification
    provider: str = ""
    region: str | None = None
    gpu_type: str | None = None
    host_id: str | None = None
    template: str | None = None
    account_id: str | None = None

    # Outcome
    outcome: FailureCategory = FailureCategory.SUCCESS
    outcome_detail: str = ""

    # Metrics
    latency_ms: int | None = None
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None

    # Context
    job_id: str | None = None
    worker_id: str | None = None
    policy_version: str = ""

    # Timing
    recorded_at: float = field(default_factory=time.time)


# =============================================================================
# Routing Decision Record
# =============================================================================


@dataclass
class RoutingDecision:
    """Record of a routing decision with full context for audit."""
    decision_id: str = field(default_factory=lambda: f"rd-{uuid.uuid4().hex[:12]}")
    org_id: str = ""

    # What was decided
    selected_provider: str = ""
    selected_region: str | None = None
    selected_gpu_type: str | None = None
    selected_host_id: str | None = None

    # Alternatives
    candidates_considered: int = 0
    candidates_suppressed: int = 0

    # Evidence used
    evidence_count: int = 0
    evidence_freshness_hours: float | None = None
    confidence: float = 0.0  # 0.0 = no evidence, 1.0 = high confidence

    # Policy
    policy_version: str = ""
    reason: str = ""

    # Cost
    estimated_cost_usd: float | None = None

    # Timing
    decided_at: float = field(default_factory=time.time)


# =============================================================================
# Scoped Reputation
# =============================================================================


@dataclass
class ReputationRecord:
    """Aggregated reputation for a specific scope."""
    scope: EvidenceScope = EvidenceScope.PROVIDER
    scope_id: str = ""  # e.g., "vast", "us-east-1", "RTX 4090"

    # Aggregated metrics
    total_attempts: int = 0
    successes: int = 0
    failures: int = 0
    avg_latency_ms: float | None = None

    # Failure breakdown
    failure_categories: dict[str, int] = field(default_factory=dict)

    # Confidence
    confidence: float = 0.0  # Based on evidence count and freshness
    last_evidence_at: float | None = None
    is_stale: bool = False  # True if no recent evidence

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.successes / self.total_attempts

    @property
    def failure_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.failures / self.total_attempts


# =============================================================================
# Suppression/Blacklist Record
# =============================================================================


@dataclass
class SuppressionRecord:
    """A scoped suppression or blacklist entry with full audit trail."""
    suppression_id: str = field(default_factory=lambda: f"sup-{uuid.uuid4().hex[:12]}")

    # Scope
    scope: EvidenceScope = EvidenceScope.HOST
    scope_id: str = ""
    provider: str = ""

    # Reason and authority
    reason: str = ""
    authority: str = ""  # "automated:failure_threshold" or "manual:user-xyz"
    evidence_ids: list[str] = field(default_factory=list)

    # Lifecycle
    status: SuppressionStatus = SuppressionStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    review_at: float | None = None
    reinstated_at: float | None = None
    reinstated_by: str | None = None

    # Audit
    history: list[dict] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at and self.status == SuppressionStatus.ACTIVE

    @property
    def is_active(self) -> bool:
        return self.status == SuppressionStatus.ACTIVE and not self.is_expired

    @property
    def needs_review(self) -> bool:
        if self.review_at and time.time() > self.review_at:
            return True
        return False


# =============================================================================
# Store
# =============================================================================

_evidence_store: list[RoutingEvidence] = []
_decision_store: list[RoutingDecision] = []
_suppression_store: dict[str, SuppressionRecord] = {}

# DECISION-REQUIRED: configurable policy values
STALE_EVIDENCE_HOURS = 72  # Evidence older than this is considered stale
MIN_EVIDENCE_FOR_CONFIDENCE = 5  # Below this, confidence is low
DEFAULT_SUPPRESSION_HOURS = 24  # Auto-suppression duration


# =============================================================================
# Evidence Recording
# =============================================================================


def record_evidence(
    org_id: str,
    provider: str,
    outcome: FailureCategory,
    region: str | None = None,
    gpu_type: str | None = None,
    host_id: str | None = None,
    template: str | None = None,
    latency_ms: int | None = None,
    estimated_cost_usd: float | None = None,
    actual_cost_usd: float | None = None,
    job_id: str | None = None,
    detail: str = "",
    policy_version: str = "",
) -> RoutingEvidence:
    """Record a routing outcome as durable evidence."""
    if not org_id or not provider:
        raise ValueError("org_id and provider required for evidence recording")

    evidence = RoutingEvidence(
        org_id=org_id,
        provider=provider,
        region=region,
        gpu_type=gpu_type,
        host_id=host_id,
        template=template,
        outcome=outcome,
        outcome_detail=detail,
        latency_ms=latency_ms,
        estimated_cost_usd=estimated_cost_usd,
        actual_cost_usd=actual_cost_usd,
        job_id=job_id,
        policy_version=policy_version,
    )
    _evidence_store.append(evidence)

    logger.info(
        f"ROUTING_EVIDENCE: provider={provider} outcome={outcome.value} "
        f"host={host_id or '-'} org={org_id[:8]}"
    )
    return evidence


# =============================================================================
# Routing Decision Recording
# =============================================================================


def record_routing_decision(
    org_id: str,
    selected_provider: str,
    candidates_considered: int,
    candidates_suppressed: int = 0,
    reason: str = "",
    confidence: float = 0.0,
    evidence_count: int = 0,
    policy_version: str = "",
    estimated_cost_usd: float | None = None,
    selected_region: str | None = None,
    selected_gpu_type: str | None = None,
) -> RoutingDecision:
    """Record a routing decision for audit."""
    decision = RoutingDecision(
        org_id=org_id,
        selected_provider=selected_provider,
        selected_region=selected_region,
        selected_gpu_type=selected_gpu_type,
        candidates_considered=candidates_considered,
        candidates_suppressed=candidates_suppressed,
        evidence_count=evidence_count,
        confidence=confidence,
        policy_version=policy_version,
        reason=reason,
        estimated_cost_usd=estimated_cost_usd,
    )
    _decision_store.append(decision)
    return decision


# =============================================================================
# Reputation Aggregation
# =============================================================================


def get_reputation(
    scope: EvidenceScope,
    scope_id: str,
    max_age_hours: float = STALE_EVIDENCE_HOURS,
) -> ReputationRecord:
    """Aggregate reputation for a specific scope.

    Honest about evidence quality: stale/sparse evidence is explicitly marked.
    """
    cutoff = time.time() - (max_age_hours * 3600)
    relevant = []

    for ev in _evidence_store:
        if ev.recorded_at < cutoff:
            continue

        # Match scope
        if scope == EvidenceScope.PROVIDER and ev.provider == scope_id:
            relevant.append(ev)
        elif scope == EvidenceScope.REGION and ev.region == scope_id:
            relevant.append(ev)
        elif scope == EvidenceScope.GPU_TYPE and ev.gpu_type == scope_id:
            relevant.append(ev)
        elif scope == EvidenceScope.HOST and ev.host_id == scope_id:
            relevant.append(ev)
        elif scope == EvidenceScope.TEMPLATE and ev.template == scope_id:
            relevant.append(ev)
        elif scope == EvidenceScope.ACCOUNT and ev.account_id == scope_id:
            relevant.append(ev)

    # Build reputation
    record = ReputationRecord(scope=scope, scope_id=scope_id)
    record.total_attempts = len(relevant)

    if not relevant:
        record.is_stale = True
        record.confidence = 0.0
        return record

    record.successes = sum(1 for e in relevant if e.outcome == FailureCategory.SUCCESS)
    record.failures = sum(1 for e in relevant if e.outcome != FailureCategory.SUCCESS and e.outcome != FailureCategory.CUSTOMER_CANCEL)
    record.last_evidence_at = max(e.recorded_at for e in relevant)

    # Latency
    latencies = [e.latency_ms for e in relevant if e.latency_ms is not None]
    if latencies:
        record.avg_latency_ms = sum(latencies) / len(latencies)

    # Failure breakdown
    for ev in relevant:
        if ev.outcome != FailureCategory.SUCCESS:
            cat = ev.outcome.value
            record.failure_categories[cat] = record.failure_categories.get(cat, 0) + 1

    # Confidence: based on evidence count and freshness
    count_factor = min(record.total_attempts / MIN_EVIDENCE_FOR_CONFIDENCE, 1.0)
    freshness_hours = (time.time() - record.last_evidence_at) / 3600
    freshness_factor = max(0.0, 1.0 - (freshness_hours / max_age_hours))
    record.confidence = round(count_factor * freshness_factor, 2)

    # Stale if last evidence is old
    record.is_stale = freshness_hours > max_age_hours * 0.8

    return record


# =============================================================================
# Suppression/Blacklist Operations
# =============================================================================


def suppress(
    scope: EvidenceScope,
    scope_id: str,
    provider: str,
    reason: str,
    authority: str,
    duration_hours: float = DEFAULT_SUPPRESSION_HOURS,
    evidence_ids: list[str] | None = None,
    review_hours: float | None = None,
) -> SuppressionRecord:
    """Create a scoped suppression (temporary block from routing).

    Args:
        scope: What level is being suppressed (host, region, provider, etc.)
        scope_id: The identifier at that scope
        provider: Which provider this applies to
        reason: Why this suppression exists
        authority: Who/what created it ("automated:rule_name" or "manual:user_id")
        duration_hours: How long the suppression lasts
        evidence_ids: Links to supporting evidence
        review_hours: When to trigger review (optional, defaults to expiry)
    """
    if not scope_id or not reason or not authority:
        raise ValueError("scope_id, reason, and authority required for suppression")

    record = SuppressionRecord(
        scope=scope,
        scope_id=scope_id,
        provider=provider,
        reason=reason,
        authority=authority,
        evidence_ids=evidence_ids or [],
        expires_at=time.time() + (duration_hours * 3600),
        review_at=time.time() + ((review_hours or duration_hours) * 3600),
    )
    record.history.append({
        "action": "created",
        "at": time.time(),
        "by": authority,
        "reason": reason,
    })

    _suppression_store[record.suppression_id] = record
    logger.info(f"SUPPRESSION_CREATED: scope={scope.value}:{scope_id} provider={provider} duration={duration_hours}h")
    return record


def reinstate(suppression_id: str, reinstated_by: str, reason: str = "") -> SuppressionRecord:
    """Reinstate a suppressed resource (end suppression early)."""
    record = _suppression_store.get(suppression_id)
    if not record:
        raise ValueError(f"Suppression {suppression_id} not found")

    if record.status != SuppressionStatus.ACTIVE:
        raise ValueError(f"Cannot reinstate: status is {record.status.value}")

    record.status = SuppressionStatus.REINSTATED
    record.reinstated_at = time.time()
    record.reinstated_by = reinstated_by
    record.history.append({
        "action": "reinstated",
        "at": time.time(),
        "by": reinstated_by,
        "reason": reason,
    })

    logger.info(f"SUPPRESSION_REINSTATED: id={suppression_id} by={reinstated_by}")
    return record


def is_suppressed(scope: EvidenceScope, scope_id: str) -> bool:
    """Check if a resource is currently suppressed (active and not expired)."""
    for record in _suppression_store.values():
        if record.scope == scope and record.scope_id == scope_id and record.is_active:
            return True
    return False


def get_active_suppressions(provider: str | None = None) -> list[SuppressionRecord]:
    """List all active (non-expired, non-reinstated) suppressions."""
    results = []
    for record in _suppression_store.values():
        if record.is_active:
            if provider is None or record.provider == provider:
                results.append(record)
    return results


def expire_stale_suppressions() -> list[str]:
    """Check and mark expired suppressions. Returns IDs of newly expired."""
    expired_ids = []
    for record in _suppression_store.values():
        if record.status == SuppressionStatus.ACTIVE and record.is_expired:
            record.status = SuppressionStatus.EXPIRED
            record.history.append({"action": "expired", "at": time.time(), "by": "system"})
            expired_ids.append(record.suppression_id)
    return expired_ids


# =============================================================================
# Routing Query (consume reputation + suppression)
# =============================================================================


def get_routing_context(provider: str, region: str | None = None, gpu_type: str | None = None, host_id: str | None = None) -> dict[str, Any]:
    """Get routing context for a candidate — reputation + suppression status.

    Returns a dict suitable for routing decisions. Fails safely:
    no evidence = neutral (not positive, not negative).
    """
    context: dict[str, Any] = {
        "provider": provider,
        "suppressed": False,
        "suppression_reason": None,
        "reputation": None,
        "evidence_available": False,
    }

    # Check suppressions at all applicable scopes
    if is_suppressed(EvidenceScope.PROVIDER, provider):
        context["suppressed"] = True
        context["suppression_reason"] = f"Provider '{provider}' is suppressed"
        return context

    if region and is_suppressed(EvidenceScope.REGION, region):
        context["suppressed"] = True
        context["suppression_reason"] = f"Region '{region}' is suppressed"
        return context

    if gpu_type and is_suppressed(EvidenceScope.GPU_TYPE, gpu_type):
        context["suppressed"] = True
        context["suppression_reason"] = f"GPU type '{gpu_type}' is suppressed"
        return context

    if host_id and is_suppressed(EvidenceScope.HOST, host_id):
        context["suppressed"] = True
        context["suppression_reason"] = f"Host '{host_id}' is suppressed"
        return context

    # Get reputation
    rep = get_reputation(EvidenceScope.PROVIDER, provider)
    context["reputation"] = {
        "success_rate": rep.success_rate,
        "total_attempts": rep.total_attempts,
        "confidence": rep.confidence,
        "is_stale": rep.is_stale,
        "avg_latency_ms": rep.avg_latency_ms,
    }
    context["evidence_available"] = rep.total_attempts > 0

    return context


# =============================================================================
# Testing
# =============================================================================


def _reset_store() -> None:
    _evidence_store.clear()
    _decision_store.clear()
    _suppression_store.clear()
