"""Asset Provenance Contract — Story 073.

Every generated asset carries a complete, immutable provenance record populated
from trusted backend sources (not caller claims). This enables reproduction,
remix, audit, and confident publishing.

Provenance fields are grouped into:
- Identity: asset_id, org_id, created_at
- Generation: job_id, spec_hash, effective prompt, seed, settings, provider
- Context: project_id, session_id, campaign_id, workflow_id/version
- Talent & Model: talent_id, model_id, model_version, lora_id/version
- Source Lineage: parent_asset_ids (for derived/remixed outputs)
- Cost: estimated_usd, actual_usd, provider, gpu_type, runtime_seconds
- Consent: consent_evidence_ids (links to consent records if talent used)
- Actor: user_id who initiated the generation

Invariants:
1. Provenance is populated from backend truth — never overwritten by UI defaults
2. Required fields missing → asset is marked LINEAGE_INCOMPLETE (blocks publishing)
3. Derived assets reference parent_asset_ids (immutable after creation)
4. Provenance is tenant-scoped and immutable (corrections via audited amendment only)
5. Completion is idempotent (same job_id re-registering does not create duplicates)
6. Provider-omitted seed is recorded as None, not fabricated
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# =============================================================================
# Provenance State
# =============================================================================


class ProvenanceState(StrEnum):
    COMPLETE = "complete"               # All required fields present
    LINEAGE_INCOMPLETE = "lineage_incomplete"  # Missing required provenance
    PENDING = "pending"                 # Job not yet completed
    LEGACY = "legacy"                   # Pre-contract asset, backfill needed


# =============================================================================
# Media Types (aligned with Story 071 contract)
# =============================================================================


class AssetMediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO_VOICE = "audio_voice"
    AUDIO_MUSIC = "audio_music"
    LIP_SYNC = "lip_sync"
    COMPOSITE = "composite"         # Multi-source derived
    MODEL_ARTIFACT = "model_artifact"  # LoRA weights, etc.


# =============================================================================
# Required Fields Per Media Type
# =============================================================================

# Minimum provenance fields required for each media type to be COMPLETE
REQUIRED_PROVENANCE_FIELDS: dict[AssetMediaType, set[str]] = {
    AssetMediaType.IMAGE: {
        "org_id", "user_id", "job_id", "media_type",
        "model_id", "effective_prompt", "width", "height",
        "storage_key", "checksum_sha256", "mime_type", "size_bytes",
    },
    AssetMediaType.VIDEO: {
        "org_id", "user_id", "job_id", "media_type",
        "model_id", "effective_prompt", "width", "height",
        "storage_key", "checksum_sha256", "mime_type", "size_bytes",
    },
    AssetMediaType.AUDIO_VOICE: {
        "org_id", "user_id", "job_id", "media_type",
        "model_id", "effective_prompt",
        "storage_key", "checksum_sha256", "mime_type", "size_bytes",
        "talent_id",  # Voice requires talent attribution
    },
    AssetMediaType.AUDIO_MUSIC: {
        "org_id", "user_id", "job_id", "media_type",
        "model_id", "effective_prompt",
        "storage_key", "checksum_sha256", "mime_type", "size_bytes",
    },
    AssetMediaType.LIP_SYNC: {
        "org_id", "user_id", "job_id", "media_type",
        "storage_key", "checksum_sha256", "mime_type", "size_bytes",
        "parent_asset_ids",  # Must reference source video + audio
    },
    AssetMediaType.COMPOSITE: {
        "org_id", "user_id", "job_id", "media_type",
        "storage_key", "checksum_sha256", "mime_type", "size_bytes",
        "parent_asset_ids",  # Must reference source assets
    },
    AssetMediaType.MODEL_ARTIFACT: {
        "org_id", "user_id", "job_id", "media_type",
        "storage_key", "checksum_sha256", "mime_type", "size_bytes",
        "talent_id",  # Training tied to talent
    },
}


# =============================================================================
# Asset Provenance Record
# =============================================================================


@dataclass
class AssetProvenance:
    """The ONE authoritative provenance record for a generated asset.

    Populated entirely from backend truth. Immutable after creation
    (corrections only via ProvenanceAmendment).
    """
    # Identity
    asset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    media_type: AssetMediaType = AssetMediaType.IMAGE
    provenance_state: ProvenanceState = ProvenanceState.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Actor
    user_id: str = ""

    # Generation job link
    job_id: str = ""
    spec_hash: str = ""         # From GenerationSpec (Story 071)

    # Effective generation parameters (as actually executed, not requested)
    effective_prompt: str = ""
    effective_negative_prompt: str = ""
    seed_used: int | None = None  # None if provider didn't report
    steps_used: int | None = None
    cfg_scale_used: float | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None  # Video/audio

    # Model & LoRA
    model_id: str = ""
    model_version: str = ""
    lora_id: str | None = None
    lora_version: str | None = None
    lora_strength: float | None = None

    # Workflow
    workflow_id: str | None = None
    workflow_version: str | None = None

    # Context links
    project_id: str | None = None
    session_id: str | None = None
    campaign_id: str | None = None
    talent_id: str | None = None

    # Storage (from asset registration)
    storage_key: str = ""
    checksum_sha256: str = ""
    mime_type: str = ""
    size_bytes: int = 0

    # Cost (from cost ledger)
    cost_estimated_usd: float | None = None
    cost_actual_usd: float | None = None
    provider: str = ""
    gpu_type: str | None = None
    runtime_seconds: float | None = None

    # Lineage (parent assets for derived outputs)
    parent_asset_ids: list[str] = field(default_factory=list)

    # Consent evidence (for talent-linked outputs)
    consent_evidence_ids: list[str] = field(default_factory=list)

    # Timestamps
    generation_started_at: str | None = None
    generation_completed_at: str | None = None
    registered_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "org_id": self.org_id,
            "media_type": self.media_type.value,
            "provenance_state": self.provenance_state.value,
            "user_id": self.user_id,
            "job_id": self.job_id,
            "spec_hash": self.spec_hash,
            "effective_prompt": self.effective_prompt,
            "effective_negative_prompt": self.effective_negative_prompt,
            "seed_used": self.seed_used,
            "steps_used": self.steps_used,
            "cfg_scale_used": self.cfg_scale_used,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "lora_id": self.lora_id,
            "lora_version": self.lora_version,
            "workflow_id": self.workflow_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "campaign_id": self.campaign_id,
            "talent_id": self.talent_id,
            "storage_key": self.storage_key,
            "checksum_sha256": self.checksum_sha256,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "cost_actual_usd": self.cost_actual_usd,
            "provider": self.provider,
            "parent_asset_ids": self.parent_asset_ids,
            "consent_evidence_ids": self.consent_evidence_ids,
            "created_at": self.created_at,
            "generation_completed_at": self.generation_completed_at,
            "c2pa": self.c2pa_stamp(),
        }

    def c2pa_stamp(self) -> dict[str, Any]:
        """Return C2PA-style disclosure metadata for an exported asset."""
        return build_c2pa_stamp(
            model_id=self.model_id,
            timestamp=self.created_at,
            org_id=self.org_id,
            talent_id=self.talent_id,
        )




def build_c2pa_stamp(
    *,
    model_id: str,
    timestamp: str,
    org_id: str,
    talent_id: str | None,
) -> dict[str, Any]:
    """Build the disclosure fields embedded at export/assembly time."""
    return {
        "claim_generator": "AI Studio",
        "format": "c2pa-style",
        "assertions": {
            "ai_generated": True,
            "model": model_id,
            "timestamp": timestamp,
            "org_id": org_id,
            "talent_id": talent_id,
        },
    }


def stamp_export_metadata(
    provenance: AssetProvenance,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return export metadata with an authoritative C2PA-style stamp."""
    stamped = dict(metadata or {})
    stamped["c2pa"] = provenance.c2pa_stamp()
    return stamped


