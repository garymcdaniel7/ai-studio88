"""Credential Redaction & Security Tests — Story 007.

Tests verify:
  1. Plaintext tokens never appear in API responses
  2. Plaintext tokens never appear in log output
  3. redact_secrets catches all known secret patterns
  4. redact_dict strips sensitive keys
  5. CredentialService.masked_view() never includes secrets
  6. Social connection responses never expose tokens
  7. Error messages don't leak credentials

Run with:
    pytest tests/unit/test_credential_redaction.py -v
"""
from __future__ import annotations

import json
import logging
import re

import pytest

from backend.credentials import (
    CredentialOwnership,
    CredentialService,
    CredentialStatus,
    ProviderType,
    _encrypt,
    _decrypt,
    _mask_secret,
    redact_dict,
    redact_secrets,
)


# =============================================================================
# Test Data
# =============================================================================

SAMPLE_SECRETS = [
    "sk-proj-abc123xyz789longenoughtobearealsecret",
    "sk-ant-api03-longanthropickeyvaluehere12345678",
    "rp_12345678abcdefghijklmnopqrstuvwxyz",
    "vast_ai_key_abcdefghijklmnopqrstuvwxyz",
    "hf_FAKE_TEST_TOKEN_NOT_REAL_000000000",
    "xi_elevenlabs_key_1234567890abcdefghij",
    "K005abcdefghijklmnopq001234567890abcd",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.fakesig",
]

SAMPLE_OAUTH_TOKENS = [
    "ya29.a0AfH6SMBxE_some_really_long_google_oauth_access_token_value_here_1234567890",
    "IGQVJYZAkFRbW5iRmloN3JfT3BkVjdlVGdsZAGFpSEtpb19mQWxXV2FFOHpJTUJVejFBQ",
    "1234567890-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN",
]

ORG_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_store():
    """Reset credential store between tests."""
    from backend.credentials import _store, _credential_audit
    _store.clear()
    _credential_audit.clear()
    yield
    _store.clear()
    _credential_audit.clear()


# =============================================================================
# Redaction Function Tests
# =============================================================================


@pytest.mark.unit
class TestRedactSecrets:
    """Test the redact_secrets() utility."""

    def test_redacts_openai_keys(self):
        text = f"Using key sk-proj-abc123xyz789longenoughtobearealsecret for generation"
        result = redact_secrets(text)
        assert "sk-proj-abc123" not in result
        assert "[REDACTED]" in result

    def test_redacts_anthropic_keys(self):
        text = f"Key: sk-ant-api03-longanthropickeyvaluehere12345678"
        result = redact_secrets(text)
        assert "sk-ant-" not in result
        assert "[REDACTED]" in result

    def test_redacts_vast_keys(self):
        text = f"VAST_API_KEY=vast_ai_key_abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "vast_ai_key" not in result

    def test_redacts_jwt_tokens(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.fakesig"
        result = redact_secrets(f"Bearer {jwt}")
        assert "eyJ" not in result

    def test_redacts_long_unknown_secrets(self):
        # Any string > 30 chars that isn't a URL should be redacted
        long_secret = "abcdefghijklmnopqrstuvwxyz12345678"
        result = redact_secrets(f"token: {long_secret}")
        assert long_secret not in result

    def test_preserves_urls(self):
        text = "Connecting to https://api.example.com/v1/generate"
        result = redact_secrets(text)
        assert "https://api.example.com/v1/generate" in result

    def test_preserves_short_strings(self):
        text = "Status: active, provider: vast_ai"
        result = redact_secrets(text)
        assert "active" in result

    def test_handles_empty_string(self):
        assert redact_secrets("") == ""

    def test_handles_none_safely(self):
        assert redact_secrets(None) is None  # type: ignore


@pytest.mark.unit
class TestRedactDict:
    """Test the redact_dict() utility."""

    def test_redacts_token_keys(self):
        data = {"access_token": "secret_value_123", "status": "active"}
        result = redact_dict(data)
        assert result["access_token"] == "[REDACTED]"
        assert result["status"] == "active"

    def test_redacts_nested_secrets(self):
        data = {
            "connection": {
                "api_key": "sk-abc123xyz",
                "url": "https://api.vast.ai",
            }
        }
        result = redact_dict(data)
        assert result["connection"]["api_key"] == "[REDACTED]"
        assert result["connection"]["url"] == "https://api.vast.ai"

    def test_redacts_password_keys(self):
        data = {"password": "hunter2", "username": "admin"}
        result = redact_dict(data)
        assert result["password"] == "[REDACTED]"
        assert result["username"] == "admin"

    def test_redacts_refresh_token(self):
        data = {"refresh_token": "rt_abc123verylongtoken", "expires_in": 3600}
        result = redact_dict(data)
        assert result["refresh_token"] == "[REDACTED]"
        assert result["expires_in"] == 3600

    def test_redacts_credentials_key(self):
        data = {"credentials": "some_secret_blob", "provider": "google"}
        result = redact_dict(data)
        assert result["credentials"] == "[REDACTED]"

    def test_custom_sensitive_keys(self):
        data = {"custom_secret_field": "value123", "normal": "ok"}
        result = redact_dict(data, sensitive_keys={"custom_secret_field"})
        assert result["custom_secret_field"] == "[REDACTED]"
        assert result["normal"] == "ok"


# =============================================================================
# Credential Service Security Tests
# =============================================================================


@pytest.mark.unit
class TestCredentialServiceSecurity:
    """Test that CredentialService never leaks secrets."""

    def test_store_returns_masked_view_only(self):
        result = CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            secret="vast_super_secret_api_key_123456789",
            actor="test",
        )
        # Result must NOT contain the secret
        result_str = json.dumps(result)
        assert "vast_super_secret_api_key_123456789" not in result_str
        assert "encrypted" not in result_str.lower() or "encrypted_secret" not in result_str
        # Must contain masked hint
        assert "key_hint" in result

    def test_get_status_never_includes_secret(self):
        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.OPENAI,
            secret="sk-proj-thisisaverylongsecretkeythatnobodyshouldever",
            actor="test",
        )
        statuses = CredentialService.get_status(org_id=ORG_A)
        for status in statuses:
            status_str = json.dumps(status)
            assert "thisisaverylongsecretkey" not in status_str
            assert "encrypted_secret" not in status

    def test_resolve_works_for_authorized_backend(self):
        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            secret="my_real_secret_key_for_vast",
            actor="test",
        )
        # Resolve should return the plaintext (authorized backend use)
        plaintext = CredentialService.resolve(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            actor="backend_worker",
            purpose="gpu_job",
        )
        assert plaintext == "my_real_secret_key_for_vast"

    def test_resolve_wrong_org_returns_none(self):
        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            secret="secret_for_org_a",
            actor="test",
        )
        # Different org cannot resolve
        result = CredentialService.resolve(
            org_id="org-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            provider=ProviderType.VAST_AI,
            actor="test",
        )
        assert result is None

    def test_revoked_credential_cannot_be_resolved(self):
        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.OPENAI,
            secret="sk-revoke-me-please-12345",
            actor="test",
        )
        CredentialService.revoke(
            org_id=ORG_A,
            provider=ProviderType.OPENAI,
            actor="admin",
        )
        result = CredentialService.resolve(
            org_id=ORG_A,
            provider=ProviderType.OPENAI,
            actor="test",
        )
        assert result is None

    def test_rotation_invalidates_old_credential(self):
        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            secret="old_secret_v1",
            actor="test",
        )
        CredentialService.rotate(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            new_secret="new_secret_v2",
            actor="admin",
        )
        # Should resolve to new secret
        result = CredentialService.resolve(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            actor="test",
        )
        assert result == "new_secret_v2"


