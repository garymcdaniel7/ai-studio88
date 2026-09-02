"""Canonical Creative DNA — Story 080.

One versioned authoritative record for each talent's creative identity.
Replaces duplicated values across flat columns, JSON metadata, and frontend types.

Design:
    - One CreativeDNA record per talent (org-scoped)
    - Versioned: each mutation creates an attributable version
    - Conflict detection: legacy flat fields vs canonical record surfaced
    - Historical: generations reference exact version used
    - Reads always go through canonical; legacy fields are compatibility-only
    - Cross-workspace access blocked

Duplicate sources consolidated:
    1. talent.creative_dna (JSONB) — flexible metadata blob
    2. talent.negative_prompt (TEXT) — flat column
    3. talent.visual_style (TEXT) — flat column
    4. talent.best_for (TEXT) — flat column
    5. talent.persona (TEXT) — flat column
    6. talent.style_tags (array) — via schema

Canonical fields:
    - trigger_words: list of exact tokens for model activation
    - negative_prompt: what to avoid in generation
    - visual_style: primary visual aesthetic
    - best_for: intended use cases
    - persona: character description / personality
    - style_tags: searchable category tags
    - appearance: physical attributes (hair, eye, body, height)
    - custom_attributes: extensible key-value (replaces raw JSONB)
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class DNAStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ConflictResolution(str, Enum):
    """How a conflict between legacy and canonical was resolved."""
    CANONICAL_WINS = "canonical_wins"   # Canonical value kept
    LEGACY_ADOPTED = "legacy_adopted"   # Legacy value adopted into canonical
    MERGED = "merged"                   # Values merged
    UNRESOLVED = "unresolved"           # Needs manual decision


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class CreativeDNAVersion:
    """A single version of a talent's Creative DNA."""
    version_id: str = field(default_factory=lambda: f"dna-v-{uuid.uuid4().hex[:10]}")
    version_number: int = 1
    author_id: str = ""         # Who made this change
    created_at: float = field(default_factory=time.time)
    reason: str = ""            # Why this version was created

    # Canonical fields
    trigger_words: list[str] = field(default_factory=list)
    negative_prompt: str = ""
    visual_style: str = ""
    best_for: str = ""
    persona: str = ""
    style_tags: list[str] = field(default_factory=list)
    appearance: dict[str, str] = field(default_factory=dict)  # hair_color, eye_color, etc.
    custom_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CreativeDNA:
    """Canonical Creative DNA record for a talent."""
    dna_id: str = field(default_factory=lambda: f"dna-{uuid.uuid4().hex[:10]}")
    talent_id: str = ""
    org_id: str = ""
    status: DNAStatus = DNAStatus.DRAFT

    # Version history (latest is authoritative)
    versions: list[CreativeDNAVersion] = field(default_factory=list)

    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def effective(self) -> CreativeDNAVersion | None:
        """Get the current effective (latest) version."""
        if not self.versions:
            return None
        return self.versions[-1]

    @property
    def version_count(self) -> int:
        return len(self.versions)

    def get_version(self, version_number: int) -> CreativeDNAVersion | None:
        """Get a specific historical version."""
        for v in self.versions:
            if v.version_number == version_number:
                return v
        return None


@dataclass
class ConflictReport:
    """Report of conflicts between legacy fields and canonical record."""
    talent_id: str = ""
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0

    @property
    def unresolved_count(self) -> int:
        return sum(1 for c in self.conflicts if c.get("resolution") == ConflictResolution.UNRESOLVED.value)


# =============================================================================
# Store
# =============================================================================

_dna_store: dict[str, CreativeDNA] = {}  # dna_id → record
_talent_index: dict[str, str] = {}        # (org_id, talent_id) → dna_id
_generation_refs: dict[str, str] = {}     # job_id → version_id (historical reference)


# =============================================================================
# Canonical API
# =============================================================================


