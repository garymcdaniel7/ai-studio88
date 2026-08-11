"""Release Identity Context — provides current release info for structured logs and /ready.

This module provides a lightweight, synchronous accessor for the current
Release Identity. It caches the result to avoid repeated DB queries in
hot paths (structured logging, /ready checks).

The cache is invalidated when a new release is created (via the service).

Usage:
    from app.core.release_identity_context import get_release_version_info

    # In /ready endpoint:
    info = get_release_version_info()

    # In structured log context:
    logger.info("event", release_id=info.get("release_id"))

Validates: Requirements R72.2 (surfaced in /ready, structured logs, job records, error reports)
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

# Cache TTL (seconds) — how long to reuse cached release info
_CACHE_TTL = 60.0

_cached_info: dict[str, Any] | None = None
_cached_at: float = 0.0
_cache_lock = threading.Lock()


def get_release_version_info() -> dict[str, Any]:
    """Get the current Release Identity info for HTTP responses and logs.

    Returns a dict safe for JSON serialization (no secrets).
    Falls back to environment variables if no DB release record exists
    (for local development and pre-first-deployment scenarios).

    The result is cached for 60 seconds to avoid repeated DB queries.
    """
    global _cached_info, _cached_at

    with _cache_lock:
        if _cached_info is not None and (time.time() - _cached_at) < _CACHE_TTL:
            return _cached_info

    # Try DB-backed release identity (async via sync wrapper)
    info = _resolve_from_db()
    if info is None:
        # Fallback: resolve from environment variables
        info = _resolve_from_env()

    with _cache_lock:
        _cached_info = info
        _cached_at = time.time()

    return info


def invalidate_cache() -> None:
    """Invalidate the cached release identity info.

    Called after creating a new release identity to ensure the
    next call to get_release_version_info() fetches fresh data.
    """
    global _cached_info, _cached_at
    with _cache_lock:
        _cached_info = None
        _cached_at = 0.0


def _resolve_from_db() -> dict[str, Any] | None:
    """Try to resolve the current release identity from the database.

    Uses a synchronous approach since this is called from sync contexts
    (/ready endpoint, structured logging). Returns None if the DB is
    not available or no release has been registered.
    """
    try:
        from backend.database import get_supabase_client, is_supabase_configured

        if not is_supabase_configured():
            return None

        client = get_supabase_client()
        result = (
            client.table("release_identities")
            .select(
                "id, git_commit_sha, frontend_artifact, backend_artifact, "
                "migration_set, config_version, created_at"
            )
            .eq("is_current", True)
            .limit(1)
            .execute()
        )

        records = result.data or []
        if not records:
            return None

        record = records[0]
        return {
            "release_id": record["id"],
            "git_commit_sha": record["git_commit_sha"][:7],
            "frontend_artifact": record["frontend_artifact"],
            "backend_artifact": record["backend_artifact"],
            "migration_set": record["migration_set"],
            "config_version": record["config_version"],
            "created_at": record["created_at"],
        }
    except Exception:
        # DB not available — fall through to env-based resolution
        return None


def _resolve_from_env() -> dict[str, Any]:
    """Resolve release identity from environment variables.

    Used as fallback when no DB release record exists (local dev,
    or pre-first-deployment). CI/CD pipelines can inject these vars.
    """
    return {
        "release_id": os.getenv("RELEASE_ID", "dev-local"),
        "git_commit_sha": os.getenv("GIT_COMMIT_SHA", "unknown")[:7],
        "frontend_artifact": os.getenv("FRONTEND_ARTIFACT", "local"),
        "backend_artifact": os.getenv("BACKEND_ARTIFACT", "local"),
        "migration_set": os.getenv("MIGRATION_SET", "unknown"),
        "config_version": os.getenv("CONFIG_VERSION", "local"),
        "created_at": None,
    }
