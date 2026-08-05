"""Credential Service Tests (Story 023).

Proves workspace isolation, encryption, masking, rotation, revocation,
audit trail, and secret leak prevention.

Run with:
    pytest tests/unit/test_credentials.py -v
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from backend.credentials import (
    CredentialOwnership,
    CredentialService,
    CredentialStatus,
    ProviderType,
    _credential_audit,
    _store,
    get_credential_audit,
    redact_dict,
    redact_secrets,
)


ORG_A = str(uuid4())
ORG_B = str(uuid4())


@pytest.fixture(autouse=True)
def clean_store():
    """Clear credential store and audit between tests."""
    _store.clear()
    _credential_audit.clear()
    yield
    _store.clear()
    _credential_audit.clear()


# =============================================================================
# Workspace Isolation
# =============================================================================


class TestWorkspaceIsolation:
    """Prove credentials are scoped to their workspace."""

    @pytest.mark.unit
    def test_store_and_resolve_same_org(self):
        """Org A can store and resolve its own credential."""
        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            secret="vast_ai_key_12345678",
            actor="user-a",
        )
        result = CredentialService.resolve(
            org_id=ORG_A, provider=ProviderType.VAST_AI, actor="user-a"
        )
        assert result == "vast_ai_key_12345678"

    @pytest.mark.unit
    def test_cross_org_resolve_returns_none(self):
        """Org B cannot resolve Org A's credential."""
        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            secret="vast_secret_org_a",
            actor="user-a",
        )
        result = CredentialService.resolve(
            org_id=ORG_B, provider=ProviderType.VAST_AI, actor="user-b"
        )
        # Should NOT find org_a's credential
        assert result is None or result != "vast_secret_org_a"

    @pytest.mark.unit
    def test_get_status_scoped_to_org(self):
        """Status listing only shows own org's credentials."""
        CredentialService.store(org_id=ORG_A, provider=ProviderType.OPENAI, secret="sk-aaa", actor="a")
        CredentialService.store(org_id=ORG_B, provider=ProviderType.OPENAI, secret="sk-bbb", actor="b")

        status_a = CredentialService.get_status(org_id=ORG_A)
        status_b = CredentialService.get_status(org_id=ORG_B)

        assert len(status_a) == 1
        assert len(status_b) == 1
        assert status_a[0]["org_id"] == ORG_A
        assert status_b[0]["org_id"] == ORG_B

    @pytest.mark.unit
    def test_different_providers_independent(self):
        """Same org can have credentials for different providers."""
        CredentialService.store(org_id=ORG_A, provider=ProviderType.VAST_AI, secret="vast_key", actor="a")
        CredentialService.store(org_id=ORG_A, provider=ProviderType.RUNPOD, secret="rp_key", actor="a")

        vast = CredentialService.resolve(org_id=ORG_A, provider=ProviderType.VAST_AI, actor="a")
        runpod = CredentialService.resolve(org_id=ORG_A, provider=ProviderType.RUNPOD, actor="a")

        assert vast == "vast_key"
        assert runpod == "rp_key"


# =============================================================================
# Encryption & Masking
# =============================================================================


class TestEncryptionMasking:
    """Prove secrets are encrypted and masked."""

    @pytest.mark.unit
    def test_stored_secret_is_encrypted(self):
        """The stored record contains encrypted material, not plaintext."""
        CredentialService.store(
            org_id=ORG_A, provider=ProviderType.OPENAI, secret="sk-real-secret-value", actor="a"
        )
        # Get the raw stored record
        record = list(_store.values())[0]
        assert record.encrypted_secret != "sk-real-secret-value"
        assert "sk-real-secret-value" not in record.encrypted_secret
        assert len(record.encrypted_secret) > 50  # Fernet output is long

    @pytest.mark.unit
    def test_masked_view_never_contains_secret(self):
        """masked_view() never exposes the secret."""
        result = CredentialService.store(
            org_id=ORG_A, provider=ProviderType.ANTHROPIC, secret="sk-ant-super-secret-key", actor="a"
        )
        # Result is the masked view
        assert "sk-ant-super-secret-key" not in str(result)
        assert "encrypted" not in str(result)
        assert "key_hint" in result
        # Mask: first 4 chars + ... + last 4 chars
        assert result["key_hint"] == "sk-a...-key"

    @pytest.mark.unit
    def test_status_never_exposes_secret(self):
        """get_status() never includes encrypted or plaintext secrets."""
        CredentialService.store(
            org_id=ORG_A, provider=ProviderType.VAST_AI, secret="vast_ai_xxxx_yyyy", actor="a"
        )
        status = CredentialService.get_status(org_id=ORG_A)
        for cred in status:
            assert "secret" not in str(cred).lower() or "encrypted_secret" not in cred
            assert "vast_ai_xxxx_yyyy" not in str(cred)


