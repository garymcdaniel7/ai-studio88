"""Connection Permission Service — access control and member departure handling.

Implements the connection permission model:
    - WORKSPACE_CONNECTION: admin/owner to create, remains when members leave
    - USER_CONNECTION: any authenticated member creates, revoked on workspace departure
    - Access governed by allowed_roles + tool_policy
    - Member departure: personal connections revoked, workspace connections stay

Permission layers (A2-013):
    Connection existence ≠ capability ≠ permission.
    A connected service with no explicit permission grants has zero invocable
    capabilities.

Validates: Requirements R85.6, R85.7, R92.4, R92.5, R92.7, R96.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.models.connection import ConnectionLifecycle, ConnectionOwnership

if TYPE_CHECKING:
    from app.models.connection import Connection
    from app.repositories.connection_repository import ConnectionRepository

logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class ConnectionPermissionDenied(Exception):
    """Raised when a user lacks permission to access a connection.

    Attributes:
        message: Human-readable description.
        code: Machine-readable error code.
    """

    def __init__(self, message: str, code: str = "CONNECTION_PERMISSION_DENIED") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ConnectionToolDenied(Exception):
    """Raised when a tool invocation is denied by tool_policy.

    Attributes:
        message: Human-readable description.
        code: Machine-readable error code.
        tool_name: The denied tool.
    """

    def __init__(
        self,
        message: str,
        tool_name: str,
        code: str = "CONNECTION_TOOL_DENIED",
    ) -> None:
        self.message = message
        self.code = code
        self.tool_name = tool_name
        super().__init__(message)


class ConnectionCreationDenied(Exception):
    """Raised when a user lacks permission to create a connection type.

    Attributes:
        message: Human-readable description.
        code: Machine-readable error code.
    """

    def __init__(self, message: str, code: str = "CONNECTION_CREATION_DENIED") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


# =============================================================================
# Result types
# =============================================================================


class MemberDepartureResult:
    """Result of processing a member departure.

    Attributes:
        revoked_connection_ids: USER_CONNECTIONs that were revoked.
        preserved_connection_ids: WORKSPACE_CONNECTIONs that remain unchanged.
        flagged_for_reauth: Connections flagged for reauthorization (scheduled ops).
    """

    def __init__(
        self,
        revoked_connection_ids: list[UUID],
        preserved_connection_ids: list[UUID],
        flagged_for_reauth: list[UUID],
    ) -> None:
        self.revoked_connection_ids = revoked_connection_ids
        self.preserved_connection_ids = preserved_connection_ids
        self.flagged_for_reauth = flagged_for_reauth


# =============================================================================
# Service
# =============================================================================


class ConnectionPermissionService:
    """Connection permission enforcement and member departure handling.

    Responsibilities:
        - check_connection_access: verify user role is in allowed_roles
        - check_tool_permission: verify tool_policy allows invocation
        - check_creation_permission: verify role for connection creation
        - process_member_departure: handle departing user's connections

    Requirements: R85.6, R85.7, R92.4, R92.5, R92.7, R96.2
    """

    def __init__(self, repo: "ConnectionRepository") -> None:
        """Initialize with a connection repository.

        Args:
            repo: Tenant-scoped ConnectionRepository instance.
        """
        self._repo = repo

    # =========================================================================
    # Permission Checks
    # =========================================================================

    def check_connection_access(
        self,
        connection: "Connection",
        user_role: str,
    ) -> bool:
        """Verify a user's role grants access to a connection.

        A connection's allowed_roles array determines which workspace roles
        can use it. If the user's role is not in the array, access is denied.

        Connection existence alone never grants capabilities (A2-013).
        A connection with an empty allowed_roles list is usable by no one.

        Args:
            connection: The Connection entity to check access for.
            user_role: The user's workspace role (e.g. 'owner', 'admin', 'editor', 'viewer').

        Returns:
            True if access is granted.

        Raises:
            ConnectionPermissionDenied: If user's role is not in allowed_roles.

        Validates: R85.7, R92.5
        """
        allowed_roles = connection.allowed_roles or []

        if user_role not in allowed_roles:
            logger.warning(
                "connection_access_denied",
                connection_id=str(connection.id),
                user_role=user_role,
                allowed_roles=allowed_roles,
            )
            raise ConnectionPermissionDenied(
                message=(
                    f"Role '{user_role}' is not permitted to use this connection. "
                    f"Allowed roles: {allowed_roles}"
                ),
                code="CONNECTION_PERMISSION_DENIED",
            )

        return True

    def check_tool_permission(
        self,
        connection: "Connection",
        tool_name: str,
    ) -> bool:
        """Check whether a specific tool invocation is permitted by tool_policy.

        The tool_policy is a JSON object with optional keys:
            - "allow": list of tool names explicitly allowed
            - "deny": list of tool names explicitly denied

        Evaluation order:
            1. If "deny" list exists and tool_name is in it → DENIED
            2. If "allow" list exists and tool_name is NOT in it → DENIED
            3. If no policy (empty dict) → ALLOWED (all tools permitted by default)

        This implements the layered permission model (A2-013) where
        tool-level restrictions add granularity beyond role-based access.

        Args:
            connection: The Connection entity.
            tool_name: The tool being invoked.

        Returns:
            True if the tool is permitted.

        Raises:
            ConnectionToolDenied: If tool_policy blocks this tool.

        Validates: R85.7, R92.7
        """
        tool_policy = connection.tool_policy or {}

        # Check deny list first (deny takes precedence)
        deny_list = tool_policy.get("deny", [])
        if deny_list and tool_name in deny_list:
            logger.warning(
                "connection_tool_denied",
                connection_id=str(connection.id),
                tool_name=tool_name,
                reason="tool_in_deny_list",
            )
            raise ConnectionToolDenied(
                message=f"Tool '{tool_name}' is explicitly denied by connection policy",
                tool_name=tool_name,
                code="CONNECTION_TOOL_DENIED",
            )

        # Check allow list (if present, only listed tools are permitted)
        allow_list = tool_policy.get("allow", [])
        if allow_list and tool_name not in allow_list:
            logger.warning(
                "connection_tool_denied",
                connection_id=str(connection.id),
                tool_name=tool_name,
                reason="tool_not_in_allow_list",
            )
            raise ConnectionToolDenied(
                message=(
                    f"Tool '{tool_name}' is not in the connection's allow list. "
                    f"Permitted tools: {allow_list}"
                ),
                tool_name=tool_name,
                code="CONNECTION_TOOL_DENIED",
            )

        return True

    def check_creation_permission(
        self,
        ownership: str,
        user_role: str,
    ) -> bool:
        """Verify a user can create a connection of the given ownership type.

        Rules (R85.6, R92.4):
            - WORKSPACE_CONNECTION: requires admin or owner role
            - USER_CONNECTION: any authenticated member (editor+)

        Args:
            ownership: Connection ownership type ('workspace' or 'user').
            user_role: The user's workspace role.

        Returns:
            True if creation is permitted.

        Raises:
            ConnectionCreationDenied: If the user lacks permission.

        Validates: R85.6, R92.4
        """
        if ownership == ConnectionOwnership.WORKSPACE.value:
            if user_role not in ("admin", "owner"):
                logger.warning(
                    "connection_creation_denied",
                    ownership=ownership,
                    user_role=user_role,
                    reason="workspace_connection_requires_admin",
                )
                raise ConnectionCreationDenied(
                    message=(
                        f"Creating workspace connections requires admin or owner role. "
                        f"Current role: '{user_role}'"
                    ),
                    code="CONNECTION_CREATION_DENIED",
                )
        elif ownership == ConnectionOwnership.USER.value:
            # Any authenticated member can create user connections (editor+)
            # Viewers are not considered "editors" — they have read-only access
            if user_role not in ("editor", "admin", "owner"):
                logger.warning(
                    "connection_creation_denied",
                    ownership=ownership,
                    user_role=user_role,
                    reason="user_connection_requires_editor",
                )
                raise ConnectionCreationDenied(
                    message=(
                        f"Creating user connections requires at least editor role. "
                        f"Current role: '{user_role}'"
                    ),
                    code="CONNECTION_CREATION_DENIED",
                )

        return True

    # =========================================================================
    # Member Departure (R92.5, R92.7, R96.2)
    # =========================================================================

    async def process_member_departure(
        self,
        org_id: UUID,
        departing_user_id: UUID,
    ) -> MemberDepartureResult:
        """Handle connection cleanup when a member leaves the workspace.

        Behavior (R92.5, R92.7, R96.2):
            1. USER_CONNECTIONs owned by departing user → lifecycle_state='revoked'
            2. WORKSPACE_CONNECTIONs → remain unchanged (they belong to the org)
            3. Scheduled operations using departing user's connections → flagged
               for pause/reauthorization

        This method is idempotent — calling it multiple times for the same
        user produces the same result (already-revoked connections stay revoked).

        Args:
            org_id: The organisation UUID.
            departing_user_id: The UUID of the member who is leaving.

        Returns:
            MemberDepartureResult with lists of affected connection IDs.

        Validates: R92.5, R92.7, R96.2
        """
        revoked_ids: list[UUID] = []
        preserved_ids: list[UUID] = []
        flagged_ids: list[UUID] = []

        # Fetch all active user connections owned by the departing user
        user_connections, _ = await self._repo.list_all(
            limit=1000,
            offset=0,
            ownership=ConnectionOwnership.USER.value,
            user_id=departing_user_id,
        )

        # Revoke each user connection that isn't already terminal
        terminal_states = {
            ConnectionLifecycle.DISCONNECTED.value,
            ConnectionLifecycle.REVOKED.value,
        }

        for conn in user_connections:
            if conn.lifecycle_state not in terminal_states:
                await self._repo.update_lifecycle_state(
                    connection_id=conn.id,
                    new_state=ConnectionLifecycle.REVOKED.value,
                )
                revoked_ids.append(conn.id)
                # Flag for scheduled operations pause
                flagged_ids.append(conn.id)
            else:
                # Already terminal — no action needed
                revoked_ids.append(conn.id)

        # Fetch workspace connections — these remain unchanged
        workspace_connections, _ = await self._repo.list_all(
            limit=1000,
            offset=0,
            ownership=ConnectionOwnership.WORKSPACE.value,
        )

        for conn in workspace_connections:
            preserved_ids.append(conn.id)

        logger.info(
            "member_departure_processed",
            org_id=str(org_id),
            departing_user_id=str(departing_user_id),
            revoked_count=len(revoked_ids),
            preserved_count=len(preserved_ids),
            flagged_count=len(flagged_ids),
        )

        return MemberDepartureResult(
            revoked_connection_ids=revoked_ids,
            preserved_connection_ids=preserved_ids,
            flagged_for_reauth=flagged_ids,
        )
