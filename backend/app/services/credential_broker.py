"""Credential Broker — issues short-lived, job-scoped credentials.

Handles secure credential issuance and revocation for GPU compute workers.
Workers receive only the minimum access required for their specific job,
scoped to exact storage paths, with automatic expiration.

Requirements covered: R8.1, R8.2, R8.3, R8.4, R8.5, R8.6, R8.7, R8.9
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

import structlog

from backend.app.services.credential_storage_adapters import (
    CredentialBrokerConfig,
    EncryptionAuthority,
    EncryptionEnvironment,
    StorageAdapterError,
    StorageSigningAdapter,
    build_adapter_registry,
    create_encryption_authority,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Grace period added to job max_timeout for credential expiration (R8.2)
CREDENTIAL_GRACE_PERIOD_SECONDS: int = 300  # 5 minutes

# Maximum allowed credential lifetime (hard cap for safety)
MAX_CREDENTIAL_LIFETIME_SECONDS: int = 14_400 + CREDENTIAL_GRACE_PERIOD_SECONDS  # 4 hrs + grace

# Lease token length (bytes of randomness before base64 encoding)
LEASE_TOKEN_BYTES: int = 32

# Default signed URL duration for pre-signed URL generation
DEFAULT_SIGNED_URL_DURATION_SECONDS: int = 3600


# =============================================================================
# Enums
# =============================================================================


class StorageProvider(StrEnum):
    """Supported storage providers for credential issuance."""

    B2 = "b2"
    S3 = "s3"
    R2 = "r2"


class StorageOperation(StrEnum):
    """Allowed storage operations for signed URL generation."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


# =============================================================================
# Exceptions
# =============================================================================


class CredentialBrokerError(Exception):
    """Base exception for Credential Broker operations."""

    def __init__(self, message: str, credential_id: UUID | None = None) -> None:
        self.message = message
        self.credential_id = credential_id
        super().__init__(message)


class CredentialNotFoundError(CredentialBrokerError):
    """Raised when a credential cannot be found."""


class CredentialExpiredError(CredentialBrokerError):
    """Raised when a credential has expired."""


class CredentialRevokedError(CredentialBrokerError):
    """Raised when a revoked credential is used."""


class CredentialScopeViolationError(CredentialBrokerError):
    """Raised when access is attempted outside the credential's authorized scope."""

    def __init__(
        self,
        message: str,
        credential_id: UUID | None = None,
        requested_path: str = "",
        allowed_paths: list[str] | None = None,
        worker_id: str | None = None,
    ) -> None:
        super().__init__(message, credential_id)
        self.requested_path = requested_path
        self.allowed_paths = allowed_paths or []
        self.worker_id = worker_id


class CredentialIssuanceError(CredentialBrokerError):
    """Raised when credential issuance fails."""


# =============================================================================
# Data Structures
# =============================================================================


@dataclass(frozen=True)
class JobCredential:
    """A short-lived, job-scoped credential for compute worker storage access.

    Attributes:
        credential_id: Unique identifier for this credential.
        job_id: The job this credential is scoped to.
        org_id: The organization that owns the job.
        allowed_paths: Storage paths this credential grants access to.
        storage_provider: Which storage backend this credential is for.
        issued_at: When the credential was issued.
        expires_at: When the credential expires (max_timeout + grace).
        lease_token: Secure random token for credential validation.
        is_revoked: Whether the credential has been revoked.
    """

    credential_id: UUID
    job_id: UUID
    org_id: UUID
    allowed_paths: list[str]
    storage_provider: str
    issued_at: datetime
    expires_at: datetime
    lease_token: str
    is_revoked: bool = False


