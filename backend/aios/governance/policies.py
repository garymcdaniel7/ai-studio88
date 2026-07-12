"""Configurable Governance Policies — per-user overrides.

Default policies are sensible for solo creators.
Enterprise/team users can tighten them.
Stored in Supabase user_preferences or aios_policies table.
Falls back to hardcoded defaults if no config found.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# =============================================================================
# Default policies (env-overridable for dev)
# =============================================================================

DEFAULTS: dict = {
    "auto_approve_generation": True,      # Images auto-approved
    "auto_approve_training": False,       # Training requires approval
    "auto_approve_gpu_launch": False,     # GPU launch requires approval
    "require_publish_approval": True,     # Publishing always approved by human
    "require_delete_approval": True,      # Deletions always approved by human
    "max_auto_spend_usd": float(os.getenv("GOVERNANCE_MAX_AUTO_SPEND", "5.0")),
    "budget_daily_usd": float(os.getenv("GOVERNANCE_DAILY_BUDGET", "20.0")),
    "budget_monthly_usd": float(os.getenv("GOVERNANCE_MONTHLY_BUDGET", "200.0")),
    "require_gpu_approval": False,
}


def get_policies(user_id: str | None = None, org_id: str | None = None) -> dict:
    """Get governance policies for a user/org.

    Tries Supabase first, falls back to defaults.
    """
    if not user_id and not org_id:
        return DEFAULTS.copy()

    try:
        from backend.database import supabase

        query = supabase.table("aios_policies").select("*")
        if org_id:
            query = query.eq("org_id", org_id)
        elif user_id:
            query = query.eq("user_id", user_id)

        result = query.limit(1).execute()
        if result.data:
            saved = result.data[0].get("policies", {})
            # Merge with defaults (saved overrides defaults)
            merged = {**DEFAULTS, **saved}
            return merged
    except Exception as e:
        logger.debug(f"Could not load governance policies: {e}")

    return DEFAULTS.copy()


def save_policies(policies: dict, user_id: str | None = None, org_id: str | None = None) -> bool:
    """Save governance policies for a user/org."""
    try:
        from backend.database import supabase

        record = {
            "user_id": user_id,
            "org_id": org_id or "00000000-0000-0000-0000-000000000000",
            "policies": policies,
        }

        # Upsert
        supabase.table("aios_policies").upsert(
            record, on_conflict="org_id" if org_id else "user_id"
        ).execute()
        return True
    except Exception as e:
        logger.warning(f"Failed to save governance policies: {e}")
        return False
