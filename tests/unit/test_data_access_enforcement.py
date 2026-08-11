"""Enforcement tests — prevent new unauthorized raw service-role usage.

These tests scan the codebase to detect direct supabase.table() calls
that bypass the AuthorizedClient boundary (backend/data_access.py).

Files in ALLOWED_RAW_USAGE are grandfathered until migrated.
New files MUST use AuthorizedClient — adding a file here requires review.

Run with:
    pytest tests/unit/test_data_access_enforcement.py -v
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# =============================================================================
# Configuration
# =============================================================================

BACKEND_ROOT = Path(__file__).parent.parent.parent / "backend"

# Files that are ALLOWED to use raw supabase.table() (grandfathered)
# Each entry must justify its presence. New entries require story approval.
ALLOWED_RAW_USAGE: set[str] = {
    # Core infrastructure — provides the client itself
    "database.py",
    # Authorization boundary — wraps the client
    "data_access.py",
    # Migration helper — references pattern in documentation only
    "data_access_helpers.py",
    # Membership resolution — scoped by user_id, not org_id
    "membership.py",
    # Auth middleware — uses service key for token validation, not data access
    "app/core/auth_middleware.py",
    "app/core/tenant.py",
    # Infrastructure health checks — connectivity probes only
    "infrastructure/admin_settings.py",
    # --- GRANDFATHERED: scheduled for migration ---
    # These files existed before Story 009 and still use raw access.
    # Each should be migrated in subsequent stories.
    "api_v1.py",
    "infrastructure/router.py",
    "infrastructure/cost_intelligence.py",
    "infrastructure/fleet_settings.py",
    "infrastructure/sse_progress.py",
    "intelligence_engine/context.py",
    "training/router.py",
    "company/router.py",
    "publishing/router.py",
    "publishing/oauth.py",
    "audio/router.py",
    "video/router.py",
    "brain/router.py",
    "brain/rag.py",
    "cinematic/router.py",
    "asset_intelligence/router.py",
    "object_intelligence/router.py",
    "performance/router.py",
    "production_intelligence/router.py",
    "autonomous_studio/orchestrator.py",
    "engine/lora_injector.py",
    "aios/decisions.py",
    "aios/gateway.py",
    "aios/governance/queue.py",
    "aios/governance/policies.py",
    "aios/knowledge/graph.py",
    "aios/knowledge/memory.py",
    "aios/knowledge/workflow_dna.py",
    "aios/sessions.py",
    "aios/workflow/intelligence.py",
    "aios/obaluaye/monitor.py",
    "aios/obaluaye/recovery.py",
    "aios/mcp/server.py",
    "aios/execution/tools.py",
    "aios/orchestration/model_lifecycle.py",
    "aios/orchestration/session_planner.py",
    "aios/orchestration/interceptor.py",
    # --- GRANDFATHERED: Phase 14+ additions (scheduled for migration) ---
    "storyboard_repository.py",
    "governance_policy.py",
    "memory_service.py",
    "aios/tenant_service.py",
    "lifecycle/router.py",
    "audio/repository.py",
    "provenance/router.py",
    "aios/governance/enforcement.py",
    "aios/hermes/tool_context.py",
}

# Patterns that indicate raw service-role usage
RAW_USAGE_PATTERNS = [
    re.compile(r'supabase\.table\('),
    re.compile(r'_db\(\)\.table\('),
    re.compile(r'from backend\.database import supabase'),
]


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.unit
def test_no_new_raw_supabase_usage():
    """Enforce: no NEW files may use raw supabase.table() outside the boundary.

    Any file doing raw CRUD must be listed in ALLOWED_RAW_USAGE.
    To add a file, it must be justified and tracked for future migration.
    """
    if not BACKEND_ROOT.exists():
        pytest.skip("Backend root not found")

    violations: list[str] = []

    for py_file in BACKEND_ROOT.rglob("*.py"):
        # Get relative path for matching against allow-list
        rel_path = str(py_file.relative_to(BACKEND_ROOT))

        # Skip __pycache__ and test files
        if "__pycache__" in rel_path or rel_path.startswith("tests"):
            continue

        # Skip allowed files
        if rel_path in ALLOWED_RAW_USAGE:
            continue

        # Check file content for raw patterns
        try:
            content = py_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        for pattern in RAW_USAGE_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                violations.append(
                    f"{rel_path}: {len(matches)} occurrence(s) of '{pattern.pattern}'"
                )
                break  # One violation per file is enough

    if violations:
        msg = (
            "New raw service-role usage detected!\n"
            "These files use supabase.table() outside the AuthorizedClient boundary.\n"
            "Either:\n"
            "  1. Migrate to AuthorizedClient (preferred)\n"
            "  2. Add to ALLOWED_RAW_USAGE with justification (requires review)\n\n"
            "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
        )
        pytest.fail(msg)


@pytest.mark.unit
def test_allowed_files_still_exist():
    """Verify that grandfathered files still exist (detect stale entries)."""
    if not BACKEND_ROOT.exists():
        pytest.skip("Backend root not found")

    missing = []
    for rel_path in ALLOWED_RAW_USAGE:
        full_path = BACKEND_ROOT / rel_path
        if not full_path.exists():
            missing.append(rel_path)

    if missing:
        msg = (
            "Grandfathered files no longer exist — remove from ALLOWED_RAW_USAGE:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )
        pytest.fail(msg)


@pytest.mark.unit
def test_data_access_module_exports():
    """Verify the data_access module exports the expected public API."""
    from backend.data_access import (
        AuthorizationError,
        AuthorizedClient,
        ContextKind,
        ExecutionContext,
        SystemContext,
        WorkerContext,
        authorized_client,
        get_recent_audit_entries,
        system_client,
        worker_client,
    )

    # Verify classes are importable and have expected attributes
    assert hasattr(AuthorizedClient, "select")
    assert hasattr(AuthorizedClient, "insert")
    assert hasattr(AuthorizedClient, "update")
    assert hasattr(AuthorizedClient, "delete")
    assert hasattr(AuthorizedClient, "select_by_id")
    assert hasattr(AuthorizedClient, "raw_query")

    # Verify context types
    assert ContextKind.TENANT.value == "tenant"
    assert ContextKind.SYSTEM.value == "system"
    assert ContextKind.WORKER.value == "worker"
