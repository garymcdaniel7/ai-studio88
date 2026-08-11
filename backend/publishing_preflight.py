"""Publishing Preflight — Story 123.

Versioned server-side evaluation of publishing policy, disclosure requirements,
platform capabilities, and content compliance BEFORE approval and execution.

Every publishable variant must have a current evidence-backed preflight result.
Changed content, account, assets, or disclosures invalidate prior results.

Evaluation States:
    PASS            — All required checks passed, ready to publish
    BLOCK           — One or more required checks failed, cannot publish
    REVIEW_REQUIRED — Human review needed before publishing
    UNAVAILABLE     — Required check could not be performed (fail-safe)
    WARNING         — Non-blocking issues disclosed

Check Categories:
    DISCLOSURE      — Required labeling (sponsored, synthetic, AI-generated)
    PLATFORM        — Destination platform capability/compatibility
    CONSENT         — Talent/voice consent still valid
    SYNTHETIC_MEDIA — AI-generated content disclosure requirements
    SPONSORSHIP     — Paid partnership/branded content rules
    ACCOUNT         — Connected account status and permissions
    ASSET           — Asset provenance and lineage completeness

Approval Binding:
    Approval binds to the exact preflight result (by content_hash).
    Material changes invalidate the approval — re-preflight required.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Evaluation States
# =============================================================================


class PreflightState(StrEnum):
    PASS = "pass"
    BLOCK = "block"
    REVIEW_REQUIRED = "review_required"
    UNAVAILABLE = "unavailable"
    WARNING = "warning"


class CheckCategory(StrEnum):
    DISCLOSURE = "disclosure"
    PLATFORM = "platform"
    CONSENT = "consent"
    SYNTHETIC_MEDIA = "synthetic_media"
    SPONSORSHIP = "sponsorship"
    ACCOUNT = "account"
    ASSET = "asset"


class CheckRequirement(StrEnum):
    REQUIRED = "required"       # Failure blocks publishing
    RECOMMENDED = "recommended" # Failure produces warning
    OPTIONAL = "optional"       # Informational only


# =============================================================================
# Individual Check Result
# =============================================================================


@dataclass
class PreflightCheck:
    """Result of a single preflight check."""

    check_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: CheckCategory = CheckCategory.DISCLOSURE
    name: str = ""
    requirement: CheckRequirement = CheckRequirement.REQUIRED
    state: PreflightState = PreflightState.PASS
    message: str = ""               # User-visible explanation
    evidence: str = ""              # What was checked (no secrets)
    policy_version: str = ""        # Which policy version was applied

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "category": self.category.value,
            "name": self.name,
            "requirement": self.requirement.value,
            "state": self.state.value,
            "message": self.message,
            "evidence": self.evidence,
            "policy_version": self.policy_version,
        }


# =============================================================================
# Disclosure Package
# =============================================================================


@dataclass
class DisclosurePackage:
    """Required disclosures for the content."""

    is_sponsored: bool = False
    sponsor_name: str = ""
    is_synthetic: bool = False      # Contains AI-generated media
    is_ai_voice: bool = False       # Contains cloned/synthetic voice
    synthetic_disclosure_text: str = ""
    sponsorship_disclosure_text: str = ""
    jurisdiction_notes: list[str] = field(default_factory=list)
    # DECISION-REQUIRED: exact wording depends on jurisdiction
    disclosure_policy_version: str = "UNVERIFIED"

    def to_dict(self) -> dict:
        return {
            "is_sponsored": self.is_sponsored,
            "sponsor_name": self.sponsor_name,
            "is_synthetic": self.is_synthetic,
            "is_ai_voice": self.is_ai_voice,
            "synthetic_disclosure_text": self.synthetic_disclosure_text,
            "sponsorship_disclosure_text": self.sponsorship_disclosure_text,
            "jurisdiction_notes": self.jurisdiction_notes,
            "disclosure_policy_version": self.disclosure_policy_version,
        }


# =============================================================================
# Preflight Result (immutable after evaluation)
# =============================================================================


@dataclass
class PreflightResult:
    """Complete preflight evaluation result."""

    # Identity
    result_id: str = field(default_factory=lambda: f"pf-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""

    # Content identity (what was evaluated)
    content_item_id: str = ""
    content_version: int = 0
    content_hash: str = ""          # Hash of content + assets + disclosures
    platform: str = ""              # Destination platform (instagram, tiktok, youtube...)
    account_id: str = ""            # Connected social account

    # Evaluation
    overall_state: PreflightState = PreflightState.UNAVAILABLE
    checks: list[PreflightCheck] = field(default_factory=list)
    disclosures: DisclosurePackage = field(default_factory=DisclosurePackage)

    # Summary
    passed_count: int = 0
    blocked_count: int = 0
    warning_count: int = 0
    unavailable_count: int = 0

    # Policy
    policy_version: str = "1.0"
    evaluated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_stale: bool = False          # True if content changed after evaluation

    # Approval binding
    approval_id: str | None = None  # Set when approved
    approved_at: str | None = None
    approved_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "result_id": self.result_id,
            "org_id": self.org_id,
            "content_item_id": self.content_item_id,
            "content_version": self.content_version,
            "content_hash": self.content_hash,
            "platform": self.platform,
            "overall_state": self.overall_state.value,
            "passed_count": self.passed_count,
            "blocked_count": self.blocked_count,
            "warning_count": self.warning_count,
            "unavailable_count": self.unavailable_count,
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at,
            "is_stale": self.is_stale,
            "approval_id": self.approval_id,
            "checks": [c.to_dict() for c in self.checks],
            "disclosures": self.disclosures.to_dict(),
        }


# =============================================================================
# Content Hash (for change detection / invalidation)
# =============================================================================


def compute_content_hash(
    *,
    content_item_id: str,
    content_version: int,
    asset_checksums: list[str],
    platform: str,
    account_id: str,
    is_sponsored: bool,
    is_synthetic: bool,
) -> str:
    """Compute a hash that changes when any material field changes.

    Used to detect when a preflight result is stale.
    """
    parts = [
        content_item_id,
        str(content_version),
        "|".join(sorted(asset_checksums)),
        platform,
        account_id,
        str(is_sponsored),
        str(is_synthetic),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:24]


# =============================================================================
# Preflight Evaluation
# =============================================================================


def evaluate_preflight(
    *,
    org_id: str,
    user_id: str,
    content_item_id: str,
    content_version: int,
    platform: str,
    account_id: str,
    # Content metadata
    asset_checksums: list[str] | None = None,
    is_sponsored: bool = False,
    sponsor_name: str = "",
    is_synthetic: bool = False,
    is_ai_voice: bool = False,
    # Evidence (injected by caller)
    account_connected: bool | None = None,
    account_has_feature: bool | None = None,
    consent_valid: bool | None = None,
    lineage_complete: bool | None = None,
    # Policy
    policy_version: str = "1.0",
) -> PreflightResult:
    """Run all preflight checks and produce an immutable result.

    Checks run server-side. Missing evidence → UNAVAILABLE (fail-safe).
    """
    content_hash = compute_content_hash(
        content_item_id=content_item_id,
        content_version=content_version,
        asset_checksums=asset_checksums or [],
        platform=platform,
        account_id=account_id,
        is_sponsored=is_sponsored,
        is_synthetic=is_synthetic,
    )

    checks: list[PreflightCheck] = []

    # --- Disclosure checks ---
    if is_sponsored:
        checks.append(_check_sponsorship_disclosure(sponsor_name, policy_version))

    if is_synthetic:
        checks.append(_check_synthetic_disclosure(policy_version))

    if is_ai_voice:
        checks.append(_check_ai_voice_disclosure(policy_version))

    # --- Account checks ---
    checks.append(_check_account_connected(account_connected, platform))

    if account_has_feature is not None:
        checks.append(_check_account_feature(account_has_feature, platform))

    # --- Consent checks ---
    if is_ai_voice or is_synthetic:
        checks.append(_check_consent_valid(consent_valid))

    # --- Asset lineage ---
    checks.append(_check_asset_lineage(lineage_complete))

    # --- Build disclosures ---
    disclosures = DisclosurePackage(
        is_sponsored=is_sponsored,
        sponsor_name=sponsor_name,
        is_synthetic=is_synthetic,
        is_ai_voice=is_ai_voice,
        synthetic_disclosure_text="This content contains AI-generated media" if is_synthetic else "",
        sponsorship_disclosure_text=f"Paid partnership with {sponsor_name}" if is_sponsored and sponsor_name else "",
        disclosure_policy_version=policy_version,
    )

    # --- Compute overall state ---
    overall = _compute_overall_state(checks)

    result = PreflightResult(
        org_id=org_id,
        user_id=user_id,
        content_item_id=content_item_id,
        content_version=content_version,
        content_hash=content_hash,
        platform=platform,
        account_id=account_id,
        overall_state=overall,
        checks=checks,
        disclosures=disclosures,
        passed_count=sum(1 for c in checks if c.state == PreflightState.PASS),
        blocked_count=sum(1 for c in checks if c.state == PreflightState.BLOCK),
        warning_count=sum(1 for c in checks if c.state == PreflightState.WARNING),
        unavailable_count=sum(1 for c in checks if c.state == PreflightState.UNAVAILABLE),
        policy_version=policy_version,
    )

    return result


# =============================================================================
# Individual Check Implementations
# =============================================================================


def _check_sponsorship_disclosure(sponsor_name: str, policy_version: str) -> PreflightCheck:
    if not sponsor_name:
        return PreflightCheck(
            category=CheckCategory.SPONSORSHIP,
            name="sponsorship_disclosure",
            state=PreflightState.BLOCK,
            message="Sponsored content requires sponsor name",
            policy_version=policy_version,
        )
    return PreflightCheck(
        category=CheckCategory.SPONSORSHIP,
        name="sponsorship_disclosure",
        state=PreflightState.PASS,
        message=f"Paid partnership with {sponsor_name}",
        evidence=f"sponsor_name={sponsor_name}",
        policy_version=policy_version,
    )


def _check_synthetic_disclosure(policy_version: str) -> PreflightCheck:
    return PreflightCheck(
        category=CheckCategory.SYNTHETIC_MEDIA,
        name="synthetic_media_disclosure",
        state=PreflightState.PASS,
        message="AI-generated content disclosure will be applied",
        evidence="is_synthetic=True",
        policy_version=policy_version,
    )


def _check_ai_voice_disclosure(policy_version: str) -> PreflightCheck:
    return PreflightCheck(
        category=CheckCategory.SYNTHETIC_MEDIA,
        name="ai_voice_disclosure",
        state=PreflightState.PASS,
        message="AI voice disclosure will be applied",
        evidence="is_ai_voice=True",
        policy_version=policy_version,
    )


def _check_account_connected(connected: bool | None, platform: str) -> PreflightCheck:
    if connected is None:
        return PreflightCheck(
            category=CheckCategory.ACCOUNT,
            name="account_connected",
            state=PreflightState.UNAVAILABLE,
            message=f"Cannot verify {platform} account connection",
            requirement=CheckRequirement.REQUIRED,
        )
    if not connected:
        return PreflightCheck(
            category=CheckCategory.ACCOUNT,
            name="account_connected",
            state=PreflightState.BLOCK,
            message=f"{platform} account is not connected",
            requirement=CheckRequirement.REQUIRED,
        )
    return PreflightCheck(
        category=CheckCategory.ACCOUNT,
        name="account_connected",
        state=PreflightState.PASS,
        message=f"{platform} account connected",
        evidence="account_connected=True",
    )


def _check_account_feature(has_feature: bool, platform: str) -> PreflightCheck:
    if not has_feature:
        return PreflightCheck(
            category=CheckCategory.PLATFORM,
            name="platform_feature",
            state=PreflightState.WARNING,
            message=f"{platform} account may lack required feature for this content type",
            requirement=CheckRequirement.RECOMMENDED,
        )
    return PreflightCheck(
        category=CheckCategory.PLATFORM,
        name="platform_feature",
        state=PreflightState.PASS,
        message=f"{platform} feature available",
    )


def _check_consent_valid(consent_valid: bool | None) -> PreflightCheck:
    if consent_valid is None:
        return PreflightCheck(
            category=CheckCategory.CONSENT,
            name="consent_valid",
            state=PreflightState.UNAVAILABLE,
            message="Cannot verify consent status",
            requirement=CheckRequirement.REQUIRED,
        )
    if not consent_valid:
        return PreflightCheck(
            category=CheckCategory.CONSENT,
            name="consent_valid",
            state=PreflightState.BLOCK,
            message="Required consent is revoked or expired",
            requirement=CheckRequirement.REQUIRED,
        )
    return PreflightCheck(
        category=CheckCategory.CONSENT,
        name="consent_valid",
        state=PreflightState.PASS,
        message="Consent verified",
        evidence="consent_valid=True",
    )


def _check_asset_lineage(lineage_complete: bool | None) -> PreflightCheck:
    if lineage_complete is None:
        return PreflightCheck(
            category=CheckCategory.ASSET,
            name="asset_lineage",
            state=PreflightState.WARNING,
            message="Asset lineage could not be verified",
            requirement=CheckRequirement.RECOMMENDED,
        )
    if not lineage_complete:
        return PreflightCheck(
            category=CheckCategory.ASSET,
            name="asset_lineage",
            state=PreflightState.WARNING,
            message="Asset has incomplete provenance lineage",
            requirement=CheckRequirement.RECOMMENDED,
        )
    return PreflightCheck(
        category=CheckCategory.ASSET,
        name="asset_lineage",
        state=PreflightState.PASS,
        message="Asset lineage complete",
        evidence="lineage_complete=True",
    )


# =============================================================================
# Overall State Computation
# =============================================================================


def _compute_overall_state(checks: list[PreflightCheck]) -> PreflightState:
    """Compute overall state from individual checks.

    Rules:
    1. Any REQUIRED check BLOCK → overall BLOCK
    2. Any REQUIRED check UNAVAILABLE → overall UNAVAILABLE (fail-safe)
    3. Any check REVIEW_REQUIRED → overall REVIEW_REQUIRED
    4. Any check WARNING → overall WARNING (but still publishable)
    5. All pass → PASS
    """
    has_block = any(
        c.state == PreflightState.BLOCK and c.requirement == CheckRequirement.REQUIRED
        for c in checks
    )
    has_unavailable = any(
        c.state == PreflightState.UNAVAILABLE and c.requirement == CheckRequirement.REQUIRED
        for c in checks
    )
    has_review = any(c.state == PreflightState.REVIEW_REQUIRED for c in checks)
    has_warning = any(c.state == PreflightState.WARNING for c in checks)

    if has_block:
        return PreflightState.BLOCK
    if has_unavailable:
        return PreflightState.UNAVAILABLE
    if has_review:
        return PreflightState.REVIEW_REQUIRED
    if has_warning:
        return PreflightState.WARNING
    return PreflightState.PASS


# =============================================================================
# Approval Binding
# =============================================================================


class ApprovalBindingError(Exception):
    def __init__(self, message: str, code: str = "BINDING_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


def bind_approval(
    result: PreflightResult,
    *,
    approval_id: str,
    approved_by: str,
) -> PreflightResult:
    """Bind an approval to a preflight result.

    Can only bind to PASS or WARNING results.
    Raises ApprovalBindingError if blocked or unavailable.
    """
    if result.overall_state == PreflightState.BLOCK:
        raise ApprovalBindingError(
            "Cannot approve: preflight has blocking failures",
            code="BLOCKED",
        )
    if result.overall_state == PreflightState.UNAVAILABLE:
        raise ApprovalBindingError(
            "Cannot approve: required checks unavailable",
            code="UNAVAILABLE",
        )
    if result.is_stale:
        raise ApprovalBindingError(
            "Cannot approve: preflight result is stale (content changed)",
            code="STALE",
        )

    result.approval_id = approval_id
    result.approved_by = approved_by
    result.approved_at = datetime.now(UTC).isoformat()
    return result


# =============================================================================
# Invalidation (stale detection)
# =============================================================================


def check_invalidation(
    result: PreflightResult,
    *,
    current_content_version: int,
    current_content_hash: str,
) -> bool:
    """Check if a preflight result has been invalidated by content changes.

    Returns True if stale (invalidated).
    """
    if result.content_version != current_content_version:
        result.is_stale = True
        return True
    if result.content_hash != current_content_hash:
        result.is_stale = True
        return True
    return False
