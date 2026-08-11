"""Storage provider adapters for the Credential Broker.

Provides pre-signed URL generation for multiple storage backends (B2, S3, R2)
using the boto3 S3-compatible API. Each adapter implements the
StorageSigningAdapter protocol.

Requirements covered: R8.7 (multiple storage providers), R8.9 (encryption authority separation)
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Encryption Authority
# =============================================================================


class EncryptionEnvironment(StrEnum):
    """Environment classification for encryption authority separation."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True)
class EncryptionAuthority:
    """Encryption authority configuration for credential signing.

    Separates production and development signing keys so that
    development credentials are never valid in production (R8.9).

    Attributes:
        environment: Which environment this authority governs.
        signing_key: The key used to sign/verify credential tokens.
        key_id: Identifier for key rotation tracking.
        created_at: When this authority was provisioned.
    """

    environment: EncryptionEnvironment
    signing_key: str
    key_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def sign(self, payload: str) -> str:
        """Sign a payload using this authority's key.

        Args:
            payload: The string payload to sign.

        Returns:
            HMAC-SHA256 hex digest of the payload.
        """
        return hmac.new(
            key=self.signing_key.encode(),
            msg=payload.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

    def verify(self, payload: str, signature: str) -> bool:
        """Verify a signature against the payload.

        Uses constant-time comparison to prevent timing attacks.

        Args:
            payload: The original payload.
            signature: The signature to verify.

        Returns:
            True if the signature is valid.
        """
        expected = self.sign(payload)
        return hmac.compare_digest(expected, signature)


def create_encryption_authority(
    environment: EncryptionEnvironment,
    signing_key: str | None = None,
    key_id: str | None = None,
) -> EncryptionAuthority:
    """Create an encryption authority for the given environment.

    If no signing_key is provided, generates a secure random key.
    Production environments SHOULD use a key from a secrets manager.

    Args:
        environment: development or production.
        signing_key: Optional explicit key. If None, generates one.
        key_id: Optional key identifier. If None, generates one.

    Returns:
        Configured EncryptionAuthority instance.
    """
    if signing_key is None:
        signing_key = secrets.token_urlsafe(64)
    if key_id is None:
        key_id = f"{environment.value}-{secrets.token_hex(8)}"

    return EncryptionAuthority(
        environment=environment,
        signing_key=signing_key,
        key_id=key_id,
    )


# =============================================================================
# Credential Broker Configuration
# =============================================================================


@dataclass(frozen=True)
class StorageProviderConfig:
    """Configuration for a single storage provider.

    Attributes:
        provider_name: Identifier (b2, s3, r2).
        endpoint_url: S3-compatible endpoint URL.
        access_key_id: AWS/B2/R2 access key ID.
        secret_access_key: AWS/B2/R2 secret key.
        region: Provider region.
        bucket_name: Default bucket name.
    """

    provider_name: str
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    region: str
    bucket_name: str


@dataclass
class CredentialBrokerConfig:
    """Configuration for the Credential Broker including environment-specific behavior.

    Configures per-environment encryption authority, storage providers,
    and operational parameters.

    Attributes:
        environment: Current deployment environment.
        encryption_authority: The signing authority for this environment.
        storage_providers: Map of provider name to configuration.
        max_credential_lifetime_seconds: Hard cap on credential lifetime.
        grace_period_seconds: Grace period added to job timeout for credential expiry.
        signed_url_default_duration_seconds: Default signed URL validity.
        cleanup_interval_seconds: How often to run credential cleanup.
    """

    environment: EncryptionEnvironment
    encryption_authority: EncryptionAuthority
    storage_providers: dict[str, StorageProviderConfig] = field(default_factory=dict)
    max_credential_lifetime_seconds: int = 14_700  # 4hrs + 5min grace
    grace_period_seconds: int = 300
    signed_url_default_duration_seconds: int = 3600
    cleanup_interval_seconds: int = 300

    @classmethod
    def from_settings(
        cls,
        app_env: str,
        signing_key: str,
        b2_key_id: str = "",
        b2_application_key: str = "",
        b2_endpoint_url: str = "",
        b2_bucket_name: str = "",
        b2_region: str = "us-east-005",
        s3_access_key_id: str = "",
        s3_secret_access_key: str = "",
        s3_region: str = "us-east-1",
        s3_bucket_name: str = "",
        r2_access_key_id: str = "",
        r2_secret_access_key: str = "",
        r2_endpoint_url: str = "",
        r2_bucket_name: str = "",
    ) -> CredentialBrokerConfig:
        """Create configuration from application settings.

        Args:
            app_env: Application environment string (local, test, staging, production).
            signing_key: Key used for credential signing.
            b2_key_id: Backblaze B2 key ID.
            b2_application_key: Backblaze B2 application key.
            b2_endpoint_url: Backblaze B2 S3-compatible endpoint.
            b2_bucket_name: Backblaze B2 bucket name.
            b2_region: Backblaze B2 region.
            s3_access_key_id: AWS S3 access key ID.
            s3_secret_access_key: AWS S3 secret access key.
            s3_region: AWS S3 region.
            s3_bucket_name: AWS S3 bucket name.
            r2_access_key_id: Cloudflare R2 access key ID.
            r2_secret_access_key: Cloudflare R2 secret access key.
            r2_endpoint_url: Cloudflare R2 endpoint URL.
            r2_bucket_name: Cloudflare R2 bucket name.

        Returns:
            Configured CredentialBrokerConfig.
        """
        env = (
            EncryptionEnvironment.PRODUCTION
            if app_env in ("production", "staging")
            else EncryptionEnvironment.DEVELOPMENT
        )

        authority = create_encryption_authority(
            environment=env,
            signing_key=signing_key,
        )

        providers: dict[str, StorageProviderConfig] = {}

        if b2_key_id and b2_application_key:
            providers["b2"] = StorageProviderConfig(
                provider_name="b2",
                endpoint_url=b2_endpoint_url or "https://s3.us-east-005.backblazeb2.com",
                access_key_id=b2_key_id,
                secret_access_key=b2_application_key,
                region=b2_region,
                bucket_name=b2_bucket_name,
            )

        if s3_access_key_id and s3_secret_access_key:
            providers["s3"] = StorageProviderConfig(
                provider_name="s3",
                endpoint_url="",  # Native S3 uses region-based endpoints
                access_key_id=s3_access_key_id,
                secret_access_key=s3_secret_access_key,
                region=s3_region,
                bucket_name=s3_bucket_name,
            )

        if r2_access_key_id and r2_secret_access_key:
            providers["r2"] = StorageProviderConfig(
                provider_name="r2",
                endpoint_url=r2_endpoint_url,
                access_key_id=r2_access_key_id,
                secret_access_key=r2_secret_access_key,
                region="auto",
                bucket_name=r2_bucket_name,
            )

        return cls(
            environment=env,
            encryption_authority=authority,
            storage_providers=providers,
        )


# =============================================================================
# Storage Signing Adapter Protocol
# =============================================================================


class StorageSigningAdapter(Protocol):
    """Protocol for storage provider pre-signed URL generation.

    Each adapter handles generating time-limited signed URLs for
    a specific storage backend. The Credential Broker delegates
    actual URL signing to the appropriate adapter based on the
    credential's storage_provider field.
    """

    @property
    def provider_name(self) -> str:
        """Return the provider identifier (b2, s3, r2)."""
        ...

    def generate_signed_url(
        self,
        storage_key: str,
        operation: str,
        duration_seconds: int,
        bucket_name: str | None = None,
    ) -> str:
        """Generate a pre-signed URL for the given storage operation.

        Args:
            storage_key: The object key in the storage bucket.
            operation: The operation type (read, write, delete).
            duration_seconds: How long the URL is valid.
            bucket_name: Override bucket name. Uses config default if None.

        Returns:
            A pre-signed URL valid for the specified duration.

        Raises:
            StorageAdapterError: If URL generation fails.
        """
        ...

    def health_check(self) -> bool:
        """Check if the storage provider is reachable.

        Returns:
            True if the provider is reachable and functional.
        """
        ...


# =============================================================================
# Exceptions
# =============================================================================


class StorageAdapterError(Exception):
    """Base exception for storage adapter operations."""

    def __init__(self, message: str, provider: str = "") -> None:
        self.message = message
        self.provider = provider
        super().__init__(message)


class StorageAdapterUnavailableError(StorageAdapterError):
    """Raised when a storage adapter cannot reach its provider."""


# =============================================================================
# Operation Mapping
# =============================================================================

# Maps our operation names to boto3 client method names
_OPERATION_TO_S3_METHOD: dict[str, str] = {
    "read": "get_object",
    "write": "put_object",
    "delete": "delete_object",
}


# =============================================================================
# Concrete Adapters
# =============================================================================


class B2StorageAdapter:
    """Backblaze B2 storage adapter using the S3-compatible API.

    Generates pre-signed URLs via boto3 using B2's S3-compatible endpoint.
    """

    def __init__(self, config: StorageProviderConfig) -> None:
        """Initialize the B2 adapter.

        Args:
            config: B2 provider configuration with credentials and endpoint.
        """
        self._config = config
        self._client = None

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "b2"

    def _get_client(self):
        """Create or return the cached boto3 S3 client for B2."""
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=self._config.endpoint_url,
                aws_access_key_id=self._config.access_key_id,
                aws_secret_access_key=self._config.secret_access_key,
                region_name=self._config.region,
            )
        return self._client

    def generate_signed_url(
        self,
        storage_key: str,
        operation: str,
        duration_seconds: int,
        bucket_name: str | None = None,
    ) -> str:
        """Generate a B2 pre-signed URL.

        Args:
            storage_key: The object key in the B2 bucket.
            operation: The operation type (read, write, delete).
            duration_seconds: How long the URL is valid.
            bucket_name: Override bucket. Uses config default if None.

        Returns:
            A pre-signed URL for the B2 operation.

        Raises:
            StorageAdapterError: If generation fails.
        """
        s3_method = _OPERATION_TO_S3_METHOD.get(operation)
        if not s3_method:
            raise StorageAdapterError(
                message=f"Unsupported operation '{operation}' for B2",
                provider="b2",
            )

        bucket = bucket_name or self._config.bucket_name
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                ClientMethod=s3_method,
                Params={"Bucket": bucket, "Key": storage_key},
                ExpiresIn=duration_seconds,
            )
            logger.debug(
                "b2_signed_url_generated",
                storage_key=storage_key,
                operation=operation,
                duration_seconds=duration_seconds,
            )
            return url
        except Exception as exc:
            raise StorageAdapterError(
                message=f"Failed to generate B2 signed URL: {exc}",
                provider="b2",
            ) from exc

    def health_check(self) -> bool:
        """Check B2 reachability by listing bucket metadata."""
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self._config.bucket_name)
            return True
        except Exception:
            return False


