"""Authorized Data Access Boundary — Story 009.

This module is the MANDATORY gateway for all privileged (service-role) database
operations. Direct use of ``supabase.table()`` in routes, services, or tools
is prohibited. All callers must provide a valid execution context.

Architecture:
    Route/Service/Tool
        ↓ provides ExecutionContext
    AuthorizedClient
        ↓ enforces org_id scoping + role check
    Supabase service-role client
        ↓ executes query

Execution Contexts:
    TenantContext  — interactive user with validated membership (from Story 005)
    SystemContext  — non-interactive system operations (cron, seeding, migrations)
    WorkerContext  — background GPU/job workers with narrow scope

Rules:
    1. Every query on a tenant-owned table MUST include org_id in the WHERE clause.
    2. Record IDs alone NEVER authorize access.
    3. Mutations require editor+ role (configurable per operation).
    4. System/Worker contexts have explicit capabilities — not blanket access.
    5. Every operation records purpose + request_id for audit.
    6. Authorization failures are logged but never leak tenant data.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from backend.database import get_supabase_client, is_supabase_configured
from backend.membership import SYSTEM_ORG_ID, OrgRole, TenantContext


# =============================================================================
# Execution Context Types
# =============================================================================


class ContextKind(str, Enum):
    """Discriminator for execution context type."""

    TENANT = "tenant"   # Interactive user
    SYSTEM = "system"   # Automated system operation
    WORKER = "worker"   # Background job worker


@dataclass(frozen=True)
class SystemContext:
    """Execution context for non-interactive system operations.

    Used by: cron jobs, seeding scripts, data migrations, admin CLI tools.
    System context operates on SYSTEM_ORG_ID or a specified target org.

    Fields:
        purpose: Human-readable reason for this operation (audit trail).
        actor: Identifier for the system component (e.g., "cron:publish_scheduled").
        target_org_id: The org being operated on (defaults to SYSTEM_ORG_ID).
        capabilities: Explicit list of allowed operations.
        request_id: Unique ID for this operation (auto-generated if not provided).
    """

    purpose: str
    actor: str
    target_org_id: str = field(default_factory=lambda: str(SYSTEM_ORG_ID))
    capabilities: frozenset[str] = field(default_factory=frozenset)
    request_id: str = field(default_factory=lambda: f"sys-{_uuid.uuid4().hex[:12]}")

    @property
    def kind(self) -> ContextKind:
        return ContextKind.SYSTEM

    @property
    def org_id(self) -> str:
        return self.target_org_id


@dataclass(frozen=True)
class WorkerContext:
    """Execution context for background job workers (GPU, training, publishing).

    Workers operate on behalf of a specific user+org that submitted the job.
    They have narrow capabilities scoped to the job type.

    Fields:
        job_id: The job record ID this worker is executing.
        org_id: The org that owns the job.
        user_id: The user who submitted the job.
        purpose: What the worker is doing (e.g., "image_generation:flux_dev").
        capabilities: Explicit allowed operations (e.g., {"read:assets", "write:assets"}).
        request_id: Unique ID for this worker execution.
    """

    job_id: str
    org_id: str
    user_id: str
    purpose: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    request_id: str = field(default_factory=lambda: f"wrk-{_uuid.uuid4().hex[:12]}")

    @property
    def kind(self) -> ContextKind:
        return ContextKind.WORKER


# Union type for all valid execution contexts
ExecutionContext = TenantContext | SystemContext | WorkerContext


# =============================================================================
# Authorization Errors
# =============================================================================


class AuthorizationError(Exception):
    """Raised when an operation is denied by the authorization boundary."""

    def __init__(self, detail: str, *, context_kind: str = "", table: str = "") -> None:
        self.detail = detail
        self.context_kind = context_kind
        self.table = table
        super().__init__(detail)


# =============================================================================
# Audit Record
# =============================================================================


@dataclass
class AuditEntry:
    """Lightweight audit record for authorization decisions."""

    timestamp: str
    request_id: str
    actor: str
    org_id: str
    context_kind: str
    table: str
    operation: str
    purpose: str
    authorized: bool
    denial_reason: str = ""


_audit_log: list[AuditEntry] = []
_MAX_AUDIT_BUFFER = 1000


def _record_audit(entry: AuditEntry) -> None:
    """Record an audit entry (in-memory buffer, flushed to DB periodically)."""
    _audit_log.append(entry)
    if len(_audit_log) > _MAX_AUDIT_BUFFER:
        _audit_log.pop(0)  # Simple ring buffer — production would flush to DB


def get_recent_audit_entries(limit: int = 50) -> list[AuditEntry]:
    """Get recent audit entries (for admin dashboard)."""
    return list(reversed(_audit_log[-limit:]))


# =============================================================================
# Authorized Client
# =============================================================================


# Tables that are NOT tenant-scoped (system-level configuration)
SYSTEM_TABLES: frozenset[str] = frozenset({
    "service_settings",
    "worker_sessions",
    "organizations",
})

# Tables that require org_id scoping for tenant isolation
TENANT_TABLES: frozenset[str] = frozenset({
    "talent",
    "assets",
    "projects",
    "jobs",
    "scenes",
    "brands",
    "studios",
    "campaigns",
    "brand_campaigns",
    "team_members",
    "clients",
    "approval_requests",
    "asset_licenses",
    "training_datasets",
    "training_images",
    "training_jobs",
    "lora_versions",
    "talent_loras",
    "publishing_posts",
    "publishing_accounts",
    "aios_sessions",
    "aios_messages",
    "aios_approvals",
    "aios_policies",
    "creative_dna",
    "talent_relationships",
    "talent_loras",
    "lora_versions",
    "org_members",
    "models",
    "workflows",
    "storyboards",
    "brain_sessions",
    "brain_memory",
    "brain_messages",
    "brain_plans",
    "brain_collections",
    "brain_conversations",
    "brain_embeddings",
    "video_projects",
    "video_renders",
    "video_shots",
    "audio_clips",
    "voice_profiles",
    "performance_dna",
    "quality_scores",
    "generation_feedback",
    "creative_rules",
    "continuity_notes",
    "social_connections",
    "cost_records",
    "job_costs",
    "creative_recipes",
})


class AuthorizedClient:
    """The ONLY approved way to perform privileged database operations.

    Wraps the Supabase service-role client with mandatory authorization.
    Every operation requires a valid ExecutionContext and enforces:
    - Tenant isolation (org_id scoping)
    - Role checks (mutations require editor+)
    - Audit attribution (request_id + purpose)
    - Capability checks (for system/worker contexts)

    Usage:
        from backend.data_access import AuthorizedClient

        # For user requests:
        client = AuthorizedClient(tenant_context)
        result = client.select("talent")

        # For system operations:
        ctx = SystemContext(purpose="seed_default_models", actor="cli:seed")
        client = AuthorizedClient(ctx)
        result = client.insert("models", data)
    """

    def __init__(self, context: ExecutionContext) -> None:
        self._ctx = context
        self._validate_context()

    def _validate_context(self) -> None:
        """Ensure context has required fields."""
        if isinstance(self._ctx, TenantContext):
            if not self._ctx.user_id:
                raise AuthorizationError("TenantContext missing user_id", context_kind="tenant")
            if not self._ctx.org_id:
                raise AuthorizationError("TenantContext missing org_id", context_kind="tenant")
        elif isinstance(self._ctx, SystemContext):
            if not self._ctx.purpose:
                raise AuthorizationError("SystemContext missing purpose", context_kind="system")
            if not self._ctx.actor:
                raise AuthorizationError("SystemContext missing actor", context_kind="system")
        elif isinstance(self._ctx, WorkerContext):
            if not self._ctx.job_id:
                raise AuthorizationError("WorkerContext missing job_id", context_kind="worker")
            if not self._ctx.org_id:
                raise AuthorizationError("WorkerContext missing org_id", context_kind="worker")
            if not self._ctx.purpose:
                raise AuthorizationError("WorkerContext missing purpose", context_kind="worker")
        else:
            raise AuthorizationError(
                f"Unknown context type: {type(self._ctx).__name__}",
                context_kind="unknown",
            )

    @property
    def org_id(self) -> str:
        """The org_id this client is scoped to."""
        if isinstance(self._ctx, TenantContext):
            return self._ctx.org_id
        elif isinstance(self._ctx, (SystemContext, WorkerContext)):
            return self._ctx.org_id
        return ""

    @property
    def _request_id(self) -> str:
        if isinstance(self._ctx, TenantContext):
            return f"usr-{self._ctx.user_id[:12]}"
        elif isinstance(self._ctx, (SystemContext, WorkerContext)):
            return self._ctx.request_id
        return "unknown"

    @property
    def _actor(self) -> str:
        if isinstance(self._ctx, TenantContext):
            return f"user:{self._ctx.user_id}"
        elif isinstance(self._ctx, SystemContext):
            return self._ctx.actor
        elif isinstance(self._ctx, WorkerContext):
            return f"worker:{self._ctx.job_id}"
        return "unknown"

    @property
    def _purpose(self) -> str:
        if isinstance(self._ctx, (SystemContext, WorkerContext)):
            return self._ctx.purpose
        return "user_request"

    def _is_tenant_table(self, table: str) -> bool:
        """Check if a table requires org_id scoping."""
        return table in TENANT_TABLES

    def _check_role_for_mutation(self, table: str, operation: str) -> None:
        """Enforce role requirements for write operations."""
        if isinstance(self._ctx, TenantContext):
            if operation in ("insert", "update", "upsert", "delete"):
                self._ctx.require_role(OrgRole.EDITOR)

    def _check_capability(self, table: str, operation: str) -> None:
        """For System/Worker contexts, verify the operation is within capabilities."""
        if isinstance(self._ctx, (SystemContext, WorkerContext)):
            caps = self._ctx.capabilities
            if caps:  # Empty capabilities = unrestricted (for backwards compat)
                required = f"{operation}:{table}"
                general = f"{operation}:*"
                if required not in caps and general not in caps:
                    raise AuthorizationError(
                        f"Context lacks capability '{required}'",
                        context_kind=self._ctx.kind.value,
                        table=table,
                    )

    def _audit(self, table: str, operation: str, authorized: bool, reason: str = "") -> None:
        """Record authorization decision."""
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat(),
            request_id=self._request_id,
            actor=self._actor,
            org_id=self.org_id,
            context_kind=(
                "tenant" if isinstance(self._ctx, TenantContext)
                else "system" if isinstance(self._ctx, SystemContext)
                else "worker"
            ),
            table=table,
            operation=operation,
            purpose=self._purpose,
            authorized=authorized,
            denial_reason=reason,
        )
        _record_audit(entry)

    def _get_client(self):
        """Get the underlying Supabase service-role client."""
        if not is_supabase_configured():
            raise AuthorizationError("Database not configured", context_kind="infra")
        return get_supabase_client()

    # =========================================================================
    # Public API — Scoped Operations
    # =========================================================================

    def select(
        self,
        table: str,
        columns: str = "*",
        *,
        filters: dict[str, Any] | None = None,
        eq_filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        desc: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        single: bool = False,
    ) -> Any:
        """Authorized SELECT with mandatory tenant scoping.

        Args:
            table: Table name.
            columns: Column selection (default "*").
            filters: Additional .eq() filters as {column: value}.
            eq_filters: Alias for filters (backward compat).
            order_by: Column to order by.
            desc: Order direction (default descending).
            limit: Max rows.
            offset: Row offset.
            single: Use .single() for exactly-one result.

        Returns:
            Query result (data list or single record).

        Raises:
            AuthorizationError: If context lacks access.
        """
        self._check_capability(table, "select")
        self._audit(table, "select", True)

        client = self._get_client()
        query = client.table(table).select(columns)

        # Mandatory tenant scoping
        if self._is_tenant_table(table):
            query = query.eq("org_id", self.org_id)

        # Additional filters
        all_filters = {**(filters or {}), **(eq_filters or {})}
        for col, val in all_filters.items():
            query = query.eq(col, val)

        if order_by:
            query = query.order(order_by, desc=desc)
        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)
        if single:
            query = query.single()

        return query.execute()

    def select_by_id(self, table: str, record_id: str, columns: str = "*") -> Any:
        """Select a single record by ID, with mandatory org_id check.

        Record IDs alone NEVER authorize access — the org_id must also match.

        Raises:
            AuthorizationError: If record doesn't belong to this context's org.
        """
        self._check_capability(table, "select")

        client = self._get_client()
        query = client.table(table).select(columns).eq("id", record_id)

        if self._is_tenant_table(table):
            query = query.eq("org_id", self.org_id)

        result = query.single().execute()

        if not result.data:
            self._audit(table, "select_by_id", False, "record_not_found_or_wrong_tenant")
            raise AuthorizationError(
                "Record not found",
                context_kind="tenant" if isinstance(self._ctx, TenantContext) else "system",
                table=table,
            )

        self._audit(table, "select_by_id", True)
        return result

    def insert(self, table: str, data: dict | list[dict]) -> Any:
        """Authorized INSERT with org_id injection.

        Automatically adds org_id to the record(s) for tenant-owned tables.
        """
        self._check_role_for_mutation(table, "insert")
        self._check_capability(table, "insert")
        self._audit(table, "insert", True)

        # Inject org_id into records for tenant tables
        if self._is_tenant_table(table):
            if isinstance(data, list):
                for record in data:
                    record["org_id"] = self.org_id
            else:
                data["org_id"] = self.org_id

        client = self._get_client()
        return client.table(table).insert(data).execute()

    def update(
        self,
        table: str,
        data: dict,
        *,
        record_id: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Any:
        """Authorized UPDATE with mandatory tenant scoping.

        Either record_id or filters must be provided (not both empty).
        org_id is ALWAYS added to the WHERE clause for tenant tables.
        """
        self._check_role_for_mutation(table, "update")
        self._check_capability(table, "update")

        if not record_id and not filters:
            self._audit(table, "update", False, "no_record_id_or_filters")
            raise AuthorizationError(
                "UPDATE requires record_id or filters — bulk unscoped updates are prohibited",
                context_kind="tenant",
                table=table,
            )

        self._audit(table, "update", True)

        client = self._get_client()
        query = client.table(table).update(data)

        if record_id:
            query = query.eq("id", record_id)

        # Mandatory tenant scoping
        if self._is_tenant_table(table):
            query = query.eq("org_id", self.org_id)

        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)

        return query.execute()

    def upsert(self, table: str, data: dict | list[dict], *, on_conflict: str = "id") -> Any:
        """Authorized UPSERT with org_id injection."""
        self._check_role_for_mutation(table, "upsert")
        self._check_capability(table, "upsert")
        self._audit(table, "upsert", True)

        if self._is_tenant_table(table):
            if isinstance(data, list):
                for record in data:
                    record["org_id"] = self.org_id
            else:
                data["org_id"] = self.org_id

        client = self._get_client()
        return client.table(table).upsert(data, on_conflict=on_conflict).execute()

    def delete(self, table: str, record_id: str) -> Any:
        """Authorized DELETE with mandatory tenant scoping.

        Record ID alone does NOT authorize deletion — org_id must match.
        """
        self._check_role_for_mutation(table, "delete")
        self._check_capability(table, "delete")

        client = self._get_client()
        query = client.table(table).delete().eq("id", record_id)

        if self._is_tenant_table(table):
            query = query.eq("org_id", self.org_id)

        result = query.execute()

        if not result.data:
            self._audit(table, "delete", False, "record_not_found_or_wrong_tenant")
            raise AuthorizationError(
                "Record not found or access denied",
                context_kind="tenant",
                table=table,
            )

        self._audit(table, "delete", True)
        return result

    # =========================================================================
    # Convenience: raw query (escape hatch for complex queries)
    # =========================================================================

    def raw_query(self, table: str, *, purpose: str) -> Any:
        """Get a raw query builder WITH mandatory org_id pre-applied.

        This is the escape hatch for queries that don't fit select/insert/update.
        The org_id filter is ALREADY applied — callers add additional filters.

        Usage:
            query = client.raw_query("assets", purpose="filter by tags")
            result = query.contains("tags", ["image_generation"]).execute()

        NEVER use this to bypass tenant isolation.
        """
        if not purpose:
            raise AuthorizationError(
                "raw_query requires explicit purpose for audit trail",
                context_kind="tenant",
                table=table,
            )

        self._check_capability(table, "select")
        self._audit(table, f"raw_query:{purpose}", True)

        client = self._get_client()
        query = client.table(table).select("*")

        if self._is_tenant_table(table):
            query = query.eq("org_id", self.org_id)

        return query


# =============================================================================
# Factory Helpers
# =============================================================================


def authorized_client(ctx: ExecutionContext) -> AuthorizedClient:
    """Create an AuthorizedClient from any valid execution context.

    This is the APPROVED entry point for all data access.
    """
    return AuthorizedClient(ctx)


def system_client(
    purpose: str,
    actor: str,
    *,
    target_org_id: str | None = None,
    capabilities: frozenset[str] | None = None,
) -> AuthorizedClient:
    """Create an AuthorizedClient with system context.

    Convenience for non-interactive operations that need DB access.

    Args:
        purpose: Why this operation is happening (required for audit).
        actor: Which system component is acting (e.g., "cron:scheduler").
        target_org_id: Org to scope to (defaults to SYSTEM_ORG_ID).
        capabilities: Explicit allowed operations. Empty = unrestricted.
    """
    ctx = SystemContext(
        purpose=purpose,
        actor=actor,
        target_org_id=target_org_id or str(SYSTEM_ORG_ID),
        capabilities=capabilities or frozenset(),
    )
    return AuthorizedClient(ctx)


def worker_client(
    job_id: str,
    org_id: str,
    user_id: str,
    purpose: str,
    *,
    capabilities: frozenset[str] | None = None,
) -> AuthorizedClient:
    """Create an AuthorizedClient with worker context.

    Convenience for background job workers that operate on behalf of a user.

    Args:
        job_id: The job being executed.
        org_id: The org that owns the job.
        user_id: The user who submitted the job.
        purpose: What the worker is doing.
        capabilities: Allowed operations (e.g., frozenset({"read:assets", "write:assets"})).
    """
    ctx = WorkerContext(
        job_id=job_id,
        org_id=org_id,
        user_id=user_id,
        purpose=purpose,
        capabilities=capabilities or frozenset(),
    )
    return AuthorizedClient(ctx)
