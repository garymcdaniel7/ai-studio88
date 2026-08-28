"""Production LoRA Catalog — Story 098.

Returns only approved, compatible, deployable LoRA versions for production
use. Excludes simulated, rejected, unapproved, inactive, retired,
missing-artifact, and incompatible versions.

Eligibility matrix (ALL must be true):
    1. Status is ACTIVE or DEPLOYABLE (approved lifecycle gate passed)
    2. Artifact exists (storage_key non-empty, artifact_hash present)
    3. Not simulated (evidence_type == REAL in evaluation)
    4. Compatible with target base model
    5. Tenant-scoped (org_id matches requester)
    6. Not retired (no retirement flag)

Cache:
    - Per-org + base-model catalog cached
    - Invalidated on: promotion, rollback, retirement, deployment change
    - TTL-based fallback (60 seconds)

Response includes:
    - Exact immutable version_id
    - Compatibility requirements (base_model, min_vram_gb)
    - Talent assignment
    - Trigger words
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Catalog Entry
# =============================================================================


@dataclass
class CatalogEntry:
    """A production-eligible LoRA version in the catalog."""
    version_id: str
    org_id: str
    talent_id: str
    model_name: str
    version_number: int
    status: str              # "active" or "deployable"

    # Artifact
    storage_key: str
    artifact_hash: str
    file_size_bytes: int = 0

    # Compatibility
    compatible_base_models: list[str] = field(default_factory=list)
    min_vram_gb: int = 8
    trigger_words: list[str] = field(default_factory=list)
    recommended_strength: float = 0.8

    # Metadata
    activated_at: float | None = None
    evaluation_score: float | None = None


# =============================================================================
# LoRA Record (internal representation for catalog filtering)
# =============================================================================


@dataclass
class LoRARecord:
    """Internal LoRA record for catalog eligibility evaluation."""
    version_id: str = ""
    org_id: str = ""
    talent_id: str = ""
    model_name: str = ""
    version_number: int = 1
    status: str = ""             # active, deployable, rejected, etc.
    artifact_hash: str = ""
    storage_key: str = ""
    file_size_bytes: int = 0
    evidence_type: str = "real"  # real or simulation
    compatible_base_models: list[str] = field(default_factory=list)
    min_vram_gb: int = 8
    trigger_words: list[str] = field(default_factory=list)
    recommended_strength: float = 0.8
    retired: bool = False
    activated_at: float | None = None
    evaluation_score: float | None = None


# =============================================================================
# Store
# =============================================================================

_lora_records: list[LoRARecord] = []
_cache: dict[str, tuple[float, list[CatalogEntry]]] = {}  # cache_key → (timestamp, entries)
_cache_ttl_seconds: float = 60.0


# =============================================================================
# Eligibility Check
# =============================================================================


def is_eligible(record: LoRARecord, base_model: str | None = None) -> bool:
    """Check if a LoRA record passes all eligibility gates."""
    # Gate 1: Status must be active or deployable
    if record.status not in ("active", "deployable"):
        return False

    # Gate 2: Artifact must exist
    if not record.storage_key or not record.artifact_hash:
        return False

    # Gate 3: Not simulated
    if record.evidence_type == "simulation":
        return False

    # Gate 4: Compatible with base model (if specified)
    if base_model and record.compatible_base_models:
        if base_model not in record.compatible_base_models:
            return False

    # Gate 5: Not retired
    if record.retired:
        return False

    return True


# =============================================================================
# Catalog API
# =============================================================================


def get_production_catalog(
    org_id: str,
    base_model: str | None = None,
    talent_id: str | None = None,
    force_refresh: bool = False,
) -> list[CatalogEntry]:
    """Get the production LoRA catalog for a workspace.

    Returns only eligible versions. Cached per org+base_model.
    """
    if not org_id:
        raise ValueError("org_id is required")

    cache_key = f"{org_id}:{base_model or 'all'}:{talent_id or 'all'}"

    # Check cache
    if not force_refresh and cache_key in _cache:
        cached_at, entries = _cache[cache_key]
        if time.time() - cached_at < _cache_ttl_seconds:
            return entries

    # Build catalog from records
    entries = []
    for record in _lora_records:
        # Tenant isolation
        if record.org_id != org_id:
            continue

        # Talent filter
        if talent_id and record.talent_id != talent_id:
            continue

        # Eligibility check
        if not is_eligible(record, base_model):
            continue

        entry = CatalogEntry(
            version_id=record.version_id,
            org_id=record.org_id,
            talent_id=record.talent_id,
            model_name=record.model_name,
            version_number=record.version_number,
            status=record.status,
            storage_key=record.storage_key,
            artifact_hash=record.artifact_hash,
            file_size_bytes=record.file_size_bytes,
            compatible_base_models=record.compatible_base_models,
            min_vram_gb=record.min_vram_gb,
            trigger_words=record.trigger_words,
            recommended_strength=record.recommended_strength,
            activated_at=record.activated_at,
            evaluation_score=record.evaluation_score,
        )
        entries.append(entry)

    # Cache result
    _cache[cache_key] = (time.time(), entries)

    logger.info(f"CATALOG_QUERY: org={org_id} base_model={base_model} results={len(entries)}")
    return entries


def get_catalog_for_generation(
    org_id: str,
    base_model: str,
    talent_id: str | None = None,
) -> list[CatalogEntry]:
    """Get catalog filtered for a specific generation context.

    Used by Create and other production surfaces to populate model selection.
    Only returns versions compatible with the target base model.
    """
    return get_production_catalog(org_id, base_model=base_model, talent_id=talent_id)


# =============================================================================
# Cache Invalidation
# =============================================================================


def invalidate_catalog(org_id: str) -> None:
    """Invalidate catalog cache for an org.

    Called after: promotion, rollback, retirement, deployment-state change.
    """
    keys_to_remove = [k for k in _cache if k.startswith(f"{org_id}:")]
    for key in keys_to_remove:
        del _cache[key]
    logger.info(f"CATALOG_INVALIDATED: org={org_id} keys={len(keys_to_remove)}")


def invalidate_all() -> None:
    """Invalidate entire cache (e.g. after system-wide model update)."""
    _cache.clear()


# =============================================================================
# Record Management (for catalog source data)
# =============================================================================


def register_lora_record(record: LoRARecord) -> None:
    """Register or update a LoRA record in the catalog source."""
    # Replace existing if same version_id
    _lora_records[:] = [r for r in _lora_records if r.version_id != record.version_id]
    _lora_records.append(record)
    # Invalidate cache for this org
    invalidate_catalog(record.org_id)


def retire_lora(version_id: str, org_id: str) -> bool:
    """Mark a LoRA as retired (excluded from catalog)."""
    for record in _lora_records:
        if record.version_id == version_id and record.org_id == org_id:
            record.retired = True
            invalidate_catalog(org_id)
            return True
    return False


def unretire_lora(version_id: str, org_id: str) -> bool:
    """Unretire a LoRA (re-include in catalog if still eligible)."""
    for record in _lora_records:
        if record.version_id == version_id and record.org_id == org_id:
            record.retired = False
            invalidate_catalog(org_id)
            return True
    return False


# =============================================================================
# Diagnostic
# =============================================================================


def explain_exclusion(version_id: str, org_id: str, base_model: str | None = None) -> dict[str, Any]:
    """Explain why a LoRA version is excluded from the catalog.

    Useful for debugging "why can't I see my model?" questions.
    """
    record = None
    for r in _lora_records:
        if r.version_id == version_id and r.org_id == org_id:
            record = r
            break

    if not record:
        return {"found": False, "reason": "Version not found in this workspace"}

    reasons = []
    if record.status not in ("active", "deployable"):
        reasons.append(f"Status is '{record.status}' (must be active or deployable)")
    if not record.storage_key or not record.artifact_hash:
        reasons.append("Artifact missing (no storage_key or artifact_hash)")
    if record.evidence_type == "simulation":
        reasons.append("Evaluated with simulation evidence only (real evaluation required)")
    if base_model and record.compatible_base_models and base_model not in record.compatible_base_models:
        reasons.append(f"Incompatible with base model '{base_model}' (compatible: {record.compatible_base_models})")
    if record.retired:
        reasons.append("Model is retired")

    return {
        "found": True,
        "version_id": version_id,
        "eligible": len(reasons) == 0,
        "exclusion_reasons": reasons,
        "current_status": record.status,
    }


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _lora_records.clear()
    _cache.clear()
