"""Idempotent Workspace Provisioning Service.

Handles workspace creation for new users (signup or OAuth first-login).
Uses INSERT...ON CONFLICT DO NOTHING to ensure idempotency — retries
(network failure, browser back) never create duplicate organizations,
memberships, or onboarding records.

This service is called by the Auth Gateway when a newly authenticated
user has no org_members record and is eligible for provisioning.

Requirements covered: R1.6, R1.11, R84.4, R84.5
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from app.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# System org — never used for user workspace provisioning
SYSTEM_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")

# Default workspace name derived from email
DEFAULT_WORKSPACE_SLUG_MAX_LENGTH = 50


# =============================================================================
# Exceptions
# =============================================================================


class ProvisioningError(Exception):
    """Raised when workspace provisioning fails."""

    def __init__(self, message: str, user_id: str | None = None) -> None:
        self.message = message
        self.user_id = user_id
        super().__init__(message)


# =============================================================================
# Data Structures
# =============================================================================


@dataclass(frozen=True)
class ProvisioningResult:
    """Result of a workspace provisioning operation.

    Attributes:
        tenant_context: The resolved TenantContext for the provisioned user.
        created: True if a new workspace was created, False if existing.
        org_id: The organization ID (new or existing).
        org_name: The organization display name.
    """

    tenant_context: TenantContext
    created: bool
    org_id: UUID
    org_name: str


# =============================================================================
# Provisioning Service
# =============================================================================


class ProvisioningService:
    """Handles idempotent workspace creation for new users.

    Uses INSERT...ON CONFLICT DO NOTHING for org + membership creation.
    Retries (network failure, browser back) do NOT create duplicates.
    OAuth users do NOT need a separate AI Studio password.
    Returns existing workspace if already provisioned.
    """

    def __init__(self, supabase_client: object | None = None) -> None:
        """Initialize with an optional Supabase client.

        Args:
            supabase_client: A Supabase client instance. If None, will be
                resolved lazily via get_supabase_client().
        """
        self._client = supabase_client

    @property
    def client(self) -> object:
        """Lazily resolve the Supabase client."""
        if self._client is None:
            from backend.database import get_supabase_client

            self._client = get_supabase_client()
        return self._client

    async def provision_workspace(
        self, user_id: UUID, email: str
    ) -> ProvisioningResult:
        """Create a workspace idempotently for a new user.

        This method is safe to call multiple times for the same user.
        Subsequent calls return the existing workspace without creating
        duplicates, thanks to INSERT...ON CONFLICT DO NOTHING semantics.

        Flow:
            1. Check if user already has an active org_members record
            2. If yes, return existing workspace (idempotent)
            3. If no, create organization + membership + onboarding_state
            4. Use ON CONFLICT DO NOTHING to handle race conditions

        Args:
            user_id: Supabase auth user UUID (from JWT 'sub' claim).
            email: User's email address (from JWT or auth provider).

        Returns:
            ProvisioningResult with TenantContext and creation status.

        Raises:
            ProvisioningError: If provisioning fails due to DB errors.
        """
        return self.provision_workspace_sync(user_id, email)

    def provision_workspace_sync(
        self, user_id: UUID, email: str
    ) -> ProvisioningResult:
        """Synchronous entry point for workspace provisioning.

        Used by the auth path (FastAPI sync dependencies) where an async
        call is not possible. Internals are synchronous Supabase calls,
        so the async `provision_workspace` simply delegates here.
        """
        logger.info(
            "provisioning_workspace_start",
            user_id=str(user_id),
            email_domain=email.split("@")[-1] if "@" in email else "unknown",
        )

        # Step 1: Check for existing membership (idempotent return)
        existing = self._get_existing_membership(user_id)
        if existing:
            logger.info(
                "provisioning_existing_workspace",
                user_id=str(user_id),
                org_id=existing["org_id"],
            )
            return ProvisioningResult(
                tenant_context=TenantContext(
                    user_id=user_id,
                    org_id=UUID(existing["org_id"]),
                    role=WorkspaceRole(existing["role"]),
                    trust_domain=TrustDomain.WORKSPACE_ADMIN,
                    email=email,
                ),
                created=False,
                org_id=UUID(existing["org_id"]),
                org_name=existing.get("org_name", ""),
            )

        # Step 2: Create new workspace (org + membership + onboarding)
        try:
            org_id = uuid4()
            org_name = self._derive_org_name(email)
            org_slug = self._derive_org_slug(email, org_id)

            # Create organization with ON CONFLICT DO NOTHING
            self._create_organization(org_id, org_name, org_slug, user_id)

            # Create org_member with ON CONFLICT DO NOTHING
            self._create_membership(org_id, user_id, WorkspaceRole.OWNER)

            # Create onboarding_state with ON CONFLICT DO NOTHING
            self._create_onboarding_state(org_id, user_id)

            logger.info(
                "provisioning_workspace_created",
                user_id=str(user_id),
                org_id=str(org_id),
                org_name=org_name,
            )

            return ProvisioningResult(
                tenant_context=TenantContext(
                    user_id=user_id,
                    org_id=org_id,
                    role=WorkspaceRole.OWNER,
                    trust_domain=TrustDomain.WORKSPACE_ADMIN,
                    email=email,
                ),
                created=True,
                org_id=org_id,
                org_name=org_name,
            )

        except Exception as exc:
            # If creation failed due to a race condition (concurrent request
            # created the workspace between our check and insert), try to
            # return the existing workspace.
            existing = self._get_existing_membership(user_id)
            if existing:
                logger.info(
                    "provisioning_race_condition_resolved",
                    user_id=str(user_id),
                    org_id=existing["org_id"],
                )
                return ProvisioningResult(
                    tenant_context=TenantContext(
                        user_id=user_id,
                        org_id=UUID(existing["org_id"]),
                        role=WorkspaceRole(existing["role"]),
                        trust_domain=TrustDomain.WORKSPACE_ADMIN,
                        email=email,
                    ),
                    created=False,
                    org_id=UUID(existing["org_id"]),
                    org_name=existing.get("org_name", ""),
                )

            logger.error(
                "provisioning_workspace_failed",
                user_id=str(user_id),
                error=str(exc),
            )
            raise ProvisioningError(
                message=f"Failed to provision workspace: {exc}",
                user_id=str(user_id),
            ) from exc

    def is_eligible_for_provisioning(self, user_id: UUID) -> bool:
        """Check if a user is eligible for workspace provisioning.

        A user is eligible if they have NO active org_members record.
        This indicates a new signup or an OAuth first-login.

        Args:
            user_id: Supabase auth user UUID.

        Returns:
            True if user has no org_members record (eligible for provisioning).
        """
        existing = self._get_existing_membership(user_id)
        return existing is None

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _get_existing_membership(self, user_id: UUID) -> dict | None:
        """Query org_members for an active membership for this user.

        Returns the first active membership (excluding system org), or None.
        """
        try:
            result = (
                self.client.table("org_members")
                .select("org_id, role, status")
                .eq("user_id", str(user_id))
                .eq("status", "active")
                .order("created_at", desc=False)
                .execute()
            )

            memberships = result.data or []

            # Filter out system org
            user_memberships = [
                m
                for m in memberships
                if m.get("org_id") != str(SYSTEM_ORG_ID)
            ]

            if not user_memberships:
                return None

            membership = user_memberships[0]

            # Fetch org name for the result
            org_result = (
                self.client.table("organizations")
                .select("name")
                .eq("id", membership["org_id"])
                .execute()
            )
            org_name = ""
            if org_result.data:
                org_name = org_result.data[0].get("name", "")

            return {
                "org_id": membership["org_id"],
                "role": membership["role"],
                "status": membership["status"],
                "org_name": org_name,
            }

        except Exception as exc:
            logger.warning(
                "membership_lookup_failed",
                user_id=str(user_id),
                error=str(exc),
            )
            return None

    def _create_organization(
        self, org_id: UUID, name: str, slug: str, owner_user_id: UUID
    ) -> None:
        """Create an organization record with ON CONFLICT DO NOTHING.

        Uses upsert with ignoreDuplicates=true to handle idempotent retries.
        Column names match the deployed schema: `owner_id` (not
        `owner_user_id`) and no `is_active` column (metadata carries flags).
        """
        self.client.table("organizations").upsert(
            {
                "id": str(org_id),
                "name": name,
                "slug": slug,
                "owner_id": str(owner_user_id),
                "plan": "starter",
                "metadata": {"provisioned": True},
            },
            on_conflict="id",
            ignore_duplicates=True,
        ).execute()

    def _create_membership(
        self, org_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> None:
        """Create an org_member record with ON CONFLICT DO NOTHING.

        The unique constraint on (org_id, user_id) ensures idempotency.
        """
        self.client.table("org_members").upsert(
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "user_id": str(user_id),
                "role": role.value,
                "status": "active",
            },
            on_conflict="org_id,user_id",
            ignore_duplicates=True,
        ).execute()

    def _create_onboarding_state(self, org_id: UUID, user_id: UUID) -> None:
        """Create an onboarding_state record with ON CONFLICT DO NOTHING.

        Tracks the user's onboarding progress within their workspace.

        NOTE: The `onboarding_state` table may not exist in every deployed
        schema (it was not created in the initial migration). Provisioning
        must not fail because of a missing optional table, so this is
        best-effort: failures are logged and swallowed.
        """
        try:
            self.client.table("onboarding_state").upsert(
                {
                    "id": str(uuid4()),
                    "org_id": str(org_id),
                    "user_id": str(user_id),
                    "step": "welcome",
                    "completed": False,
                },
                on_conflict="org_id,user_id",
                ignore_duplicates=True,
            ).execute()
        except Exception as exc:
            logger.warning(
                "onboarding_state_skipped table_missing_or_error=%s",
                exc,
            )

    def _derive_org_name(self, email: str) -> str:
        """Derive a workspace name from the user's email.

        Examples:
            "alice@company.com" → "Alice's Workspace"
            "bob@gmail.com" → "Bob's Workspace"
        """
        if "@" not in email:
            return "My Workspace"

        local_part = email.split("@")[0]
        # Clean up common email patterns
        name = local_part.replace(".", " ").replace("_", " ").replace("-", " ")
        # Capitalize first letter of each word
        name = name.title().strip()

        if not name:
            return "My Workspace"

        return f"{name}'s Workspace"

    def _derive_org_slug(self, email: str, org_id: UUID) -> str:
        """Derive a URL-safe slug from email, with org_id suffix for uniqueness.

        The slug is used in workspace URLs. The org_id suffix (first 8 chars)
        guarantees uniqueness even if multiple users share the same email prefix.
        """
        if "@" not in email:
            return f"workspace-{str(org_id)[:8]}"

        local_part = email.split("@")[0].lower()
        # Replace non-alphanumeric chars with hyphens
        slug = ""
        for char in local_part:
            if char.isalnum():
                slug += char
            elif slug and slug[-1] != "-":
                slug += "-"

        slug = slug.strip("-")

        if not slug:
            slug = "workspace"

        # Append org_id prefix for uniqueness
        slug = f"{slug}-{str(org_id)[:8]}"

        # Enforce max length
        return slug[:DEFAULT_WORKSPACE_SLUG_MAX_LENGTH]
