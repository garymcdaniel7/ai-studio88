"""Unit tests for credential storage adapters and encryption authority.

Tests cover: R8.5 (worker_id in violations), R8.7 (multi-provider signed URLs),
R8.9 (encryption authority separation).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.services.credential_broker import (
    CredentialBroker,
    CredentialScopeViolationError,
    JobCredential,
)
from backend.app.services.credential_storage_adapters import (
    B2StorageAdapter,
    CredentialBrokerConfig,
    EncryptionAuthority,
    EncryptionEnvironment,
    R2StorageAdapter,
    S3StorageAdapter,
    StorageAdapterError,
    StorageProviderConfig,
    build_adapter_registry,
    create_adapter_from_config,
    create_encryption_authority,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def b2_config() -> StorageProviderConfig:
    """B2 storage provider configuration for testing."""
    return StorageProviderConfig(
        provider_name="b2",
        endpoint_url="https://s3.us-east-005.backblazeb2.com",
        access_key_id="test_b2_key_id",
        secret_access_key="test_b2_secret",
        region="us-east-005",
        bucket_name="test-bucket",
    )


@pytest.fixture
def s3_config() -> StorageProviderConfig:
    """S3 storage provider configuration for testing."""
    return StorageProviderConfig(
        provider_name="s3",
        endpoint_url="",
        access_key_id="test_s3_key_id",
        secret_access_key="test_s3_secret",
        region="us-east-1",
        bucket_name="test-s3-bucket",
    )


@pytest.fixture
def r2_config() -> StorageProviderConfig:
    """R2 storage provider configuration for testing."""
    return StorageProviderConfig(
        provider_name="r2",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key_id="test_r2_key_id",
        secret_access_key="test_r2_secret",
        region="auto",
        bucket_name="test-r2-bucket",
    )


@pytest.fixture
def dev_authority() -> EncryptionAuthority:
    """Development encryption authority."""
    return create_encryption_authority(
        environment=EncryptionEnvironment.DEVELOPMENT,
        signing_key="dev-test-signing-key-for-tests",
        key_id="dev-test-key-001",
    )


@pytest.fixture
def prod_authority() -> EncryptionAuthority:
    """Production encryption authority."""
    return create_encryption_authority(
        environment=EncryptionEnvironment.PRODUCTION,
        signing_key="prod-very-secret-signing-key",
        key_id="prod-key-001",
    )


@pytest.fixture
def broker_config(b2_config: StorageProviderConfig) -> CredentialBrokerConfig:
    """Credential broker configuration with B2 adapter."""
    return CredentialBrokerConfig(
        environment=EncryptionEnvironment.DEVELOPMENT,
        encryption_authority=create_encryption_authority(
            environment=EncryptionEnvironment.DEVELOPMENT,
            signing_key="test-signing-key",
        ),
        storage_providers={"b2": b2_config},
    )


# =============================================================================
# Tests: EncryptionAuthority (R8.9)
# =============================================================================


@pytest.mark.unit
class TestEncryptionAuthority:
    """Test encryption authority separation — R8.9."""

    def test_dev_and_prod_use_different_environments(
        self, dev_authority: EncryptionAuthority, prod_authority: EncryptionAuthority
    ) -> None:
        """Development and production authorities have distinct environments."""
        assert dev_authority.environment == EncryptionEnvironment.DEVELOPMENT
        assert prod_authority.environment == EncryptionEnvironment.PRODUCTION

    def test_sign_produces_deterministic_output(
        self, dev_authority: EncryptionAuthority
    ) -> None:
        """Same payload signed twice produces the same signature."""
        sig1 = dev_authority.sign("test-payload-123")
        sig2 = dev_authority.sign("test-payload-123")
        assert sig1 == sig2

    def test_different_payloads_produce_different_signatures(
        self, dev_authority: EncryptionAuthority
    ) -> None:
        """Different payloads produce different signatures."""
        sig1 = dev_authority.sign("payload-a")
        sig2 = dev_authority.sign("payload-b")
        assert sig1 != sig2

    def test_verify_accepts_valid_signature(
        self, dev_authority: EncryptionAuthority
    ) -> None:
        """Verify returns True for a correctly signed payload."""
        payload = "credential-xyz-123"
        signature = dev_authority.sign(payload)
        assert dev_authority.verify(payload, signature) is True

    def test_verify_rejects_invalid_signature(
        self, dev_authority: EncryptionAuthority
    ) -> None:
        """Verify returns False for a wrong signature."""
        assert dev_authority.verify("payload", "invalid-signature") is False

    def test_prod_key_cannot_verify_dev_signatures(
        self, dev_authority: EncryptionAuthority, prod_authority: EncryptionAuthority
    ) -> None:
        """Production authority cannot verify development signatures (R8.9)."""
        payload = "cross-environment-test"
        dev_sig = dev_authority.sign(payload)
        assert prod_authority.verify(payload, dev_sig) is False

    def test_dev_key_cannot_verify_prod_signatures(
        self, dev_authority: EncryptionAuthority, prod_authority: EncryptionAuthority
    ) -> None:
        """Development authority cannot verify production signatures (R8.9)."""
        payload = "cross-environment-test"
        prod_sig = prod_authority.sign(payload)
        assert dev_authority.verify(payload, prod_sig) is False

    def test_create_encryption_authority_generates_key_when_none(self) -> None:
        """When no signing_key is provided, a secure random key is generated."""
        auth = create_encryption_authority(environment=EncryptionEnvironment.DEVELOPMENT)
        assert len(auth.signing_key) > 32
        assert auth.key_id.startswith("development-")

    def test_create_encryption_authority_uses_provided_key(self) -> None:
        """When a signing_key is provided, it is used as-is."""
        auth = create_encryption_authority(
            environment=EncryptionEnvironment.PRODUCTION,
            signing_key="my-explicit-key",
            key_id="explicit-id",
        )
        assert auth.signing_key == "my-explicit-key"
        assert auth.key_id == "explicit-id"


# =============================================================================
# Tests: CredentialBrokerConfig
# =============================================================================


@pytest.mark.unit
class TestCredentialBrokerConfig:
    """Test CredentialBrokerConfig creation and from_settings."""

    def test_from_settings_production(self) -> None:
        """Production environment creates production encryption authority."""
        config = CredentialBrokerConfig.from_settings(
            app_env="production",
            signing_key="prod-key-value",
            b2_key_id="b2_id",
            b2_application_key="b2_key",
            b2_endpoint_url="https://s3.b2.com",
            b2_bucket_name="mybucket",
        )
        assert config.environment == EncryptionEnvironment.PRODUCTION
        assert config.encryption_authority.environment == EncryptionEnvironment.PRODUCTION
        assert "b2" in config.storage_providers

    def test_from_settings_local(self) -> None:
        """Local environment creates development encryption authority."""
        config = CredentialBrokerConfig.from_settings(
            app_env="local",
            signing_key="dev-key-value",
        )
        assert config.environment == EncryptionEnvironment.DEVELOPMENT
        assert config.encryption_authority.environment == EncryptionEnvironment.DEVELOPMENT

    def test_from_settings_registers_all_providers(self) -> None:
        """All provided storage configs are registered."""
        config = CredentialBrokerConfig.from_settings(
            app_env="local",
            signing_key="key",
            b2_key_id="b2id",
            b2_application_key="b2key",
            b2_bucket_name="b2bucket",
            s3_access_key_id="s3id",
            s3_secret_access_key="s3key",
            s3_bucket_name="s3bucket",
            r2_access_key_id="r2id",
            r2_secret_access_key="r2key",
            r2_endpoint_url="https://r2.example.com",
            r2_bucket_name="r2bucket",
        )
        assert "b2" in config.storage_providers
        assert "s3" in config.storage_providers
        assert "r2" in config.storage_providers

    def test_from_settings_skips_unconfigured_providers(self) -> None:
        """Providers without credentials are not registered."""
        config = CredentialBrokerConfig.from_settings(
            app_env="local",
            signing_key="key",
            # Only B2 has credentials
            b2_key_id="b2id",
            b2_application_key="b2key",
        )
        assert "b2" in config.storage_providers
        assert "s3" not in config.storage_providers
        assert "r2" not in config.storage_providers


# =============================================================================
# Tests: Storage Adapters (R8.7) — with mocked boto3
# =============================================================================


@pytest.mark.unit
class TestB2StorageAdapter:
    """Test B2 storage adapter signed URL generation."""

    def test_provider_name(self, b2_config: StorageProviderConfig) -> None:
        """B2 adapter identifies itself as 'b2'."""
        adapter = B2StorageAdapter(b2_config)
        assert adapter.provider_name == "b2"

    @patch("boto3.client")
    def test_generate_signed_url_read(
        self, mock_boto3_client: MagicMock, b2_config: StorageProviderConfig
    ) -> None:
        """Read operation generates a get_object presigned URL."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://b2.example.com/signed"
        mock_boto3_client.return_value = mock_client

        adapter = B2StorageAdapter(b2_config)
        url = adapter.generate_signed_url("/org1/output/file.png", "read", 3600)

        assert url == "https://b2.example.com/signed"
        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-bucket", "Key": "/org1/output/file.png"},
            ExpiresIn=3600,
        )

    @patch("boto3.client")
    def test_generate_signed_url_write(
        self, mock_boto3_client: MagicMock, b2_config: StorageProviderConfig
    ) -> None:
        """Write operation generates a put_object presigned URL."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://b2.example.com/upload"
        mock_boto3_client.return_value = mock_client

        adapter = B2StorageAdapter(b2_config)
        url = adapter.generate_signed_url("/org1/output/file.png", "write", 3600)

        assert url == "https://b2.example.com/upload"
        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="put_object",
            Params={"Bucket": "test-bucket", "Key": "/org1/output/file.png"},
            ExpiresIn=3600,
        )

    @patch("boto3.client")
    def test_generate_signed_url_delete(
        self, mock_boto3_client: MagicMock, b2_config: StorageProviderConfig
    ) -> None:
        """Delete operation generates a delete_object presigned URL."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://b2.example.com/delete"
        mock_boto3_client.return_value = mock_client

        adapter = B2StorageAdapter(b2_config)
        url = adapter.generate_signed_url("/org1/output/file.png", "delete", 3600)

        assert url == "https://b2.example.com/delete"
        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="delete_object",
            Params={"Bucket": "test-bucket", "Key": "/org1/output/file.png"},
            ExpiresIn=3600,
        )

    def test_rejects_invalid_operation(self, b2_config: StorageProviderConfig) -> None:
        """Unsupported operations raise StorageAdapterError."""
        adapter = B2StorageAdapter(b2_config)
        with pytest.raises(StorageAdapterError, match="Unsupported operation"):
            adapter.generate_signed_url("/key", "execute", 3600)

    @patch("boto3.client")
    def test_custom_bucket_name(
        self, mock_boto3_client: MagicMock, b2_config: StorageProviderConfig
    ) -> None:
        """Custom bucket_name overrides config default."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://signed.url"
        mock_boto3_client.return_value = mock_client

        adapter = B2StorageAdapter(b2_config)
        adapter.generate_signed_url("/key", "read", 3600, bucket_name="custom-bucket")

        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "custom-bucket", "Key": "/key"},
            ExpiresIn=3600,
        )


@pytest.mark.unit
class TestS3StorageAdapter:
    """Test S3 storage adapter signed URL generation."""

    def test_provider_name(self, s3_config: StorageProviderConfig) -> None:
        """S3 adapter identifies itself as 's3'."""
        adapter = S3StorageAdapter(s3_config)
        assert adapter.provider_name == "s3"

    @patch("boto3.client")
    def test_generate_signed_url_read(
        self, mock_boto3_client: MagicMock, s3_config: StorageProviderConfig
    ) -> None:
        """S3 read operation uses native boto3 presigned URL."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/signed"
        mock_boto3_client.return_value = mock_client

        adapter = S3StorageAdapter(s3_config)
        url = adapter.generate_signed_url("/org1/output/file.png", "read", 1800)

        assert url == "https://s3.amazonaws.com/signed"
        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-s3-bucket", "Key": "/org1/output/file.png"},
            ExpiresIn=1800,
        )


