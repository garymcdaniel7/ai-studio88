"""Immutable Context Package — Story 083.

Every enriched generation request produces a persisted, hashed, inspectable
package that jobs and assets reference for reproducibility and audit.

The package is:
- Immutable after creation (corrections via amendment only)
- Canonically hashed (stable equivalent input → same hash)
- Workspace-scoped (authorized retrieval, no secret leakage)
- Persisted BEFORE generation begins

Contents:
- Source record IDs + versions (provenance)
- Effective positive and negative prompts
- Applied and rejected rules
- Conflicts and warnings
- Model/LoRA requirements
- Talent + project + consent references
- Merge-policy version
- Stable canonical content hash
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


# =============================================================================
# Context Package
# =============================================================================


@dataclass
class ContextPackage:
    """Immutable, versioned context package for one generation.

    Created from resolved context (Story 082). Persisted before execution.
    Referenced by job_id and asset provenance for full reproducibility.
    """

    # Identity
    package_id: str = field(default_factory=lambda: f"ctx-{uuid.uuid4().hex[:16]}")
    canonical_hash: str = ""        # Computed after all fields set
    org_id: str = ""
    user_id: str = ""

    # Provenance (source IDs and versions)
    talent_id: str = ""
    talent_version: int = 0
    preferences_id: str | None = None
    preferences_version: int | None = None
    lora_id: str | None = None
    lora_version: str | None = None
    lora_strength: float | None = None
    workflow_id: str | None = None
    workflow_version: str | None = None
    project_id: str | None = None
    campaign_id: str | None = None

    # Source records loaded
    source_records: list[dict] = field(default_factory=list)
    # Each entry: {"source": "...", "record_id": "...", "version": N}

    # Effective prompts (final output of merge/enrichment)
    effective_positive_prompt: str = ""
    effective_negative_prompt: str = ""

    # Model requirements
    model_id: str = ""
    model_version: str = ""
    required_vram_gb: float | None = None

    # Applied rules
    applied_rules: list[dict] = field(default_factory=list)
    # Each: {"rule_id": "...", "version": N, "type": "include/avoid", "text": "..."}

    # Rejected rules (with reasons)
    rejected_rules: list[dict] = field(default_factory=list)
    # Each: {"rule_id": "...", "reason": "..."}

    # Conflicts detected during merge
    conflicts: list[dict] = field(default_factory=list)
    # Each: {"type": "...", "sources": [...], "resolution": "...", "warning": "..."}

    # Warnings (non-blocking issues)
    warnings: list[str] = field(default_factory=list)

    # Consent references (for talent-linked generations)
    consent_ids: list[str] = field(default_factory=list)

    # Merge policy
    merge_policy_version: str = "1.0"

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_immutable: bool = True       # Once persisted, cannot be modified

    # References (populated after use)
    job_ids: list[str] = field(default_factory=list)
    asset_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serializable representation (safe for authorized users)."""
        return {
            "package_id": self.package_id,
            "canonical_hash": self.canonical_hash,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "talent_id": self.talent_id,
            "talent_version": self.talent_version,
            "preferences_version": self.preferences_version,
            "lora_id": self.lora_id,
            "lora_version": self.lora_version,
            "model_id": self.model_id,
            "effective_positive_prompt": self.effective_positive_prompt,
            "effective_negative_prompt": self.effective_negative_prompt,
            "applied_rules_count": len(self.applied_rules),
            "rejected_rules_count": len(self.rejected_rules),
            "conflicts_count": len(self.conflicts),
            "warnings": self.warnings,
            "consent_ids": self.consent_ids,
            "merge_policy_version": self.merge_policy_version,
            "source_records_count": len(self.source_records),
            "created_at": self.created_at,
            "job_ids": self.job_ids,
            "asset_ids": self.asset_ids,
        }

    def to_inspectable(self) -> dict:
        """Full inspectable representation for authorized users.

        Excludes: provider secrets, internal system prompts.
        """
        return {
            "package_id": self.package_id,
            "canonical_hash": self.canonical_hash,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "talent_version": self.talent_version,
            "effective_positive_prompt": self.effective_positive_prompt,
            "effective_negative_prompt": self.effective_negative_prompt,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "lora_id": self.lora_id,
            "lora_version": self.lora_version,
            "lora_strength": self.lora_strength,
            "applied_rules": self.applied_rules,
            "rejected_rules": self.rejected_rules,
            "conflicts": self.conflicts,
            "warnings": self.warnings,
            "source_records": self.source_records,
            "consent_ids": self.consent_ids,
            "merge_policy_version": self.merge_policy_version,
            "project_id": self.project_id,
            "campaign_id": self.campaign_id,
            "created_at": self.created_at,
        }


