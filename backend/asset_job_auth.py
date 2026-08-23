"""Asset & Job Authorization — Story 015.

Centralized authorization helpers for asset and job endpoints.
Every asset/job operation must flow through these helpers to ensure:
1. Authentication is required (no anonymous access to user data)
2. Tenant isolation (org_id scoping via AuthorizedClient)
3. Audit trail for destructive/spend-affecting actions
4. Resource ownership verification (record ID + org_id)

Usage in routes:
    from backend.asset_job_auth import (
        authorized_asset_read,
        authorized_asset_write,
        authorized_job_read,
        authorized_job_write,
        audit_destructive_action,
    )
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException

from backend.auth import AuthUser
from backend.data_access import AuthorizationError, AuthorizedClient
from backend.data_access_helpers import get_authorized_client, get_authorized_client_strict

# =============================================================================
# Audit Trail (in-memory, production flushes to DB)
# =============================================================================

_destructive_audit: list[dict] = []
_MAX_AUDIT = 500


def audit_destructive_action(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    user: AuthUser,
    org_id: str | None,
    outcome: str = "success",
    details: str = "",
) -> None:
    """Record a destructive or spend-affecting action for audit.

    Actions: delete_asset, cancel_job, retry_job, delete_job, run_generation
    """
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "actor_user_id": user.user_id,
        "actor_email": user.email,
        "org_id": org_id,
        "outcome": outcome,
        "details": details,
    }
    _destructive_audit.append(entry)
    if len(_destructive_audit) > _MAX_AUDIT:
        _destructive_audit.pop(0)


def get_audit_log(limit: int = 50) -> list[dict]:
    """Get recent destructive action audit entries."""
    return list(reversed(_destructive_audit[-limit:]))


# =============================================================================
# Asset Authorization Helpers
# =============================================================================


def authorized_asset_list(user: AuthUser) -> AuthorizedClient | None:
    """Get an authorized client for listing assets (scoped to user's org).

    Returns None if user has no org membership (dev mode fallback).
    """
    return get_authorized_client(user)


def authorized_asset_read(user: AuthUser, asset_id: str) -> dict:
    """Read a single asset with ownership verification.

    Returns the asset record if the user's org owns it.
    Raises 404 if not found or belongs to another org (no existence leak).
    """
    from backend.compliance.quarantine import is_asset_quarantined

    if is_asset_quarantined(asset_id, user.org_id):
        raise HTTPException(status_code=404, detail="Asset not found")

    client = get_authorized_client(user)
    if client:
        try:
            result = client.select_by_id("assets", asset_id)
            asset = result.data
            if asset.get("compliance_status") == "quarantined":
                raise HTTPException(status_code=404, detail="Asset not found")
            return asset
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Asset not found")
    else:
        # Dev mode fallback (no membership)
        from backend.database import get_asset_by_id
        try:
            asset = get_asset_by_id(asset_id).data
            if asset.get("compliance_status") == "quarantined":
                raise HTTPException(status_code=404, detail="Asset not found")
            return asset
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=404, detail="Asset not found")


def authorized_asset_delete(user: AuthUser, asset_id: str) -> dict:
    """Delete an asset with ownership verification + audit.

    Returns the deleted asset record.
    Raises 404 if not found or belongs to another org.
    """
    client = get_authorized_client_strict(user)
    try:
        result = client.select_by_id("assets", asset_id)
        asset = result.data
    except (AuthorizationError, HTTPException):
        raise HTTPException(status_code=404, detail="Asset not found")

    # Perform delete
    try:
        client.delete("assets", asset_id)
    except AuthorizationError:
        raise HTTPException(status_code=404, detail="Asset not found")

    audit_destructive_action(
        action="delete_asset",
        resource_type="asset",
        resource_id=asset_id,
        user=user,
        org_id=user.org_id,
        details=f"filename={asset.get('filename', 'unknown')}",
    )
    return asset


# =============================================================================
# Job Authorization Helpers
# =============================================================================


def authorized_job_list(user: AuthUser) -> AuthorizedClient | None:
    """Get an authorized client for listing jobs (scoped to user's org)."""
    return get_authorized_client(user)


def authorized_job_read(user: AuthUser, job_id: str) -> dict:
    """Read a single job with ownership verification.

    Returns the job record if the user's org owns it.
    Raises 404 if not found or belongs to another org.
    """
    client = get_authorized_client(user)
    if client:
        try:
            result = client.select_by_id("jobs", job_id)
            return result.data
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Job not found")
    else:
        from backend.database import get_job_by_id
        try:
            return get_job_by_id(job_id).data
        except Exception:
            raise HTTPException(status_code=404, detail="Job not found")


def authorized_job_cancel(user: AuthUser, job_id: str) -> dict:
    """Cancel a job with ownership verification + audit.

    Returns the updated job record.
    Raises 404 if not found, 400 if not cancellable.
    """
    client = get_authorized_client_strict(user)
    try:
        result = client.select_by_id("jobs", job_id)
        job = result.data
    except (AuthorizationError, HTTPException):
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") not in ("queued", "running", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in '{job.get('status')}' state",
        )

    client.update("jobs", {"status": "cancelled"}, record_id=job_id)

    audit_destructive_action(
        action="cancel_job",
        resource_type="job",
        resource_id=job_id,
        user=user,
        org_id=user.org_id,
        details=f"type={job.get('type', 'unknown')}, prev_status={job.get('status')}",
    )
    return {**job, "status": "cancelled"}


def authorized_job_retry(user: AuthUser, job_id: str) -> dict:
    """Retry a job with ownership verification + audit.

    Returns the updated job record.
    Raises 404 if not found, 400 if not retryable.
    """
    client = get_authorized_client_strict(user)
    try:
        result = client.select_by_id("jobs", job_id)
        job = result.data
    except (AuthorizationError, HTTPException):
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") not in ("failed", "cancelled", "error"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job in '{job.get('status')}' state",
        )

    client.update(
        "jobs",
        {"status": "queued", "progress": 0, "error": None},
        record_id=job_id,
    )

    audit_destructive_action(
        action="retry_job",
        resource_type="job",
        resource_id=job_id,
        user=user,
        org_id=user.org_id,
        details=f"type={job.get('type', 'unknown')}, prev_status={job.get('status')}",
    )
    return {**job, "status": "queued", "progress": 0}


def authorized_job_delete(user: AuthUser, job_id: str) -> dict:
    """Delete a job with ownership verification + audit.

    Only queued or terminal jobs can be deleted.
    """
    client = get_authorized_client_strict(user)
    try:
        result = client.select_by_id("jobs", job_id)
        job = result.data
    except (AuthorizationError, HTTPException):
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") in ("running", "pending"):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running job. Cancel it first.",
        )

    try:
        client.delete("jobs", job_id)
    except AuthorizationError:
        raise HTTPException(status_code=404, detail="Job not found")

    audit_destructive_action(
        action="delete_job",
        resource_type="job",
        resource_id=job_id,
        user=user,
        org_id=user.org_id,
        details=f"type={job.get('type', 'unknown')}",
    )
    return job
