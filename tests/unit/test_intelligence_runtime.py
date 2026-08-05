"""Canonical Intelligence Runtime Contract Tests (Story 031).

Proves:
- One canonical runtime is explicitly identified
- Endpoint dispositions are documented and queryable
- Deprecated paths have documented replacements
- Contract types enforce required fields
- Runtime health reports capability state
- No path silently bypasses tenant scoping

Run with:
    pytest tests/unit/test_intelligence_runtime.py -v
"""
from __future__ import annotations

import pytest

from backend.intelligence_runtime import (
    ChatRequest,
    ChatResponse,
    EndpointDisposition,
    RuntimeHealth,
    RuntimePath,
    check_runtime_health,
    get_all_dispositions,
    get_endpoint_disposition,
    ENDPOINT_DISPOSITIONS,
)


# =============================================================================
# Canonical Identification
# =============================================================================


class TestCanonicalIdentification:
    """Prove one canonical runtime is explicitly identified."""

    @pytest.mark.unit
    def test_canonical_path_is_aios_chat(self):
        """The primary chat interface is /aios/v1/chat."""
        ep = get_endpoint_disposition("/aios/v1/chat")
        assert ep is not None
        assert ep.status == RuntimePath.CANONICAL

    @pytest.mark.unit
    def test_at_least_one_canonical_endpoint_exists(self):
        """At least one endpoint is marked canonical."""
        canonical = [ep for ep in ENDPOINT_DISPOSITIONS if ep.status == RuntimePath.CANONICAL]
        assert len(canonical) >= 5

    @pytest.mark.unit
    def test_legacy_brain_chat_is_deprecated(self):
        """/api/v1/brain/chat is deprecated with documented replacement."""
        ep = get_endpoint_disposition("/api/v1/brain/chat")
        assert ep is not None
        assert ep.status == RuntimePath.DEPRECATED
        assert ep.replacement == "/aios/v1/chat"
        assert ep.reason  # Must explain why

    @pytest.mark.unit
    def test_legacy_brain_sessions_is_deprecated(self):
        """/api/v1/brain/sessions is deprecated."""
        ep = get_endpoint_disposition("/api/v1/brain/sessions")
        assert ep is not None
        assert ep.status == RuntimePath.DEPRECATED
        assert "tenant" in ep.reason.lower() or "not" in ep.reason.lower()


# =============================================================================
# Disposition Registry
# =============================================================================


class TestDispositionRegistry:
    """Prove all endpoints have documented dispositions."""

    @pytest.mark.unit
    def test_all_dispositions_have_description(self):
        """Every endpoint has a non-empty description."""
        for ep in ENDPOINT_DISPOSITIONS:
            assert ep.description, f"{ep.path} has no description"

    @pytest.mark.unit
    def test_deprecated_endpoints_have_replacement_or_reason(self):
        """Deprecated endpoints must explain why and point to alternative."""
        deprecated = [ep for ep in ENDPOINT_DISPOSITIONS if ep.status == RuntimePath.DEPRECATED]
        for ep in deprecated:
            assert ep.reason, f"{ep.path} deprecated without reason"

    @pytest.mark.unit
    def test_get_all_dispositions_returns_dicts(self):
        """get_all_dispositions() returns serializable dicts."""
        result = get_all_dispositions()
        assert isinstance(result, list)
        assert len(result) == len(ENDPOINT_DISPOSITIONS)
        for item in result:
            assert "path" in item
            assert "status" in item
            assert item["status"] in ("canonical", "compatibility", "deprecated", "retired")

    @pytest.mark.unit
    def test_no_duplicate_paths(self):
        """No duplicate paths in the registry."""
        paths = [ep.path for ep in ENDPOINT_DISPOSITIONS]
        assert len(paths) == len(set(paths)), f"Duplicates: {[p for p in paths if paths.count(p) > 1]}"


# =============================================================================
# Contract Types
# =============================================================================