# =============================================================================
# Rotation
# =============================================================================


class TestRotation:
    """Prove rotation creates new version and marks old as rotated."""

    @pytest.mark.unit
    def test_rotate_creates_new_version(self):
        """Rotation increments version and old becomes 'rotated'."""
        CredentialService.store(
            org_id=ORG_A, provider=ProviderType.VAST_AI, secret="old_key_v1", actor="a"
        )
        CredentialService.rotate(
            org_id=ORG_A, provider=ProviderType.VAST_AI, new_secret="new_key_v2", actor="a"
        )

        # Active credential should be the new one
        resolved = CredentialService.resolve(org_id=ORG_A, provider=ProviderType.VAST_AI, actor="a")
        assert resolved == "new_key_v2"

        # Old should be marked rotated
        all_records = [r for r in _store.values() if r.org_id == ORG_A]
        rotated = [r for r in all_records if r.status == CredentialStatus.ROTATED]
        assert len(rotated) == 1

    @pytest.mark.unit
    def test_rotate_preserves_history(self):
        """Both old and new credential records exist after rotation."""
        CredentialService.store(org_id=ORG_A, provider=ProviderType.OPENAI, secret="v1", actor="a")
        CredentialService.rotate(org_id=ORG_A, provider=ProviderType.OPENAI, new_secret="v2", actor="a")
        CredentialService.rotate(org_id=ORG_A, provider=ProviderType.OPENAI, new_secret="v3", actor="a")

        all_openai = [r for r in _store.values() if r.provider == ProviderType.OPENAI]
        assert len(all_openai) == 3
        active = [r for r in all_openai if r.status == CredentialStatus.ACTIVE]
        assert len(active) == 1
        assert active[0].version == 3


# =============================================================================
# Revocation
# =============================================================================


class TestRevocation:
    """Prove revocation is immediate and irreversible."""

    @pytest.mark.unit
    def test_revoke_makes_credential_unresolvable(self):
        """After revocation, resolve returns None."""
        CredentialService.store(
            org_id=ORG_A, provider=ProviderType.RUNPOD, secret="rp_secret", actor="a"
        )
        assert CredentialService.resolve(org_id=ORG_A, provider=ProviderType.RUNPOD, actor="a") == "rp_secret"

        CredentialService.revoke(org_id=ORG_A, provider=ProviderType.RUNPOD, actor="a")

        result = CredentialService.resolve(org_id=ORG_A, provider=ProviderType.RUNPOD, actor="a")
        # Should fall through to env var or None
        assert result != "rp_secret"

    @pytest.mark.unit
    def test_revoke_wipes_encrypted_material(self):
        """Revocation clears the encrypted blob."""
        CredentialService.store(org_id=ORG_A, provider=ProviderType.ELEVENLABS, secret="xi_key", actor="a")
        CredentialService.revoke(org_id=ORG_A, provider=ProviderType.ELEVENLABS, actor="a")

        revoked = [r for r in _store.values() if r.status == CredentialStatus.REVOKED]
        assert len(revoked) == 1
        assert revoked[0].encrypted_secret == ""

    @pytest.mark.unit
    def test_revoke_nonexistent_returns_false(self):
        """Revoking when no credential exists returns False."""
        result = CredentialService.revoke(org_id=ORG_A, provider=ProviderType.KLING, actor="a")
        assert result is False


# =============================================================================
# Validation
# =============================================================================


