"""Phase 1 credential expiry and masking tests.

Persistence migration 034 and automated credential rotation are intentionally
out of scope for Phase 1. These tests exercise the in-memory credential record
and resolution contract only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.credentials import (
    CredentialService,
    CredentialStatus,
    ProviderType,
    _credential_audit,
    _store,
)

ORG_ID = "org-phase-one"
SECRET = "user-api-key-secret-value"


@pytest.fixture(autouse=True)
def clean_store() -> None:
    """Clear credential records and audit entries between tests."""
    _store.clear()
    _credential_audit.clear()
    yield
    _store.clear()
    _credential_audit.clear()


def _future_expiry() -> str:
    """Return a timezone-aware expiry safely in the future."""
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


@pytest.mark.unit
def test_user_api_key_provider_type_is_supported() -> None:
    """The generic user API key provider has a stable serialized value."""
    assert ProviderType.USER_API_KEY.value == "user_api_key"


@pytest.mark.unit
def test_active_future_expiry_resolves_and_is_masked() -> None:
    """An active credential with a valid future expiry resolves normally."""
    result = CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret=SECRET,
        expires_at=_future_expiry(),
        metadata={"label": "customer key", "private_note": SECRET},
        actor="test",
    )

    assert CredentialService.resolve(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        actor="worker",
    ) == SECRET
    assert result["expires_at"] is not None
    assert SECRET not in str(result)
    assert "encrypted_secret" not in result
    assert "metadata" not in result


@pytest.mark.unit
def test_null_expiry_remains_active() -> None:
    """A null expiry preserves the existing non-expiring credential behavior."""
    result = CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret=SECRET,
        expires_at=None,
        actor="test",
    )

    assert result["expires_at"] is None
    assert CredentialService.resolve(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
    ) == SECRET


@pytest.mark.unit
def test_expired_credential_is_inactive() -> None:
    """An active record whose expiry is in the past cannot be resolved."""
    CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret=SECRET,
        expires_at="2000-01-01T00:00:00+00:00",
        actor="test",
    )

    assert CredentialService._find_active(
        ORG_ID, ProviderType.USER_API_KEY, "production"
    ) is None
    assert CredentialService.resolve(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
    ) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "expires_at",
    ["not-a-timestamp", "", "2027-01-01T00:00:00"],
)
def test_malformed_or_ambiguous_expiry_fails_closed(expires_at: str) -> None:
    """Malformed and timezone-naive expiry values are treated as inactive."""
    CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret=SECRET,
        expires_at=expires_at,
        actor="test",
    )

    assert CredentialService.resolve(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
    ) is None


@pytest.mark.unit
def test_revoked_credential_is_inactive() -> None:
    """Revocation remains immediate even when expiry metadata is present."""
    CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret=SECRET,
        expires_at=_future_expiry(),
        actor="test",
    )

    assert CredentialService.revoke(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        actor="admin",
    ) is True
    assert CredentialService.resolve(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
    ) is None


@pytest.mark.unit
def test_rotated_credential_is_inactive_and_new_version_resolves() -> None:
    """Rotation marks the old record inactive and resolves the new version."""
    CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret="old-secret-value",
        expires_at=_future_expiry(),
        actor="test",
    )
    CredentialService.rotate(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        new_secret="new-secret-value",
        actor="admin",
    )

    records = [record for record in _store.values() if record.org_id == ORG_ID]
    assert [record.status for record in records].count(CredentialStatus.ROTATED) == 1
    assert CredentialService.resolve(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
    ) == "new-secret-value"


@pytest.mark.unit
@given(
    status=st.sampled_from(list(CredentialStatus)),
    expiry_kind=st.sampled_from(["null", "future", "expired", "malformed"]),
)
@settings(max_examples=20)
def test_only_active_non_expired_records_resolve(
    status: CredentialStatus,
    expiry_kind: str,
) -> None:
    """**Validates: Requirements 2.17, 3.1, 3.13**

    Across lifecycle statuses and expiry encodings, only active records with
    null or future expiry are eligible for resolution.
    """
    _store.clear()
    _credential_audit.clear()
    expiry_by_kind = {
        "null": None,
        "future": _future_expiry(),
        "expired": "2000-01-01T00:00:00+00:00",
        "malformed": "not-a-timestamp",
    }
    CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret=SECRET,
        expires_at=expiry_by_kind[expiry_kind],
        actor="test",
    )
    record = next(iter(_store.values()))
    record.status = status

    expected = (
        SECRET
        if status == CredentialStatus.ACTIVE and expiry_kind in {"null", "future"}
        else None
    )
    assert CredentialService.resolve(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
    ) == expected


@pytest.mark.unit
def test_status_metadata_discloses_expiry_but_never_secret() -> None:
    """Masked status includes expiry metadata without plaintext or ciphertext."""
    CredentialService.store(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
        secret=SECRET,
        expires_at=_future_expiry(),
        metadata={"private_note": SECRET},
        actor="test",
    )

    status = CredentialService.get_status(
        org_id=ORG_ID,
        provider=ProviderType.USER_API_KEY,
    )[0]
    status_text = str(status)
    assert status["expires_at"] is not None
    assert SECRET not in status_text
    assert "encrypted_secret" not in status_text
    assert "private_note" not in status_text
    assert "encrypted_secret" not in status
