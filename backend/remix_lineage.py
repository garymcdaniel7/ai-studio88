"""Remix Lineage & Specification — Story 108.

Every remix is a first-class derived generation with explicit inheritance
decisions and immutable parent-child lineage. Source values come from the
historical snapshot (not current mutable records).

Field semantics:
    INHERIT  — use the value from the source generation snapshot
    OVERRIDE — use a new value provided by the creator
    RESET    — clear to system default (explicit decision, not silent)

Lineage:
    parent_asset_id → child_asset_id (direct)
    ancestry chain: asset → parent → grandparent → ... (multi-generation)

Authorization:
    - Source asset must belong to the same org
    - Source context package must be accessible
    - Consent still valid for referenced talent
    - Model/LoRA still deployable (or use RESET)
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


class FieldAction(str, Enum):
    """How a field is handled in a remix."""
    INHERIT = "inherit"     # Use source snapshot value
    OVERRIDE = "override"   # Use new value
    RESET = "reset"         # Clear to default


class RemixStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Remix Field
# =============================================================================


@dataclass
class RemixField:
    """A single field in a remix with explicit action."""
    name: str
    action: FieldAction
    source_value: Any = None      # From source snapshot (immutable)
    override_value: Any = None    # Creator's new value (for OVERRIDE)
    default_value: Any = None     # System default (for RESET)

    @property
    def effective_value(self) -> Any:
        if self.action == FieldAction.INHERIT:
            return self.source_value
        elif self.action == FieldAction.OVERRIDE:
            return self.override_value
        elif self.action == FieldAction.RESET:
            return self.default_value
        return self.source_value


# =============================================================================
# Remix Specification
# =============================================================================


@dataclass
class RemixSpec:
    """Typed remix specification with full source references."""
    remix_id: str = field(default_factory=lambda: f"rmx-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""

    # Source references (immutable — from historical snapshot)
    source_asset_id: str = ""
    source_job_id: str = ""
    source_snapshot_id: str = ""
    source_context_package_id: str = ""

    # Fields with explicit actions
    fields: dict[str, RemixField] = field(default_factory=dict)

    # Status
    status: RemixStatus = RemixStatus.DRAFT

    # Result
    result_asset_id: str | None = None
    result_job_id: str | None = None

    # Idempotency
    idempotency_key: str | None = None

    # Timing
    created_at: float = field(default_factory=time.time)
    submitted_at: float | None = None
    completed_at: float | None = None

    @property
    def inherited_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.action == FieldAction.INHERIT]

    @property
    def overridden_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.action == FieldAction.OVERRIDE]

    @property
    def reset_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.action == FieldAction.RESET]


# =============================================================================
# Lineage Record
# =============================================================================


@dataclass
class LineageLink:
    """Parent-child lineage link between assets."""
    link_id: str = field(default_factory=lambda: f"lin-{uuid.uuid4().hex[:10]}")
    parent_asset_id: str = ""
    child_asset_id: str = ""
    remix_id: str = ""
    org_id: str = ""
    created_at: float = field(default_factory=time.time)


# =============================================================================
# Store
# =============================================================================

_remixes: dict[str, RemixSpec] = {}
_lineage: list[LineageLink] = []

# Source data simulation (asset_id → snapshot data)
_source_snapshots: dict[str, dict[str, Any]] = {}
_asset_orgs: dict[str, str] = {}  # asset_id → org_id

# Simulation flags
_simulate_source_deleted: bool = False
_simulate_context_incomplete: bool = False
_simulate_model_unavailable: bool = False
_simulate_consent_revoked: bool = False


# =============================================================================
# Supported Remix Fields
# =============================================================================

REMIXABLE_FIELDS = {
    "prompt", "negative_prompt", "model_id", "model_version",
    "lora_ids", "lora_versions", "lora_strengths",
    "seed", "width", "height", "steps", "cfg", "guidance",
    "talent_id", "workflow_id", "recipe_id",
    "controlnet_input", "style_preset",
}

FIELD_DEFAULTS: dict[str, Any] = {
    "prompt": "",
    "negative_prompt": "",
    "model_id": "flux_dev",
    "model_version": "",
    "lora_ids": [],
    "lora_versions": [],
    "lora_strengths": [],
    "seed": None,  # Random
    "width": 1024,
    "height": 1024,
    "steps": 20,
    "cfg": 7.0,
    "guidance": None,
    "talent_id": None,
    "workflow_id": None,
    "recipe_id": None,
    "controlnet_input": None,
    "style_preset": None,
}


# =============================================================================
# Remix API
# =============================================================================


def create_remix(
    org_id: str,
    user_id: str,
    source_asset_id: str,
    field_actions: dict[str, dict[str, Any]],
    idempotency_key: str | None = None,
) -> RemixSpec:
    """Create a typed remix specification.

    Args:
        org_id: Workspace (from JWT)
        user_id: Actor (from JWT)
        source_asset_id: The asset being remixed
        field_actions: {field_name: {"action": "inherit"|"override"|"reset", "value": ...}}
        idempotency_key: For duplicate prevention

    Returns:
        RemixSpec with all fields explicitly marked.
    """
    if not org_id or not user_id or not source_asset_id:
        raise ValueError("org_id, user_id, and source_asset_id are required")

    # Idempotency check
    if idempotency_key:
        existing = _find_by_idempotency(org_id, idempotency_key)
        if existing:
            return existing

    # Authorization: source must belong to same org
    source_org = _asset_orgs.get(source_asset_id)
    if source_org and source_org != org_id:
        raise RemixDenied("Source asset belongs to a different workspace")

    # Get source snapshot
    if _simulate_source_deleted:
        raise SourceUnavailable("Source asset has been deleted")

    snapshot = _source_snapshots.get(source_asset_id, {})
    if _simulate_context_incomplete and not snapshot:
        raise SourceUnavailable("Source context is incomplete — cannot remix")

    # Build fields with explicit actions
    fields: dict[str, RemixField] = {}
    for field_name in REMIXABLE_FIELDS:
        action_spec = field_actions.get(field_name, {})
        action = FieldAction(action_spec.get("action", "inherit"))

        remix_field = RemixField(
            name=field_name,
            action=action,
            source_value=snapshot.get(field_name),
            override_value=action_spec.get("value") if action == FieldAction.OVERRIDE else None,
            default_value=FIELD_DEFAULTS.get(field_name),
        )
        fields[field_name] = remix_field

    spec = RemixSpec(
        org_id=org_id,
        user_id=user_id,
        source_asset_id=source_asset_id,
        source_job_id=snapshot.get("job_id", ""),
        source_snapshot_id=snapshot.get("snapshot_id", ""),
        source_context_package_id=snapshot.get("context_package_id", ""),
        fields=fields,
        idempotency_key=idempotency_key,
    )

    _remixes[spec.remix_id] = spec
    logger.info(f"REMIX_CREATED: id={spec.remix_id} source={source_asset_id} overrides={spec.overridden_fields}")
    return spec


def validate_remix(remix_id: str, org_id: str) -> RemixSpec:
    """Validate remix before submission.

    Checks:
    1. Source accessible
    2. Model still deployable (for inherited model)
    3. Consent valid (for inherited talent)
    4. LoRA compatible
    """
    spec = _get_remix(remix_id, org_id)

    if spec.status != RemixStatus.DRAFT:
        return spec  # Already validated

    # Check model availability (if inheriting model)
    model_field = spec.fields.get("model_id")
    if model_field and model_field.action == FieldAction.INHERIT:
        if _simulate_model_unavailable:
            raise CompatibilityError(
                f"Inherited model '{model_field.source_value}' is no longer deployable. "
                f"Use OVERRIDE or RESET for model_id."
            )

    # Check consent (if inheriting talent)
    talent_field = spec.fields.get("talent_id")
    if talent_field and talent_field.action == FieldAction.INHERIT and talent_field.source_value:
        if _simulate_consent_revoked:
            raise ConsentError(
                f"Consent revoked for talent '{talent_field.source_value}'. "
                f"Use RESET for talent_id."
            )

    spec.status = RemixStatus.VALIDATED
    return spec


def submit_remix(remix_id: str, org_id: str, job_id: str) -> RemixSpec:
    """Submit a validated remix for generation."""
    spec = _get_remix(remix_id, org_id)

    if spec.status not in (RemixStatus.VALIDATED, RemixStatus.DRAFT):
        if spec.status == RemixStatus.SUBMITTED:
            return spec  # Idempotent
        raise InvalidRemixState(f"Cannot submit from state {spec.status.value}")

    # Auto-validate if still draft
    if spec.status == RemixStatus.DRAFT:
        validate_remix(remix_id, org_id)

    spec.status = RemixStatus.SUBMITTED
    spec.result_job_id = job_id
    spec.submitted_at = time.time()

    logger.info(f"REMIX_SUBMITTED: id={remix_id} job={job_id}")
    return spec


def complete_remix(remix_id: str, org_id: str, result_asset_id: str) -> RemixSpec:
    """Mark remix complete and establish parent-child lineage."""
    spec = _get_remix(remix_id, org_id)

    if spec.status == RemixStatus.COMPLETED:
        return spec  # Idempotent

    spec.status = RemixStatus.COMPLETED
    spec.result_asset_id = result_asset_id
    spec.completed_at = time.time()

    # Create lineage link
    link = LineageLink(
        parent_asset_id=spec.source_asset_id,
        child_asset_id=result_asset_id,
        remix_id=remix_id,
        org_id=org_id,
    )
    _lineage.append(link)

    # Register the result asset's org for future remixes
    _asset_orgs[result_asset_id] = org_id

    logger.info(f"REMIX_COMPLETED: id={remix_id} parent={spec.source_asset_id} child={result_asset_id}")
    return spec


def fail_remix(remix_id: str, org_id: str, error: str) -> RemixSpec:
    """Mark remix as failed."""
    spec = _get_remix(remix_id, org_id)
    spec.status = RemixStatus.FAILED
    return spec


# =============================================================================
# Lineage Query
# =============================================================================


def get_ancestry(asset_id: str, org_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
    """Get the full ancestry chain for an asset (multi-generation).

    Returns ordered list: [immediate parent, grandparent, ...]
    """
    chain = []
    current = asset_id
    depth = 0

    while depth < max_depth:
        parent_link = _find_parent(current, org_id)
        if not parent_link:
            break
        chain.append({
            "asset_id": parent_link.parent_asset_id,
            "remix_id": parent_link.remix_id,
            "depth": depth + 1,
        })
        current = parent_link.parent_asset_id
        depth += 1

    return chain


def get_children(asset_id: str, org_id: str) -> list[dict[str, Any]]:
    """Get direct children (assets remixed from this one)."""
    return [
        {
            "asset_id": link.child_asset_id,
            "remix_id": link.remix_id,
        }
        for link in _lineage
        if link.parent_asset_id == asset_id and link.org_id == org_id
    ]


def get_remix_details(remix_id: str, org_id: str) -> dict[str, Any] | None:
    """Get full remix details including field actions."""
    spec = _remixes.get(remix_id)
    if not spec or spec.org_id != org_id:
        return None

    return {
        "remix_id": spec.remix_id,
        "source_asset_id": spec.source_asset_id,
        "source_snapshot_id": spec.source_snapshot_id,
        "status": spec.status.value,
        "result_asset_id": spec.result_asset_id,
        "inherited_fields": spec.inherited_fields,
        "overridden_fields": spec.overridden_fields,
        "reset_fields": spec.reset_fields,
        "fields": {
            name: {
                "action": f.action.value,
                "effective_value": f.effective_value,
            }
            for name, f in spec.fields.items()
        },
    }


# =============================================================================
# Helpers
# =============================================================================


def _get_remix(remix_id: str, org_id: str) -> RemixSpec:
    spec = _remixes.get(remix_id)
    if not spec or spec.org_id != org_id:
        raise RemixNotFound(f"Remix {remix_id} not found")
    return spec


def _find_by_idempotency(org_id: str, key: str) -> RemixSpec | None:
    for spec in _remixes.values():
        if spec.org_id == org_id and spec.idempotency_key == key:
            return spec
    return None


def _find_parent(asset_id: str, org_id: str) -> LineageLink | None:
    for link in _lineage:
        if link.child_asset_id == asset_id and link.org_id == org_id:
            return link
    return None


# =============================================================================
# Exceptions
# =============================================================================


class RemixError(Exception):
    """Base remix error."""


class RemixNotFound(RemixError):
    """Remix not found or cross-tenant."""


class RemixDenied(RemixError):
    """Authorization denied."""


class SourceUnavailable(RemixError):
    """Source asset/context unavailable."""


class CompatibilityError(RemixError):
    """Inherited value no longer compatible."""


class ConsentError(RemixError):
    """Consent revoked for inherited reference."""


class InvalidRemixState(RemixError):
    """Invalid state transition."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    global _simulate_source_deleted, _simulate_context_incomplete
    global _simulate_model_unavailable, _simulate_consent_revoked
    _remixes.clear()
    _lineage.clear()
    _source_snapshots.clear()
    _asset_orgs.clear()
    _simulate_source_deleted = False
    _simulate_context_incomplete = False
    _simulate_model_unavailable = False
    _simulate_consent_revoked = False


def _register_source(asset_id: str, org_id: str, snapshot: dict[str, Any]) -> None:
    """Register a source asset with its snapshot for testing."""
    _source_snapshots[asset_id] = snapshot
    _asset_orgs[asset_id] = org_id


def _inject_condition(condition: str, enabled: bool = True) -> None:
    global _simulate_source_deleted, _simulate_context_incomplete
    global _simulate_model_unavailable, _simulate_consent_revoked
    if condition == "source_deleted":
        _simulate_source_deleted = enabled
    elif condition == "context_incomplete":
        _simulate_context_incomplete = enabled
    elif condition == "model_unavailable":
        _simulate_model_unavailable = enabled
    elif condition == "consent_revoked":
        _simulate_consent_revoked = enabled
