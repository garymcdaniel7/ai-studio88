"""AI Studio — Router registry and registration.

Consolidates the repeated try/import/except/include_router blocks that
previously lived inline in backend/main.py into a single data-driven
registry. Behavior is identical: each router is imported under a
guarded try/except, mounted with an optional prefix, and failures are
recorded via the capability-readiness startup-failure registry.

This is a pure structural consolidation — no routes change, no
dependencies change.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import FastAPI


@dataclass(frozen=True)
class RouterEntry:
    """Describes one router to mount on the FastAPI app."""

    name: str
    module: str          # e.g. "backend.video.router"
    attribute: str = "router"
    prefix: str = ""
    # Optional post-import init callback (called after successful import)
    init: Optional[Callable[[], None]] = None
    # Optional callback to invoke on ImportError (e.g. record failure)
    on_error: Optional[Callable[[str, str], None]] = None


# Default failure recorder — mirrors main.py's `_reg_failure` behavior.
def _default_on_error(name: str, error: str) -> None:
    from backend.app.core.capability_readiness import register_startup_failure
    register_startup_failure(name, error)


def _video_provider_init() -> None:
    """Initialize the canonical video provider registry (Story 143)."""
    from backend.video.registry import setup_video_providers
    setup_video_providers()


ROUTER_REGISTRY: list[RouterEntry] = [
    RouterEntry("v1", "backend.api_v1", prefix="/api/v1"),
    RouterEntry("creator_os", "backend.creator_os.router"),
    RouterEntry("autonomous_studio", "backend.autonomous_studio.router"),
    RouterEntry("training", "backend.training.router"),
    RouterEntry("video", "backend.video.router", init=_video_provider_init),
    RouterEntry("audio", "backend.audio.router"),
    RouterEntry("performance", "backend.performance.router"),
    RouterEntry("publishing", "backend.publishing.router"),
    RouterEntry("publishing_oauth", "backend.publishing.oauth"),
    RouterEntry("brain", "backend.brain.router"),
    RouterEntry("production_intelligence", "backend.production_intelligence.router"),
    RouterEntry("asset_intelligence", "backend.asset_intelligence.router"),
    RouterEntry("cinematic", "backend.cinematic.router"),
    RouterEntry("company", "backend.company.router"),
    RouterEntry("object_intelligence", "backend.object_intelligence.router"),
    RouterEntry("infrastructure", "backend.infrastructure.router"),
    RouterEntry("generate", "backend.infrastructure.generate"),
    RouterEntry("aios_gateway", "backend.aios.gateway"),
    RouterEntry("aios_mcp", "backend.aios.mcp.server"),
    RouterEntry("aios_approval", "backend.aios.approval_router"),
    RouterEntry("batch_generation", "backend.batch_generation_router"),
    RouterEntry("provenance", "backend.provenance.router"),
    RouterEntry("lifecycle", "backend.lifecycle.router"),
    RouterEntry("notifications", "backend.notifications.notification_router"),
    RouterEntry("social_analytics", "backend.social_analytics.router"),
    RouterEntry("billing", "backend.billing_router", prefix="/api/v1/billing"),
    RouterEntry("compliance", "backend.compliance.router"),
]


def register_routers(app: FastAPI) -> list[str]:
    """Mount all routers from ROUTER_REGISTRY onto the app.

    Returns a list of router names that failed to load (for diagnostics).
    """
    failed: list[str] = []

    for entry in ROUTER_REGISTRY:
        try:
            module = __import__(entry.module, fromlist=[entry.attribute])
            router = getattr(module, entry.attribute)
            app.include_router(router, prefix=entry.prefix)
            if entry.init is not None:
                entry.init()
        except ImportError as exc:
            warnings.warn(f"{entry.name} router not loaded: {exc}", stacklevel=2)
            failed.append(entry.name)
            if entry.on_error is not None:
                entry.on_error(entry.name, str(exc))
        except Exception as exc:  # init callbacks may raise; don't kill startup
            warnings.warn(f"{entry.name} router init failed: {exc}", stacklevel=2)
            failed.append(entry.name)

    return failed
