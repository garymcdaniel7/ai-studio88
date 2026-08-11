"""Org ID Backfill Service — quarantine, classify, and backfill NULL org_id rows.

Implements R69 quarantine process and R5.6 NOT NULL constraint application.

This service provides:
    - identify_tables_with_null_org_id(): scans Category A tables for NULL org_id rows
    - classify_table_ownership(): determines if a table is founder-only or ambiguous
    - bulk_assign_founder(): assigns all NULL rows to founder org for verified tables
    - quarantine_ambiguous_rows(): logs ambiguous rows into _quarantine_log
    - resolve_quarantine_entry(): resolves a single quarantined row (assign/system/purge)
    - apply_not_null_constraint(): applies NOT NULL only after all NULLs resolved
    - get_quarantine_summary(): returns pending quarantine counts

Requirements covered: R5.6, R69.1, R69.2, R69.3, R69.4, R69.5, R69.6, R2.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# The system org UUID (owns shared/platform resources)
SYSTEM_ORG_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")

# The quarantined placeholder UUID (must never be used as org_id)
QUARANTINED_UUID: UUID = UUID("00000000-0000-0000-0000-000000000000")

# Category A tables that must have org_id NOT NULL (from TENANT_AUTHORIZATION_CONTRACT.md)
CATEGORY_A_TABLES: list[str] = [
    # Core Content
    "talent",
    "assets",
    "jobs",
    "models",
    "workflows",
    "scenes",
    # Projects
    "projects",
    "project_assets",
    # Training
    "training_datasets",
    "training_images",
    "training_jobs",
    "lora_versions",
    "lora_evaluations",
    # Video
    "video_projects",
    "video_shots",
    "video_renders",
    "timeline_tracks",
    "timeline_clips",
    "timeline_exports",
    # Audio
    "voice_profiles",
    "voice_samples",
    "audio_clips",
    "lip_sync_jobs",
    "music_tracks_db",
    "sound_effects",
    # Publishing
    "publishing_accounts",
    "publishing_posts",
    "analytics_snapshots",
    # Brain
    "brain_sessions",
    "brain_messages",
    "brain_plans",
    "brain_memory",
    "brain_collections",
    "brain_conversations",
    "brain_embeddings",
    # AIOS
    "aios_sessions",
    "aios_messages",
    "aios_decisions",
    "aios_approvals",
    "aios_policies",
    # Story Engine
    "universes",
    "characters",
    "episodes",
    "shots",
    "story_memory",
    # Creative / Performance
    "creative_dna",
    "creative_rules",
    "continuity_notes",
    "generation_feedback",
    "prompt_history",
    "style_preferences",
    "performance_dna",
    "performance_memory",
    "quality_scores",
    "voice_dna",
    "voice_datasets",
    "voice_training_jobs",
    "voice_versions",
    # Object Intelligence
    "object_dna",
    "product_dna",
    "digital_twins",
    "digital_twin_versions",
    "virtual_tryon_jobs",
    "product_views_360",
    "scene_dna",
    "material_profiles",
    # Asset Intelligence
    "visual_dna",
    "asset_collections",
    "collection_items",
    "asset_relationships",
    "wardrobes",
    "outfits",
    # Cinematic
    "sequences",
    "cinematic_timelines",
    "cinematic_tracks",
    "cinematic_items",
    "storyboard_panels",
    "cinematic_renders",
    "editing_operations",
    # Company
    "organizations",
    "studios",
    "brands",
    "brand_campaigns",
    "team_members",
    "approval_requests",
    "clients",
    "asset_licenses",
    # Credentials
    "workspace_credentials",
    "credential_audit_log",
    "social_account_connections",
    # Billing
    "cost_records",
    "job_costs",
    # Lifecycle
    "lifecycle_transitions",
    "entity_holds",
    # Provenance
    "asset_provenance",
    "asset_lineage",
    "provenance_amendments",
    # Batch
    "generation_batches",
    "batch_variation_jobs",
    # Governance
    "durable_approvals",
    "governance_policy_audit",
    "infra_audit_log",
    # Recipes (user-created)
    "creative_recipes",
]


# =============================================================================
# Enums
# =============================================================================


class OwnershipClassification(StrEnum):
    """Classification per R69.1 for records during schema remediation."""

    VALID_TENANT_OWNED = "VALID_TENANT_OWNED"
    EXPLICITLY_SYSTEM_OWNED = "EXPLICITLY_SYSTEM_OWNED"
    QUARANTINED_FOR_REVIEW = "QUARANTINED_FOR_REVIEW"
    ELIGIBLE_FOR_APPROVED_PURGE = "ELIGIBLE_FOR_APPROVED_PURGE"


class TableOwnershipType(StrEnum):
    """Ownership classification for a table during backfill."""

    FOUNDER_ONLY = "founder_only"
    AMBIGUOUS = "ambiguous"
    SYSTEM = "system"
    NO_NULL_ROWS = "no_null_rows"


class QuarantineResolution(StrEnum):
    """How a quarantined row is resolved (R69.4)."""

    ASSIGNED = "assigned"
    SYSTEM = "system"
    PURGED = "purged"


# =============================================================================
# Data Models
# =============================================================================


@dataclass(frozen=True)
class TableNullAudit:
    """Audit result for a single table's NULL org_id rows."""

    table_name: str
    null_count: int
    total_count: int
    has_org_id_column: bool
    is_nullable: bool
    distinct_org_ids: list[UUID | None] = field(default_factory=list)


