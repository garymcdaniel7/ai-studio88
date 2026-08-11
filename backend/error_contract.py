"""Error Handling Contract — Story 120.

Typed error taxonomy, correlation IDs, structured logging, retry rules,
durable failure state, redaction, and user messaging.

Error categories:
    VALIDATION       — Input validation failed (422, not retryable)
    AUTHENTICATION   — Invalid/expired credentials (401, not retryable)
    AUTHORIZATION    — Insufficient permissions (403, not retryable)
    NOT_FOUND        — Resource not found (404, not retryable)
    CONFLICT         — Version/state conflict (409, retry with fresh data)
    CAPABILITY       — Service unavailable (503, retryable after backoff)
    PROVIDER         — External provider failed (502, retryable)
    TIMEOUT          — Operation timed out (504, retryable)
    CANCELLATION     — User cancelled (not a failure, not retryable)
    PARTIAL_SUCCESS  — Some operations succeeded, some failed (mixed)
    PERSISTENCE      — Storage/DB write failed (500, retryable)
    UNKNOWN          — Unexpected error (500, not auto-retried)

Rules:
    - Every error has a correlation_id for tracing
    - User messages are non-technical and actionable
    - Internal details are logged but NEVER sent to client
    - Secrets are redacted before logging
    - Only safe/idempotent operations auto-retry
    - Background failures persist with retryability flag
    - Cancellation is NEVER converted to failure
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Error Categories
# =============================================================================


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    CAPABILITY = "capability_unavailable"
    PROVIDER = "provider_failure"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    PARTIAL_SUCCESS = "partial_success"
    PERSISTENCE = "persistence_failure"
    UNKNOWN = "unknown"


# =============================================================================
# Retry Policy
# =============================================================================


class RetryPolicy(str, Enum):
    NOT_RETRYABLE = "not_retryable"       # Never retry (user error, auth, not found)
    SAFE_RETRY = "safe_retry"             # Safe to retry (idempotent, GET, read-only)
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # Retry after delay (provider, timeout)
    RETRY_WITH_FRESH = "retry_with_fresh"      # Retry after refreshing data (conflict)
    MANUAL_RETRY = "manual_retry"              # User must explicitly retry


# Default retry policy per category
CATEGORY_RETRY_POLICY: dict[ErrorCategory, RetryPolicy] = {
    ErrorCategory.VALIDATION: RetryPolicy.NOT_RETRYABLE,
    ErrorCategory.AUTHENTICATION: RetryPolicy.NOT_RETRYABLE,
    ErrorCategory.AUTHORIZATION: RetryPolicy.NOT_RETRYABLE,
    ErrorCategory.NOT_FOUND: RetryPolicy.NOT_RETRYABLE,
    ErrorCategory.CONFLICT: RetryPolicy.RETRY_WITH_FRESH,
    ErrorCategory.CAPABILITY: RetryPolicy.RETRY_WITH_BACKOFF,
    ErrorCategory.PROVIDER: RetryPolicy.RETRY_WITH_BACKOFF,
    ErrorCategory.TIMEOUT: RetryPolicy.RETRY_WITH_BACKOFF,
    ErrorCategory.CANCELLATION: RetryPolicy.NOT_RETRYABLE,
    ErrorCategory.PARTIAL_SUCCESS: RetryPolicy.MANUAL_RETRY,
    ErrorCategory.PERSISTENCE: RetryPolicy.RETRY_WITH_BACKOFF,
    ErrorCategory.UNKNOWN: RetryPolicy.NOT_RETRYABLE,
}

# HTTP status codes per category
CATEGORY_HTTP_STATUS: dict[ErrorCategory, int] = {
    ErrorCategory.VALIDATION: 422,
    ErrorCategory.AUTHENTICATION: 401,
    ErrorCategory.AUTHORIZATION: 403,
    ErrorCategory.NOT_FOUND: 404,
    ErrorCategory.CONFLICT: 409,
    ErrorCategory.CAPABILITY: 503,
    ErrorCategory.PROVIDER: 502,
    ErrorCategory.TIMEOUT: 504,
    ErrorCategory.CANCELLATION: 499,
    ErrorCategory.PARTIAL_SUCCESS: 207,
    ErrorCategory.PERSISTENCE: 500,
    ErrorCategory.UNKNOWN: 500,
}


# =============================================================================
# Structured Error
# =============================================================================


@dataclass
class StructuredError:
    """A typed, traceable error with user-safe messaging and redaction."""
    # Identity
    error_id: str = field(default_factory=lambda: f"err-{uuid.uuid4().hex[:12]}")
    correlation_id: str = ""  # Links to request/job for tracing

    # Classification
    category: ErrorCategory = ErrorCategory.UNKNOWN
    code: str = ""            # Machine-readable code (e.g. "BUDGET_EXCEEDED")

    # Messages
    user_message: str = ""    # Non-technical, actionable, safe for display
    internal_detail: str = "" # Technical detail (NEVER sent to client)

    # Context
    service: str = ""         # Which service/module produced this
    resource_type: str = ""   # What resource was affected
    resource_id: str = ""     # Which specific resource

    # Retry
    retry_policy: RetryPolicy = RetryPolicy.NOT_RETRYABLE
    retry_after_seconds: int | None = None  # Suggested retry delay
    max_retries: int = 0
    attempt: int = 0

    # Partial success
    succeeded_items: list[str] = field(default_factory=list)
    failed_items: list[str] = field(default_factory=list)

    # State
    is_cancellation: bool = False  # Explicitly NOT a failure
    timestamp: float = field(default_factory=time.time)

    @property
    def is_retryable(self) -> bool:
        """Can this error be safely retried?"""
        if self.is_cancellation:
            return False
        return self.retry_policy in (
            RetryPolicy.SAFE_RETRY,
            RetryPolicy.RETRY_WITH_BACKOFF,
            RetryPolicy.RETRY_WITH_FRESH,
        )

    @property
    def http_status(self) -> int:
        return CATEGORY_HTTP_STATUS.get(self.category, 500)

    def to_client_response(self) -> dict[str, Any]:
        """Serialize for API response — redacts internal details."""
        response: dict[str, Any] = {
            "error": {
                "code": self.code or self.category.value,
                "message": self.user_message,
                "category": self.category.value,
                "correlation_id": self.correlation_id,
                "is_retryable": self.is_retryable,
            },
        }
        if self.retry_after_seconds:
            response["error"]["retry_after_seconds"] = self.retry_after_seconds
        if self.succeeded_items or self.failed_items:
            response["error"]["partial"] = {
                "succeeded": self.succeeded_items,
                "failed": self.failed_items,
            }
        return response

    def to_log_entry(self) -> dict[str, Any]:
        """Serialize for structured logging — includes internal detail (redacted)."""
        return {
            "error_id": self.error_id,
            "correlation_id": self.correlation_id,
            "category": self.category.value,
            "code": self.code,
            "service": self.service,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "internal_detail": redact_secrets(self.internal_detail),
            "retry_policy": self.retry_policy.value,
            "attempt": self.attempt,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Durable Failure State (for background jobs)
# =============================================================================


@dataclass
class DurableFailure:
    """Persisted failure record for background operations.

    Unlike transient HTTP errors, these persist until resolved or
    retry limit exhausted.
    """
    failure_id: str = field(default_factory=lambda: f"fail-{uuid.uuid4().hex[:12]}")
    job_id: str = ""
    org_id: str = ""
    error: StructuredError = field(default_factory=StructuredError)

    # Retry state
    attempts: int = 0
    max_attempts: int = 3
    next_retry_at: float | None = None
    exhausted: bool = False

    # Outcome
    resolved: bool = False
    resolved_at: float | None = None
    resolution: str = ""  # "retried_successfully" | "manually_resolved" | "abandoned"

    @property
    def can_retry(self) -> bool:
        return (
            not self.resolved
            and not self.exhausted
            and self.error.is_retryable
            and self.attempts < self.max_attempts
        )


# =============================================================================
# Store (durable failures)
# =============================================================================

_durable_failures: dict[str, DurableFailure] = {}


# =============================================================================
# Error Factory
# =============================================================================


def create_error(
    category: ErrorCategory,
    user_message: str,
    internal_detail: str = "",
    code: str = "",
    service: str = "",
    resource_type: str = "",
    resource_id: str = "",
    correlation_id: str = "",
    retry_after_seconds: int | None = None,
) -> StructuredError:
    """Create a typed structured error."""
    return StructuredError(
        category=category,
        code=code or category.value.upper(),
        user_message=user_message,
        internal_detail=internal_detail,
        service=service,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id or generate_correlation_id(),
        retry_policy=CATEGORY_RETRY_POLICY[category],
        retry_after_seconds=retry_after_seconds,
        is_cancellation=category == ErrorCategory.CANCELLATION,
    )


def create_partial_success(
    user_message: str,
    succeeded: list[str],
    failed: list[str],
    correlation_id: str = "",
) -> StructuredError:
    """Create a partial success error (some items succeeded, some failed)."""
    error = create_error(
        ErrorCategory.PARTIAL_SUCCESS,
        user_message=user_message,
        correlation_id=correlation_id,
    )
    error.succeeded_items = succeeded
    error.failed_items = failed
    return error


def create_cancellation(
    resource_type: str = "",
    resource_id: str = "",
    correlation_id: str = "",
) -> StructuredError:
    """Create a cancellation record (explicitly NOT a failure)."""
    return create_error(
        ErrorCategory.CANCELLATION,
        user_message="Operation was cancelled.",
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
    )


# =============================================================================
# Durable Failure Management
# =============================================================================


def record_durable_failure(
    job_id: str,
    org_id: str,
    error: StructuredError,
    max_attempts: int = 3,
) -> DurableFailure:
    """Record a background failure that persists until resolved."""
    # Check for existing
    existing = _durable_failures.get(job_id)
    if existing and not existing.resolved:
        existing.attempts += 1
        existing.error = error
        if existing.attempts >= existing.max_attempts:
            existing.exhausted = True
        elif error.retry_after_seconds:
            existing.next_retry_at = time.time() + error.retry_after_seconds
        return existing

    failure = DurableFailure(
        job_id=job_id,
        org_id=org_id,
        error=error,
        max_attempts=max_attempts,
        attempts=1,
    )
    if error.retry_after_seconds:
        failure.next_retry_at = time.time() + error.retry_after_seconds

    _durable_failures[job_id] = failure
    return failure


def resolve_failure(job_id: str, resolution: str = "retried_successfully") -> DurableFailure | None:
    """Mark a durable failure as resolved."""
    failure = _durable_failures.get(job_id)
    if not failure:
        return None
    failure.resolved = True
    failure.resolved_at = time.time()
    failure.resolution = resolution
    return failure


def get_retryable_failures(org_id: str) -> list[DurableFailure]:
    """Get all retryable failures for an org (for retry scheduler)."""
    now = time.time()
    return [
        f for f in _durable_failures.values()
        if f.org_id == org_id
        and f.can_retry
        and (f.next_retry_at is None or now >= f.next_retry_at)
    ]


def get_exhausted_failures(org_id: str) -> list[DurableFailure]:
    """Get failures that have exhausted retries (need manual attention)."""
    return [
        f for f in _durable_failures.values()
        if f.org_id == org_id and f.exhausted and not f.resolved
    ]


# =============================================================================
# Secret Redaction
# =============================================================================

# Patterns that indicate secrets (key=value, Bearer tokens, connection strings)
SECRET_PATTERNS = [
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"(api[_-]?key|apikey)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"(secret|token)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer ***REDACTED***"),
    (re.compile(r"(supabase[_-]?\w*key)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"(b2[_-]?\w*key)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"postgres://\S+", re.IGNORECASE), "postgres://***REDACTED***"),
    (re.compile(r"(eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+)"), "***JWT_REDACTED***"),
]


def redact_secrets(text: str) -> str:
    """Redact known secret patterns from text before logging."""
    if not text:
        return text
    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def contains_secret(text: str) -> bool:
    """Check if text likely contains a secret."""
    if not text:
        return False
    for pattern, _ in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


# =============================================================================
# Correlation ID
# =============================================================================


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracing."""
    return f"cor-{uuid.uuid4().hex[:16]}"


