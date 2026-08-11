"""Property tests for Consent Enforcement (Property 19).

Property 19: Consent Enforcement
    *For any* operation requiring consent (generation, training, publishing
    with a real-person talent), the operation SHALL NOT execute when the
    applicable consent scope is absent, expired, or revoked for the referenced
    talent.

    Also validates the fictional talent exemption: FICTIONAL talent does NOT
    require consent for generation operations.

    Invariants tested:
    - For ANY operation with a non-fictional talent, absent consent scope → 403
    - For ANY operation with a non-fictional talent, expired consent → 403
    - For ANY operation with a non-fictional talent, revoked consent → 403 CONSENT_REVOKED
    - For ANY operation with a FICTIONAL talent, consent is NOT required → passes
    - For ANY operation with no required scopes, evaluation always succeeds

**Validates: Requirements R10.2, R10.12, R39.6, A2-004**

No I/O, no DB — ConsentService.evaluate_consent is tested with mocked
repository and talent lookups.

Run with:
    pytest backend/tests/unit/test_properties/test_property_19_consent_enforcement.py -v
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st


# =============================================================================
# Lightweight in-memory fakes (no DB, no I/O)
# =============================================================================


@dataclass
class FakeConsentRecord:
    """Minimal consent record for testing consent enforcement logic."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    org_id: uuid.UUID = field(default_factory=uuid.uuid4)
    talent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    scopes: list[str] = field(default_factory=list)
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    expires_at: datetime | None = None
    granted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1