def create_dna(
    org_id: str,
    talent_id: str,
    author_id: str,
    initial_values: dict[str, Any] | None = None,
) -> CreativeDNA:
    """Create a canonical Creative DNA record for a talent.

    Idempotent: returns existing if already created.
    """
    if not org_id or not talent_id:
        raise ValueError("org_id and talent_id are required")

    key = f"{org_id}:{talent_id}"
    if key in _talent_index:
        existing = _dna_store.get(_talent_index[key])
        if existing:
            return existing

    dna = CreativeDNA(talent_id=talent_id, org_id=org_id)

    # Create initial version
    values = initial_values or {}
    version = CreativeDNAVersion(
        version_number=1,
        author_id=author_id,
        reason="Initial creation",
        trigger_words=values.get("trigger_words", []),
        negative_prompt=values.get("negative_prompt", ""),
        visual_style=values.get("visual_style", ""),
        best_for=values.get("best_for", ""),
        persona=values.get("persona", ""),
        style_tags=values.get("style_tags", []),
        appearance=values.get("appearance", {}),
        custom_attributes=values.get("custom_attributes", {}),
    )
    dna.versions.append(version)

    _dna_store[dna.dna_id] = dna
    _talent_index[key] = dna.dna_id

    logger.info(f"CREATIVE_DNA_CREATED: dna={dna.dna_id} talent={talent_id} org={org_id}")
    return dna


def update_dna(
    talent_id: str,
    org_id: str,
    author_id: str,
    updates: dict[str, Any],
    reason: str = "",
    expected_version: int | None = None,
) -> CreativeDNA:
    """Update Creative DNA — creates a new version.

    Supports optimistic concurrency via expected_version.
    Each update is attributable (author + reason).
    """
    dna = _get_dna_by_talent(talent_id, org_id)

    # Optimistic concurrency check
    if expected_version is not None:
        if dna.version_count != expected_version:
            raise ConcurrentEditConflict(
                f"Expected version {expected_version} but current is {dna.version_count}"
            )

    # Build new version from current effective + updates
    current = dna.effective
    new_version = CreativeDNAVersion(
        version_number=dna.version_count + 1,
        author_id=author_id,
        reason=reason,
        trigger_words=updates.get("trigger_words", current.trigger_words if current else []),
        negative_prompt=updates.get("negative_prompt", current.negative_prompt if current else ""),
        visual_style=updates.get("visual_style", current.visual_style if current else ""),
        best_for=updates.get("best_for", current.best_for if current else ""),
        persona=updates.get("persona", current.persona if current else ""),
        style_tags=updates.get("style_tags", current.style_tags if current else []),
        appearance=updates.get("appearance", current.appearance if current else {}),
        custom_attributes=updates.get("custom_attributes", current.custom_attributes if current else {}),
    )

    dna.versions.append(new_version)
    dna.updated_at = time.time()

    logger.info(
        f"CREATIVE_DNA_UPDATED: talent={talent_id} version={new_version.version_number} "
        f"by={author_id} reason={reason}"
    )
    return dna


def rollback_dna(
    talent_id: str,
    org_id: str,
    author_id: str,
    target_version: int,
) -> CreativeDNA:
    """Rollback to a prior version (creates a new version with old values)."""
    dna = _get_dna_by_talent(talent_id, org_id)

    target = dna.get_version(target_version)
    if not target:
        raise VersionNotFound(f"Version {target_version} not found")

    # Rollback = create new version with old values
    return update_dna(
        talent_id, org_id, author_id,
        updates={
            "trigger_words": list(target.trigger_words),
            "negative_prompt": target.negative_prompt,
            "visual_style": target.visual_style,
            "best_for": target.best_for,
            "persona": target.persona,
            "style_tags": list(target.style_tags),
            "appearance": dict(target.appearance),
            "custom_attributes": dict(target.custom_attributes),
        },
        reason=f"Rollback to version {target_version}",
    )


# =============================================================================
# Read API (canonical source of truth)
# =============================================================================


