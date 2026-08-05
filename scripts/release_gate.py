"""Release Promotion Gate — Story 063.

One authoritative promotion decision across all required deployment targets.
Partial success does NOT permit promotion — every required check must pass.

Usage:
    python scripts/release_gate.py --env staging --manifest release-manifest.json
    python scripts/release_gate.py --env production --dry-run

Targets validated:
    - Frontend (Vercel): deployed, healthy, login renders
    - API (Railway/Render): /health + /ready + /api/v1/health
    - Database: migrations applied, RLS active
    - Worker: Docker image built, scanned
    - Security: secrets scan passed, dependencies audited
    - Smoke tests: critical workflows pass against deployed URLs

Promotion decision:
    PROMOTE — all required checks passed
    BLOCK   — one or more required checks failed (with evidence)
    OVERRIDE — manual bypass (role-restricted, reasoned, time-bound, audited)
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


# =============================================================================
# Canonical Source-to-Deployment Identity (Story 065)
# =============================================================================

DEPLOYMENT_IDENTITY: dict[str, Any] = {
    "product_name": "AI Studio",
    "source": {
        "repository": "garymcdaniel7/ai-studio88",
        "branch_production": "main",
        "branch_preview": "PR branches",
    },
    "targets": {
        "frontend": {
            "platform": "vercel",
            "project_name": "ai-studio99",
            "root_directory": "frontend/",
            "framework": "nextjs",
            "domain_production": "ai-studio99.vercel.app",
            "domain_pattern_preview": "ai-studio99-*.vercel.app",
        },
        "api": {
            "platform": "TBD",
            "root_directory": "./",
            "entry_point": "backend.main:app",
        },
        "worker": {
            "platform": "ghcr",
            "registry": "ghcr.io/garymcdaniel7/ai-studio88/worker",
            "dockerfile": "docker/comfyui-worker/Dockerfile.hardened",
        },
        "database": {
            "platform": "supabase",
            "project_ref": "vipmjgglascthwoqqqji",
        },
        "storage": {
            "platform": "backblaze_b2",
            "bucket": "ai-studio88",
            "region": "us-east-005",
        },
    },
    "historical_note": (
        "Repository is 'ai-studio88' (GitHub); Vercel project is 'ai-studio99'. "
        "Same product, divergent naming from initial setup. "
        "See docs/DEPLOYMENT_IDENTITY.md for full mapping."
    ),
}


# =============================================================================
# Types
# =============================================================================


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    NOT_RUN = "not_run"


class PromotionDecision(str, Enum):
    PROMOTE = "promote"     # All required checks passed
    BLOCK = "block"         # One or more required failures
    OVERRIDE = "override"   # Manual bypass (audited)
    PENDING = "pending"     # Evaluation not complete


class TargetCategory(str, Enum):
    FRONTEND = "frontend"
    API = "api"
    DATABASE = "database"
    WORKER = "worker"
    SECURITY = "security"
    SMOKE_TEST = "smoke_test"
    MIGRATION = "migration"


# =============================================================================
# Check Result
# =============================================================================


@dataclass
class CheckResult:
    """Result of a single promotion check."""

    name: str
    category: TargetCategory
    status: CheckStatus
    required: bool = True  # If required, failure blocks promotion
    message: str = ""
    duration_ms: int = 0
    evidence_url: str = ""  # Link to logs, screenshots, artifacts
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category.value,
            "status": self.status.value,
            "required": self.required,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "evidence_url": self.evidence_url,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Smoke Test Journey
# =============================================================================


@dataclass
class SmokeJourney:
    """A critical workflow smoke test executed against a deployed URL."""

    name: str
    description: str
    steps: list[str]
    expected_outcome: str
    status: CheckStatus = CheckStatus.NOT_RUN
    actual_outcome: str = ""
    error: str = ""
    screenshot_path: str = ""
    duration_ms: int = 0


# Critical journeys that must pass for promotion
CRITICAL_SMOKE_JOURNEYS: list[dict] = [
    {
        "name": "health_endpoints",
        "description": "API health and readiness respond correctly",
        "steps": ["GET /", "GET /health", "GET /ready", "GET /api/v1/health"],
        "expected_outcome": "All return 200 with status: ok",
    },
    {
        "name": "login_page_renders",
        "description": "Frontend login page loads without errors",
        "steps": ["GET /login", "Check page title", "Check form visible", "Check no console errors"],
        "expected_outcome": "Login form renders with email+password fields",
    },
    {
        "name": "auth_gate_enforced",
        "description": "Protected endpoints reject unauthenticated requests",
        "steps": ["GET /api/v1/talent without auth", "GET /api/v1/jobs without auth"],
        "expected_outcome": "All return 401 Unauthorized",
    },
    {
        "name": "authenticated_list",
        "description": "Authenticated user can list resources",
        "steps": ["Login with test credentials", "GET /api/v1/talent", "Verify 200 response"],
        "expected_outcome": "Returns array (empty OK) with 200",
    },
]


# =============================================================================
# Release Gate
# =============================================================================


@dataclass
class ReleaseGate:
    """The authoritative promotion decision for a release."""

    id: str = field(default_factory=lambda: f"rel-{secrets.token_hex(8)}")
    environment: str = "staging"
    commit_sha: str = ""
    version: str = ""
    # Results
    checks: list[CheckResult] = field(default_factory=list)
    smoke_journeys: list[SmokeJourney] = field(default_factory=list)
    # Decision
    decision: PromotionDecision = PromotionDecision.PENDING
    decision_reason: str = ""
    decided_at: str | None = None
    # Override (if applicable)
    override_by: str | None = None
    override_reason: str = ""
    override_expires_at: str | None = None
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "environment": self.environment,
            "commit_sha": self.commit_sha,
            "version": self.version,
            "decision": self.decision.value,
            "decision_reason": self.decision_reason,
            "decided_at": self.decided_at,
            "override_by": self.override_by,
            "override_reason": self.override_reason,
            "checks_passed": sum(1 for c in self.checks if c.status == CheckStatus.PASSED),
            "checks_failed": sum(1 for c in self.checks if c.status == CheckStatus.FAILED),
            "checks_total": len(self.checks),
            "required_failures": [
                c.to_dict() for c in self.checks
                if c.required and c.status != CheckStatus.PASSED
            ],
            "created_at": self.created_at,
        }


# =============================================================================
# Required Target Matrix
# =============================================================================

# What must pass for each environment before promotion
REQUIRED_TARGETS: dict[str, list[dict]] = {
    "staging": [
        {"name": "frontend_build", "category": "frontend", "description": "Next.js build succeeds"},
        {"name": "frontend_deploy", "category": "frontend", "description": "Vercel deployment healthy"},
        {"name": "api_build", "category": "api", "description": "Backend builds without error"},
        {"name": "api_tests", "category": "api", "description": "Unit tests pass with coverage"},
        {"name": "api_health", "category": "api", "description": "/health returns 200"},
        {"name": "api_readiness", "category": "api", "description": "/ready returns 200"},
        {"name": "worker_build", "category": "worker", "description": "Docker image builds"},
        {"name": "security_scan", "category": "security", "description": "No HIGH secrets detected"},
        {"name": "schema_valid", "category": "database", "description": "Schema control matrix runs"},
        {"name": "smoke_health", "category": "smoke_test", "description": "Health endpoints respond"},
        {"name": "smoke_auth", "category": "smoke_test", "description": "Auth gate enforced"},
        {"name": "enforcement_pass", "category": "security", "description": "No new raw DB access"},
    ],
    "production": [
        {"name": "staging_promoted", "category": "api", "description": "Staging gate passed first"},
        {"name": "frontend_deploy", "category": "frontend", "description": "Production frontend healthy"},
        {"name": "api_health", "category": "api", "description": "Production API healthy"},
        {"name": "migration_applied", "category": "migration", "description": "All migrations applied"},
        {"name": "smoke_health", "category": "smoke_test", "description": "Production health OK"},
        {"name": "smoke_auth", "category": "smoke_test", "description": "Auth gate enforced"},
        {"name": "smoke_login", "category": "smoke_test", "description": "Login page renders"},
    ],
}


# =============================================================================
# Gate Evaluation
# =============================================================================


def evaluate_gate(gate: ReleaseGate) -> ReleaseGate:
    """Evaluate the promotion decision based on all check results.

    Rules:
    1. If ANY required check is FAILED or NOT_RUN → BLOCK
    2. If ALL required checks are PASSED → PROMOTE
    3. TIMEOUT counts as failure for required checks
    4. SKIPPED on a required check → BLOCK (must run)
    """
    required_checks = [c for c in gate.checks if c.required]

    if not required_checks:
        gate.decision = PromotionDecision.BLOCK
        gate.decision_reason = "No required checks evaluated — cannot promote empty gate"
        gate.decided_at = datetime.now(UTC).isoformat()
        return gate

    failures = [
        c for c in required_checks
        if c.status in (CheckStatus.FAILED, CheckStatus.NOT_RUN, CheckStatus.TIMEOUT, CheckStatus.SKIPPED)
    ]

    if failures:
        gate.decision = PromotionDecision.BLOCK
        failure_names = [f"{c.name}({c.status.value})" for c in failures]
        gate.decision_reason = f"Blocked by {len(failures)} required failure(s): {', '.join(failure_names[:5])}"
        gate.decided_at = datetime.now(UTC).isoformat()
    else:
        gate.decision = PromotionDecision.PROMOTE
        gate.decision_reason = f"All {len(required_checks)} required checks passed"
        gate.decided_at = datetime.now(UTC).isoformat()

    return gate


def apply_override(
    gate: ReleaseGate,
    *,
    override_by: str,
    override_reason: str,
    override_role: str,
    expires_hours: int = 4,
) -> ReleaseGate:
    """Apply a manual override to a blocked gate.

    Restricted to admin/owner role, requires reason, and is time-bound.
    DECISION-REQUIRED: Whether manual overrides are allowed at all.
    """
    OVERRIDE_ROLES = {"admin", "owner"}

    if override_role not in OVERRIDE_ROLES:
        return gate  # Insufficient role — no override

    if gate.decision != PromotionDecision.BLOCK:
        return gate  # Can only override a blocked gate

    if not override_reason or len(override_reason) < 10:
        return gate  # Must provide meaningful reason

    gate.decision = PromotionDecision.OVERRIDE
    gate.override_by = override_by
    gate.override_reason = override_reason
    gate.override_expires_at = (
        datetime.now(UTC).__class__(
            *datetime.now(UTC).timetuple()[:3],
            datetime.now(UTC).hour + expires_hours,
        ).isoformat()
        if expires_hours > 0 else None
    )
    gate.decision_reason = f"Manual override by {override_by}: {override_reason}"
    gate.decided_at = datetime.now(UTC).isoformat()

    return gate


# =============================================================================
# Evidence Preservation
# =============================================================================


def preserve_evidence(gate: ReleaseGate) -> dict:
    """Generate evidence record for the release decision.

    All logs, screenshots, check results, and decision metadata are
    preserved for audit and dispute resolution.
    """
    return {
        "release_id": gate.id,
        "environment": gate.environment,
        "commit_sha": gate.commit_sha,
        "version": gate.version,
        "deployment_identity": DEPLOYMENT_IDENTITY,
        "decision": gate.decision.value,
        "decision_reason": gate.decision_reason,
        "decided_at": gate.decided_at,
        "checks": [c.to_dict() for c in gate.checks],
        "smoke_journeys": [
            {
                "name": j.name,
                "status": j.status.value,
                "actual_outcome": j.actual_outcome,
                "error": j.error,
                "duration_ms": j.duration_ms,
            }
            for j in gate.smoke_journeys
        ],
        "override": {
            "by": gate.override_by,
            "reason": gate.override_reason,
            "expires_at": gate.override_expires_at,
        } if gate.override_by else None,
        "created_at": gate.created_at,
        "total_checks": len(gate.checks),
        "passed": sum(1 for c in gate.checks if c.status == CheckStatus.PASSED),
        "failed": sum(1 for c in gate.checks if c.status == CheckStatus.FAILED),
    }