@dataclass
class FakeTalent:
    """Minimal talent object for testing identity_classification lookup."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    org_id: uuid.UUID = field(default_factory=uuid.uuid4)
    identity_classification: str = "REAL_PERSON_AUTHORIZED"


# =============================================================================
# Constants from the consent service (canonical scope/operation mappings)
# =============================================================================

OPERATION_SCOPE_MAP: dict[str, list[str]] = {
    "generation": ["generation"],
    "image_generation": ["generation", "likeness"],
    "voice_generation": ["voice"],
    "training": ["training"],
    "lora_training": ["training"],
    "publishing": ["publishing"],
    "commercial_use": ["commercial"],
    "adult_content": ["adult_content"],
    "client_work": ["client_work"],
}

VALID_CONSENT_SCOPES: list[str] = [
    "likeness",
    "voice",
    "training",
    "generation",
    "adult_content",
    "commercial",
    "publishing",
    "client_work",
]

# Operations that require at least one scope
CONSENT_REQUIRED_OPERATIONS: list[str] = list(OPERATION_SCOPE_MAP.keys())


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Strategy for a single valid consent scope
scope_strategy = st.sampled_from(VALID_CONSENT_SCOPES)

# Strategy for a non-empty subset of scopes
scopes_subset_strategy = st.lists(
    scope_strategy,
    min_size=1,
    max_size=len(VALID_CONSENT_SCOPES),
    unique=True,
)

# Strategy for operations that require consent
operation_strategy = st.sampled_from(CONSENT_REQUIRED_OPERATIONS)

# Strategy for identity classifications
identity_classification_strategy = st.sampled_from([
    "REAL_PERSON_AUTHORIZED",
    "REAL_PERSON_SELF",
])

# Strategy for fictional classification
fictional_classification_strategy = st.just("FICTIONAL")


# =============================================================================
# Helpers: Build ConsentService with controlled mocks (no DB)
# =============================================================================


def _make_consent_service(
    org_id: uuid.UUID,
    talent_id: uuid.UUID,
    identity_classification: str = "REAL_PERSON_AUTHORIZED",
    active_records: list[FakeConsentRecord] | None = None,
    revoked_records: list[FakeConsentRecord] | None = None,
):
    """Create a ConsentService with mocked internals for pure unit testing.

    No DB, no SQLAlchemy session — the service's internal methods are
    patched to return controlled data.

    Args:
        org_id: The tenant org_id.
        talent_id: The talent being evaluated.
        identity_classification: Talent's identity classification.
        active_records: List of active (non-revoked, non-expired) consent records.
        revoked_records: List of revoked consent records (for revoked-scope detection).

    Returns:
        A ConsentService instance with mocked dependencies.
    """
    from app.services.consent_service import ConsentService

    # Create mock DB session and tenant context
    mock_db = AsyncMock()
    mock_tenant = MagicMock()
    mock_tenant.org_id = org_id

    service = ConsentService(db=mock_db, tenant=mock_tenant)

    # Mock _is_fictional_talent
    async def _mock_is_fictional(tid: uuid.UUID) -> bool:
        return identity_classification == "FICTIONAL"

    service._is_fictional_talent = _mock_is_fictional  # type: ignore[method-assign]

    # Mock the repository's get_active_for_talent
    if active_records is None:
        active_records = []

    async def _mock_get_active(tid: uuid.UUID) -> list[FakeConsentRecord]:
        return active_records  # type: ignore[return-value]

    service._repo = MagicMock()
    service._repo.get_active_for_talent = AsyncMock(side_effect=_mock_get_active)

    # Mock _get_revoked_scopes
    if revoked_records is None:
        revoked_records = []

    revoked_scopes: set[str] = set()
    for rec in revoked_records:
        revoked_scopes.update(rec.scopes)

    async def _mock_get_revoked(tid: uuid.UUID) -> set[str]:
        return revoked_scopes

    service._get_revoked_scopes = _mock_get_revoked  # type: ignore[method-assign]

    return service


# =============================================================================
# Property 19: Consent Enforcement
# Feature: production-revamp, Property 19
# =============================================================================


@pytest.mark.unit
class TestProperty19ConsentEnforcement:
    """Property 19: Consent Enforcement.

    For any operation requiring consent with absent/expired/revoked scope,
    the operation is blocked (403). Fictional talent exemption allows
    operations without consent.

    **Validates: Requirements R10.2, R10.12, R39.6, A2-004**
    """

    # =========================================================================
    # Absent consent → 403 CONSENT_REQUIRED
    # =========================================================================

    @settings(max_examples=200, deadline=None)
    @given(
        operation=operation_strategy,
        identity_class=identity_classification_strategy,
    )
    @pytest.mark.asyncio
    async def test_absent_consent_blocks_operation(
        self,
        operation: str,
        identity_class: str,
    ) -> None:
        """Operation requiring consent with NO active consent records → 403.

        **Validates: Requirements R10.2, R10.12**

        Property: For ANY operation in OPERATION_SCOPE_MAP and ANY non-fictional
        talent with zero active consent records, evaluate_consent raises 403.
        """
        from fastapi import HTTPException

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # No active records at all
        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification=identity_class,
            active_records=[],
            revoked_records=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(talent_id, operation)

        assert exc_info.value.status_code == 403
        assert "CONSENT_REQUIRED" in (
            exc_info.value.headers.get("X-Error-Code", "")
        )

    @settings(max_examples=200, deadline=None)
    @given(
        operation=operation_strategy,
        identity_class=identity_classification_strategy,
        available_scopes=scopes_subset_strategy,
    )
    @pytest.mark.asyncio
    async def test_wrong_scopes_blocks_operation(
        self,
        operation: str,
        identity_class: str,
        available_scopes: list[str],
    ) -> None:
        """Operation where active scopes do NOT cover required scopes → 403.

        **Validates: Requirements R10.2, R10.12, A2-004**

        Property: For ANY operation, if the active consent scopes do not
        include ALL required scopes for that operation, evaluate_consent
        raises 403.
        """
        from fastapi import HTTPException

        required_scopes = OPERATION_SCOPE_MAP.get(operation, [])
        # Only test when the available scopes do NOT cover the required ones
        assume(not all(s in available_scopes for s in required_scopes))

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # Create a record with the available scopes (which don't cover requirement)
        active_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=available_scopes,
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification=identity_class,
            active_records=[active_record],
            revoked_records=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(talent_id, operation)

        assert exc_info.value.status_code == 403

    # =========================================================================
    # Revoked consent → 403 CONSENT_REVOKED
    # =========================================================================

    @settings(max_examples=200, deadline=None)
    @given(
        operation=operation_strategy,
        identity_class=identity_classification_strategy,
    )
    @pytest.mark.asyncio
    async def test_revoked_consent_blocks_with_consent_revoked(
        self,
        operation: str,
        identity_class: str,
    ) -> None:
        """Operation where required scopes have been revoked → 403 CONSENT_REVOKED.

        **Validates: Requirements R10.2, R10.12, R39.6, A2-004**

        Property: For ANY operation with a non-fictional talent whose
        required consent scopes are REVOKED, evaluate_consent raises 403
        with error code CONSENT_REVOKED (not just CONSENT_REQUIRED).
        """
        from fastapi import HTTPException

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        required_scopes = OPERATION_SCOPE_MAP.get(operation, [])
        assume(len(required_scopes) > 0)

        # Create revoked records covering the required scopes
        revoked_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=required_scopes,
            revoked_at=datetime.now(UTC) - timedelta(hours=1),
            revocation_reason="Consent withdrawn by talent",
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification=identity_class,
            active_records=[],  # No active records
            revoked_records=[revoked_record],
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(talent_id, operation)

        assert exc_info.value.status_code == 403
        assert "CONSENT_REVOKED" in (
            exc_info.value.headers.get("X-Error-Code", "")
        )

    # =========================================================================
    # Expired consent → 403 CONSENT_REQUIRED
    # =========================================================================

    @settings(max_examples=200, deadline=None)
    @given(
        operation=operation_strategy,
        identity_class=identity_classification_strategy,
    )
    @pytest.mark.asyncio
    async def test_expired_consent_blocks_operation(
        self,
        operation: str,
        identity_class: str,
    ) -> None:
        """Operation with only expired consent (not in active records) → 403.

        **Validates: Requirements R10.2, A2-004**

        Property: For ANY operation with a non-fictional talent whose
        consent has expired (not returned by get_active_for_talent which
        filters expired records), evaluate_consent raises 403.

        Note: The repository's get_active_for_talent already excludes expired
        records, so from the service's perspective, expired = absent.
        """
        from fastapi import HTTPException

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        required_scopes = OPERATION_SCOPE_MAP.get(operation, [])
        assume(len(required_scopes) > 0)

        # No active records returned (expired ones are filtered by repo)
        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification=identity_class,
            active_records=[],
            revoked_records=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(talent_id, operation)

        assert exc_info.value.status_code == 403
        assert "CONSENT_REQUIRED" in (
            exc_info.value.headers.get("X-Error-Code", "")
        )

    # =========================================================================
    # Fictional talent exemption → passes without consent
    # =========================================================================

    @settings(max_examples=200, deadline=None)
    @given(operation=operation_strategy)
    @pytest.mark.asyncio
    async def test_fictional_talent_exempt_from_consent(
        self,
        operation: str,
    ) -> None:
        """FICTIONAL talent is exempt from consent for all operations.

        **Validates: Requirements R10.12, R39.6, A2-004**

        Property: For ANY operation, if the talent has identity_classification
        = FICTIONAL, evaluate_consent returns True regardless of whether
        consent records exist.
        """
        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # No consent records at all — should still pass for fictional
        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="FICTIONAL",
            active_records=[],
            revoked_records=[],
        )

        result = await service.evaluate_consent(talent_id, operation)
        assert result is True

    # =========================================================================
    # Sufficient consent → operation passes
    # =========================================================================

    @settings(max_examples=200, deadline=None)
    @given(
        operation=operation_strategy,
        identity_class=identity_classification_strategy,
    )
    @pytest.mark.asyncio
    async def test_sufficient_consent_allows_operation(
        self,
        operation: str,
        identity_class: str,
    ) -> None:
        """Operation with ALL required scopes covered → passes (returns True).

        **Validates: Requirements R10.2, R10.12, A2-004**

        Property: For ANY operation with a non-fictional talent, if active
        consent records cover ALL required scopes, evaluate_consent returns
        True (does not raise).
        """
        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        required_scopes = OPERATION_SCOPE_MAP.get(operation, [])

        # Create active record covering all required scopes
        active_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=required_scopes,
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification=identity_class,
            active_records=[active_record],
            revoked_records=[],
        )

        result = await service.evaluate_consent(talent_id, operation)
        assert result is True

    # =========================================================================
    # Multiple records cover scopes cumulatively
    # =========================================================================

    @settings(max_examples=100, deadline=None)
    @given(
        operation=st.sampled_from(["image_generation"]),
        identity_class=identity_classification_strategy,
    )
    @pytest.mark.asyncio
    async def test_multiple_records_provide_cumulative_coverage(
        self,
        operation: str,
        identity_class: str,
    ) -> None:
        """Multiple consent records collectively cover required scopes → passes.

        **Validates: Requirements R10.2, A2-004**

        Property: For image_generation (which requires ["generation", "likeness"]),
        two separate records each covering one scope still allows the operation.
        """
        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # Two separate records, each covering one scope
        record_1 = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["generation"],
        )
        record_2 = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["likeness"],
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification=identity_class,
            active_records=[record_1, record_2],
            revoked_records=[],
        )

        result = await service.evaluate_consent(talent_id, operation)
        assert result is True

    # =========================================================================
    # Unknown operation (no mapped scopes) → always passes
    # =========================================================================

    @settings(max_examples=50, deadline=None)
    @given(
        identity_class=identity_classification_strategy,
    )
    @pytest.mark.asyncio
    async def test_operation_with_no_required_scopes_always_passes(
        self,
        identity_class: str,
    ) -> None:
        """Operation not in OPERATION_SCOPE_MAP (no scopes needed) → passes.

        **Validates: Requirements R10.2, A2-004**

        Property: For ANY operation that maps to an empty scope list (or is
        not in the map), evaluate_consent returns True regardless of consent
        state.
        """
        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # Use an operation not in the map
        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification=identity_class,
            active_records=[],
            revoked_records=[],
        )

        result = await service.evaluate_consent(talent_id, "unknown_operation")
        assert result is True


# =============================================================================
# Deterministic Edge Case Tests (complement to property tests)
# =============================================================================


@pytest.mark.unit
class TestConsentEnforcementEdgeCases:
    """Deterministic edge cases for consent enforcement."""

    @pytest.mark.asyncio
    async def test_partial_scope_coverage_blocks(self) -> None:
        """image_generation needs both generation + likeness; only one → 403."""
        from fastapi import HTTPException

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # Only "generation" but not "likeness"
        active_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["generation"],
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="REAL_PERSON_AUTHORIZED",
            active_records=[active_record],
            revoked_records=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(talent_id, "image_generation")

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_revoked_plus_absent_shows_consent_revoked(self) -> None:
        """When a missing scope was specifically revoked, error is CONSENT_REVOKED."""
        from fastapi import HTTPException

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        revoked_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["training"],
            revoked_at=datetime.now(UTC) - timedelta(days=1),
            revocation_reason="Talent withdrew training consent",
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="REAL_PERSON_SELF",
            active_records=[],
            revoked_records=[revoked_record],
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(talent_id, "training")

        assert exc_info.value.status_code == 403
        assert exc_info.value.headers["X-Error-Code"] == "CONSENT_REVOKED"

    @pytest.mark.asyncio
    async def test_fictional_talent_no_consent_no_records(self) -> None:
        """FICTIONAL talent passes even with zero records and revoked scopes."""
        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        revoked_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["generation", "likeness", "voice", "training"],
            revoked_at=datetime.now(UTC),
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="FICTIONAL",
            active_records=[],
            revoked_records=[revoked_record],
        )

        # All operations pass for fictional
        for operation in CONSENT_REQUIRED_OPERATIONS:
            result = await service.evaluate_consent(talent_id, operation)
            assert result is True

    @pytest.mark.asyncio
    async def test_all_scopes_covered_passes_all_operations(self) -> None:
        """Active consent covering all scopes passes every operation."""
        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # One record with all scopes
        active_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=VALID_CONSENT_SCOPES,
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="REAL_PERSON_AUTHORIZED",
            active_records=[active_record],
            revoked_records=[],
        )

        for operation in CONSENT_REQUIRED_OPERATIONS:
            result = await service.evaluate_consent(talent_id, operation)
            assert result is True

    @pytest.mark.asyncio
    async def test_voice_generation_requires_voice_scope(self) -> None:
        """voice_generation specifically requires 'voice' scope."""
        from fastapi import HTTPException

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # Has all scopes EXCEPT voice
        active_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["generation", "likeness", "training", "publishing"],
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="REAL_PERSON_SELF",
            active_records=[active_record],
            revoked_records=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(talent_id, "voice_generation")

        assert exc_info.value.status_code == 403
        assert "voice" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_explicit_required_scopes_override(self) -> None:
        """Caller can pass explicit required_scopes to override the map."""
        from fastapi import HTTPException

        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        # Has generation scope but not a custom one
        active_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["generation"],
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="REAL_PERSON_AUTHORIZED",
            active_records=[active_record],
            revoked_records=[],
        )

        # Override with a custom required scope
        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_consent(
                talent_id, "generation", required_scopes=["commercial"]
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_explicit_required_scopes_when_covered(self) -> None:
        """Explicit required_scopes that are covered → passes."""
        org_id = uuid.uuid4()
        talent_id = uuid.uuid4()

        active_record = FakeConsentRecord(
            org_id=org_id,
            talent_id=talent_id,
            scopes=["commercial", "publishing"],
        )

        service = _make_consent_service(
            org_id=org_id,
            talent_id=talent_id,
            identity_classification="REAL_PERSON_AUTHORIZED",
            active_records=[active_record],
            revoked_records=[],
        )

        result = await service.evaluate_consent(
            talent_id, "custom_op", required_scopes=["commercial"]
        )
        assert result is True