@pytest.mark.unit
class TestR2StorageAdapter:
    """Test R2 storage adapter signed URL generation."""

    def test_provider_name(self, r2_config: StorageProviderConfig) -> None:
        """R2 adapter identifies itself as 'r2'."""
        adapter = R2StorageAdapter(r2_config)
        assert adapter.provider_name == "r2"

    @patch("boto3.client")
    def test_generate_signed_url_read(
        self, mock_boto3_client: MagicMock, r2_config: StorageProviderConfig
    ) -> None:
        """R2 read operation uses S3-compatible presigned URL."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://r2.example.com/signed"
        mock_boto3_client.return_value = mock_client

        adapter = R2StorageAdapter(r2_config)
        url = adapter.generate_signed_url("/org1/output/file.png", "read", 900)

        assert url == "https://r2.example.com/signed"
        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-r2-bucket", "Key": "/org1/output/file.png"},
            ExpiresIn=900,
        )


# =============================================================================
# Tests: Adapter Registry
# =============================================================================


@pytest.mark.unit
class TestAdapterRegistry:
    """Test adapter creation and registry building."""

    def test_create_adapter_from_config_b2(self, b2_config: StorageProviderConfig) -> None:
        """B2 config creates a B2StorageAdapter."""
        adapter = create_adapter_from_config(b2_config)
        assert adapter.provider_name == "b2"
        assert isinstance(adapter, B2StorageAdapter)

    def test_create_adapter_from_config_s3(self, s3_config: StorageProviderConfig) -> None:
        """S3 config creates an S3StorageAdapter."""
        adapter = create_adapter_from_config(s3_config)
        assert adapter.provider_name == "s3"
        assert isinstance(adapter, S3StorageAdapter)

    def test_create_adapter_from_config_r2(self, r2_config: StorageProviderConfig) -> None:
        """R2 config creates an R2StorageAdapter."""
        adapter = create_adapter_from_config(r2_config)
        assert adapter.provider_name == "r2"
        assert isinstance(adapter, R2StorageAdapter)

    def test_create_adapter_unknown_provider(self) -> None:
        """Unknown provider raises StorageAdapterError."""
        config = StorageProviderConfig(
            provider_name="azure",
            endpoint_url="https://azure.blob.example.com",
            access_key_id="key",
            secret_access_key="secret",
            region="us-west",
            bucket_name="container",
        )
        with pytest.raises(StorageAdapterError, match="No adapter for provider"):
            create_adapter_from_config(config)

    def test_build_adapter_registry(self, broker_config: CredentialBrokerConfig) -> None:
        """Registry is built from config's storage providers."""
        registry = build_adapter_registry(broker_config)
        assert "b2" in registry
        assert registry["b2"].provider_name == "b2"