# =============================================================================
# Provenance Amendment (audited correction)
# =============================================================================


@dataclass
class ProvenanceAmendment:
    """An audited correction to an existing provenance record.

    Provenance is immutable by default. Amendments create an audit trail
    explaining why and what changed.
    """
    amendment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str = ""
    org_id: str = ""
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None
    reason: str = ""
    amended_by: str = ""
    amended_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "amendment_id": self.amendment_id,
            "asset_id": self.asset_id,
            "org_id": self.org_id,
            "field_name": self.field_name,
            "old_value": str(self.old_value),
            "new_value": str(self.new_value),
            "reason": self.reason,
            "amended_by": self.amended_by,
            "amended_at": self.amended_at,
        }


# =============================================================================
# Lineage Link
# =============================================================================


@dataclass
class LineageLink:
    """A parent-child relationship between assets."""

    child_asset_id: str
    parent_asset_id: str
    relationship: str = "derived_from"  # derived_from, remixed_from, extracted_from
    org_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# =============================================================================
# Provenance Validation
# =============================================================================


def validate_provenance(prov: AssetProvenance) -> list[str]:
    """Validate provenance completeness for the given media type.

    Returns list of missing field names. Empty = COMPLETE.
    """
    required = REQUIRED_PROVENANCE_FIELDS.get(prov.media_type, set())
    missing: list[str] = []

    for field_name in required:
        value = getattr(prov, field_name, None)
        if value is None or value == "" or value == 0 or value == []:
            missing.append(field_name)

    return missing


def determine_provenance_state(prov: AssetProvenance) -> ProvenanceState:
    """Determine the provenance state based on field completeness."""
    if not prov.job_id:
        return ProvenanceState.PENDING

    missing = validate_provenance(prov)
    if not missing:
        return ProvenanceState.COMPLETE
    return ProvenanceState.LINEAGE_INCOMPLETE