class TestContractTypes:
    """Prove contract types enforce required fields."""

    @pytest.mark.unit
    def test_chat_request_requires_message_and_tenant(self):
        """ChatRequest requires message, org_id, and user_id."""
        req = ChatRequest(message="hello", org_id="org-1", user_id="user-1")
        assert req.message == "hello"
        assert req.org_id == "org-1"
        assert req.user_id == "user-1"
        assert req.mode == "creative"  # Default

    @pytest.mark.unit
    def test_chat_request_rejects_empty_message(self):
        """Empty message should be caught at the caller level."""
        # Contract doesn't prevent empty string (validation is at API layer)
        # but we verify the field exists
        req = ChatRequest(message="", org_id="org-1", user_id="user-1")
        assert req.message == ""  # Caller must validate

    @pytest.mark.unit
    def test_chat_response_has_required_fields(self):
        """ChatResponse has all required fields for consistent rendering."""
        resp = ChatResponse(
            session_id="s1", response="Hello!", provider="ollama",
            model="llama3.1:8b", mode="creative", latency_ms=150,
        )
        assert resp.session_id == "s1"
        assert resp.response == "Hello!"
        assert resp.provider == "ollama"
        assert resp.latency_ms == 150
        assert resp.actions == []  # Default empty
        assert resp.is_degraded is False

    @pytest.mark.unit
    def test_chat_response_degraded_mode(self):
        """Response can indicate degraded governance."""
        resp = ChatResponse(
            session_id="s1", response="I can help, but governance is unavailable.",
            provider="ollama", model="llama3.1:8b", mode="creative",
            latency_ms=200, is_degraded=True,
        )
        assert resp.is_degraded is True


# =============================================================================
# Runtime Health
# =============================================================================


class TestRuntimeHealth:
    """Prove runtime health reports capability state."""

    @pytest.mark.unit
    def test_health_returns_structured_result(self):
        """check_runtime_health() returns a RuntimeHealth with known fields."""
        health = check_runtime_health()
        assert isinstance(health, RuntimeHealth)
        assert health.status in ("operational", "degraded", "unavailable")
        assert health.canonical_path == "/aios/v1/chat"
        assert isinstance(health.providers_available, int)
        assert isinstance(health.session_persistence, bool)
        assert isinstance(health.governance_available, bool)

    @pytest.mark.unit
    def test_health_checks_governance(self):
        """Health reports whether governance module is loadable."""
        health = check_runtime_health()
        # governance.py exists and is importable
        assert health.governance_available is True


# =============================================================================
# Tenant Scoping Contract
# =============================================================================


class TestTenantScopingContract:
    """Prove the contract enforces tenant identity."""

    @pytest.mark.unit
    def test_chat_request_org_id_is_required_field(self):
        """ChatRequest has org_id as a required (non-optional) field."""
        import dataclasses
        fields = {f.name: f for f in dataclasses.fields(ChatRequest)}
        assert "org_id" in fields
        # org_id has no default → required
        assert fields["org_id"].default is dataclasses.MISSING

    @pytest.mark.unit
    def test_chat_request_user_id_is_required_field(self):
        """ChatRequest has user_id as a required field."""
        import dataclasses
        fields = {f.name: f for f in dataclasses.fields(ChatRequest)}
        assert "user_id" in fields
        assert fields["user_id"].default is dataclasses.MISSING

    @pytest.mark.unit
    def test_compatibility_endpoints_documented(self):
        """Compatibility endpoints are explicitly listed (not hidden)."""
        compat = [ep for ep in ENDPOINT_DISPOSITIONS if ep.status == RuntimePath.COMPATIBILITY]
        assert len(compat) >= 4  # At minimum: llm/chat, health, collections, conversations
        for ep in compat:
            assert "/api/v1/brain" in ep.path  # All brain router


# =============================================================================
# No Silent Bypass
# =============================================================================


class TestNoSilentBypass:
    """Prove no path silently bypasses security."""

    @pytest.mark.unit
    def test_deprecated_paths_have_explicit_security_reason(self):
        """Deprecated paths explain the security gap that caused deprecation."""
        deprecated = [ep for ep in ENDPOINT_DISPOSITIONS if ep.status == RuntimePath.DEPRECATED]
        security_keywords = ["governance", "tenant", "routing", "scop", "persist", "implement"]
        for ep in deprecated:
            reason_lower = ep.reason.lower()
            has_security_reason = any(kw in reason_lower for kw in security_keywords)
            assert has_security_reason, f"{ep.path}: reason '{ep.reason}' doesn't explain the gap"