def get_effective_dna(talent_id: str, org_id: str) -> CreativeDNAVersion | None:
    """Get the current effective Creative DNA for a talent.

    This is the ONLY read path for generation and talent display.
    Returns None for cross-tenant access (no existence leak).
    """
    key = f"{org_id}:{talent_id}"
    dna_id = _talent_index.get(key)
    if not dna_id:
        return None
    dna = _dna_store.get(dna_id)
    if not dna or dna.org_id != org_id:
        return None
    return dna.effective


def get_dna_for_generation(talent_id: str, org_id: str, job_id: str) -> CreativeDNAVersion | None:
    """Get Creative DNA for a generation job and record the reference.

    The version used is pinned to this job for historical replay.
    """
    effective = get_effective_dna(talent_id, org_id)
    if effective and job_id:
        _generation_refs[job_id] = effective.version_id
    return effective


def get_historical_dna(job_id: str) -> str | None:
    """Get the DNA version_id used for a historical generation."""
    return _generation_refs.get(job_id)


# =============================================================================
# Conflict Detection & Migration
# =============================================================================


def detect_conflicts(
    talent_id: str,
    org_id: str,
    legacy_flat: dict[str, Any],
    legacy_json: dict[str, Any] | None = None,
) -> ConflictReport:
    """Detect conflicts between legacy fields and canonical record.

    Legacy sources:
    - legacy_flat: talent table flat columns (negative_prompt, visual_style, etc.)
    - legacy_json: talent.creative_dna JSONB blob

    Returns a report of all conflicts with resolution suggestions.
    """
    report = ConflictReport(talent_id=talent_id)
    effective = get_effective_dna(talent_id, org_id)

    if not effective:
        # No canonical record — all legacy values can be adopted
        return report

    # Check each field
    _check_field(report, "negative_prompt", effective.negative_prompt, legacy_flat.get("negative_prompt"))
    _check_field(report, "visual_style", effective.visual_style, legacy_flat.get("visual_style"))
    _check_field(report, "best_for", effective.best_for, legacy_flat.get("best_for"))
    _check_field(report, "persona", effective.persona, legacy_flat.get("persona"))

    # Check JSON blob fields
    if legacy_json:
        json_neg = legacy_json.get("negative_prompt")
        if json_neg and json_neg != effective.negative_prompt and json_neg != legacy_flat.get("negative_prompt"):
            report.conflicts.append({
                "field": "negative_prompt",
                "source": "creative_dna_json",
                "canonical_value": effective.negative_prompt,
                "legacy_value": json_neg,
                "resolution": ConflictResolution.UNRESOLVED.value,
            })

        json_style = legacy_json.get("visual_style") or legacy_json.get("style")
        if json_style and json_style != effective.visual_style:
            report.conflicts.append({
                "field": "visual_style",
                "source": "creative_dna_json",
                "canonical_value": effective.visual_style,
                "legacy_value": json_style,
                "resolution": ConflictResolution.UNRESOLVED.value,
            })

    return report