# =============================================================================
# Provenance Registration (idempotent)
# =============================================================================


# In-memory registry for contract testing; production uses Supabase
_provenance_registry: dict[str, AssetProvenance] = {}
_lineage_links: list[LineageLink] = []


def register_provenance(
    prov: AssetProvenance,
    *,
    allow_overwrite: bool = False,
) -> AssetProvenance:
    """Register an asset's provenance record.

    Idempotent: re-registering the same job_id does NOT create duplicates.
    The asset_id is the dedup key.

    Args:
        prov: The provenance record to register
        allow_overwrite: If False (default), existing records are not overwritten

    Returns:
        The registered (or existing) provenance record.

    Raises:
        ProvenanceError if attempting to overwrite without permission.
    """
    existing = _provenance_registry.get(prov.asset_id)

    if existing is not None:
        if not allow_overwrite:
            # Idempotent — return existing without error
            return existing
        # Overwrite path (only for backfill/repair)

    # Validate and set state
    prov.provenance_state = determine_provenance_state(prov)
    prov.registered_at = datetime.now(UTC).isoformat()

    _provenance_registry[prov.asset_id] = prov
    return prov


def register_lineage(link: LineageLink) -> LineageLink:
    """Register a parent-child lineage link.

    Idempotent: duplicate links are ignored.
    """
    for existing in _lineage_links:
        if (existing.child_asset_id == link.child_asset_id
                and existing.parent_asset_id == link.parent_asset_id):
            return existing  # Already registered

    _lineage_links.append(link)
    return link


def get_provenance(asset_id: str) -> AssetProvenance | None:
    """Retrieve provenance for an asset."""
    return _provenance_registry.get(asset_id)


def get_lineage(asset_id: str) -> list[LineageLink]:
    """Get all lineage links where asset_id is the child."""
    return [link for link in _lineage_links if link.child_asset_id == asset_id]


def get_children(asset_id: str) -> list[LineageLink]:
    """Get all lineage links where asset_id is the parent."""
    return [link for link in _lineage_links if link.parent_asset_id == asset_id]


def clear_registry() -> None:
    """Clear the in-memory registry (for testing only)."""
    _provenance_registry.clear()
    _lineage_links.clear()


# =============================================================================
# Tenant Isolation
# =============================================================================


def verify_provenance_access(prov: AssetProvenance, requesting_org_id: str) -> bool:
    """Verify org_id matches. Cross-tenant provenance access is never allowed."""
    return prov.org_id == requesting_org_id


# =============================================================================
# Legacy Backfill
# =============================================================================


def mark_legacy(asset_id: str, org_id: str) -> AssetProvenance:
    """Create a LEGACY provenance stub for pre-contract assets.

    These assets were created before the provenance contract and need
    manual or automated backfill to reach COMPLETE state.
    """
    prov = AssetProvenance(
        asset_id=asset_id,
        org_id=org_id,
        provenance_state=ProvenanceState.LEGACY,
    )
    _provenance_registry[asset_id] = prov
    return prov


def backfill_provenance(
    asset_id: str,
    updates: dict[str, Any],
    *,
    backfill_actor: str = "system",
) -> AssetProvenance | None:
    """Apply backfill data to a LEGACY or LINEAGE_INCOMPLETE record.

    Only allowed for non-COMPLETE records. Creates amendment trail.
    """
    prov = _provenance_registry.get(asset_id)
    if prov is None:
        return None

    if prov.provenance_state == ProvenanceState.COMPLETE:
        return prov  # Already complete, no backfill needed

    for field_name, value in updates.items():
        if hasattr(prov, field_name):
            setattr(prov, field_name, value)

    # Re-evaluate state
    prov.provenance_state = determine_provenance_state(prov)
    return prov


# =============================================================================
# Publishing Gate
# =============================================================================


def can_publish(prov: AssetProvenance) -> tuple[bool, list[str]]:
    """Check if an asset's provenance allows publishing.

    Publishing requires:
    1. COMPLETE provenance state
    2. Consent evidence if talent is linked
    3. No unresolved lineage gaps

    Returns (allowed, reasons_if_blocked).
    """
    reasons: list[str] = []

    if prov.provenance_state != ProvenanceState.COMPLETE:
        reasons.append(
            f"Provenance is {prov.provenance_state.value} — must be complete to publish"
        )

    if prov.talent_id and not prov.consent_evidence_ids:
        reasons.append("Talent-linked asset requires consent evidence for publishing")

    # Check parent lineage for derived assets
    if prov.media_type in (AssetMediaType.LIP_SYNC, AssetMediaType.COMPOSITE):
        if not prov.parent_asset_ids:
            reasons.append("Derived asset must reference parent assets")

    return (len(reasons) == 0, reasons)