# =============================================================================
# Tests: worker_id in Credential Broker (R8.5)
# =============================================================================


@pytest.mark.unit
class TestWorkerIdInViolations:
    """Test that worker_id is captured in scope violations — R8.5."""

    def test_scope_violation_includes_worker_id(self) -> None:
        """Scope violations include worker_id in the exception and audit."""
        broker = CredentialBroker()
        org_id = uuid4()
        job_id = uuid4()

        cred = broker.issue_job_credential(
            job_id=job_id,
            org_id=org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        with pytest.raises(CredentialScopeViolationError) as exc_info:
            broker.validate_access(
                cred.credential_id,
                "/org2/secret/data.bin",
                worker_id="worker-gpu-42",
            )

        assert exc_info.value.worker_id == "worker-gpu-42"
        assert exc_info.value.requested_path == "/org2/secret/data.bin"

    def test_scope_violation_audit_includes_worker_id(self) -> None:
        """Audit log entry for scope violation includes worker_id."""
        broker = CredentialBroker()
        org_id = uuid4()
        job_id = uuid4()

        cred = broker.issue_job_credential(
            job_id=job_id,
            org_id=org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(
                cred.credential_id,
                "/other/path",
                worker_id="worker-vast-99",
            )

        audit = broker.get_audit_log(org_id=org_id, job_id=job_id)
        violation_entries = [e for e in audit if e.action == "scope_violation"]
        assert len(violation_entries) == 1
        assert violation_entries[0].worker_id == "worker-vast-99"

    def test_access_granted_audit_includes_worker_id(self) -> None:
        """Successful access audit entry also includes worker_id."""
        broker = CredentialBroker()
        org_id = uuid4()
        job_id = uuid4()

        cred = broker.issue_job_credential(
            job_id=job_id,
            org_id=org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        broker.validate_access(
            cred.credential_id,
            "/org1/output/result.png",
            worker_id="worker-runpod-7",
        )

        audit = broker.get_audit_log(org_id=org_id, job_id=job_id)
        access_entries = [e for e in audit if e.action == "access_granted"]
        assert len(access_entries) == 1
        assert access_entries[0].worker_id == "worker-runpod-7"

    def test_worker_id_none_when_not_provided(self) -> None:
        """worker_id defaults to None when not explicitly passed."""
        broker = CredentialBroker()
        org_id = uuid4()
        job_id = uuid4()

        cred = broker.issue_job_credential(
            job_id=job_id,
            org_id=org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        broker.validate_access(cred.credential_id, "/org1/output/file.png")

        audit = broker.get_audit_log(org_id=org_id, job_id=job_id)
        access_entries = [e for e in audit if e.action == "access_granted"]
        assert access_entries[0].worker_id is None


# =============================================================================
# Tests: Broker with real adapters wired (R8.7)
# =============================================================================


@pytest.mark.unit
class TestBrokerWithAdapters:
    """Test CredentialBroker delegates to storage adapters for signed URLs."""

    @patch("boto3.client")
    def test_signed_url_uses_adapter(self, mock_boto3_client: MagicMock) -> None:
        """When an adapter is configured, get_signed_url delegates to it."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://real-b2-url.example.com/signed"
        mock_boto3_client.return_value = mock_client

        config = CredentialBrokerConfig(
            environment=EncryptionEnvironment.DEVELOPMENT,
            encryption_authority=create_encryption_authority(
                environment=EncryptionEnvironment.DEVELOPMENT,
                signing_key="test-key",
            ),
            storage_providers={
                "b2": StorageProviderConfig(
                    provider_name="b2",
                    endpoint_url="https://s3.b2.example.com",
                    access_key_id="key_id",
                    secret_access_key="secret",
                    region="us-east-005",
                    bucket_name="my-bucket",
                ),
            },
        )

        broker = CredentialBroker(config=config)
        org_id = uuid4()
        job_id = uuid4()

        cred = broker.issue_job_credential(
            job_id=job_id,
            org_id=org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        url = broker.get_signed_url(cred.credential_id, "/org1/output/result.png", "read")
        assert url == "https://real-b2-url.example.com/signed"

    def test_signed_url_fallback_when_no_adapter(self) -> None:
        """When no adapter is configured, fallback placeholder URL is returned."""
        broker = CredentialBroker()  # No config = no adapters
        org_id = uuid4()
        job_id = uuid4()

        cred = broker.issue_job_credential(
            job_id=job_id,
            org_id=org_id,
            allowed_paths=["/org1/output"],
            storage_provider="b2",
            max_timeout_seconds=1800,
        )

        url = broker.get_signed_url(cred.credential_id, "/org1/output/result.png", "read")
        assert "b2.storage.example.com" in url
        assert "PLACEHOLDER_SIGN" in url


# =============================================================================
# Tests: Encryption authority on broker (R8.9)
# =============================================================================


@pytest.mark.unit
class TestBrokerEncryptionAuthority:
    """Test broker encryption authority property."""

    def test_encryption_authority_from_config(self) -> None:
        """Broker exposes configured encryption authority."""
        config = CredentialBrokerConfig(
            environment=EncryptionEnvironment.PRODUCTION,
            encryption_authority=create_encryption_authority(
                environment=EncryptionEnvironment.PRODUCTION,
                signing_key="prod-key",
                key_id="prod-001",
            ),
            storage_providers={},
        )
        broker = CredentialBroker(config=config)

        assert broker.encryption_authority is not None
        assert broker.encryption_authority.environment == EncryptionEnvironment.PRODUCTION
        assert broker.encryption_authority.key_id == "prod-001"

    def test_encryption_authority_none_without_config(self) -> None:
        """Broker without config returns None for encryption_authority."""
        broker = CredentialBroker()
        assert broker.encryption_authority is None

    def test_environment_property(self) -> None:
        """Broker exposes environment classification."""
        config = CredentialBrokerConfig(
            environment=EncryptionEnvironment.DEVELOPMENT,
            encryption_authority=create_encryption_authority(
                environment=EncryptionEnvironment.DEVELOPMENT,
                signing_key="dev-key",
            ),
            storage_providers={},
        )
        broker = CredentialBroker(config=config)
        assert broker.environment == EncryptionEnvironment.DEVELOPMENT

    def test_environment_none_without_config(self) -> None:
        """Broker without config returns None for environment."""
        broker = CredentialBroker()
        assert broker.environment is None