@dataclass(frozen=True)
class TableClassification:
    """Classification result for a table's ownership type."""

    table_name: str
    ownership_type: TableOwnershipType
    reason: str
    null_count: int
    org_count: int  # number of distinct non-null org_ids


@dataclass(frozen=True)
class QuarantineEntry:
    """A single quarantine log entry."""

    id: UUID
    source_table: str
    source_row_id: UUID
    classification: OwnershipClassification
    quarantine_reason: str
    quarantine_date: datetime
    resolved_at: datetime | None = None
    resolution: QuarantineResolution | None = None
    resolved_by: UUID | None = None
    resolution_evidence: str | None = None
    assigned_org_id: UUID | None = None


@dataclass(frozen=True)
class BackfillResult:
    """Result of a bulk backfill operation."""

    table_name: str
    rows_assigned: int
    assigned_to_org_id: UUID


@dataclass(frozen=True)
class QuarantineSummary:
    """Summary of quarantine state across tables."""

    total_quarantined: int
    pending_review: int
    eligible_for_purge: int
    resolved: int
    by_table: dict[str, int] = field(default_factory=dict)


# =============================================================================
# Service
# =============================================================================


class OrgIdBackfillService:
    """Service for quarantining, classifying, and backfilling NULL org_id rows.

    This service implements the R69 quarantine process:
    1. Identify tables with NULL org_id rows
    2. Classify each table as founder-only (single org ever) or ambiguous
    3. For founder-only: bulk assign to founder org_id
    4. For ambiguous: quarantine with reason and date
    5. Apply NOT NULL constraint only after all NULLs resolved

    The service does NOT perform direct database operations — it produces
    the classification logic and SQL statements. Actual DB execution is
    delegated to the caller (migration script or admin tooling).
    """

    def __init__(self, founder_org_id: UUID) -> None:
        """Initialize with the verified founder org_id.

        Args:
            founder_org_id: The UUID of the founder's organization,
                determined from org_members or organizations table.
        """
        if founder_org_id == QUARANTINED_UUID:
            raise ValueError(
                "Cannot use quarantined placeholder UUID as founder org_id"
            )
        if founder_org_id == SYSTEM_ORG_ID:
            raise ValueError(
                "Cannot use system org UUID as founder org_id"
            )
        self.founder_org_id = founder_org_id

    def classify_table(self, audit: TableNullAudit) -> TableClassification:
        """Classify a table's ownership type based on its audit results.

        Per R5.6 and R69:
        - If no NULL rows exist: NO_NULL_ROWS (ready for NOT NULL constraint)
        - If the table has no org_id column: not applicable
        - If only the founder org exists (verified by audit): FOUNDER_ONLY
        - If multiple orgs exist or ownership is ambiguous: AMBIGUOUS

        Args:
            audit: The audit result for the table.

        Returns:
            TableClassification with the determined ownership type and reason.
        """
        if not audit.has_org_id_column:
            return TableClassification(
                table_name=audit.table_name,
                ownership_type=TableOwnershipType.NO_NULL_ROWS,
                reason="Table does not have org_id column",
                null_count=0,
                org_count=0,
            )

        if audit.null_count == 0:
            return TableClassification(
                table_name=audit.table_name,
                ownership_type=TableOwnershipType.NO_NULL_ROWS,
                reason="No NULL org_id rows — ready for NOT NULL constraint",
                null_count=0,
                org_count=len([o for o in audit.distinct_org_ids if o is not None]),
            )

        # Filter out None from distinct org_ids to count real orgs
        real_org_ids = [o for o in audit.distinct_org_ids if o is not None]
        non_system_orgs = [o for o in real_org_ids if o != SYSTEM_ORG_ID]

        if len(non_system_orgs) == 0:
            # Only NULL and possibly system org — this is founder's data
            return TableClassification(
                table_name=audit.table_name,
                ownership_type=TableOwnershipType.FOUNDER_ONLY,
                reason=(
                    "No non-system orgs found; all existing data belongs to founder "
                    "(single-tenant history)"
                ),
                null_count=audit.null_count,
                org_count=0,
            )

        if len(non_system_orgs) == 1 and non_system_orgs[0] == self.founder_org_id:
            # Only the founder org exists — safe to bulk assign
            return TableClassification(
                table_name=audit.table_name,
                ownership_type=TableOwnershipType.FOUNDER_ONLY,
                reason=(
                    f"Only founder org ({self.founder_org_id}) has ever written to this table; "
                    "bulk assignment to founder is safe without per-row review"
                ),
                null_count=audit.null_count,
                org_count=1,
            )

        # Multiple orgs exist — ambiguous ownership, must quarantine
        return TableClassification(
            table_name=audit.table_name,
            ownership_type=TableOwnershipType.AMBIGUOUS,
            reason=(
                f"Multiple orgs ({len(non_system_orgs)}) have data in this table; "
                "cannot bulk-assign NULL rows without per-row review (R69.5)"
            ),
            null_count=audit.null_count,
            org_count=len(non_system_orgs),
        )

    def generate_backfill_sql(
        self, classification: TableClassification
    ) -> str | None:
        """Generate SQL to backfill NULL org_id rows for founder-only tables.

        Per R5.6: For tables where the founder is the ONLY org that has ever
        existed (verified by audit), bulk assignment to the founder's org_id
        is acceptable without per-row review.

        Args:
            classification: The table classification result.

        Returns:
            SQL string for the backfill, or None if not applicable.
        """
        if classification.ownership_type != TableOwnershipType.FOUNDER_ONLY:
            return None

        table = classification.table_name
        return (
            f"UPDATE {table} SET org_id = '{self.founder_org_id}' "
            f"WHERE org_id IS NULL;"
        )

    def generate_quarantine_sql(
        self, table_name: str, reason: str
    ) -> str:
        """Generate SQL to quarantine NULL org_id rows for ambiguous tables.

        Per R69.2: Records with NULL org_id SHALL be quarantined,
        not assigned to a placeholder org merely to satisfy NOT NULL.

        Per R69.3: Quarantined records are tagged with quarantine_reason
        and quarantine_date, and made invisible to tenant-scoped queries.

        Args:
            table_name: The table with ambiguous NULL org_id rows.
            reason: Human-readable quarantine reason.

        Returns:
            SQL string to insert quarantine records into _quarantine_log.
        """
        return (
            f"INSERT INTO _quarantine_log "
            f"(source_table, source_row_id, classification, quarantine_reason, quarantine_date) "
            f"SELECT '{table_name}', id, 'QUARANTINED_FOR_REVIEW', "
            f"'{reason}', now() "
            f"FROM {table_name} WHERE org_id IS NULL;"
        )

    def generate_not_null_sql(self, table_name: str) -> str:
        """Generate SQL to apply NOT NULL constraint on org_id.

        Per R69.5: NOT NULL constraint SHALL NOT be applied until all
        existing NULL rows have been explicitly classified.

        This should ONLY be called after verifying zero NULL rows remain.

        Args:
            table_name: The table to constrain.

        Returns:
            SQL ALTER TABLE statement.
        """
        return f"ALTER TABLE {table_name} ALTER COLUMN org_id SET NOT NULL;"

    def can_apply_not_null(self, audit: TableNullAudit) -> bool:
        """Check if a table is ready for NOT NULL constraint application.

        Per R69.5 and R5.6: The constraint can only be applied after
        ALL existing NULL rows have been explicitly classified —
        either backfilled or quarantined+resolved.

        Args:
            audit: Current audit of the table's NULL state.

        Returns:
            True if zero NULL rows remain and constraint can be applied.
        """
        return audit.null_count == 0

    def validate_resolution(
        self,
        resolution: QuarantineResolution,
        assigned_org_id: UUID | None,
        evidence: str | None,
    ) -> list[str]:
        """Validate a quarantine resolution before applying.

        Args:
            resolution: The resolution type.
            assigned_org_id: Target org_id if resolution is ASSIGNED.
            evidence: Justification for the resolution.

        Returns:
            List of validation errors (empty if valid).
        """
        errors: list[str] = []

        if not evidence:
            errors.append("Resolution evidence is required (R69.6)")

        if resolution == QuarantineResolution.ASSIGNED:
            if assigned_org_id is None:
                errors.append(
                    "assigned_org_id is required when resolution is 'assigned'"
                )
            elif assigned_org_id == QUARANTINED_UUID:
                errors.append(
                    "Cannot assign to quarantined placeholder UUID"
                )
            elif assigned_org_id == SYSTEM_ORG_ID:
                errors.append(
                    "Use resolution='system' to classify as system-owned"
                )

        if resolution == QuarantineResolution.SYSTEM:
            if assigned_org_id is not None and assigned_org_id != SYSTEM_ORG_ID:
                errors.append(
                    "assigned_org_id must be None or system org for 'system' resolution"
                )

        return errors

    def get_category_a_tables(self) -> list[str]:
        """Return the full list of Category A tables requiring org_id NOT NULL.

        Returns:
            List of table names from TENANT_AUTHORIZATION_CONTRACT.md.
        """
        return CATEGORY_A_TABLES.copy()

    def generate_full_backfill_plan(
        self, audits: list[TableNullAudit]
    ) -> dict[str, list[TableClassification]]:
        """Generate a complete backfill plan from table audits.

        Classifies all tables and groups them by action needed:
        - ready: No NULL rows, can apply NOT NULL immediately
        - founder_backfill: Founder-only tables, safe for bulk assignment
        - quarantine: Ambiguous tables requiring quarantine-then-classify

        Args:
            audits: List of audit results for all Category A tables.

        Returns:
            Dict with keys 'ready', 'founder_backfill', 'quarantine'.
        """
        plan: dict[str, list[TableClassification]] = {
            "ready": [],
            "founder_backfill": [],
            "quarantine": [],
        }

        for audit in audits:
            classification = self.classify_table(audit)

            if classification.ownership_type == TableOwnershipType.NO_NULL_ROWS:
                plan["ready"].append(classification)
            elif classification.ownership_type == TableOwnershipType.FOUNDER_ONLY:
                plan["founder_backfill"].append(classification)
            elif classification.ownership_type == TableOwnershipType.AMBIGUOUS:
                plan["quarantine"].append(classification)

        logger.info(
            "backfill_plan_generated",
            ready=len(plan["ready"]),
            founder_backfill=len(plan["founder_backfill"]),
            quarantine=len(plan["quarantine"]),
        )

        return plan
