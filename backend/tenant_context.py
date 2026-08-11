"""Centralized tenant validation for Supabase-direct database queries.

This module provides the validation layer for the legacy Supabase-direct
query functions in backend/database.py. It ensures:
    - org_id is never empty or None
    - The quarantined UUID (all zeros) is always rejected
    - Consistent error messages across all database functions

For the new SQLAlchemy-based repository layer, see backend/app/db/tenant_scope.py
which provides equivalent protections via TenantScopedRepository.

Validates: Requirements R2.2, R2.6, R2.7, R2.8, R2.9, R2.10
"""

from __future__ import annotations

# =============================================================================
# Constants
# =============================================================================

QUARANTINED_UUID: str = "00000000-0000-0000-0000-000000000000"
"""Quarantined placeholder UUID that must never be used as an org_id.

Any request referencing this UUID is rejected with a clear error.
See R2.8 and the quarantine process defined in R69.
"""


# =============================================================================
# Exceptions
# =============================================================================


class TenantValidationError(ValueError):
    """Raised when org_id validation fails.

    Subclass of ValueError for backward compatibility with existing
    error handling in database.py callers.
    """

    pass


# =============================================================================
# Validation
# =============================================================================


def validate_org_id(org_id: str | None) -> str:
    """Validate that org_id is non-empty and not the quarantined UUID.

    This function MUST be called at the top of every tenant-scoped
    database function. It replaces the inline `if not org_id` checks
    with centralized validation that also rejects the quarantined UUID.

    Args:
        org_id: The organization ID to validate. Must come from TenantContext
                (JWT + org_members lookup), never from client request parameters.

    Returns:
        The validated org_id string (unchanged).

    Raises:
        TenantValidationError: If org_id is empty, None, or the quarantined UUID.

    Validates: R2.2, R2.8, R2.10
    """
    if not org_id:
        raise TenantValidationError(
            "org_id is required for tenant-scoped queries"
        )

    if org_id == QUARANTINED_UUID:
        raise TenantValidationError(
            "Quarantined org_id rejected — cannot access data with "
            "quarantined UUID (00000000-0000-0000-0000-000000000000)"
        )

    return org_id