@dataclass(frozen=True)
class CredentialAuditEntry:
    """Audit log entry for credential operations.

    Attributes:
        entry_id: Unique identifier for this audit entry.
        credential_id: The credential this entry refers to.
        job_id: The job associated with the credential.
        org_id: The organization that owns the job.
        action: What happened (issued, revoked, access_granted, scope_violation).
        timestamp: When the action occurred.
        details: Additional context about the action.
        worker_id: The worker that triggered this event (if applicable).
    """

    entry_id: UUID
    credential_id: UUID
    job_id: UUID
    org_id: UUID
    action: str
    timestamp: datetime
    details: str = ""
    worker_id: str | None = None


# =============================================================================
# Credential Broker Service
# =============================================================================


class CredentialBroker:
    """Issues short-lived, job-scoped credentials to compute workers.

    Workers receive only the minimum access required for their specific job,
    scoped to exact storage paths, with automatic expiration.

    This MVP implementation stores credentials in-memory. Production
    deployment should persist to Supabase for durability and cross-instance
    consistency.

    Never issues long-lived credentials to GPU workers (R8.4).
    Never transmits durable secrets (B2 master keys, service role key) (R8.3).
    """

    def __init__(self, config: CredentialBrokerConfig | None = None) -> None:
        """Initialize the Credential Broker with in-memory storage.

        Args:
            config: Optional broker configuration. If None, creates a
                development-mode config with no storage adapters.
        """
        # TODO: Replace with Supabase persistence for production deployment.
        # In-memory storage is sufficient for MVP/single-instance, but
        # production requires durable storage for cross-instance consistency,
        # crash recovery, and audit queryability.
        self._credentials: dict[UUID, JobCredential] = {}
        self._audit_log: list[CredentialAuditEntry] = []

        # Configuration and adapters
        if config is not None:
            self._config = config
            self._adapters = build_adapter_registry(config)
        else:
            # Development fallback: no real adapters, placeholder URLs
            self._config = None
            self._adapters: dict[str, StorageSigningAdapter] = {}

    def issue_job_credential(
        self,
        job_id: UUID,
        org_id: UUID,
        allowed_paths: list[str],
        storage_provider: str,
        max_timeout_seconds: int,
    ) -> JobCredential:
        """Issue a short-lived credential scoped to a specific job.

        The credential grants access only to the specified storage paths
        for the specified org and job. Expiration is set to max_timeout
        plus a 5-minute grace period (R8.2).

        Args:
            job_id: The job this credential is for.
            org_id: The organization that owns the job.
            allowed_paths: Storage paths the worker needs access to.
            storage_provider: Which storage backend (b2, s3, r2).
            max_timeout_seconds: Job's maximum execution time in seconds.

        Returns:
            JobCredential with a secure lease token and scoped access.

        Raises:
            CredentialIssuanceError: If issuance fails due to invalid params.
        """
        if not allowed_paths:
            raise CredentialIssuanceError(
                message="allowed_paths must not be empty",
                credential_id=None,
            )

        if max_timeout_seconds <= 0:
            raise CredentialIssuanceError(
                message="max_timeout_seconds must be positive",
                credential_id=None,
            )

        # Validate storage provider
        try:
            StorageProvider(storage_provider)
        except ValueError:
            valid_providers = [p.value for p in StorageProvider]
            raise CredentialIssuanceError(
                message=(
                    f"Invalid storage_provider '{storage_provider}'. "
                    f"Valid options: {valid_providers}"
                ),
                credential_id=None,
            )

        # Cap lifetime to prevent accidental long-lived credentials (R8.4)
        effective_timeout = min(max_timeout_seconds, MAX_CREDENTIAL_LIFETIME_SECONDS)

        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(seconds=effective_timeout + CREDENTIAL_GRACE_PERIOD_SECONDS)
        credential_id = uuid4()
        lease_token = secrets.token_urlsafe(LEASE_TOKEN_BYTES)

        credential = JobCredential(
            credential_id=credential_id,
            job_id=job_id,
            org_id=org_id,
            allowed_paths=list(allowed_paths),
            storage_provider=storage_provider,
            issued_at=now,
            expires_at=expires_at,
            lease_token=lease_token,
            is_revoked=False,
        )

        self._credentials[credential_id] = credential

        self._record_audit(
            credential_id=credential_id,
            job_id=job_id,
            org_id=org_id,
            action="issued",
            details=(
                f"provider={storage_provider} "
                f"paths={allowed_paths} "
                f"expires_at={expires_at.isoformat()}"
            ),
        )

        logger.info(
            "credential_issued",
            credential_id=str(credential_id),
            job_id=str(job_id),
            org_id=str(org_id),
            storage_provider=storage_provider,
            allowed_paths=allowed_paths,
            expires_at=expires_at.isoformat(),
        )

        return credential

    def revoke_credential(self, credential_id: UUID) -> bool:
        """Revoke a credential, preventing further use.

        Must be called within 60 seconds of job completion/failure/cancellation
        per R8.4. Safe to call multiple times (idempotent).

        Args:
            credential_id: The credential to revoke.

        Returns:
            True if the credential was revoked, False if already revoked.

        Raises:
            CredentialNotFoundError: If the credential does not exist.
        """
        credential = self._credentials.get(credential_id)
        if credential is None:
            raise CredentialNotFoundError(
                message=f"Credential {credential_id} not found",
                credential_id=credential_id,
            )

        if credential.is_revoked:
            logger.debug(
                "credential_already_revoked",
                credential_id=str(credential_id),
            )
            return False

        # Replace with a revoked version (frozen dataclass — must reconstruct)
        revoked = JobCredential(
            credential_id=credential.credential_id,
            job_id=credential.job_id,
            org_id=credential.org_id,
            allowed_paths=credential.allowed_paths,
            storage_provider=credential.storage_provider,
            issued_at=credential.issued_at,
            expires_at=credential.expires_at,
            lease_token=credential.lease_token,
            is_revoked=True,
        )
        self._credentials[credential_id] = revoked

        self._record_audit(
            credential_id=credential_id,
            job_id=credential.job_id,
            org_id=credential.org_id,
            action="revoked",
            details="Credential revoked on job completion/failure/cancellation",
        )

        logger.info(
            "credential_revoked",
            credential_id=str(credential_id),
            job_id=str(credential.job_id),
            org_id=str(credential.org_id),
        )

        return True

    def validate_access(
        self, credential_id: UUID, requested_path: str, worker_id: str | None = None
    ) -> bool:
        """Validate that a credential grants access to the requested path.

        Checks: credential exists, not revoked, not expired, and the
        requested path is within the credential's allowed scope.

        Args:
            credential_id: The credential to validate.
            requested_path: The storage path being accessed.
            worker_id: The worker attempting access (logged on violations, R8.5).

        Returns:
            True if access is granted.

        Raises:
            CredentialNotFoundError: If the credential does not exist.
            CredentialRevokedError: If the credential has been revoked.
            CredentialExpiredError: If the credential has expired.
            CredentialScopeViolationError: If the path is outside scope.
        """
        credential = self._credentials.get(credential_id)
        if credential is None:
            raise CredentialNotFoundError(
                message=f"Credential {credential_id} not found",
                credential_id=credential_id,
            )

        if credential.is_revoked:
            self._record_audit(
                credential_id=credential_id,
                job_id=credential.job_id,
                org_id=credential.org_id,
                action="access_denied_revoked",
                details=f"Attempted access to '{requested_path}' with revoked credential",
                worker_id=worker_id,
            )
            raise CredentialRevokedError(
                message=f"Credential {credential_id} has been revoked",
                credential_id=credential_id,
            )

        now = datetime.now(tz=UTC)
        if now > credential.expires_at:
            self._record_audit(
                credential_id=credential_id,
                job_id=credential.job_id,
                org_id=credential.org_id,
                action="access_denied_expired",
                details=f"Attempted access to '{requested_path}' with expired credential",
                worker_id=worker_id,
            )
            raise CredentialExpiredError(
                message=(
                    f"Credential {credential_id} expired at "
                    f"{credential.expires_at.isoformat()}"
                ),
                credential_id=credential_id,
            )

        # Path validation: requested path must start with one of the allowed paths
        if not self._path_is_allowed(requested_path, credential.allowed_paths):
            self._record_audit(
                credential_id=credential_id,
                job_id=credential.job_id,
                org_id=credential.org_id,
                action="scope_violation",
                details=(
                    f"Attempted access to '{requested_path}' outside scope. "
                    f"Allowed: {credential.allowed_paths}"
                ),
                worker_id=worker_id,
            )

            logger.warning(
                "credential_scope_violation",
                credential_id=str(credential_id),
                job_id=str(credential.job_id),
                org_id=str(credential.org_id),
                worker_id=worker_id,
                requested_path=requested_path,
                allowed_paths=credential.allowed_paths,
                timestamp=datetime.now(tz=UTC).isoformat(),
            )

            raise CredentialScopeViolationError(
                message=(
                    f"Path '{requested_path}' is outside credential scope. "
                    f"Allowed paths: {credential.allowed_paths}"
                ),
                credential_id=credential_id,
                requested_path=requested_path,
                allowed_paths=credential.allowed_paths,
                worker_id=worker_id,
            )

        # Access granted
        self._record_audit(
            credential_id=credential_id,
            job_id=credential.job_id,
            org_id=credential.org_id,
            action="access_granted",
            details=f"Access granted to '{requested_path}'",
            worker_id=worker_id,
        )

        return True

    def get_signed_url(
        self,
        credential_id: UUID,
        storage_key: str,
        operation: str,
        duration_seconds: int = DEFAULT_SIGNED_URL_DURATION_SECONDS,
        worker_id: str | None = None,
    ) -> str:
        """Generate a provider-specific pre-signed URL for storage access.

        Validates the credential's scope before generating the URL. Delegates
        actual URL generation to the appropriate storage provider adapter.

        Args:
            credential_id: The credential authorizing this access.
            storage_key: The storage object key to generate a URL for.
            operation: The operation type (read, write, delete).
            duration_seconds: How long the signed URL should be valid.
            worker_id: The worker requesting the URL (for audit, R8.5).

        Returns:
            A pre-signed URL for the requested operation.

        Raises:
            CredentialNotFoundError: If the credential does not exist.
            CredentialRevokedError: If the credential has been revoked.
            CredentialExpiredError: If the credential has expired.
            CredentialScopeViolationError: If the key is outside scope.
            CredentialBrokerError: If the operation is invalid or adapter unavailable.
        """
        # Validate operation
        try:
            StorageOperation(operation)
        except ValueError:
            valid_ops = [op.value for op in StorageOperation]
            raise CredentialBrokerError(
                message=f"Invalid operation '{operation}'. Valid options: {valid_ops}",
                credential_id=credential_id,
            )

        # Validate access (checks revocation, expiry, scope)
        self.validate_access(credential_id, storage_key, worker_id=worker_id)

        credential = self._credentials[credential_id]

        # Cap signed URL duration to credential remaining lifetime
        now = datetime.now(tz=UTC)
        remaining_seconds = int((credential.expires_at - now).total_seconds())
        effective_duration = min(duration_seconds, remaining_seconds)

        # Attempt to use a real storage adapter
        adapter = self._adapters.get(credential.storage_provider)
        if adapter is not None:
            try:
                signed_url = adapter.generate_signed_url(
                    storage_key=storage_key,
                    operation=operation,
                    duration_seconds=effective_duration,
                )
            except StorageAdapterError as exc:
                logger.error(
                    "signed_url_adapter_failed",
                    credential_id=str(credential_id),
                    provider=credential.storage_provider,
                    error=exc.message,
                )
                raise CredentialBrokerError(
                    message=(
                        f"Storage adapter '{credential.storage_provider}' failed: "
                        f"{exc.message}"
                    ),
                    credential_id=credential_id,
                ) from exc
        else:
            # Fallback: structured placeholder URL when no adapter is configured
            # (development mode or unconfigured provider)
            signed_url = (
                f"https://{credential.storage_provider}.storage.example.com"
                f"/{storage_key}"
                f"?X-Credential-Id={credential.credential_id}"
                f"&X-Operation={operation}"
                f"&X-Expires={effective_duration}"
                f"&X-Signature=PLACEHOLDER_SIGN"
            )

        logger.info(
            "signed_url_generated",
            credential_id=str(credential_id),
            job_id=str(credential.job_id),
            org_id=str(credential.org_id),
            storage_key=storage_key,
            operation=operation,
            duration_seconds=effective_duration,
            worker_id=worker_id,
            adapter_used=adapter is not None,
        )

        return signed_url

    def cleanup_expired(self) -> int:
        """Remove expired and revoked credentials from the in-memory store.

        Production deployments should run this periodically (e.g., every 5 min)
        to prevent unbounded memory growth.

        Returns:
            The number of credentials cleaned up.
        """
        now = datetime.now(tz=UTC)
        expired_ids: list[UUID] = []

        for cred_id, credential in self._credentials.items():
            if credential.is_revoked or now > credential.expires_at:
                expired_ids.append(cred_id)

        for cred_id in expired_ids:
            del self._credentials[cred_id]

        if expired_ids:
            logger.info(
                "credentials_cleaned_up",
                count=len(expired_ids),
            )

        return len(expired_ids)

    def get_audit_log(
        self, org_id: UUID, job_id: UUID | None = None
    ) -> list[CredentialAuditEntry]:
        """Query the audit log for credential operations.

        Filterable by org_id (required) and optionally by job_id (R8.6).

        Args:
            org_id: Filter entries by organization.
            job_id: Optionally filter by specific job.

        Returns:
            List of audit entries matching the filters.
        """
        entries = [e for e in self._audit_log if e.org_id == org_id]
        if job_id is not None:
            entries = [e for e in entries if e.job_id == job_id]
        return entries

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def encryption_authority(self) -> EncryptionAuthority | None:
        """Return the encryption authority for this broker instance.

        Production and development environments use separate authorities
        so that development credentials cannot be valid in production (R8.9).

        Returns:
            The configured EncryptionAuthority, or None if unconfigured.
        """
        if self._config is not None:
            return self._config.encryption_authority
        return None

    @property
    def environment(self) -> EncryptionEnvironment | None:
        """Return the encryption environment classification.

        Returns:
            DEVELOPMENT or PRODUCTION, or None if unconfigured.
        """
        if self._config is not None:
            return self._config.environment
        return None

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _path_is_allowed(self, requested_path: str, allowed_paths: list[str]) -> bool:
        """Check if a requested path falls within any of the allowed paths.

        A path is allowed if it starts with (is a prefix of) one of the
        allowed paths. This enforces that workers can only access storage
        objects within their job's designated paths.

        Args:
            requested_path: The path being accessed.
            allowed_paths: List of path prefixes that are permitted.

        Returns:
            True if the requested path is within scope.
        """
        normalized_request = requested_path.rstrip("/")
        for allowed in allowed_paths:
            normalized_allowed = allowed.rstrip("/")
            if normalized_request == normalized_allowed:
                return True
            if normalized_request.startswith(normalized_allowed + "/"):
                return True
        return False

    def _record_audit(
        self,
        credential_id: UUID,
        job_id: UUID,
        org_id: UUID,
        action: str,
        details: str = "",
        worker_id: str | None = None,
    ) -> None:
        """Record an entry in the audit log.

        Args:
            credential_id: The credential involved.
            job_id: The job associated with the credential.
            org_id: The organization that owns the job.
            action: What happened.
            details: Additional context.
            worker_id: The worker involved (if applicable).
        """
        entry = CredentialAuditEntry(
            entry_id=uuid4(),
            credential_id=credential_id,
            job_id=job_id,
            org_id=org_id,
            action=action,
            timestamp=datetime.now(tz=UTC),
            details=details,
            worker_id=worker_id,
        )
        self._audit_log.append(entry)
