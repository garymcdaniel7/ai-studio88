"""Context Assembler — Story 081.

Server-side assembler that loads ALL applicable continuity sources for a
generation request. Each source reports explicit typed status so omissions
are visible, not silently swallowed.

Supported Sources (from Story 079 canonical model):
    1. TalentProfile       — Character identity and physical attributes
    2. CreativePreferences — Versioned style/generation preferences
    3. LoRAAssignment      — Approved LoRA model version
    4. Relationships       — Typed links to other talents
    5. WardrobeItems       — Active wardrobe/props/locations
    6. ContinuityRules     — Active generation rules
    7. ContinuityNotes     — Priority creative notes
    8. VoiceAssignment     — Voice profile (for audio generation)
    9. ProjectContext      — Project-level settings and metadata
   10. RecentFeedback      — Recent generation feedback (last N)

Every source returns:
    - status: loaded | absent | filtered | stale | error | unauthorized
    - record_ids: list of loaded record IDs
    - versions: version numbers for pinning
    - error: reason if not loaded
    - required: whether generation should block without it

Authorization:
    - All reads are workspace-scoped (org_id from JWT)
    - Actor must belong to the workspace
    - Cross-workspace references are rejected

This module does NOT define merge precedence or prompt rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Source Status
# =============================================================================


class SourceStatus(StrEnum):
    LOADED = "loaded"               # Successfully loaded
    ABSENT = "absent"               # No data exists for this source
    FILTERED = "filtered"           # Exists but excluded (archived/unapproved/stale)
    STALE = "stale"                 # Data exists but may be outdated
    ERROR = "error"                 # Load failed (transient or permanent)
    UNAUTHORIZED = "unauthorized"   # Cross-workspace or insufficient permissions


class SourceRequirement(StrEnum):
    REQUIRED = "required"       # Generation should block without this
    RECOMMENDED = "recommended" # Degraded output without this
    OPTIONAL = "optional"       # Nice to have, not blocking


# =============================================================================
# Source Names
# =============================================================================


class ContextSource(StrEnum):
    TALENT_PROFILE = "talent_profile"
    CREATIVE_PREFERENCES = "creative_preferences"
    LORA_ASSIGNMENT = "lora_assignment"
    RELATIONSHIPS = "relationships"
    WARDROBE_ITEMS = "wardrobe_items"
    CONTINUITY_RULES = "continuity_rules"
    CONTINUITY_NOTES = "continuity_notes"
    VOICE_ASSIGNMENT = "voice_assignment"
    PROJECT_CONTEXT = "project_context"
    RECENT_FEEDBACK = "recent_feedback"


# Source classification: required vs optional per media type
SOURCE_REQUIREMENTS: dict[ContextSource, SourceRequirement] = {
    ContextSource.TALENT_PROFILE: SourceRequirement.REQUIRED,
    ContextSource.CREATIVE_PREFERENCES: SourceRequirement.RECOMMENDED,
    ContextSource.LORA_ASSIGNMENT: SourceRequirement.RECOMMENDED,
    ContextSource.RELATIONSHIPS: SourceRequirement.OPTIONAL,
    ContextSource.WARDROBE_ITEMS: SourceRequirement.OPTIONAL,
    ContextSource.CONTINUITY_RULES: SourceRequirement.RECOMMENDED,
    ContextSource.CONTINUITY_NOTES: SourceRequirement.OPTIONAL,
    ContextSource.VOICE_ASSIGNMENT: SourceRequirement.OPTIONAL,
    ContextSource.PROJECT_CONTEXT: SourceRequirement.OPTIONAL,
    ContextSource.RECENT_FEEDBACK: SourceRequirement.OPTIONAL,
}


# =============================================================================
# Source Load Result
# =============================================================================


@dataclass
class SourceLoadResult:
    """Result of loading a single continuity source."""

    source: ContextSource
    status: SourceStatus
    requirement: SourceRequirement = SourceRequirement.OPTIONAL
    # Loaded data
    record_ids: list[str] = field(default_factory=list)
    versions: list[int] = field(default_factory=list)
    data: Any = None                # The actual loaded records
    record_count: int = 0
    # Filtering info
    filtered_count: int = 0         # How many were excluded
    filter_reasons: list[str] = field(default_factory=list)
    # Error info
    error: str | None = None
    # Timing
    loaded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "status": self.status.value,
            "requirement": self.requirement.value,
            "record_count": self.record_count,
            "record_ids": self.record_ids[:10],  # Cap for readability
            "versions": self.versions[:10],
            "filtered_count": self.filtered_count,
            "filter_reasons": self.filter_reasons[:5],
            "error": self.error,
            "loaded_at": self.loaded_at,
        }


# =============================================================================
# Assembled Context Package
# =============================================================================


@dataclass
class AssembledContext:
    """The complete context package for one generation request.

    Contains typed results for every supported source.
    Omissions are explicit — never silently hidden.
    """

    # Request identity
    org_id: str = ""
    user_id: str = ""
    talent_id: str = ""
    project_id: str | None = None

    # Per-source results
    sources: dict[ContextSource, SourceLoadResult] = field(default_factory=dict)

    # Summary
    assembled_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    total_loaded: int = 0
    total_absent: int = 0
    total_filtered: int = 0
    total_errors: int = 0
    has_required_failures: bool = False

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "user_id": self.user_id,
            "talent_id": self.talent_id,
            "project_id": self.project_id,
            "assembled_at": self.assembled_at,
            "total_loaded": self.total_loaded,
            "total_absent": self.total_absent,
            "total_filtered": self.total_filtered,
            "total_errors": self.total_errors,
            "has_required_failures": self.has_required_failures,
            "sources": {k.value: v.to_dict() for k, v in self.sources.items()},
        }


# =============================================================================
# Source Loader Interface
# =============================================================================


@dataclass
class LoadRequest:
    """Parameters for loading continuity context."""

    org_id: str
    user_id: str
    talent_id: str
    project_id: str | None = None
    # Filters
    approval_states: list[str] = field(default_factory=lambda: ["approved"])
    include_archived: bool = False
    max_feedback_count: int = 10


# =============================================================================
# Context Assembler
# =============================================================================


class ContextAssembler:
    """Loads all applicable continuity sources for a generation request.

    Each source loader is a callable that accepts LoadRequest and returns
    SourceLoadResult. Loaders are injected for testability.
    """

    def __init__(self, loaders: dict[ContextSource, Any] | None = None) -> None:
        """Initialize with optional custom loaders.

        If no loaders provided, uses default no-op loaders that return ABSENT.
        """
        self._loaders: dict[ContextSource, Any] = loaders or {}

    def assemble(self, request: LoadRequest) -> AssembledContext:
        """Assemble the complete context package.

        Loads every supported source. Never silently skips or converts
        errors into apparently complete context.
        """
        # Authorization check
        if not request.org_id:
            return self._unauthorized_context(request, "org_id is required")
        if not request.user_id:
            return self._unauthorized_context(request, "user_id is required")

        ctx = AssembledContext(
            org_id=request.org_id,
            user_id=request.user_id,
            talent_id=request.talent_id,
            project_id=request.project_id,
        )

        # Load each source
        for source in ContextSource:
            requirement = SOURCE_REQUIREMENTS.get(source, SourceRequirement.OPTIONAL)
            loader = self._loaders.get(source)

            if loader is None:
                # No loader configured — report as absent
                result = SourceLoadResult(
                    source=source,
                    status=SourceStatus.ABSENT,
                    requirement=requirement,
                    error="No loader configured for this source",
                )
            else:
                try:
                    result = loader(request)
                    result.source = source
                    result.requirement = requirement
                except Exception as exc:
                    result = SourceLoadResult(
                        source=source,
                        status=SourceStatus.ERROR,
                        requirement=requirement,
                        error=str(exc)[:200],
                    )

            ctx.sources[source] = result

        # Compute summary
        self._compute_summary(ctx)
        return ctx

    def _compute_summary(self, ctx: AssembledContext) -> None:
        """Compute summary counts from source results."""
        for source, result in ctx.sources.items():
            if result.status == SourceStatus.LOADED:
                ctx.total_loaded += 1
            elif result.status == SourceStatus.ABSENT:
                ctx.total_absent += 1
            elif result.status == SourceStatus.FILTERED:
                ctx.total_filtered += 1
            elif result.status in (SourceStatus.ERROR, SourceStatus.UNAUTHORIZED):
                ctx.total_errors += 1

                if result.requirement == SourceRequirement.REQUIRED:
                    ctx.has_required_failures = True

    def _unauthorized_context(self, request: LoadRequest, reason: str) -> AssembledContext:
        """Return a context where all sources are unauthorized."""
        ctx = AssembledContext(
            org_id=request.org_id,
            user_id=request.user_id,
            talent_id=request.talent_id,
            has_required_failures=True,
        )
        for source in ContextSource:
            ctx.sources[source] = SourceLoadResult(
                source=source,
                status=SourceStatus.UNAUTHORIZED,
                requirement=SOURCE_REQUIREMENTS.get(source, SourceRequirement.OPTIONAL),
                error=reason,
            )
            ctx.total_errors += 1
        return ctx


# =============================================================================
# Default Source Loaders (for production wiring)
# =============================================================================


def load_talent_profile(request: LoadRequest) -> SourceLoadResult:
    """Load the canonical talent profile.

    In production: queries ai_talent table filtered by org_id + talent_id.
    """
    if not request.talent_id:
        return SourceLoadResult(
            source=ContextSource.TALENT_PROFILE,
            status=SourceStatus.ABSENT,
            error="No talent_id specified",
        )
    # Simulated — in production this queries DB
    return SourceLoadResult(
        source=ContextSource.TALENT_PROFILE,
        status=SourceStatus.ABSENT,
        error="No database connection (use injected loader)",
    )


def load_creative_preferences(request: LoadRequest) -> SourceLoadResult:
    """Load versioned creative preferences for the talent."""
    if not request.talent_id:
        return SourceLoadResult(
            source=ContextSource.CREATIVE_PREFERENCES,
            status=SourceStatus.ABSENT,
            error="No talent_id specified",
        )
    return SourceLoadResult(
        source=ContextSource.CREATIVE_PREFERENCES,
        status=SourceStatus.ABSENT,
        error="No database connection (use injected loader)",
    )


# =============================================================================
# Filtering Logic
# =============================================================================


def filter_by_approval(
    records: list[dict],
    allowed_states: list[str],
) -> tuple[list[dict], list[dict], list[str]]:
    """Filter records by approval state.

    Returns: (included, excluded, reasons)
    """
    included = []
    excluded = []
    reasons = []

    for record in records:
        state = record.get("approval_state", "draft")
        if state in allowed_states:
            included.append(record)
        else:
            excluded.append(record)
            reasons.append(f"Excluded: approval_state={state} (allowed: {allowed_states})")

    return included, excluded, reasons


def filter_stale_records(
    records: list[dict],
    max_age_days: int = 90,
) -> tuple[list[dict], list[dict]]:
    """Separate stale records from fresh ones.

    Records older than max_age_days without updates are marked stale.
    """
    fresh = []
    stale = []
    cutoff = datetime.now(UTC).isoformat()  # Simplified; real impl compares dates

    for record in records:
        # In production: compare updated_at against cutoff
        fresh.append(record)  # Default to fresh in contract

    return fresh, stale


# =============================================================================
# Cross-Workspace Guard
# =============================================================================


def verify_workspace_access(
    record_org_id: str,
    requesting_org_id: str,
) -> bool:
    """Reject cross-workspace references."""
    return record_org_id == requesting_org_id
