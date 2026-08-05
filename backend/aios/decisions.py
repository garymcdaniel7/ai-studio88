"""AIOS Decision Log — tenant-scoped audit trail for AI decisions.

Every LLM call, routing decision, and tool invocation is logged with
workspace ownership for tenant isolation and compliance.

All operations require org_id from TenantContext.

Table: aios_decisions (org_id column added by migration 032)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


def log_decision(
    org_id: str,
    session_id: str,
    decision_type: str,
    provider: str,
    model: str,
    user_id: str | None = None,
    input_summary: str = "",
    output_summary: str = "",
    latency_ms: int = 0,
    tokens_used: int | None = None,
    cost_usd: float | None = None,
    mode: str = "",
    confidence: float | None = None,
    reasoning: str = "",
    metadata: dict | None = None,
) -> dict:
    """Log an AI decision to the tenant-scoped audit trail.

    Args:
        org_id: Required. Workspace that owns this decision.
        session_id: The AIOS session this decision belongs to.
        user_id: The user who triggered this decision (actor attribution).
    """
    if not org_id:
        raise ValueError("org_id is required for decision logging")

    record = {
        "org_id": org_id,
        "user_id": user_id,
        "session_id": session_id,
        "decision_type": decision_type,
        "provider": provider,
        "model": model,
        "input_summary": input_summary[:500],
        "output_summary": output_summary[:500],
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
        "cost_usd": cost_usd,
        "mode": mode,
        "confidence": confidence,
        "reasoning": reasoning,
        "metadata": metadata or {},
    }
    try:
        result = _db().table("aios_decisions").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        logger.warning(f"Failed to log decision: {e}")
        return record


def list_decisions(
    org_id: str,
    session_id: str | None = None,
    limit: int = 50,
    provider: str | None = None,
) -> list[dict]:
    """List recent decisions for a tenant's audit trail."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")

    try:
        query = (
            _db().table("aios_decisions")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if session_id:
            query = query.eq("session_id", session_id)
        if provider:
            query = query.eq("provider", provider)
        return query.execute().data or []
    except Exception:
        return []


def get_decision_stats(org_id: str) -> dict:
    """Get aggregate stats about AI decisions for a tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")

    try:
        all_decisions = (
            _db().table("aios_decisions")
            .select("provider,latency_ms,cost_usd")
            .eq("org_id", org_id)
            .limit(1000)
            .execute().data or []
        )

        if not all_decisions:
            return {"total": 0}

        by_provider: dict[str, dict] = {}
        total_latency = 0
        total_cost = 0.0

        for d in all_decisions:
            p = d.get("provider", "unknown")
            if p not in by_provider:
                by_provider[p] = {"count": 0, "total_latency_ms": 0, "total_cost": 0.0}
            by_provider[p]["count"] += 1
            by_provider[p]["total_latency_ms"] += d.get("latency_ms", 0)
            by_provider[p]["total_cost"] += d.get("cost_usd", 0) or 0
            total_latency += d.get("latency_ms", 0)
            total_cost += d.get("cost_usd", 0) or 0

        for stats in by_provider.values():
            stats["avg_latency_ms"] = stats["total_latency_ms"] // max(stats["count"], 1)

        return {
            "total": len(all_decisions),
            "total_cost_usd": round(total_cost, 4),
            "avg_latency_ms": total_latency // max(len(all_decisions), 1),
            "by_provider": by_provider,
        }
    except Exception:
        return {"total": 0}