def backfill_from_legacy(
    talent_id: str,
    org_id: str,
    author_id: str,
    legacy_flat: dict[str, Any],
    legacy_json: dict[str, Any] | None = None,
) -> CreativeDNA:
    """Backfill canonical record from legacy data.

    Priority: canonical (if exists) > legacy_flat > legacy_json.
    Null/empty legacy values are skipped.
    """
    key = f"{org_id}:{talent_id}"
    existing_dna_id = _talent_index.get(key)

    # Merge legacy sources (flat wins over JSON for same field)
    merged: dict[str, Any] = {}
    if legacy_json:
        for k, v in legacy_json.items():
            if v:
                merged[k] = v
    for k, v in legacy_flat.items():
        if v:
            merged[k] = v

    # Map legacy field names to canonical
    values = {
        "negative_prompt": merged.get("negative_prompt", ""),
        "visual_style": merged.get("visual_style", merged.get("style", "")),
        "best_for": merged.get("best_for", ""),
        "persona": merged.get("persona", ""),
        "style_tags": merged.get("style_tags", []),
        "trigger_words": merged.get("trigger_words", []),
        "appearance": {
            k: v for k, v in {
                "hair_color": merged.get("hair_color", ""),
                "eye_color": merged.get("eye_color", ""),
                "body_type": merged.get("body_type", ""),
                "height": merged.get("height", ""),
            }.items() if v
        },
    }

    if existing_dna_id and existing_dna_id in _dna_store:
        # Update existing with non-empty legacy values that don't conflict
        dna = _dna_store[existing_dna_id]
        effective = dna.effective
        updates = {}
        for field_name, legacy_val in values.items():
            if not legacy_val:
                continue
            current_val = getattr(effective, field_name, None) if effective else None
            if not current_val:
                updates[field_name] = legacy_val
        if updates:
            return update_dna(talent_id, org_id, author_id, updates, reason="Backfill from legacy")
        return dna
    else:
        # Create new from legacy
        return create_dna(org_id, talent_id, author_id, initial_values=values)


# =============================================================================
# Legacy Compatibility Adapter
# =============================================================================


def read_legacy_format(talent_id: str, org_id: str) -> dict[str, Any]:
    """Read Creative DNA in legacy flat-field format for backward compatibility.

    Returns a dict matching the old talent column structure.
    Callers should migrate to get_effective_dna().
    """
    effective = get_effective_dna(talent_id, org_id)
    if not effective:
        return {}

    return {
        "negative_prompt": effective.negative_prompt,
        "visual_style": effective.visual_style,
        "best_for": effective.best_for,
        "persona": effective.persona,
        "style_tags": effective.style_tags,
        "creative_dna": {
            "trigger_words": effective.trigger_words,
            "appearance": effective.appearance,
            **effective.custom_attributes,
        },
    }


def write_from_legacy(
    talent_id: str,
    org_id: str,
    author_id: str,
    legacy_values: dict[str, Any],
) -> CreativeDNA:
    """Accept a write from a legacy caller and route through canonical update.

    Legacy callers may still send flat-field updates. This adapter
    routes them through the versioned update path.
    """
    return update_dna(
        talent_id, org_id, author_id,
        updates=legacy_values,
        reason="Legacy adapter write",
    )


# =============================================================================
# Internal Helpers
# =============================================================================


def _get_dna_by_talent(talent_id: str, org_id: str) -> CreativeDNA:
    key = f"{org_id}:{talent_id}"
    dna_id = _talent_index.get(key)
    if not dna_id:
        raise DNANotFound(f"No Creative DNA for talent {talent_id}")
    dna = _dna_store.get(dna_id)
    if not dna or dna.org_id != org_id:
        raise DNANotFound(f"No Creative DNA for talent {talent_id}")
    return dna


def _check_field(
    report: ConflictReport,
    field_name: str,
    canonical_value: str,
    legacy_value: str | None,
) -> None:
    """Check if a legacy field conflicts with canonical."""
    if not legacy_value:
        return  # No legacy value — no conflict
    if legacy_value == canonical_value:
        return  # Same — no conflict

    report.conflicts.append({
        "field": field_name,
        "source": "talent_column",
        "canonical_value": canonical_value,
        "legacy_value": legacy_value,
        "resolution": ConflictResolution.UNRESOLVED.value,
    })


# =============================================================================
# Exceptions
# =============================================================================


class CreativeDNAError(Exception):
    """Base Creative DNA error."""


class DNANotFound(CreativeDNAError):
    """Creative DNA record not found."""


class ConcurrentEditConflict(CreativeDNAError):
    """Optimistic concurrency check failed."""


class VersionNotFound(CreativeDNAError):
    """Requested version doesn't exist."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _dna_store.clear()
    _talent_index.clear()
    _generation_refs.clear()
