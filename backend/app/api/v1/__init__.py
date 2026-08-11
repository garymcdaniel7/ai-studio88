"""API v1 router — aggregates all versioned endpoint modules.

All routers are registered here and included via a single prefix in main.py.
RBAC enforcement is applied at the router level via enforce_method_role.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.rbac import enforce_method_role

router = APIRouter(
    tags=["v1"],
    dependencies=[Depends(enforce_method_role)],
)


# ── Platform Admin Endpoints ──────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.quarantine import router as quarantine_router

    router.include_router(quarantine_router)
except ImportError:
    pass  # Module not yet created

# ── Talent Endpoints ──────────────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.talent import router as talent_router

    router.include_router(talent_router)
except ImportError:
    pass  # Module not yet created

# ── Job Endpoints ─────────────────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.jobs import router as jobs_router

    router.include_router(jobs_router)
except ImportError:
    pass  # Module not yet created

# ── Cost Endpoints ────────────────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.costs import router as costs_router

    router.include_router(costs_router)
except ImportError:
    pass  # Module not yet created

# ── Compute Availability Endpoints (Platform Admin) ───────────────────────────
try:
    from app.api.v1.endpoints.compute_availability import (
        router as compute_availability_router,
    )

    router.include_router(compute_availability_router)
except ImportError:
    pass  # Module not yet created

# ── Brain Conversation Endpoints ──────────────────────────────────────────────
try:
    from app.api.v1.endpoints.brain_conversations import (
        router as brain_conversations_router,
    )

    router.include_router(brain_conversations_router)
except ImportError:
    pass  # Module not yet created

# ── Brain Memory Endpoints ────────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.brain_memory import router as brain_memory_router

    router.include_router(brain_memory_router)
except ImportError:
    pass  # Module not yet created

# ── Workspace Fallback Preferences Endpoints ──────────────────────────────────
try:
    from app.api.v1.endpoints.workspace_fallback import (
        router as workspace_fallback_router,
    )

    router.include_router(workspace_fallback_router)
except ImportError:
    pass  # Module not yet created

# ── Connections Hub Endpoints ─────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.connections import router as connections_router

    router.include_router(connections_router)
except ImportError:
    pass  # Module not yet created

# ── Workspace Autonomy Profile Endpoints ──────────────────────────────────────
try:
    from app.api.v1.endpoints.workspace_autonomy import (
        router as workspace_autonomy_router,
    )

    router.include_router(workspace_autonomy_router)
except ImportError:
    pass  # Module not yet created

# ── Agent Activity Feed Endpoints ─────────────────────────────────────────────
try:
    from app.api.v1.endpoints.agent_activity import router as agent_activity_router

    router.include_router(agent_activity_router)
except ImportError:
    pass  # Module not yet created

# ── Delegated Permissions Endpoints ───────────────────────────────────────────
try:
    from app.api.v1.endpoints.delegated_permissions import (
        router as delegated_permissions_router,
    )

    router.include_router(delegated_permissions_router)
except ImportError:
    pass  # Module not yet created

# ── Feature Rollout Endpoints (Platform Admin) ────────────────────────────────
try:
    from app.api.v1.endpoints.feature_rollouts import (
        router as feature_rollouts_router,
    )

    router.include_router(feature_rollouts_router)
except ImportError:
    pass  # Module not yet created

# ── Platform Admin Operator & Support Session Endpoints ───────────────────────
try:
    from app.api.v1.endpoints.platform_admin import (
        router as platform_admin_router,
    )

    router.include_router(platform_admin_router)
except ImportError:
    pass  # Module not yet created

# ── Workspace Members (Content Ownership & Departure) ─────────────────────────
try:
    from app.api.v1.endpoints.workspace_members import (
        router as workspace_members_router,
    )

    router.include_router(workspace_members_router)
except ImportError:
    pass  # Module not yet created

# ── Workspace Privacy Restrictions Endpoints ──────────────────────────────────
try:
    from app.api.v1.endpoints.workspace_privacy import (
        router as workspace_privacy_router,
    )

    router.include_router(workspace_privacy_router)
except ImportError:
    pass  # Module not yet created

# ── Consent Record Endpoints ──────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.consent import router as consent_router

    router.include_router(consent_router)
except ImportError:
    pass  # Module not yet created

# ── Takedown Report Endpoints (Public Intake + Appeal) ────────────────────────
try:
    from app.api.v1.endpoints.takedowns import router as takedowns_router

    router.include_router(takedowns_router)
except ImportError:
    pass  # Module not yet created

# ── Model/LoRA Lifecycle Promotion Gates Endpoints ────────────────────────────
try:
    from app.api.v1.endpoints.model_lifecycle import (
        router as model_lifecycle_router,
    )

    router.include_router(model_lifecycle_router)
except ImportError:
    pass  # Module not yet created

# ── Image Generation Endpoints ────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.generate import router as generate_router

    router.include_router(generate_router)
except ImportError:
    pass  # Module not yet created

# ── Competitive Intelligence & Watchlists Endpoints ───────────────────────────
try:
    from app.api.v1.endpoints.competitive_intelligence import (
        router as competitive_intelligence_router,
    )

    router.include_router(competitive_intelligence_router)
except ImportError:
    pass  # Module not yet created

# ── Publishing Approval Binding Endpoints ─────────────────────────────────────
try:
    from app.api.v1.endpoints.publishing_approval import (
        router as publishing_approval_router,
    )

    router.include_router(publishing_approval_router)
except ImportError:
    pass  # Module not yet created

# ── Publishing Disclosure Configuration Endpoints ─────────────────────────────
try:
    from app.api.v1.endpoints.disclosure_config import (
        router as disclosure_config_router,
    )

    router.include_router(disclosure_config_router)
except ImportError:
    pass  # Module not yet created

# ── Scheduled Posts (Core Publishing Service) Endpoints ───────────────────────
try:
    from app.api.v1.endpoints.scheduled_posts import (
        router as scheduled_posts_router,
    )

    router.include_router(scheduled_posts_router)
except ImportError:
    pass  # Module not yet created

# ── Dataset Manifests (Training) Endpoints ────────────────────────────────────
try:
    from app.api.v1.endpoints.dataset_manifests import (
        router as dataset_manifests_router,
    )

    router.include_router(dataset_manifests_router)
except ImportError:
    pass  # Module not yet created

# ── Training Pipeline Endpoints ───────────────────────────────────────────────
try:
    from app.api.v1.endpoints.training import router as training_pipeline_router

    router.include_router(training_pipeline_router)
except ImportError:
    pass  # Module not yet created

# ── Workspace Data Export Endpoints ───────────────────────────────────────────
try:
    from app.api.v1.endpoints.workspace_export import (
        router as workspace_export_router,
    )

    router.include_router(workspace_export_router)
except ImportError:
    pass  # Module not yet created

# ── External Deletion Tracking (Admin) Endpoints ─────────────────────────────
try:
    from app.api.v1.endpoints.external_deletions import (
        router as external_deletions_router,
    )

    router.include_router(external_deletions_router)
except ImportError:
    pass  # Module not yet created

# ── Release Gate (Production Gate Checks) Endpoints ───────────────────────────
try:
    from app.api.v1.endpoints.release_gate import router as release_gate_router

    router.include_router(release_gate_router)
except ImportError:
    pass  # Module not yet created

# ── Release Identity Endpoints (Platform-Level) ──────────────────────────────
try:
    from app.api.v1.endpoints.release_identity import (
        router as release_identity_router,
    )

    router.include_router(release_identity_router)
except ImportError:
    pass  # Module not yet created

# ── Deployment Repeatability Endpoints ────────────────────────────────────────
try:
    from app.api.v1.endpoints.deployment_repeatability import (
        router as deployment_repeatability_router,
    )

    router.include_router(deployment_repeatability_router)
except ImportError:
    pass  # Module not yet created

# ── Independent Verification Endpoints (R82) ─────────────────────────────────
try:
    from app.api.v1.endpoints.verification import router as verification_router

    router.include_router(verification_router)
except ImportError:
    pass  # Module not yet created

# ── Scalability Architecture Verification Endpoints (R91) ─────────────────────
try:
    from app.api.v1.endpoints.scalability import router as scalability_router

    router.include_router(scalability_router)
except ImportError:
    pass  # Module not yet created

# ── Performance Verification Endpoints (R76) ─────────────────────────────────
try:
    from app.api.v1.endpoints.performance_verification import (
        router as performance_verification_router,
    )

    router.include_router(performance_verification_router)
except ImportError:
    pass  # Module not yet created