class S3StorageAdapter:
    """AWS S3 native storage adapter.

    Generates pre-signed URLs via boto3 using native S3 endpoints.
    """

    def __init__(self, config: StorageProviderConfig) -> None:
        """Initialize the S3 adapter.

        Args:
            config: S3 provider configuration with credentials and region.
        """
        self._config = config
        self._client = None

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "s3"

    def _get_client(self):
        """Create or return the cached boto3 S3 client."""
        if self._client is None:
            import boto3

            kwargs = {
                "aws_access_key_id": self._config.access_key_id,
                "aws_secret_access_key": self._config.secret_access_key,
                "region_name": self._config.region,
            }
            # Only set endpoint_url if provided (for S3-compatible services)
            if self._config.endpoint_url:
                kwargs["endpoint_url"] = self._config.endpoint_url

            self._client = boto3.client("s3", **kwargs)
        return self._client

    def generate_signed_url(
        self,
        storage_key: str,
        operation: str,
        duration_seconds: int,
        bucket_name: str | None = None,
    ) -> str:
        """Generate an S3 pre-signed URL.

        Args:
            storage_key: The object key in the S3 bucket.
            operation: The operation type (read, write, delete).
            duration_seconds: How long the URL is valid.
            bucket_name: Override bucket. Uses config default if None.

        Returns:
            A pre-signed URL for the S3 operation.

        Raises:
            StorageAdapterError: If generation fails.
        """
        s3_method = _OPERATION_TO_S3_METHOD.get(operation)
        if not s3_method:
            raise StorageAdapterError(
                message=f"Unsupported operation '{operation}' for S3",
                provider="s3",
            )

        bucket = bucket_name or self._config.bucket_name
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                ClientMethod=s3_method,
                Params={"Bucket": bucket, "Key": storage_key},
                ExpiresIn=duration_seconds,
            )
            logger.debug(
                "s3_signed_url_generated",
                storage_key=storage_key,
                operation=operation,
                duration_seconds=duration_seconds,
            )
            return url
        except Exception as exc:
            raise StorageAdapterError(
                message=f"Failed to generate S3 signed URL: {exc}",
                provider="s3",
            ) from exc

    def health_check(self) -> bool:
        """Check S3 reachability by listing bucket metadata."""
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self._config.bucket_name)
            return True
        except Exception:
            return False