# =============================================================================
# Canonical Hash
# =============================================================================


def compute_canonical_hash(pkg: ContextPackage) -> str:
    """Compute a stable canonical hash for the context package.

    The hash is deterministic: equivalent effective input always produces
    the same hash regardless of field ordering or optional metadata.

    Hash inputs (canonicalized):
    - effective_positive_prompt
    - effective_negative_prompt
    - model_id + model_version
    - lora_id + lora_version + lora_strength
    - talent_id + talent_version
    - applied_rules (sorted by rule_id)
    - merge_policy_version
    """
    # Build canonical string from deterministic fields
    rules_canonical = sorted(
        [r.get("rule_id", "") + ":" + r.get("text", "") for r in pkg.applied_rules]
    )

    canonical_parts = [
        pkg.effective_positive_prompt,
        pkg.effective_negative_prompt,
        pkg.model_id,
        pkg.model_version,
        pkg.lora_id or "",
        pkg.lora_version or "",
        str(pkg.lora_strength or 0),
        pkg.talent_id,
        str(pkg.talent_version),
        "|".join(rules_canonical),
        pkg.merge_policy_version,
    ]

    canonical_str = "\n".join(canonical_parts)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:32]


def finalize_package(pkg: ContextPackage) -> ContextPackage:
    """Compute hash and mark package as ready for persistence.

    Must be called before persist. After this, package is immutable.
    """
    pkg.canonical_hash = compute_canonical_hash(pkg)
    pkg.is_immutable = True
    return pkg


# =============================================================================
# Package Store (in-memory for contract; production uses Supabase)
# =============================================================================

_package_store: dict[str, ContextPackage] = {}


def clear_store() -> None:
    """Clear store (testing only)."""
    _package_store.clear()


class PackageImmutableError(Exception):
    """Raised when attempting to modify an immutable package."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PackageNotFoundError(Exception):
    """Raised when package cannot be found."""
    pass


class PackageUnauthorizedError(Exception):
    """Raised when access is denied."""
    pass


def persist_package(pkg: ContextPackage) -> ContextPackage:
    """Persist a context package.

    Idempotent: re-persisting the same package_id returns existing.
    Package must have canonical_hash computed before persisting.

    Raises ValueError if hash not computed.
    """
    if not pkg.canonical_hash:
        raise ValueError("Package must be finalized (hash computed) before persisting")

    existing = _package_store.get(pkg.package_id)
    if existing is not None:
        return existing  # Idempotent

    _package_store[pkg.package_id] = pkg
    return pkg


def retrieve_package(
    package_id: str,
    *,
    requesting_org_id: str,
) -> ContextPackage:
    """Retrieve a persisted package with authorization check.

    Raises PackageNotFoundError or PackageUnauthorizedError.
    """
    pkg = _package_store.get(package_id)
    if pkg is None:
        raise PackageNotFoundError(f"Package {package_id} not found")

    if pkg.org_id != requesting_org_id:
        raise PackageUnauthorizedError(
            f"Package {package_id} belongs to different workspace"
        )

    return pkg


def retrieve_by_hash(
    canonical_hash: str,
    *,
    requesting_org_id: str,
) -> ContextPackage | None:
    """Find a package by its canonical hash (for deduplication).

    Returns None if not found or unauthorized.
    """
    for pkg in _package_store.values():
        if pkg.canonical_hash == canonical_hash and pkg.org_id == requesting_org_id:
            return pkg
    return None


# =============================================================================
# Immutability Enforcement
# =============================================================================


def modify_package(
    package_id: str,
    updates: dict[str, Any],
) -> None:
    """Attempt to modify a persisted package.

    Always raises PackageImmutableError — packages cannot be modified.
    Use amendments (Story 073 pattern) for corrections.
    """
    pkg = _package_store.get(package_id)
    if pkg is None:
        raise PackageNotFoundError(f"Package {package_id} not found")

    raise PackageImmutableError(
        f"Package {package_id} is immutable. Use amendment process for corrections."
    )


# =============================================================================
# Reference Linking
# =============================================================================


def link_job(package_id: str, job_id: str) -> None:
    """Link a generation job to this context package."""
    pkg = _package_store.get(package_id)
    if pkg and job_id not in pkg.job_ids:
        pkg.job_ids.append(job_id)


def link_asset(package_id: str, asset_id: str) -> None:
    """Link an output asset to this context package."""
    pkg = _package_store.get(package_id)
    if pkg and asset_id not in pkg.asset_ids:
        pkg.asset_ids.append(asset_id)
