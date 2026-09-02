"""Object DNA Contract — Story 114.

Versioned structured understanding of assets as reusable objects. Tag-only
assets are explicitly NOT Object DNA — they are labeled unanalysed.

Lifecycle:
    unanalysed → analysing → partial → review_required → approved → superseded
                           → failed

Key invariants:
    - Tag-only metadata is NOT Object DNA (explicitly unanalysed)
    - Each version captures model/source, confidence, provenance
    - User corrections create a new version (history preserved)
    - Context assembly and Hermes consume ONLY approved versions
    - Cross-workspace access denied
    - Low confidence is visible (never hidden)

DECISION-REQUIRED:
    - Final attribute taxonomy for each domain type (product, wardrobe, prop, location)
    - Minimum confidence threshold for auto-approval vs manual review
    - Which vision model(s) are approved sources
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
# Enums
# =============================================================================


class DNAStatus(str, Enum):
    UNANALYSED = "unanalysed"         # No analysis performed (tag-only)
    ANALYSING = "analysing"           # Analysis in progress
    PARTIAL = "partial"               # Some attributes extracted, incomplete
    REVIEW_REQUIRED = "review_required"  # Analysis done, needs human review
    APPROVED = "approved"             # Verified correct — safe for context use
    FAILED = "failed"                 # Analysis failed
    SUPERSEDED = "superseded"         # Replaced by newer version


class DomainType(str, Enum):
    """Object domain types (DECISION-REQUIRED: final taxonomy)."""
    PRODUCT = "product"
    WARDROBE = "wardrobe"
    PROP = "prop"
    LOCATION = "location"
    VEHICLE = "vehicle"
    FOOD = "food"
    UNKNOWN = "unknown"


class CorrectionType(str, Enum):
    ADD_ATTRIBUTE = "add_attribute"
    MODIFY_ATTRIBUTE = "modify_attribute"
    REMOVE_ATTRIBUTE = "remove_attribute"
    CHANGE_DOMAIN = "change_domain"
    CHANGE_CONFIDENCE = "change_confidence"


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class AnalysisProvenance:
    """How this analysis was produced."""
    source_model: str = ""          # e.g. "gpt-4-vision", "clip-vit-large"
    source_model_version: str = ""
    analysis_job_id: str = ""
    analysed_at: float | None = None
    analysis_duration_seconds: float = 0.0


@dataclass
class StructuredAttribute:
    """A single structured attribute with confidence."""
    key: str = ""                   # e.g. "color", "material", "brand"
    value: Any = None               # e.g. "red", "leather", "Nike"
    confidence: float = 0.0         # 0.0 - 1.0
    source: str = ""                # "model" | "user_correction" | "inherited"


@dataclass
class CorrectionRecord:
    """Record of a user correction to Object DNA."""
    correction_id: str = field(default_factory=lambda: f"cor-{uuid.uuid4().hex[:10]}")
    correction_type: CorrectionType = CorrectionType.MODIFY_ATTRIBUTE
    field_key: str = ""
    old_value: Any = None
    new_value: Any = None
    corrected_by: str = ""
    corrected_at: float = field(default_factory=time.time)
    reason: str = ""


@dataclass
class ObjectDNAVersion:
    """A single version of Object DNA for an asset."""
    version_id: str = field(default_factory=lambda: f"odna-v-{uuid.uuid4().hex[:10]}")
    version_number: int = 1

    # Domain classification
    domain_type: DomainType = DomainType.UNKNOWN
    domain_confidence: float = 0.0

    # Structured attributes
    attributes: list[StructuredAttribute] = field(default_factory=list)

    # Overall confidence
    overall_confidence: float = 0.0

    # Provenance
    provenance: AnalysisProvenance = field(default_factory=AnalysisProvenance)

    # Corrections applied in this version
    corrections: list[CorrectionRecord] = field(default_factory=list)

    # Timing
    created_at: float = field(default_factory=time.time)

    @property
    def is_low_confidence(self) -> bool:
        return self.overall_confidence < 0.7

    @property
    def attribute_count(self) -> int:
        return len(self.attributes)


@dataclass
class ObjectDNA:
    """Authoritative Object DNA record for an asset."""
    dna_id: str = field(default_factory=lambda: f"odna-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    asset_id: str = ""

    # Status
    status: DNAStatus = DNAStatus.UNANALYSED

    # Versions (latest approved is authoritative)
    versions: list[ObjectDNAVersion] = field(default_factory=list)

    # Relationships
    related_entity_ids: list[str] = field(default_factory=list)

    # Metadata
    has_tags_only: bool = True      # Explicitly flags tag-only assets
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def current_version(self) -> ObjectDNAVersion | None:
        if not self.versions:
            return None
        return self.versions[-1]

    @property
    def approved_version(self) -> ObjectDNAVersion | None:
        """Get the latest approved version (for context consumption)."""
        if self.status != DNAStatus.APPROVED:
            return None
        return self.current_version

    @property
    def version_count(self) -> int:
        return len(self.versions)

    @property
    def is_analysed(self) -> bool:
        return self.status not in (DNAStatus.UNANALYSED, DNAStatus.ANALYSING)


# =============================================================================
# Store
# =============================================================================

_dna_records: dict[str, ObjectDNA] = {}  # dna_id → record
_asset_index: dict[str, str] = {}         # asset_id → dna_id
_generation_refs: dict[str, str] = {}     # job_id → version_id


# =============================================================================
# Lifecycle API
# =============================================================================


def register_asset(org_id: str, asset_id: str) -> ObjectDNA:
    """Register an asset — starts as UNANALYSED (tag-only is NOT DNA)."""
    if not org_id or not asset_id:
        raise ValueError("org_id and asset_id are required")

    # Idempotent
    if asset_id in _asset_index:
        existing = _dna_records.get(_asset_index[asset_id])
        if existing:
            return existing

    dna = ObjectDNA(org_id=org_id, asset_id=asset_id)
    _dna_records[dna.dna_id] = dna
    _asset_index[asset_id] = dna.dna_id
    return dna


def start_analysis(
    asset_id: str,
    org_id: str,
    source_model: str,
    source_model_version: str = "",
    job_id: str = "",
) -> ObjectDNA:
    """Start analysis for an asset."""
    dna = _get_dna_by_asset(asset_id, org_id)

    dna.status = DNAStatus.ANALYSING
    dna.has_tags_only = False
    dna.updated_at = time.time()

    # Prepare provenance for upcoming version
    return dna


def complete_analysis(
    asset_id: str,
    org_id: str,
    domain_type: DomainType,
    attributes: list[dict[str, Any]],
    overall_confidence: float,
    domain_confidence: float = 0.0,
    source_model: str = "",
    source_model_version: str = "",
    job_id: str = "",
) -> ObjectDNA:
    """Complete analysis — creates a new version.

    Status transitions:
    - High confidence (≥ 0.85): review_required (could be auto-approved in future)
    - Low confidence (< 0.7): partial
    - Between: review_required
    """
    dna = _get_dna_by_asset(asset_id, org_id)

    if dna.status not in (DNAStatus.ANALYSING, DNAStatus.UNANALYSED, DNAStatus.APPROVED, DNAStatus.PARTIAL):
        raise InvalidDNAState(f"Cannot complete analysis from state {dna.status.value}")

    # Build version
    structured_attrs = [
        StructuredAttribute(
            key=a["key"],
            value=a["value"],
            confidence=a.get("confidence", overall_confidence),
            source="model",
        )
        for a in attributes
    ]

    version = ObjectDNAVersion(
        version_number=dna.version_count + 1,
        domain_type=domain_type,
        domain_confidence=domain_confidence or overall_confidence,
        attributes=structured_attrs,
        overall_confidence=overall_confidence,
        provenance=AnalysisProvenance(
            source_model=source_model,
            source_model_version=source_model_version,
            analysis_job_id=job_id,
            analysed_at=time.time(),
        ),
    )

    # Supersede previous version
    if dna.versions:
        pass  # Previous versions preserved for history

    dna.versions.append(version)
    dna.has_tags_only = False

    # Determine status based on confidence
    if overall_confidence < 0.7:
        dna.status = DNAStatus.PARTIAL
    else:
        dna.status = DNAStatus.REVIEW_REQUIRED

    dna.updated_at = time.time()

    logger.info(
        f"OBJECT_DNA_ANALYSED: asset={asset_id} domain={domain_type.value} "
        f"confidence={overall_confidence:.2f} attrs={len(attributes)}"
    )
    return dna


def approve_dna(asset_id: str, org_id: str, approver_id: str) -> ObjectDNA:
    """Approve Object DNA for context consumption."""
    dna = _get_dna_by_asset(asset_id, org_id)

    if dna.status == DNAStatus.APPROVED:
        return dna  # Idempotent

    if dna.status not in (DNAStatus.REVIEW_REQUIRED, DNAStatus.PARTIAL):
        raise InvalidDNAState(f"Cannot approve from state {dna.status.value}")

    if not dna.versions:
        raise InvalidDNAState("No analysis version to approve")

    dna.status = DNAStatus.APPROVED
    dna.updated_at = time.time()

    logger.info(f"OBJECT_DNA_APPROVED: asset={asset_id} by={approver_id}")
    return dna


def reject_dna(asset_id: str, org_id: str, reason: str) -> ObjectDNA:
    """Reject analysis — needs reanalysis or correction."""
    dna = _get_dna_by_asset(asset_id, org_id)
    dna.status = DNAStatus.FAILED
    dna.updated_at = time.time()
    return dna


# =============================================================================
# Corrections
# =============================================================================


def correct_dna(
    asset_id: str,
    org_id: str,
    corrected_by: str,
    corrections: list[dict[str, Any]],
) -> ObjectDNA:
    """Apply user corrections — creates a new version preserving history.

    Corrections don't erase previous analysis — they create a new version
    with the correction applied on top of the current attributes.
    """
    dna = _get_dna_by_asset(asset_id, org_id)

    if not corrected_by:
        raise ValueError("corrected_by is required for audit")

    if not dna.versions:
        raise InvalidDNAState("No existing analysis to correct")

    current = dna.current_version
    # Deep copy attributes from current version to avoid mutating history
    new_attrs = [
        StructuredAttribute(key=a.key, value=a.value, confidence=a.confidence, source=a.source)
        for a in (current.attributes if current else [])
    ]
    correction_records = []

    for corr in corrections:
        corr_type = CorrectionType(corr.get("type", "modify_attribute"))
        key = corr.get("key", "")
        new_value = corr.get("value")
        old_value = None

        if corr_type == CorrectionType.ADD_ATTRIBUTE:
            new_attrs.append(StructuredAttribute(
                key=key, value=new_value, confidence=1.0, source="user_correction",
            ))
        elif corr_type == CorrectionType.MODIFY_ATTRIBUTE:
            for attr in new_attrs:
                if attr.key == key:
                    old_value = attr.value
                    attr.value = new_value
                    attr.confidence = 1.0
                    attr.source = "user_correction"
                    break
        elif corr_type == CorrectionType.REMOVE_ATTRIBUTE:
            old_attrs = [a for a in new_attrs if a.key == key]
            old_value = old_attrs[0].value if old_attrs else None
            new_attrs = [a for a in new_attrs if a.key != key]
        elif corr_type == CorrectionType.CHANGE_DOMAIN:
            pass  # Handled below

        correction_records.append(CorrectionRecord(
            correction_type=corr_type,
            field_key=key,
            old_value=old_value,
            new_value=new_value,
            corrected_by=corrected_by,
            reason=corr.get("reason", ""),
        ))

    # Create new version with corrections
    new_domain = current.domain_type if current else DomainType.UNKNOWN
    for corr in corrections:
        if corr.get("type") == "change_domain":
            new_domain = DomainType(corr["value"])

    new_version = ObjectDNAVersion(
        version_number=dna.version_count + 1,
        domain_type=new_domain,
        domain_confidence=1.0,  # User-corrected = high confidence
        attributes=new_attrs,
        overall_confidence=1.0,
        corrections=correction_records,
        provenance=AnalysisProvenance(source_model="user_correction"),
    )

    dna.versions.append(new_version)
    dna.status = DNAStatus.APPROVED  # User corrections auto-approve
    dna.updated_at = time.time()

    logger.info(f"OBJECT_DNA_CORRECTED: asset={asset_id} by={corrected_by} corrections={len(corrections)}")
    return dna


# =============================================================================
# Context Consumption (ONLY approved versions)
# =============================================================================


def get_for_context(asset_id: str, org_id: str, job_id: str | None = None) -> dict[str, Any] | None:
    """Get Object DNA for context assembly — ONLY returns approved versions.

    Tag-only assets return None (not Object DNA).
    Low-confidence returns the data but flags it.
    """
    dna = _dna_records.get(_asset_index.get(asset_id, ""))
    if not dna or dna.org_id != org_id:
        return None

    approved = dna.approved_version
    if not approved:
        return None  # Not approved — cannot be consumed by context

    # Pin version for generation history
    if job_id:
        _generation_refs[job_id] = approved.version_id

    return {
        "dna_id": dna.dna_id,
        "asset_id": asset_id,
        "domain_type": approved.domain_type.value,
        "attributes": {a.key: a.value for a in approved.attributes},
        "confidence": approved.overall_confidence,
        "is_low_confidence": approved.is_low_confidence,
        "version_id": approved.version_id,
        "version_number": approved.version_number,
    }


def get_historical_dna_version(job_id: str) -> str | None:
    """Get the DNA version used for a historical generation."""
    return _generation_refs.get(job_id)


# =============================================================================
# Query
# =============================================================================


def get_dna(asset_id: str, org_id: str) -> ObjectDNA | None:
    """Get Object DNA with tenant isolation."""
    dna_id = _asset_index.get(asset_id)
    if not dna_id:
        return None
    dna = _dna_records.get(dna_id)
    if not dna or dna.org_id != org_id:
        return None
    return dna


def get_dna_status(asset_id: str, org_id: str) -> dict[str, Any]:
    """Get DNA status summary (for Library UI)."""
    dna = get_dna(asset_id, org_id)
    if not dna:
        return {"asset_id": asset_id, "status": "unanalysed", "has_tags_only": True}

    current = dna.current_version
    return {
        "asset_id": asset_id,
        "status": dna.status.value,
        "has_tags_only": dna.has_tags_only,
        "is_analysed": dna.is_analysed,
        "domain_type": current.domain_type.value if current else None,
        "confidence": current.overall_confidence if current else 0.0,
        "is_low_confidence": current.is_low_confidence if current else False,
        "version_count": dna.version_count,
        "has_approved_version": dna.approved_version is not None,
    }


def list_unanalysed(org_id: str) -> list[str]:
    """List asset IDs that have no Object DNA analysis."""
    results = []
    for dna in _dna_records.values():
        if dna.org_id == org_id and dna.status == DNAStatus.UNANALYSED:
            results.append(dna.asset_id)
    return results


# =============================================================================
# Helpers
# =============================================================================


def _get_dna_by_asset(asset_id: str, org_id: str) -> ObjectDNA:
    dna_id = _asset_index.get(asset_id)
    if not dna_id:
        # Auto-register
        dna = register_asset(org_id, asset_id)
        return dna
    dna = _dna_records.get(dna_id)
    if not dna or dna.org_id != org_id:
        raise DNANotFound(f"Object DNA for asset {asset_id} not found")
    return dna


# =============================================================================
# Exceptions
# =============================================================================


class ObjectDNAError(Exception):
    """Base Object DNA error."""


class DNANotFound(ObjectDNAError):
    """Not found or cross-tenant."""


class InvalidDNAState(ObjectDNAError):
    """Invalid state for operation."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _dna_records.clear()
    _asset_index.clear()
    _generation_refs.clear()
