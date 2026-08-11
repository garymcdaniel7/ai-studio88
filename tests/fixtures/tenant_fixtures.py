"""Multi-Tenant Security Test Fixtures — Story 009.

Provides synthetic test identities, organizations, and data for adversarial
tenant isolation testing. Two completely separate orgs with distinct users
at every role level.

Usage:
    from tests.fixtures.tenant_fixtures import ORG_ALPHA, ORG_BETA, USERS

These fixtures represent the minimum set needed to prove:
- Cross-tenant reads fail
- Cross-tenant writes fail
- Role escalation fails
- Forged org_id fails
- Revoked users fail
- Service-role operations are scoped
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Roles
# =============================================================================


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


# =============================================================================
# Test Organizations
# =============================================================================


@dataclass(frozen=True)
class TestOrg:
    """A synthetic organization for isolation testing."""

    id: str
    name: str
    slug: str


ORG_ALPHA = TestOrg(
    id="org-aaaa-1111-2222-333344445555",
    name="Alpha Studio",
    slug="alpha-studio",
)

ORG_BETA = TestOrg(
    id="org-bbbb-6666-7777-888899990000",
    name="Beta Creative",
    slug="beta-creative",
)


# =============================================================================
# Test Users
# =============================================================================


@dataclass(frozen=True)
class TestUser:
    """A synthetic user identity for testing."""

    id: str
    email: str
    org_id: str
    role: Role
    is_active: bool = True
    description: str = ""

    @property
    def jwt_claims(self) -> dict[str, Any]:
        """Simulated JWT claims as Supabase would provide."""
        return {
            "sub": self.id,
            "email": self.email,
            "org_id": self.org_id,
            "role": self.role.value,
            "aud": "authenticated",
            "iss": "https://test.supabase.co/auth/v1",
        }

    @property
    def auth_header(self) -> dict[str, str]:
        """Simulated Authorization header (token would be signed in real tests)."""
        return {"Authorization": f"Bearer test-jwt-{self.id}"}


# ── Alpha Organization Users ─────────────────────────────────────────────────

ALPHA_OWNER = TestUser(
    id="usr-a-owner-111111111111",
    email="owner@alpha-studio.test",
    org_id=ORG_ALPHA.id,
    role=Role.OWNER,
    description="Org owner — full access to Alpha Studio",
)

ALPHA_ADMIN = TestUser(
    id="usr-a-admin-222222222222",
    email="admin@alpha-studio.test",
    org_id=ORG_ALPHA.id,
    role=Role.ADMIN,
    description="Admin — manage resources but not billing",
)

ALPHA_EDITOR = TestUser(
    id="usr-a-editor-33333333333",
    email="editor@alpha-studio.test",
    org_id=ORG_ALPHA.id,
    role=Role.EDITOR,
    description="Editor — create/modify content",
)

ALPHA_VIEWER = TestUser(
    id="usr-a-viewer-44444444444",
    email="viewer@alpha-studio.test",
    org_id=ORG_ALPHA.id,
    role=Role.VIEWER,
    description="Viewer — read-only access",
)

# ── Beta Organization Users ───────────────────────────────────────────────────

BETA_OWNER = TestUser(
    id="usr-b-owner-555555555555",
    email="owner@beta-creative.test",
    org_id=ORG_BETA.id,
    role=Role.OWNER,
    description="Org owner — full access to Beta Creative",
)

BETA_EDITOR = TestUser(
    id="usr-b-editor-66666666666",
    email="editor@beta-creative.test",
    org_id=ORG_BETA.id,
    role=Role.EDITOR,
    description="Editor in Beta org",
)

# ── Special Identities ────────────────────────────────────────────────────────

REVOKED_USER = TestUser(
    id="usr-revoked-777777777777",
    email="revoked@alpha-studio.test",
    org_id=ORG_ALPHA.id,
    role=Role.EDITOR,
    is_active=False,
    description="Previously active user whose membership was revoked",
)

FORGED_USER = TestUser(
    id="usr-forged-888888888888",
    email="attacker@evil.test",
    org_id=ORG_ALPHA.id,  # Claims Alpha org but has no valid membership
    role=Role.ADMIN,
    description="Attacker with forged org_id claim — should be rejected",
)

SERVICE_IDENTITY = TestUser(
    id="srv-backend-worker-00000",
    email="worker@system.internal",
    org_id="",  # Service identities don't belong to a tenant
    role=Role.OWNER,  # Technically has elevated access via service_role
    description="Backend service identity (Celery worker, cron, etc.)",
)

# ── All Users (for iteration) ─────────────────────────────────────────────────

ALPHA_USERS = [ALPHA_OWNER, ALPHA_ADMIN, ALPHA_EDITOR, ALPHA_VIEWER]
BETA_USERS = [BETA_OWNER, BETA_EDITOR]
ALL_USERS = ALPHA_USERS + BETA_USERS + [REVOKED_USER, FORGED_USER, SERVICE_IDENTITY]


# =============================================================================
# Test Resources (synthetic data owned by each org)
# =============================================================================


@dataclass(frozen=True)
class TestResource:
    """A synthetic resource for cross-tenant testing."""

    id: str
    org_id: str
    resource_type: str
    name: str


# ── Alpha's Resources ─────────────────────────────────────────────────────────

ALPHA_TALENT = TestResource(
    id="talent-alpha-001",
    org_id=ORG_ALPHA.id,
    resource_type="talent",
    name="Alpha Model Sarah",
)

ALPHA_JOB = TestResource(
    id="job-alpha-001",
    org_id=ORG_ALPHA.id,
    resource_type="job",
    name="Alpha Portrait Generation",
)

ALPHA_ASSET = TestResource(
    id="asset-alpha-001",
    org_id=ORG_ALPHA.id,
    resource_type="asset",
    name="alpha_portrait_001.webp",
)

ALPHA_PROJECT = TestResource(
    id="proj-alpha-001",
    org_id=ORG_ALPHA.id,
    resource_type="project",
    name="Alpha Campaign Q1",
)

ALPHA_CREDENTIAL = TestResource(
    id="cred-alpha-vast-001",
    org_id=ORG_ALPHA.id,
    resource_type="credential",
    name="Alpha Vast.ai Key",
)

ALPHA_BRAIN_CONV = TestResource(
    id="conv-alpha-001",
    org_id=ORG_ALPHA.id,
    resource_type="brain_conversation",
    name="Alpha Strategy Session",
)

# ── Beta's Resources ──────────────────────────────────────────────────────────

BETA_TALENT = TestResource(
    id="talent-beta-001",
    org_id=ORG_BETA.id,
    resource_type="talent",
    name="Beta Model Alex",
)

BETA_JOB = TestResource(
    id="job-beta-001",
    org_id=ORG_BETA.id,
    resource_type="job",
    name="Beta Video Render",
)

BETA_ASSET = TestResource(
    id="asset-beta-001",
    org_id=ORG_BETA.id,
    resource_type="asset",
    name="beta_video_001.mp4",
)

BETA_CREDENTIAL = TestResource(
    id="cred-beta-openai-001",
    org_id=ORG_BETA.id,
    resource_type="credential",
    name="Beta OpenAI Key",
)

# ── All Resources ─────────────────────────────────────────────────────────────

ALPHA_RESOURCES = [ALPHA_TALENT, ALPHA_JOB, ALPHA_ASSET, ALPHA_PROJECT, ALPHA_CREDENTIAL, ALPHA_BRAIN_CONV]
BETA_RESOURCES = [BETA_TALENT, BETA_JOB, BETA_ASSET, BETA_CREDENTIAL]
ALL_RESOURCES = ALPHA_RESOURCES + BETA_RESOURCES


# =============================================================================
# Test Scenarios
# =============================================================================


@dataclass(frozen=True)
class IsolationScenario:
    """A cross-tenant test scenario."""

    name: str
    attacker: TestUser
    target_resource: TestResource
    operation: str  # read, write, delete, resolve
    expected_result: str  # denied, not_found, 403, 404, empty


# Pre-built adversarial scenarios
CROSS_TENANT_SCENARIOS = [
    # Beta user trying to access Alpha's resources
    IsolationScenario("beta_reads_alpha_talent", BETA_OWNER, ALPHA_TALENT, "read", "not_found"),
    IsolationScenario("beta_reads_alpha_job", BETA_OWNER, ALPHA_JOB, "read", "not_found"),
    IsolationScenario("beta_reads_alpha_asset", BETA_OWNER, ALPHA_ASSET, "read", "not_found"),
    IsolationScenario("beta_reads_alpha_credential", BETA_OWNER, ALPHA_CREDENTIAL, "read", "not_found"),
    IsolationScenario("beta_reads_alpha_brain", BETA_OWNER, ALPHA_BRAIN_CONV, "read", "not_found"),
    IsolationScenario("beta_writes_alpha_talent", BETA_EDITOR, ALPHA_TALENT, "write", "denied"),
    IsolationScenario("beta_deletes_alpha_asset", BETA_OWNER, ALPHA_ASSET, "delete", "denied"),

    # Alpha user trying to access Beta's resources
    IsolationScenario("alpha_reads_beta_talent", ALPHA_OWNER, BETA_TALENT, "read", "not_found"),
    IsolationScenario("alpha_reads_beta_credential", ALPHA_ADMIN, BETA_CREDENTIAL, "read", "not_found"),

    # Revoked user trying to access own org's resources
    IsolationScenario("revoked_reads_alpha_talent", REVOKED_USER, ALPHA_TALENT, "read", "denied"),
    IsolationScenario("revoked_writes_alpha_job", REVOKED_USER, ALPHA_JOB, "write", "denied"),

    # Forged identity trying to access
    IsolationScenario("forged_reads_alpha_talent", FORGED_USER, ALPHA_TALENT, "read", "denied"),
    IsolationScenario("forged_resolves_credential", FORGED_USER, ALPHA_CREDENTIAL, "resolve", "denied"),
]
