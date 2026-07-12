"""AIOS Decision Log — audit trail for every AI decision.

Every LLM call, routing decision, and tool invocation is logged.
This enables:
- Debugging (why did it pick this model?)
- Cost tracking (tokens used per provider)
- Quality analysis (which provider gives best responses?)
- Compliance (full audit trail for enterprise customers)

Table: aios_decisions
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


def log_decision(
    session_id: str,
    decision_type: str,
    provider: str,
    model: str,
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
    """Log an AI decision to the audit trail."""
    record = {
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
    session_id: str | None = None,
    limit: int = 50,
    provider: str | None = None,
) -> list[dict]:
    """List recent decisions for audit."""
    try:
        query = _db().table("aios_decisions").select("*").order("created_at", desc=True).limit(limit)
        if session_id:
            query = query.eq("session_id", session_id)
        if provider:
            query = query.eq("provider", provider)
        return query.execute().data or []
    except Exception:
        return []


def get_decision_stats() -> dict:
    """Get aggregate stats about AI decisions."""
    try:
        all_decisions = _db().table("aios_decisions").select("provider,latency_ms,cost_usd").limit(1000).execute().data or []

        if not all_decisions:
            return {"total": 0}

        by_provider = {}
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

        # Compute averages
        for p, stats in by_provider.items():
            stats["avg_latency_ms"] = stats["total_latency_ms"] // max(stats["count"], 1)

        return {
            "total": len(all_decisions),
            "total_cost_usd": round(total_cost, 4),
            "avg_latency_ms": total_latency // max(len(all_decisions), 1),
            "by_provider": by_provider,
        }
    except Exception:
        return {"total": 0}
