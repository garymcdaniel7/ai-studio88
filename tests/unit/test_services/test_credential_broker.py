"""Unit tests for the Credential Broker service.

Tests cover: R8.1 (scoped issuance), R8.2 (expiration calculation),
R8.3 (revocation), R8.4 (no long-lived credentials), R8.5 (scope violation).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.app.services.credential_broker import (
    CREDENTIAL_GRACE_PERIOD_SECONDS,
    MAX_CREDENTIAL_LIFETIME_SECONDS,
    CredentialBroker,
    CredentialBrokerError,
    CredentialExpiredError,
    CredentialIssuanceError,
    CredentialNotFoundError,
    CredentialRevokedError,
    CredentialScopeViolationError,
    JobCredential,
    StorageOperation,
    StorageProvider,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def broker() -> CredentialBroker:
    """Create a fresh CredentialBroker instance."""
    return CredentialBroker()


@pytest.fixture
def sample_job_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_org_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_paths() -> list[str]:
    return ["/org_abc123/images/talent_xyz/job_456"]


# =============================================================================
# Tests: issue_job_credential (R8.1, R8.2)
# =============================================================================


@pytest.mark.unit
class TestIssueJobCredential:
    """Test credential issuance — R8.1, R8.2."""

    def test_issue_returns_job_credential(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Issued credential has all required fields populated."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/images/talent1/job1"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        assert isinstance(cred, JobCredential)
        assert cred.job_id == sample_job_id
        assert cred.org_id == sample_org_id
        assert cred.allowed_paths == ["/org1/images/talent1/job1"]
        assert cred.storage_provider == "b2"
        assert cred.is_revoked is False
        assert len(cred.lease_token) > 0
        assert cred.credential_id is not None

    def test_expiration_is_timeout_plus_grace(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Credential expires at max_timeout + 5 min grace (R8.2)."""
        max_timeout = 1800  # 30 minutes

        before = datetime.now(tz=UTC)
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="s3",
            max_timeout_seconds=max_timeout,
        )
        after = datetime.now(tz=UTC)

        expected_min = before + timedelta(seconds=max_timeout + CREDENTIAL_GRACE_PERIOD_SECONDS)
        expected_max = after + timedelta(seconds=max_timeout + CREDENTIAL_GRACE_PERIOD_SECONDS)

        assert expected_min <= cred.expires_at <= expected_max

    def test_lifetime_capped_to_maximum(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Very long timeouts are capped to prevent accidental long-lived creds (R8.4)."""
        huge_timeout = 100_000  # way over the cap

        before = datetime.now(tz=UTC)
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=huge_timeout,
        )

        # Should be capped at MAX_CREDENTIAL_LIFETIME_SECONDS + grace
        max_expected = before + timedelta(
            seconds=MAX_CREDENTIAL_LIFETIME_SECONDS + CREDENTIAL_GRACE_PERIOD_SECONDS
        )
        assert cred.expires_at <= max_expected + timedelta(seconds=1)

    def test_rejects_empty_paths(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Empty allowed_paths raises CredentialIssuanceError."""
        with pytest.raises(CredentialIssuanceError, match="allowed_paths must not be empty"):
            broker.issue_job_credential(
                job_id=sample_job_id,
                org_id=sample_org_id,
                allowed_paths=[],
                storage_provider="b2",
                max_timeout_seconds=1800,
            )

    def test_rejects_invalid_timeout(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Zero or negative max_timeout_seconds raises CredentialIssuanceError."""
        with pytest.raises(CredentialIssuanceError, match="must be positive"):
            broker.issue_job_credential(
                job_id=sample_job_id,
                org_id=sample_org_id,
                allowed_paths=["/org1/output"],
                storage_provider="b2",
                max_timeout_seconds=0,
            )

    def test_rejects_invalid_storage_provider(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Invalid storage provider raises CredentialIssuanceError."""
        with pytest.raises(CredentialIssuanceError, match="Invalid storage_provider"):
            broker.issue_job_credential(
                job_id=sample_job_id,
                org_id=sample_org_id,
                allowed_paths=["/org1/output"],
                storage_provider="azure_blob",
                max_timeout_seconds=1800,
            )

    def test_accepts_all_valid_providers(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """All supported storage providers can be used."""
        for provider in StorageProvider:
            cred = broker.issue_job_credential(
                job_id=sample_job_id,
                org_id=sample_org_id,
                allowed_paths=["/org1/output"],
                storage_provider=provider.value,
                max_timeout_seconds=1800,
            )
            assert cred.storage_provider == provider.value

    def test_each_credential_has_unique_lease_token(
        self, broker: CredentialBroker, sample_org_id: UUID
    ) -> None:
        """Every issued credential gets a unique lease token."""
        cred1 = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )
        cred2 = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )
        assert cred1.lease_token != cred2.lease_token

    def test_audit_log_records_issuance(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Issuing a credential creates an audit log entry."""
        broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        audit = broker.get_audit_log(org_id=sample_org_id, job_id=sample_job_id)
        assert len(audit) == 1
        assert audit[0].action == "issued"
        assert audit[0].org_id == sample_org_id
        assert audit[0].job_id == sample_job_id


# =============================================================================
# Tests: revoke_credential (R8.3, R8.4)
# =============================================================================


@pytest.mark.unit
class TestRevokeCredential:
    """Test credential revocation — R8.3, R8.4."""

    def test_revoke_returns_true_on_first_call(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """First revocation returns True."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        result = broker.revoke_credential(cred.credential_id)
        assert result is True

    def test_revoke_is_idempotent(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Subsequent revocations return False (already revoked)."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        broker.revoke_credential(cred.credential_id)
        result = broker.revoke_credential(cred.credential_id)
        assert result is False

    def test_revoke_nonexistent_raises_not_found(self, broker: CredentialBroker) -> None:
        """Revoking a nonexistent credential raises CredentialNotFoundError."""
        with pytest.raises(CredentialNotFoundError):
            broker.revoke_credential(uuid4())

    def test_revoked_credential_blocks_access(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Access after revocation raises CredentialRevokedError."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        broker.revoke_credential(cred.credential_id)

        with pytest.raises(CredentialRevokedError):
            broker.validate_access(cred.credential_id, "/org1/output/file.png")

    def test_audit_log_records_revocation(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Revoking a credential creates an audit log entry."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        broker.revoke_credential(cred.credential_id)

        audit = broker.get_audit_log(org_id=sample_org_id, job_id=sample_job_id)
        revocation_entries = [e for e in audit if e.action == "revoked"]
        assert len(revocation_entries) == 1


# =============================================================================
# Tests: validate_access (R8.1, R8.5)
# =============================================================================


@pytest.mark.unit
class TestValidateAccess:
    """Test access validation — scope enforcement, expiry, revocation."""

    def test_valid_path_returns_true(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Access to an allowed path returns True."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/images/talent1/job1"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        result = broker.validate_access(cred.credential_id, "/org1/images/talent1/job1/output.png")
        assert result is True

    def test_exact_path_match_returns_true(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Exact match on the allowed path itself returns True."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/images/talent1/job1"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        result = broker.validate_access(cred.credential_id, "/org1/images/talent1/job1")
        assert result is True

    def test_path_outside_scope_raises_violation(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Access outside allowed paths raises CredentialScopeViolationError (R8.5)."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/images/talent1/job1"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        with pytest.raises(CredentialScopeViolationError) as exc_info:
            broker.validate_access(cred.credential_id, "/org2/images/talent1/job1/output.png")

        assert exc_info.value.requested_path == "/org2/images/talent1/job1/output.png"

    def test_path_traversal_blocked(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Paths that share a prefix but escape scope are blocked."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/images"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        # "/org1/images_evil" should NOT be treated as within "/org1/images"
        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, "/org1/images_evil/malicious.png")

    def test_expired_credential_raises_error(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Expired credential raises CredentialExpiredError."""
        # Issue with 1-second timeout (+ 300s grace = 301s total, too long to wait)
        # Instead, we'll manually manipulate the credential for testing
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1,
        )

        # Manually set expires_at to the past for testing
        expired_cred = JobCredential(
            credential_id=cred.credential_id,
            job_id=cred.job_id,
            org_id=cred.org_id,
            allowed_paths=cred.allowed_paths,
            storage_provider=cred.storage_provider,
            issued_at=cred.issued_at,
            expires_at=datetime.now(tz=UTC) - timedelta(seconds=10),
            lease_token=cred.lease_token,
            is_revoked=False,
        )
        broker._credentials[cred.credential_id] = expired_cred

        with pytest.raises(CredentialExpiredError):
            broker.validate_access(cred.credential_id, "/org1/output/file.png")

    def test_nonexistent_credential_raises_not_found(self, broker: CredentialBroker) -> None:
        """Validating access with a nonexistent credential raises error."""
        with pytest.raises(CredentialNotFoundError):
            broker.validate_access(uuid4(), "/some/path")

    def test_multiple_allowed_paths(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Credential can have multiple allowed paths — access to any is valid."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/input/dataset", "/org1/output/results"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        assert broker.validate_access(cred.credential_id, "/org1/input/dataset/img1.jpg") is True
        assert broker.validate_access(cred.credential_id, "/org1/output/results/out.png") is True

        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, "/org1/models/secret.safetensors")

    def test_scope_violation_logged_in_audit(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Scope violations are recorded in the audit log (R8.5)."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, "/other_org/secret/data.bin")

        audit = broker.get_audit_log(org_id=sample_org_id, job_id=sample_job_id)
        violation_entries = [e for e in audit if e.action == "scope_violation"]
        assert len(violation_entries) == 1
        assert "/other_org/secret/data.bin" in violation_entries[0].details


# =============================================================================
# Tests: get_signed_url (R8.7)
# =============================================================================


@pytest.mark.unit
class TestGetSignedUrl:
    """Test signed URL generation — R8.7."""

    def test_generates_url_for_valid_path(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Valid credential + path generates a signed URL."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        url = broker.get_signed_url(cred.credential_id, "/org1/output/result.png", "read")
        assert "b2.storage.example.com" in url
        assert "/org1/output/result.png" in url
        assert "X-Operation=read" in url

    def test_rejects_invalid_operation(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Invalid operation raises CredentialBrokerError."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        with pytest.raises(CredentialBrokerError, match="Invalid operation"):
            broker.get_signed_url(cred.credential_id, "/org1/output/file.png", "execute")

    def test_rejects_out_of_scope_path(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """Signed URL generation fails for paths outside credential scope."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        with pytest.raises(CredentialScopeViolationError):
            broker.get_signed_url(cred.credential_id, "/org2/output/stolen.png", "read")

    def test_all_operations_supported(
        self, broker: CredentialBroker, sample_job_id: UUID, sample_org_id: UUID
    ) -> None:
        """All valid storage operations produce a URL."""
        cred = broker.issue_job_credential(
            job_id=sample_job_id,
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        for op in StorageOperation:
            url = broker.get_signed_url(cred.credential_id, "/org1/output/f.png", op.value)
            assert f"X-Operation={op.value}" in url


# =============================================================================
# Tests: cleanup_expired
# =============================================================================


@pytest.mark.unit
class TestCleanupExpired:
    """Test credential cleanup."""

    def test_cleanup_removes_expired_credentials(
        self, broker: CredentialBroker, sample_org_id: UUID
    ) -> None:
        """Expired credentials are removed on cleanup."""
        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1,
        )

        # Force expire
        expired = JobCredential(
            credential_id=cred.credential_id,
            job_id=cred.job_id,
            org_id=cred.org_id,
            allowed_paths=cred.allowed_paths,
            storage_provider=cred.storage_provider,
            issued_at=cred.issued_at,
            expires_at=datetime.now(tz=UTC) - timedelta(seconds=10),
            lease_token=cred.lease_token,
            is_revoked=False,
        )
        broker._credentials[cred.credential_id] = expired

        count = broker.cleanup_expired()
        assert count == 1
        assert cred.credential_id not in broker._credentials

    def test_cleanup_removes_revoked_credentials(
        self, broker: CredentialBroker, sample_org_id: UUID
    ) -> None:
        """Revoked credentials are removed on cleanup."""
        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        broker.revoke_credential(cred.credential_id)

        count = broker.cleanup_expired()
        assert count == 1
        assert cred.credential_id not in broker._credentials

    def test_cleanup_preserves_active_credentials(
        self, broker: CredentialBroker, sample_org_id: UUID
    ) -> None:
        """Active, non-expired credentials are preserved."""
        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=sample_org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        count = broker.cleanup_expired()
        assert count == 0
        assert cred.credential_id in broker._credentials


# =============================================================================
# Tests: get_audit_log (R8.6)
# =============================================================================


@pytest.mark.unit
class TestGetAuditLog:
    """Test audit log querying — R8.6."""

    def test_filter_by_org_id(self, broker: CredentialBroker) -> None:
        """Audit log filters by org_id."""
        org_a = uuid4()
        org_b = uuid4()

        broker.issue_job_credential(
            job_id=uuid4(), org_id=org_a, allowed_paths=["/a/out"],
            storage_provider="b2", max_timeout_seconds=1800,
        )
        broker.issue_job_credential(
            job_id=uuid4(), org_id=org_b, allowed_paths=["/b/out"],
            storage_provider="b2", max_timeout_seconds=1800,
        )

        log_a = broker.get_audit_log(org_id=org_a)
        log_b = broker.get_audit_log(org_id=org_b)

        assert all(e.org_id == org_a for e in log_a)
        assert all(e.org_id == org_b for e in log_b)

    def test_filter_by_job_id(self, broker: CredentialBroker) -> None:
        """Audit log filters by job_id."""
        org = uuid4()
        job_1 = uuid4()
        job_2 = uuid4()

        broker.issue_job_credential(
            job_id=job_1, org_id=org, allowed_paths=["/out/1"],
            storage_provider="b2", max_timeout_seconds=1800,
        )
        broker.issue_job_credential(
            job_id=job_2, org_id=org, allowed_paths=["/out/2"],
            storage_provider="b2", max_timeout_seconds=1800,
        )

        log_1 = broker.get_audit_log(org_id=org, job_id=job_1)
        assert all(e.job_id == job_1 for e in log_1)
        assert len(log_1) == 1