# =============================================================================
# Structured Logging Helper
# =============================================================================


def log_error(error: StructuredError) -> None:
    """Log a structured error with proper redaction."""
    entry = error.to_log_entry()
    if error.category in (ErrorCategory.UNKNOWN, ErrorCategory.PERSISTENCE):
        logger.error(f"STRUCTURED_ERROR: {entry}")
    elif error.category in (ErrorCategory.PROVIDER, ErrorCategory.TIMEOUT, ErrorCategory.CAPABILITY):
        logger.warning(f"STRUCTURED_ERROR: {entry}")
    elif error.category == ErrorCategory.CANCELLATION:
        logger.info(f"CANCELLATION: {entry}")
    else:
        logger.info(f"STRUCTURED_ERROR: {entry}")


# =============================================================================
# Retry Safety Check
# =============================================================================


# Operations that are safe to automatically retry
SAFE_OPERATIONS = frozenset({
    "get", "head", "options",  # HTTP methods (lowercase)
    "read", "list", "query", "check", "verify",  # Action verbs
})

# Operations that must NOT be automatically retried
UNSAFE_OPERATIONS = frozenset({
    "post", "put", "delete", "patch",  # Mutating HTTP methods
    "create", "update", "submit", "transfer", "charge",
})


def is_safe_to_retry(operation: str, is_idempotent: bool = False) -> bool:
    """Determine if an operation is safe to automatically retry.

    Safe if:
    - Operation is inherently safe (GET, read, etc.)
    - Operation is explicitly marked idempotent (idempotency key)

    Never auto-retry:
    - Mutating operations without idempotency guarantee
    - Payment/charge operations
    """
    op_lower = operation.lower()
    if is_idempotent:
        return True
    if op_lower in SAFE_OPERATIONS or any(s in op_lower for s in SAFE_OPERATIONS):
        return True
    if op_lower in UNSAFE_OPERATIONS or any(s in op_lower for s in UNSAFE_OPERATIONS):
        return False
    return False  # Default: don't auto-retry unknown operations


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _durable_failures.clear()
