"""Fleet Settings — Centralized configuration for multi-instance GPU management.

Controls:
- max_instances: Maximum concurrent GPU workers (user-configurable, default 3)
- daily_budget: Maximum daily GPU spend in USD (user-configurable)
- idle_timeout: Minutes before idle worker is paused/destroyed (per-vendor handling)
- auto_provision: Whether to auto-launch workers when jobs queue up
- preferred_provider: Default GPU provider for new launches (vast, runpod)

Vendor-specific idle behavior:
- Vast.ai: Destroy instance (ephemeral, no persistent state)
- RunPod: Stop pod (preserves persistent volume, resumes fast)
- Shadow: Pause (preserves state, faster resume)

Settings are persisted to Supabase (fleet_settings table) and cached in-memory.
Falls back to env vars / defaults if DB unavailable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class FleetConfig:
    """Fleet configuration — all user-settable parameters."""

    max_instances: int = 3
    daily_budget_usd: float = 10.0
    idle_timeout_minutes: int = 10
    auto_provision: bool = True
    preferred_provider: str = "vast"  # vast | runpod
    min_vram_gb: int = 24
    max_price_per_hour: float = 1.50
    cool_down_seconds: int = 120  # Don't launch if one was destroyed < 2 min ago
    enable_spot_instances: bool = True
    updated_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "max_instances": self.max_instances,
            "daily_budget_usd": self.daily_budget_usd,
            "idle_timeout_minutes": self.idle_timeout_minutes,
            "auto_provision": self.auto_provision,
            "preferred_provider": self.preferred_provider,
            "min_vram_gb": self.min_vram_gb,
            "max_price_per_hour": self.max_price_per_hour,
            "cool_down_seconds": self.cool_down_seconds,
            "enable_spot_instances": self.enable_spot_instances,
            "updated_at": self.updated_at,
        }


# Idle behavior per vendor
IDLE_ACTIONS = {
    "vast": "destroy",  # Ephemeral — destroy to stop billing entirely
    "runpod": "stop",  # Stop pod — preserves persistent volume, no billing
    "shadow": "pause",  # Pause — fastest resume, minimal billing
}


class FleetSettingsManager:
    """Manages fleet configuration with DB persistence + in-memory cache."""

    def __init__(self) -> None:
        self._config: FleetConfig = self._load_defaults()
        self._last_launch_at: datetime | None = None
        self._daily_spend: float = 0.0
        self._daily_spend_date: str | None = None
        # Try to load from DB on init
        self._load_from_db()

    def _load_defaults(self) -> FleetConfig:
        """Load defaults from env vars."""
        return FleetConfig(
            max_instances=int(os.getenv("FLEET_MAX_INSTANCES", "3")),
            daily_budget_usd=float(os.getenv("FLEET_DAILY_BUDGET", "10.0")),
            idle_timeout_minutes=int(os.getenv("FLEET_IDLE_TIMEOUT", "10")),
            auto_provision=os.getenv("FLEET_AUTO_PROVISION", "true").lower() == "true",
            preferred_provider=os.getenv("FLEET_PREFERRED_PROVIDER", "vast"),
            min_vram_gb=int(os.getenv("FLEET_MIN_VRAM", "24")),
            max_price_per_hour=float(os.getenv("FLEET_MAX_PRICE", "1.50")),
        )

    def _load_from_db(self) -> None:
        """Try to load settings from Supabase. Graceful fallback on failure."""
        try:
            from backend.database import supabase

            result = supabase.table("fleet_settings").select("*").limit(1).execute()
            if result.data:
                row = result.data[0]
                self._config = FleetConfig(
                    max_instances=row.get("max_instances", self._config.max_instances),
                    daily_budget_usd=row.get("daily_budget_usd", self._config.daily_budget_usd),
                    idle_timeout_minutes=row.get(
                        "idle_timeout_minutes", self._config.idle_timeout_minutes
                    ),
                    auto_provision=row.get("auto_provision", self._config.auto_provision),
                    preferred_provider=row.get(
                        "preferred_provider", self._config.preferred_provider
                    ),
                    min_vram_gb=row.get("min_vram_gb", self._config.min_vram_gb),
                    max_price_per_hour=row.get(
                        "max_price_per_hour", self._config.max_price_per_hour
                    ),
                    cool_down_seconds=row.get("cool_down_seconds", self._config.cool_down_seconds),
                    enable_spot_instances=row.get(
                        "enable_spot_instances", self._config.enable_spot_instances
                    ),
                    updated_at=row.get("updated_at"),
                )
                logger.info("Fleet settings loaded from database")
        except Exception as e:
            logger.debug(f"Fleet settings DB load failed (using defaults): {e}")

    def save(self) -> bool:
        """Persist current settings to Supabase."""
        try:
            from backend.database import supabase

            data = self._config.to_dict()
            data["updated_at"] = datetime.now(UTC).isoformat()
            # Upsert (single row — use id=1 convention)
            data["id"] = "default"
            supabase.table("fleet_settings").upsert(data, on_conflict="id").execute()
            self._config.updated_at = data["updated_at"]
            return True
        except Exception as e:
            logger.warning(f"Failed to save fleet settings: {e}")
            return False

    @property
    def config(self) -> FleetConfig:
        return self._config

    def update(self, **kwargs) -> FleetConfig:
        """Update one or more settings."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self.save()
        return self._config

    def get_idle_action(self, provider: str) -> str:
        """Get the idle timeout action for a specific provider."""
        return IDLE_ACTIONS.get(provider, "destroy")

    def can_launch(self, current_instance_count: int) -> tuple[bool, str]:
        """Check if a new instance can be launched based on settings.

        Returns (allowed, reason).
        """
        # Check max instances
        if current_instance_count >= self._config.max_instances:
            return False, f"At maximum instances ({self._config.max_instances})"

        # Check cool-down
        if self._last_launch_at:
            elapsed = (datetime.now(UTC) - self._last_launch_at).total_seconds()
            if elapsed < self._config.cool_down_seconds:
                remaining = int(self._config.cool_down_seconds - elapsed)
                return False, f"Cool-down period ({remaining}s remaining)"

        # Check daily budget
        today = datetime.now(UTC).date().isoformat()
        if self._daily_spend_date != today:
            self._daily_spend = 0.0
            self._daily_spend_date = today

        if self._daily_spend >= self._config.daily_budget_usd:
            return (
                False,
                f"Daily budget exceeded (${self._daily_spend:.2f} / ${self._config.daily_budget_usd:.2f})",
            )

        return True, "OK"

    def record_launch(self) -> None:
        """Record that an instance was just launched (for cool-down tracking)."""
        self._last_launch_at = datetime.now(UTC)

    def record_spend(self, amount_usd: float) -> None:
        """Record GPU spend for budget tracking."""
        today = datetime.now(UTC).date().isoformat()
        if self._daily_spend_date != today:
            self._daily_spend = 0.0
            self._daily_spend_date = today
        self._daily_spend += amount_usd

    def get_budget_status(self) -> dict:
        """Get current budget status."""
        today = datetime.now(UTC).date().isoformat()
        if self._daily_spend_date != today:
            self._daily_spend = 0.0
            self._daily_spend_date = today

        return {
            "daily_budget": self._config.daily_budget_usd,
            "spent_today": round(self._daily_spend, 4),
            "remaining": round(self._config.daily_budget_usd - self._daily_spend, 4),
            "percentage_used": round(
                (self._daily_spend / max(self._config.daily_budget_usd, 0.01)) * 100, 1
            ),
        }


# Singleton
_fleet_settings: FleetSettingsManager | None = None


def get_fleet_settings() -> FleetSettingsManager:
    global _fleet_settings
    if _fleet_settings is None:
        _fleet_settings = FleetSettingsManager()
    return _fleet_settings