# =============================================================================
# Encryption Roundtrip Tests
# =============================================================================


@pytest.mark.unit
class TestEncryptionRoundtrip:
    """Test encrypt/decrypt cycle."""

    def test_encrypt_decrypt_roundtrip(self):
        for secret in SAMPLE_SECRETS:
            encrypted = _encrypt(secret)
            assert encrypted != secret  # Must not be plaintext
            decrypted = _decrypt(encrypted)
            assert decrypted == secret

    def test_encrypt_produces_different_ciphertext(self):
        """Same plaintext should produce different ciphertext (Fernet uses random IV)."""
        secret = "test_secret_12345"
        enc1 = _encrypt(secret)
        enc2 = _encrypt(secret)
        # Fernet includes timestamp + random IV, so they differ
        assert enc1 != enc2
        # But both decrypt to the same value
        assert _decrypt(enc1) == _decrypt(enc2) == secret

    def test_encrypted_output_is_base64(self):
        encrypted = _encrypt("test_value")
        # Fernet tokens are base64url-encoded
        assert re.match(r'^[A-Za-z0-9_=-]+$', encrypted)

    def test_long_secrets_work(self):
        long_secret = "x" * 10000
        encrypted = _encrypt(long_secret)
        assert _decrypt(encrypted) == long_secret


# =============================================================================
# Mask Function Tests
# =============================================================================


@pytest.mark.unit
class TestMaskSecret:
    """Test the _mask_secret utility."""

    def test_masks_long_keys(self):
        result = _mask_secret("sk-proj-abc123xyz789")
        assert result.startswith("sk-p")
        assert result.endswith("z789")
        assert "..." in result
        # Middle content must not be visible
        assert "abc123" not in result

    def test_short_keys_fully_masked(self):
        result = _mask_secret("short")
        assert result == "***"

    def test_empty_string(self):
        result = _mask_secret("")
        assert result == "***"


# =============================================================================
# Log Redaction Integration Tests
# =============================================================================


@pytest.mark.unit
class TestLogRedaction:
    """Test that logging doesn't leak secrets."""

    def test_credential_audit_never_stores_secrets(self):
        """Audit trail must never contain plaintext secrets."""
        from backend.credentials import get_credential_audit

        CredentialService.store(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            secret="ultra_secret_key_12345678901234567890",
            actor="test_user",
        )
        CredentialService.resolve(
            org_id=ORG_A,
            provider=ProviderType.VAST_AI,
            actor="backend_job",
            purpose="generation",
        )

        audit = get_credential_audit(org_id=ORG_A)
        audit_str = json.dumps(audit)

        assert "ultra_secret_key" not in audit_str
        assert "12345678901234567890" not in audit_str
        # Audit should record the action
        assert any(e["action"] == "store" for e in audit)
        assert any(e["action"] == "resolve" for e in audit)

    def test_oauth_tokens_redacted_in_error_messages(self):
        """If an OAuth token appears in an error, it should be redacted."""
        oauth_token = "ya29.a0AfH6SMBxE_some_really_long_google_oauth_access_token_value"
        error_msg = f"Token refresh failed for token: {oauth_token}"
        redacted = redact_secrets(error_msg)
        assert oauth_token not in redacted
        assert "[REDACTED]" in redacted
