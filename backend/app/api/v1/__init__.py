"""API v1 router — aggregates all endpoint routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    assets,
    campaigns,
    health,
    jobs,
    organizations,
    talent,
    users,
)

router = APIRouter()

# ── System ────────────────────────────────────────────────────────────────────
router.include_router(health.router, prefix="/health", tags=["health"])

# ── SaaS Core ─────────────────────────────────────────────────────────────────
router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
router.include_router(users.router, prefix="/users", tags=["users"])

# ── AI Platform ───────────────────────────────────────────────────────────────
router.include_router(talent.router, prefix="/talent", tags=["talent"])
router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
router.include_router(assets.router, prefix="/assets", tags=["assets"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