class R2StorageAdapter:
    """Cloudflare R2 storage adapter using the S3-compatible API.

    Generates pre-signed URLs via boto3 using R2's S3-compatible endpoint.
    """

    def __init__(self, config: StorageProviderConfig) -> None:
        """Initialize the R2 adapter.

        Args:
            config: R2 provider configuration with credentials and endpoint.
        """
        self._config = config
        self._client = None

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "r2"

    def _get_client(self):
        """Create or return the cached boto3 S3 client for R2."""
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=self._config.endpoint_url,
                aws_access_key_id=self._config.access_key_id,
                aws_secret_access_key=self._config.secret_access_key,
                region_name=self._config.region,
            )
        return self._client

    def generate_signed_url(
        self,
        storage_key: str,
        operation: str,
        duration_seconds: int,
        bucket_name: str | None = None,
    ) -> str:
        """Generate an R2 pre-signed URL.

        Args:
            storage_key: The object key in the R2 bucket.
            operation: The operation type (read, write, delete).
            duration_seconds: How long the URL is valid.
            bucket_name: Override bucket. Uses config default if None.

        Returns:
            A pre-signed URL for the R2 operation.

        Raises:
            StorageAdapterError: If generation fails.
        """
        s3_method = _OPERATION_TO_S3_METHOD.get(operation)
        if not s3_method:
            raise StorageAdapterError(
                message=f"Unsupported operation '{operation}' for R2",
                provider="r2",
            )

        bucket = bucket_name or self._config.bucket_name
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                ClientMethod=s3_method,
                Params={"Bucket": bucket, "Key": storage_key},
                ExpiresIn=duration_seconds,
            )
            logger.debug(
                "r2_signed_url_generated",
                storage_key=storage_key,
                operation=operation,
                duration_seconds=duration_seconds,
            )
            return url
        except Exception as exc:
            raise StorageAdapterError(
                message=f"Failed to generate R2 signed URL: {exc}",
                provider="r2",
            ) from exc

    def health_check(self) -> bool:
        """Check R2 reachability by listing bucket metadata."""
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self._config.bucket_name)
            return True
        except Exception:
            return False


