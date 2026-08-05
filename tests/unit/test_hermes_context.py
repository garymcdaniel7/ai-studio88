"""Hermes Application Context Envelope Tests (Story 037).

Proves: schema versioning, authoritative resolution, resource validation,
graceful degradation, cross-workspace rejection, and contract correctness.

Run with:
    pytest tests/unit/test_hermes_context.py -v
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from backend.hermes_context import (
    CONTEXT_SCHEMA_VERSION,
    ApplicationContext,
    AuthoritativeContext,
    ClientContext,
    ContextResolutionError,
    ValidationResult,
    _derive_capabilities,
    _parse_client_context,
    _safe_id,
    resolve_context,
)

ORG = str(uuid4())
USER = str(uuid4())


# =============================================================================
# Schema Versioning
# =============================================================================


class TestSchemaVersioning:

    @pytest.mark.unit
    def test_current_version_accepted(self):
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="editor",
            schema_version=CONTEXT_SCHEMA_VERSION,
        )
        assert ctx.schema_version == CONTEXT_SCHEMA_VERSION

    @pytest.mark.unit
    def test_unsupported_version_raises(self):
        with pytest.raises(ContextResolutionError, match="Unsupported"):
            resolve_context(
                user_id=USER, org_id=ORG, role="editor",
                schema_version=999,
            )

    @pytest.mark.unit
    def test_version_is_integer(self):
        ctx = resolve_context(user_id=USER, org_id=ORG, role="viewer")
        assert isinstance(ctx.schema_version, int)


# =============================================================================
# Authoritative Context (Server-Derived)
# =============================================================================


class TestAuthoritativeContext:

    @pytest.mark.unit
    def test_identity_from_server_params(self):
        """Authoritative fields come from server, not client."""
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="admin", email="test@x.com",
            client_context={"user_id": "SPOOFED", "org_id": "SPOOFED"},
        )
        assert ctx.authoritative.user_id == USER
        assert ctx.authoritative.org_id == ORG
        assert ctx.authoritative.role == "admin"
        assert ctx.authoritative.email == "test@x.com"

    @pytest.mark.unit
    def test_capabilities_derived_from_role(self):
        """Capabilities are computed server-side from role."""
        ctx = resolve_context(user_id=USER, org_id=ORG, role="owner")
        caps = ctx.authoritative.capabilities
        assert "chat" in caps
        assert "generate_image" in caps
        assert "manage_credentials" in caps
        assert "billing" in caps

    @pytest.mark.unit
    def test_viewer_limited_capabilities(self):
        """Viewer gets minimal capabilities."""
        ctx = resolve_context(user_id=USER, org_id=ORG, role="viewer")
        caps = ctx.authoritative.capabilities
        assert "chat" in caps
        assert "generate_image" not in caps
        assert "manage_credentials" not in caps


# =============================================================================
# Client Context Parsing
# =============================================================================


class TestClientContextParsing:

    @pytest.mark.unit
    def test_valid_client_context_parsed(self):
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="editor",
            client_context={
                "current_route": "/create",
                "active_project_id": "proj-123",
                "selected_talent_id": "talent-456",
                "ui_mode": "create",
                "locale": "en-US",
            },
        )
        assert ctx.client.current_route == "/create"
        assert ctx.client.active_project_id == "proj-123"
        assert ctx.client.selected_talent_id == "talent-456"
        assert ctx.client.ui_mode == "create"
        assert ctx.client.locale == "en-US"

    @pytest.mark.unit
    def test_missing_client_context_uses_defaults(self):
        """Missing optional context doesn't break resolution."""
        ctx = resolve_context(user_id=USER, org_id=ORG, role="editor")
        assert ctx.client.current_route == ""
        assert ctx.client.active_project_id is None
        assert ctx.client.ui_mode == ""
        assert ctx.client.locale == "en"

    @pytest.mark.unit
    def test_long_route_truncated(self):
        """Oversized strings are truncated for safety."""
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="editor",
            client_context={"current_route": "x" * 500},
        )
        assert len(ctx.client.current_route) <= 100

    @pytest.mark.unit
    def test_injection_in_ids_rejected(self):
        """IDs containing SQL/script injection are rejected."""
        assert _safe_id("'; DROP TABLE talent; --") is None
        assert _safe_id('"><script>') is None
        assert _safe_id("normal-uuid-123") == "normal-uuid-123"

    @pytest.mark.unit
    def test_asset_ids_limited(self):
        """At most 10 asset IDs are accepted."""
        raw = {"selected_asset_ids": [f"asset-{i}" for i in range(20)]}
        client = _parse_client_context(raw)
        assert len(client.selected_asset_ids) <= 10


