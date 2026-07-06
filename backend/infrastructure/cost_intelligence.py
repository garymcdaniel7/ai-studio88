"""Cost Intelligence Module — Tracks spending, enforces budgets, provides cost analytics.

Responsibilities:
- Record session costs when workers stop
- Provide real-time cost if a worker is running
- Daily/monthly spend aggregation
- Budget limit checking (warn, not block)
- Cost breakdown by GPU type and provider
- Historical cost data for charting

Storage:
- In-memory list of CostRecord (persists for app lifetime)
- Future: Supabase cost_records table for long-term persistence
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class CostRecord:
    """A single cost record representing one completed worker session."""

    session_id: str
    start_time: str  # ISO format
    end_time: str  # ISO format
    duration_seconds: float
    hourly_rate: float
    total_cost: float
    gpu_name: str = ""
    provider: str = "vast_ai"
    jobs_completed: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "hourly_rate": self.hourly_rate,
            "total_cost": self.total_cost,
            "gpu_name": self.gpu_name,
            "provider": self.provider,
            "jobs_completed": self.jobs_completed,
            "created_at": self.created_at,
        }


# =============================================================================
# Cost Tracker
# =============================================================================


class CostTracker:
    """Tracks GPU spending across sessions with budget awareness.

    Usage:
        tracker = CostTracker()
        tracker.record_session_cost(session_id, 0.50, 3600, "RTX 4090", "vast_ai")
        budget = tracker.check_budget()
        history = tracker.get_cost_history(days=30)
    """

    def __init__(self):
        self._records: list[CostRecord] = []
        self._daily_budget = float(os.getenv("COST_DAILY_BUDGET", "10.0"))
        self._monthly_budget = float(os.getenv("COST_MONTHLY_BUDGET", "200.0"))

    @property
    def daily_budget(self) -> float:
        return self._daily_budget

    @property
    def monthly_budget(self) -> float:
        return self._monthly_budget

    # ─── Persistence ─────────────────────────────────────────────────────

    def persist_to_db(self, record: CostRecord) -> None:
        """Persist a cost record to Supabase for long-term storage."""
        try:
            from backend.database import supabase
            supabase.table("cost_records").insert({
                "session_id": record.session_id,
                "start_time": record.start_time,
                "end_time": record.end_time,
                "duration_seconds": record.duration_seconds,
                "hourly_rate": record.hourly_rate,
                "total_cost": record.total_cost,
                "gpu_name": record.gpu_name,
                "provider": record.provider,
                "jobs_completed": record.jobs_completed,
            }).execute()
        except Exception:
            pass  # DB table may not exist yet — graceful fallback

    # ─── Record Costs ─────────────────────────────────────────────────────

    def record_session_cost(
        self,
        session_id: str,
        hourly_rate: float,
        duration_seconds: float,
        gpu_name: str = "",
        provider: str = "vast_ai",
        jobs_completed: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> CostRecord:
        """Record the cost of a completed worker session.

        Args:
            session_id: Unique session identifier
            hourly_rate: Cost per hour in USD
            duration_seconds: Session duration in seconds
            gpu_name: GPU model used
            provider: Cloud provider name
            jobs_completed: Number of jobs processed
            start_time: ISO start time (defaults to calculated from duration)
            end_time: ISO end time (defaults to now)

        Returns:
            The created CostRecord
        """
        now = datetime.now(timezone.utc)
        if not end_time:
            end_time = now.isoformat()
        if not start_time:
            from datetime import timedelta

            start_dt = now - timedelta(seconds=duration_seconds)
            start_time = start_dt.isoformat()

        total_cost = round((duration_seconds / 3600) * hourly_rate, 4)

        record = CostRecord(
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_seconds,
            hourly_rate=hourly_rate,
            total_cost=total_cost,
            gpu_name=gpu_name,
            provider=provider,
            jobs_completed=jobs_completed,
        )

        self._records.append(record)
        self.persist_to_db(record)
        logger.info(
            f"Recorded cost: ${total_cost:.4f} for session {session_id} "
            f"({gpu_name}, {duration_seconds:.0f}s @ ${hourly_rate}/hr)"
        )

        # Check budget after recording
        budget = self.check_budget()
        if not budget["within_budget"]:
            if not budget["daily"]["within_budget"]:
                logger.warning(
                    f"BUDGET WARNING: Daily spend ${budget['daily']['spent']:.2f} "
                    f"exceeds limit ${budget['daily']['budget']:.2f}"
                )
            if not budget["monthly"]["within_budget"]:
                logger.warning(
                    f"BUDGET WARNING: Monthly spend ${budget['monthly']['spent']:.2f} "
                    f"exceeds limit ${budget['monthly']['budget']:.2f}"
                )

        return record

    # ─── Per-Job Cost ─────────────────────────────────────────────────────

    def record_job_cost(
        self,
        job_type: str,
        model: str = "",
        provider: str = "",
        duration_seconds: float = 0,
        estimated_cost: float = 0,
        api_cost: float = 0,
        input_summary: str = "",
        output_summary: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Record the cost of an individual job (generation, voice, training).

        Persists to Supabase job_costs table if available.
        Always stored in memory for current-session analytics.
        """
        total_cost = round(estimated_cost + api_cost, 6)
        record = {
            "job_type": job_type,
            "model": model,
            "provider": provider,
            "duration_seconds": round(duration_seconds, 2),
            "estimated_cost": estimated_cost,
            "api_cost": api_cost,
            "total_cost": total_cost,
            "input_summary": input_summary[:200],
            "output_summary": output_summary[:200],
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if not hasattr(self, "_job_costs"):
            self._job_costs = []
        self._job_costs.append(record)

        # Persist to Supabase
        try:
            from backend.database import supabase
            supabase.table("job_costs").insert(record).execute()
        except Exception:
            pass  # Table may not exist yet

        logger.info(
            f"Job cost: ${total_cost:.6f} ({job_type}/{model}/{provider}, {duration_seconds:.1f}s)"
        )
        return record

    def get_job_costs(self, job_type: str | None = None, limit: int = 50) -> list[dict]:
        """Get recent job costs, optionally filtered by type."""
        costs = getattr(self, "_job_costs", [])
        if job_type:
            costs = [c for c in costs if c["job_type"] == job_type]
        return list(reversed(costs[-limit:]))

    def get_total_job_spend(self) -> dict:
        """Get aggregated spend by job type."""
        costs = getattr(self, "_job_costs", [])
        by_type: dict[str, float] = {}
        for c in costs:
            by_type[c["job_type"]] = by_type.get(c["job_type"], 0) + c["total_cost"]
        return {
            "total": round(sum(by_type.values()), 4),
            "by_type": {k: round(v, 4) for k, v in by_type.items()},
            "job_count": len(costs),
        }

    # ─── Current Spend ────────────────────────────────────────────────────

    def get_current_spend(self) -> dict[str, Any]:
        """Get real-time cost if a worker is currently running.

        Checks the worker orchestrator for an active session and
        calculates the running cost.
        """
        try:
            from backend.infrastructure.worker_orchestrator import get_orchestrator

            orchestrator = get_orchestrator()
            session = orchestrator.session

            if session and session.status not in ("stopped", "destroyed", "error"):
                started = datetime.fromisoformat(session.started_at)
                elapsed_seconds = (
                    datetime.now(timezone.utc) - started
                ).total_seconds()
                elapsed_hours = elapsed_seconds / 3600
                current_cost = round(elapsed_hours * session.hourly_rate, 4)

                return {
                    "active": True,
                    "session_id": session.id,
                    "gpu_name": session.gpu_name,
                    "hourly_rate": session.hourly_rate,
                    "elapsed_seconds": round(elapsed_seconds, 1),
                    "current_cost": current_cost,
                }
        except Exception as e:
            logger.debug(f"Could not check active session: {e}")

        return {
            "active": False,
            "session_id": None,
            "gpu_name": None,
            "hourly_rate": 0.0,
            "elapsed_seconds": 0,
            "current_cost": 0.0,
        }

    # ─── Daily Spend ──────────────────────────────────────────────────────

    def get_daily_spend(self, target_date: Optional[date] = None) -> float:
        """Get total spend for a given day.

        Args:
            target_date: Date to check (defaults to today UTC)

        Returns:
            Total cost in USD for the day
        """
        if target_date is None:
            target_date = datetime.now(timezone.utc).date()

        total = 0.0
        for record in self._records:
            try:
                record_date = datetime.fromisoformat(record.end_time).date()
                if record_date == target_date:
                    total += record.total_cost
            except (ValueError, TypeError):
                continue

        # Add current session cost if worker is running today
        current = self.get_current_spend()
        if current["active"]:
            today = datetime.now(timezone.utc).date()
            if target_date == today:
                total += current["current_cost"]

        return round(total, 4)

    # ─── Monthly Spend ────────────────────────────────────────────────────

    def get_monthly_spend(
        self, year: Optional[int] = None, month: Optional[int] = None
    ) -> float:
        """Get total spend for a given month.

        Args:
            year: Year (defaults to current UTC year)
            month: Month (defaults to current UTC month)

        Returns:
            Total cost in USD for the month
        """
        now = datetime.now(timezone.utc)
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        total = 0.0
        for record in self._records:
            try:
                record_dt = datetime.fromisoformat(record.end_time)
                if record_dt.year == year and record_dt.month == month:
                    total += record.total_cost
            except (ValueError, TypeError):
                continue

        # Add current session cost if worker is running this month
        current = self.get_current_spend()
        if current["active"] and now.year == year and now.month == month:
            total += current["current_cost"]

        return round(total, 4)

    # ─── Cost Breakdown ───────────────────────────────────────────────────

    def get_cost_breakdown(self) -> dict[str, Any]:
        """Get cost breakdown by GPU type and provider.

        Returns:
            Dict with breakdowns by gpu, provider, and summary stats
        """
        by_gpu: dict[str, float] = {}
        by_provider: dict[str, float] = {}
        total_sessions = len(self._records)
        total_cost = 0.0
        total_duration = 0.0

        for record in self._records:
            total_cost += record.total_cost
            total_duration += record.duration_seconds

            gpu_key = record.gpu_name or "unknown"
            by_gpu[gpu_key] = by_gpu.get(gpu_key, 0.0) + record.total_cost

            provider_key = record.provider or "unknown"
            by_provider[provider_key] = (
                by_provider.get(provider_key, 0.0) + record.total_cost
            )

        # Add current session to breakdown
        current = self.get_current_spend()
        if current["active"]:
            total_cost += current["current_cost"]
            gpu_key = current["gpu_name"] or "unknown"
            by_gpu[gpu_key] = by_gpu.get(gpu_key, 0.0) + current["current_cost"]

        return {
            "total_cost": round(total_cost, 4),
            "total_sessions": total_sessions,
            "total_duration_hours": round(total_duration / 3600, 2),
            "by_gpu": {k: round(v, 4) for k, v in sorted(by_gpu.items())},
            "by_provider": {k: round(v, 4) for k, v in sorted(by_provider.items())},
            "average_session_cost": (
                round(total_cost / total_sessions, 4) if total_sessions > 0 else 0.0
            ),
            "average_hourly_effective": (
                round(total_cost / (total_duration / 3600), 4)
                if total_duration > 0
                else 0.0
            ),
        }

    # ─── Budget Check ─────────────────────────────────────────────────────

    def check_budget(self) -> dict[str, Any]:
        """Check whether daily and monthly budget limits are exceeded.

        Budget limits are read from environment variables:
        - COST_DAILY_BUDGET (default: $10.00)
        - COST_MONTHLY_BUDGET (default: $200.00)

        Returns:
            Budget status with within_budget flag, daily and monthly details
        """
        daily_spent = self.get_daily_spend()
        monthly_spent = self.get_monthly_spend()

        daily_remaining = max(0.0, self._daily_budget - daily_spent)
        monthly_remaining = max(0.0, self._monthly_budget - monthly_spent)

        daily_within = daily_spent <= self._daily_budget
        monthly_within = monthly_spent <= self._monthly_budget

        return {
            "within_budget": daily_within and monthly_within,
            "daily": {
                "budget": self._daily_budget,
                "spent": round(daily_spent, 4),
                "remaining": round(daily_remaining, 4),
                "within_budget": daily_within,
            },
            "monthly": {
                "budget": self._monthly_budget,
                "spent": round(monthly_spent, 4),
                "remaining": round(monthly_remaining, 4),
                "within_budget": monthly_within,
            },
        }

    # ─── Cost History ─────────────────────────────────────────────────────

    def get_cost_history(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily cost totals for the last N days (for charting).

        Args:
            days: Number of days to include (default 30)

        Returns:
            List of {"date": "YYYY-MM-DD", "cost": float, "sessions": int}
        """
        from datetime import timedelta

        today = datetime.now(timezone.utc).date()
        history: list[dict[str, Any]] = []

        for i in range(days - 1, -1, -1):
            target_date = today - timedelta(days=i)
            day_cost = 0.0
            day_sessions = 0

            for record in self._records:
                try:
                    record_date = datetime.fromisoformat(record.end_time).date()
                    if record_date == target_date:
                        day_cost += record.total_cost
                        day_sessions += 1
                except (ValueError, TypeError):
                    continue

            # Add current session cost to today
            if target_date == today:
                current = self.get_current_spend()
                if current["active"]:
                    day_cost += current["current_cost"]

            history.append({
                "date": target_date.isoformat(),
                "cost": round(day_cost, 4),
                "sessions": day_sessions,
            })

        return history

    # ─── Summary ──────────────────────────────────────────────────────────

    def get_summary(self) -> dict[str, Any]:
        """Get a comprehensive cost summary (used by the /cost endpoint).

        Combines current spend, budget check, and breakdown in one call.
        """
        return {
            "current": self.get_current_spend(),
            "today": self.get_daily_spend(),
            "this_month": self.get_monthly_spend(),
            "budget": self.check_budget(),
            "breakdown": self.get_cost_breakdown(),
        }


# =============================================================================
# Module-level singleton
# =============================================================================

_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get or create the global CostTracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