class TestValidation:
    """Prove validation checks without logging secrets."""

    @pytest.mark.unit
    def test_validate_active_credential(self):
        """Valid active credential returns valid=True."""
        CredentialService.store(org_id=ORG_A, provider=ProviderType.OPENAI, secret="sk-valid-key-12345", actor="a")
        result = CredentialService.validate(org_id=ORG_A, provider=ProviderType.OPENAI, actor="a")
        assert result["valid"] is True

    @pytest.mark.unit
    def test_validate_missing_credential(self):
        """Missing credential returns valid=False."""
        result = CredentialService.validate(org_id=ORG_A, provider=ProviderType.KLING, actor="a")
        assert result["valid"] is False
        assert result["reason"] == "no_credential_found"

    @pytest.mark.unit
    def test_validate_revoked_credential(self):
        """Revoked credential returns valid=False."""
        CredentialService.store(org_id=ORG_A, provider=ProviderType.VAST_AI, secret="vast_key", actor="a")
        CredentialService.revoke(org_id=ORG_A, provider=ProviderType.VAST_AI, actor="a")
        result = CredentialService.validate(org_id=ORG_A, provider=ProviderType.VAST_AI, actor="a")
        assert result["valid"] is False


# =============================================================================
# Audit Trail
# =============================================================================


class TestAuditTrail:
    """Prove all operations are audited."""

    @pytest.mark.unit
    def test_store_produces_audit(self):
        CredentialService.store(org_id=ORG_A, provider=ProviderType.VAST_AI, secret="key", actor="user-1")
        audit = get_credential_audit(org_id=ORG_A)
        assert len(audit) >= 1
        assert audit[0]["action"] == "store"
        assert audit[0]["actor"] == "user-1"

    @pytest.mark.unit
    def test_resolve_produces_audit(self):
        CredentialService.store(org_id=ORG_A, provider=ProviderType.OPENAI, secret="sk-x", actor="a")
        CredentialService.resolve(org_id=ORG_A, provider=ProviderType.OPENAI, actor="job-runner", purpose="generation")
        audit = get_credential_audit(org_id=ORG_A)
        resolve_events = [e for e in audit if e["action"] == "resolve"]
        assert len(resolve_events) == 1
        assert resolve_events[0]["actor"] == "job-runner"

    @pytest.mark.unit
    def test_revoke_produces_audit(self):
        CredentialService.store(org_id=ORG_A, provider=ProviderType.RUNPOD, secret="rp", actor="a")
        CredentialService.revoke(org_id=ORG_A, provider=ProviderType.RUNPOD, actor="admin-1")
        audit = get_credential_audit(org_id=ORG_A)
        revoke_events = [e for e in audit if e["action"] == "revoke"]
        assert len(revoke_events) == 1
        assert revoke_events[0]["actor"] == "admin-1"


# =============================================================================
# Redaction / Leak Prevention
# =============================================================================


class TestRedaction:
    """Prove secrets are redacted from text and dicts."""

    @pytest.mark.unit
    def test_redact_secrets_from_text(self):
        text = "Error: Invalid API key sk-ant-abc123456789012345678901234567890"
        redacted = redact_secrets(text)
        assert "sk-ant-abc" not in redacted
        assert "[REDACTED]" in redacted

    @pytest.mark.unit
    def test_redact_dict_sensitive_keys(self):
        data = {
            "provider": "vast_ai",
            "api_key": "vast_real_secret_key_value_123456",
            "status": "connected",
            "config": {"token": "hf_abcdef123456", "model": "flux"},
        }
        redacted = redact_dict(data)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["config"]["token"] == "[REDACTED]"
        assert redacted["provider"] == "vast_ai"  # Non-sensitive preserved
        assert redacted["status"] == "connected"

    @pytest.mark.unit
    def test_redact_long_strings_that_look_like_keys(self):
        text = "Connection failed with key eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_long_token_value"
        redacted = redact_secrets(text)
        assert "eyJhbGci" not in redacted

    @pytest.mark.unit
    def test_empty_and_short_strings_not_redacted(self):
        assert redact_secrets("") == ""
        assert redact_secrets("hello world") == "hello world"
        assert redact_secrets("ok") == "ok"
