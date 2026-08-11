"""Error handling contract tests — Story 120.

Tests prove:
  - Every error category has correct HTTP status and retry policy
  - Response loss: partial success tracked
  - Cancellation is NOT a failure
  - Retry safety: safe ops OK, unsafe ops blocked
  - Redaction removes secrets before logging
  - Background retry exhaustion tracked
  - Durable failure persistence and resolution
  - Client response never contains internal detail
  - Correlation IDs generated and propagated
  - User messages are non-technical
"""

import pytest

from backend.error_contract import (
    CATEGORY_HTTP_STATUS,
    CATEGORY_RETRY_POLICY,
    DurableFailure,
    ErrorCategory,
    RetryPolicy,
    StructuredError,
    _reset_store,
    contains_secret,
    create_cancellation,
    create_error,
    create_partial_success,
    generate_correlation_id,
    get_exhausted_failures,
    get_retryable_failures,
    is_safe_to_retry,
    record_durable_failure,
    redact_secrets,
    resolve_failure,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"


# =============================================================================
# Error Categories (every category has status + retry)
# =============================================================================


@pytest.mark.unit
class TestErrorCategories:

    def test_every_category_has_http_status(self):
        for cat in ErrorCategory:
            assert cat in CATEGORY_HTTP_STATUS
            assert isinstance(CATEGORY_HTTP_STATUS[cat], int)

    def test_every_category_has_retry_policy(self):
        for cat in ErrorCategory:
            assert cat in CATEGORY_RETRY_POLICY
            assert isinstance(CATEGORY_RETRY_POLICY[cat], RetryPolicy)

    def test_validation_not_retryable(self):
        error = create_error(ErrorCategory.VALIDATION, "Invalid input")
        assert error.is_retryable is False
        assert error.http_status == 422

    def test_provider_retryable(self):
        error = create_error(ErrorCategory.PROVIDER, "Provider timeout")
        assert error.is_retryable is True
        assert error.http_status == 502

    def test_capability_retryable(self):
        error = create_error(ErrorCategory.CAPABILITY, "Service unavailable")
        assert error.is_retryable is True
        assert error.http_status == 503

    def test_conflict_retry_with_fresh(self):
        error = create_error(ErrorCategory.CONFLICT, "Version conflict")
        assert error.retry_policy == RetryPolicy.RETRY_WITH_FRESH
        assert error.is_retryable is True


# =============================================================================
# Cancellation ≠ Failure
# =============================================================================


@pytest.mark.unit
class TestCancellation:

    def test_cancellation_not_a_failure(self):
        error = create_cancellation("job", "job-001")
        assert error.is_cancellation is True
        assert error.is_retryable is False
        assert error.category == ErrorCategory.CANCELLATION

    def test_cancellation_user_message(self):
        error = create_cancellation()
        assert "cancelled" in error.user_message.lower()

    def test_cancellation_never_retried(self):
        error = create_cancellation()
        assert error.retry_policy == RetryPolicy.NOT_RETRYABLE


# =============================================================================
# Partial Success
# =============================================================================


@pytest.mark.unit
class TestPartialSuccess:

    def test_partial_success_tracks_items(self):
        error = create_partial_success(
            "3 of 5 shots completed",
            succeeded=["shot-0", "shot-1", "shot-2"],
            failed=["shot-3", "shot-4"],
        )
        assert error.category == ErrorCategory.PARTIAL_SUCCESS
        assert len(error.succeeded_items) == 3
        assert len(error.failed_items) == 2
        assert error.http_status == 207

    def test_partial_success_in_client_response(self):
        error = create_partial_success("Partial", ["a"], ["b"])
        response = error.to_client_response()
        assert "partial" in response["error"]
        assert response["error"]["partial"]["succeeded"] == ["a"]
        assert response["error"]["partial"]["failed"] == ["b"]


# =============================================================================
# Retry Safety
# =============================================================================


@pytest.mark.unit
class TestRetrySafety:

    def test_get_is_safe(self):
        assert is_safe_to_retry("GET") is True

    def test_read_is_safe(self):
        assert is_safe_to_retry("read") is True

    def test_post_is_unsafe(self):
        assert is_safe_to_retry("POST") is False

    def test_create_is_unsafe(self):
        assert is_safe_to_retry("create") is False

    def test_delete_is_unsafe(self):
        assert is_safe_to_retry("delete") is False

    def test_charge_is_unsafe(self):
        assert is_safe_to_retry("charge") is False

    def test_idempotent_overrides(self):
        assert is_safe_to_retry("POST", is_idempotent=True) is True
        assert is_safe_to_retry("create", is_idempotent=True) is True

    def test_unknown_default_unsafe(self):
        assert is_safe_to_retry("exotic_operation") is False


# =============================================================================
# Secret Redaction
# =============================================================================


@pytest.mark.unit
class TestRedaction:

    def test_password_redacted(self):
        text = "Connection failed: password=super_secret_123"
        result = redact_secrets(text)
        assert "super_secret_123" not in result
        assert "REDACTED" in result

    def test_api_key_redacted(self):
        text = "Error with api_key=sk-1234567890abcdef"
        result = redact_secrets(text)
        assert "sk-1234567890abcdef" not in result

    def test_bearer_token_redacted(self):
        text = "Auth: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
        result = redact_secrets(text)
        assert "eyJhbGci" not in result
        assert "REDACTED" in result

    def test_jwt_redacted(self):
        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = redact_secrets(text)
        assert "eyJhbGci" not in result

    def test_postgres_url_redacted(self):
        text = "DB: postgres://user:pass@host:5432/db"
        result = redact_secrets(text)
        assert "user:pass" not in result

    def test_safe_text_unchanged(self):
        text = "Generation completed successfully for talent-001"
        assert redact_secrets(text) == text

    def test_contains_secret_detection(self):
        assert contains_secret("password=abc") is True
        assert contains_secret("normal text") is False

    def test_empty_string_safe(self):
        assert redact_secrets("") == ""
        assert redact_secrets(None) is None  # type: ignore


# =============================================================================
# Client Response (no internal details)
# =============================================================================


@pytest.mark.unit
class TestClientResponse:

    def test_internal_detail_not_in_response(self):
        error = create_error(
            ErrorCategory.PERSISTENCE,
            user_message="Unable to save. Please try again.",
            internal_detail="PostgreSQL connection refused at 10.0.0.5:5432 password=abc",
        )
        response = error.to_client_response()
        assert "PostgreSQL" not in str(response)
        assert "10.0.0.5" not in str(response)
        assert "password" not in str(response)
        assert response["error"]["message"] == "Unable to save. Please try again."

    def test_response_has_correlation_id(self):
        error = create_error(ErrorCategory.UNKNOWN, "Something went wrong", correlation_id="cor-test-123")
        response = error.to_client_response()
        assert response["error"]["correlation_id"] == "cor-test-123"

    def test_response_has_retryability(self):
        retryable = create_error(ErrorCategory.TIMEOUT, "Timed out")
        not_retryable = create_error(ErrorCategory.VALIDATION, "Bad input")
        assert retryable.to_client_response()["error"]["is_retryable"] is True
        assert not_retryable.to_client_response()["error"]["is_retryable"] is False


# =============================================================================
# Durable Failure State
# =============================================================================


@pytest.mark.unit
class TestDurableFailures:

    def test_record_failure(self):
        error = create_error(ErrorCategory.PROVIDER, "GPU provider timeout")
        failure = record_durable_failure("job-001", ORG, error)
        assert failure.job_id == "job-001"
        assert failure.attempts == 1
        assert failure.can_retry is True

    def test_retry_increments_attempts(self):
        error = create_error(ErrorCategory.PROVIDER, "timeout")
        record_durable_failure("job-001", ORG, error)  # attempt 1
        record_durable_failure("job-001", ORG, error)  # attempt 2
        failure = record_durable_failure("job-001", ORG, error)  # attempt 3 → exhausted

        assert failure.attempts == 3
        assert failure.exhausted is True
        assert failure.can_retry is False

    def test_exhausted_cannot_retry(self):
        error = create_error(ErrorCategory.PROVIDER, "timeout")
        record_durable_failure("job-001", ORG, error, max_attempts=1)
        failure = record_durable_failure("job-001", ORG, error)
        assert failure.exhausted is True
        assert failure.can_retry is False

    def test_resolve_failure(self):
        error = create_error(ErrorCategory.PERSISTENCE, "DB write failed")
        record_durable_failure("job-002", ORG, error)
        failure = resolve_failure("job-002", "retried_successfully")
        assert failure.resolved is True
        assert failure.resolution == "retried_successfully"

    def test_get_retryable_failures(self):
        error = create_error(ErrorCategory.PROVIDER, "timeout")
        record_durable_failure("job-r1", ORG, error)
        retryable = get_retryable_failures(ORG)
        assert len(retryable) == 1
        assert retryable[0].job_id == "job-r1"

    def test_get_exhausted_failures(self):
        error = create_error(ErrorCategory.PROVIDER, "timeout")
        record_durable_failure("job-e1", ORG, error, max_attempts=1)
        record_durable_failure("job-e1", ORG, error)  # Exhausts
        exhausted = get_exhausted_failures(ORG)
        assert len(exhausted) == 1

    def test_not_retryable_error_not_in_retryable_list(self):
        error = create_error(ErrorCategory.VALIDATION, "bad input")
        record_durable_failure("job-v1", ORG, error)
        retryable = get_retryable_failures(ORG)
        assert len(retryable) == 0


# =============================================================================
# Correlation IDs
# =============================================================================


@pytest.mark.unit
class TestCorrelationIDs:

    def test_auto_generated(self):
        error = create_error(ErrorCategory.UNKNOWN, "oops")
        assert error.correlation_id.startswith("cor-")
        assert len(error.correlation_id) > 10

    def test_custom_correlation_preserved(self):
        error = create_error(ErrorCategory.TIMEOUT, "slow", correlation_id="cor-custom-abc")
        assert error.correlation_id == "cor-custom-abc"

    def test_uniqueness(self):
        id1 = generate_correlation_id()
        id2 = generate_correlation_id()
        assert id1 != id2


# =============================================================================
# Log Entry (redacted)
# =============================================================================


@pytest.mark.unit
class TestLogEntry:

    def test_log_entry_redacts_secrets(self):
        error = create_error(
            ErrorCategory.PERSISTENCE,
            user_message="Save failed",
            internal_detail="Connection to postgres://admin:s3cr3t@db:5432/prod failed",
        )
        entry = error.to_log_entry()
        assert "s3cr3t" not in entry["internal_detail"]
        assert "REDACTED" in entry["internal_detail"]

    def test_log_entry_has_context(self):
        error = create_error(
            ErrorCategory.PROVIDER,
            user_message="Generation failed",
            service="generation_platform",
            resource_type="job",
            resource_id="job-123",
        )
        entry = error.to_log_entry()
        assert entry["service"] == "generation_platform"
        assert entry["resource_type"] == "job"
        assert entry["resource_id"] == "job-123"