# =============================================================================
# Adapter Registry
# =============================================================================


def create_adapter_from_config(config: StorageProviderConfig) -> StorageSigningAdapter:
    """Create the appropriate adapter from a provider configuration.

    Args:
        config: Storage provider configuration.

    Returns:
        A configured StorageSigningAdapter instance.

    Raises:
        StorageAdapterError: If the provider is not supported.
    """
    adapters: dict[str, type] = {
        "b2": B2StorageAdapter,
        "s3": S3StorageAdapter,
        "r2": R2StorageAdapter,
    }

    adapter_class = adapters.get(config.provider_name)
    if adapter_class is None:
        raise StorageAdapterError(
            message=f"No adapter for provider '{config.provider_name}'",
            provider=config.provider_name,
        )

    return adapter_class(config)


def build_adapter_registry(
    broker_config: CredentialBrokerConfig,
) -> dict[str, StorageSigningAdapter]:
    """Build a registry of all configured storage adapters.

    Args:
        broker_config: The credential broker configuration.

    Returns:
        Dictionary mapping provider name to adapter instance.
    """
    registry: dict[str, StorageSigningAdapter] = {}
    for name, provider_config in broker_config.storage_providers.items():
        try:
            registry[name] = create_adapter_from_config(provider_config)
            logger.info(
                "storage_adapter_registered",
                provider=name,
                endpoint=provider_config.endpoint_url or "(native)",
            )
        except StorageAdapterError as exc:
            logger.warning(
                "storage_adapter_registration_failed",
                provider=name,
                error=exc.message,
            )
    return registry