# =============================================================================
# Resource Validation
# =============================================================================


class TestResourceValidation:

    @pytest.mark.unit
    def test_no_resources_no_validation(self):
        """Empty client context produces empty validation."""
        ctx = resolve_context(user_id=USER, org_id=ORG, role="editor")
        assert not ctx.validation.has_issues
        assert ctx.validation.valid_resources == {}

    @pytest.mark.unit
    def test_validation_result_structure(self):
        """ValidationResult has expected fields."""
        vr = ValidationResult()
        assert vr.valid_resources == {}
        assert vr.invalid_resources == {}
        assert vr.warnings == []
        assert vr.has_issues is False

    @pytest.mark.unit
    def test_invalid_resource_reported(self):
        """Invalid resources are flagged but don't block."""
        vr = ValidationResult(
            invalid_resources={"active_project_id": "not_found_or_wrong_workspace"}
        )
        assert vr.has_issues is True


# =============================================================================
# Prompt Context Output
# =============================================================================


class TestPromptContextOutput:

    @pytest.mark.unit
    def test_to_prompt_context_includes_role(self):
        """Prompt context includes workspace role."""
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="admin",
            client_context={"current_route": "/brain", "ui_mode": "creative"},
        )
        prompt_ctx = ctx.to_prompt_context()
        assert prompt_ctx["workspace_role"] == "admin"
        assert prompt_ctx["current_route"] == "/brain"
        assert prompt_ctx["ui_mode"] == "creative"

    @pytest.mark.unit
    def test_to_prompt_context_excludes_secrets(self):
        """Prompt context never includes user_id, org_id, or email."""
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="owner", email="secret@x.com",
        )
        prompt_ctx = ctx.to_prompt_context()
        ctx_str = str(prompt_ctx)
        assert USER not in ctx_str
        assert ORG not in ctx_str
        assert "secret@x.com" not in ctx_str

    @pytest.mark.unit
    def test_to_prompt_context_includes_validated_resources(self):
        """Validated resources appear in prompt context."""
        ctx = resolve_context(user_id=USER, org_id=ORG, role="editor")
        ctx.validation.valid_resources = {"active_project_id": "proj-abc"}
        prompt_ctx = ctx.to_prompt_context()
        assert prompt_ctx["active_resources"]["active_project_id"] == "proj-abc"

    @pytest.mark.unit
    def test_to_prompt_context_includes_warnings(self):
        """Context warnings are visible to Hermes for user communication."""
        ctx = resolve_context(user_id=USER, org_id=ORG, role="editor")
        ctx.validation.warnings = ["resource_validation_skipped:no_db"]
        prompt_ctx = ctx.to_prompt_context()
        assert "context_warnings" in prompt_ctx


# =============================================================================
# Graceful Degradation
# =============================================================================


class TestGracefulDegradation:

    @pytest.mark.unit
    def test_null_client_context_works(self):
        """None client_context produces valid context with defaults."""
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="viewer",
            client_context=None,
        )
        assert ctx.client.current_route == ""
        assert ctx.authoritative.user_id == USER

    @pytest.mark.unit
    def test_empty_dict_client_context_works(self):
        """Empty dict produces valid context."""
        ctx = resolve_context(
            user_id=USER, org_id=ORG, role="editor",
            client_context={},
        )
        assert ctx.schema_version == CONTEXT_SCHEMA_VERSION
        assert ctx.authoritative.org_id == ORG

    @pytest.mark.unit
    def test_request_id_generated(self):
        """Every context gets a unique request_id."""
        ctx1 = resolve_context(user_id=USER, org_id=ORG, role="editor")
        ctx2 = resolve_context(user_id=USER, org_id=ORG, role="editor")
        assert ctx1.request_id != ctx2.request_id
        assert ctx1.request_id.startswith("ctx-")


# =============================================================================
# Capability Derivation
# =============================================================================


class TestCapabilityDerivation:

    @pytest.mark.unit
    def test_role_hierarchy(self):
        viewer_caps = set(_derive_capabilities("viewer"))
        editor_caps = set(_derive_capabilities("editor"))
        admin_caps = set(_derive_capabilities("admin"))
        owner_caps = set(_derive_capabilities("owner"))

        # Each higher role includes all lower capabilities
        assert viewer_caps.issubset(editor_caps)
        assert editor_caps.issubset(admin_caps)
        assert admin_caps.issubset(owner_caps)

    @pytest.mark.unit
    def test_unknown_role_gets_base_only(self):
        caps = _derive_capabilities("unknown_role")
        assert "chat" in caps
        assert "generate_image" not in caps
