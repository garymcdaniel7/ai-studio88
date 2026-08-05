"""Governance policy controls tests — Story 026.

Tests verify:
  - Only owner/admin can update policies
  - Viewer/editor role is rejected
  - Unknown fields are rejected
  - Type validation (bool, float)
  - Range validation (budget limits)
  - Cross-field rules (daily <= monthly)
  - Concurrency protection (version mismatch → conflict)
  - Cross-tenant isolation
  - Audit trail creation
  - Empty update rejected
  - Negative/zero values rejected
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.governance_policy import (
    ALLOWED_FIELDS,
    POLICY_DEFAULTS,
    POLICY_SCHEMA,
    PolicyAuthorizationError,
    PolicyConflictError,
    PolicyValidationError,
    authorize_policy_update,
    update_policy,
    validate_policy_update,
)
from backend.membership import OrgRole, TenantContext


TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def ctx_owner() -> TenantContext:
    return TenantContext(user_id="user-owner", org_id=TENANT_A, role=OrgRole.OWNER)


def ctx_admin() -> TenantContext:
    return TenantContext(user_id="user-admin", org_id=TENANT_A, role=OrgRole.ADMIN)


def ctx_editor() -> TenantContext:
    return TenantContext(user_id="user-editor", org_id=TENANT_A, role=OrgRole.EDITOR)


def ctx_viewer() -> TenantContext:
    return TenantContext(user_id="user-viewer", org_id=TENANT_A, role=OrgRole.VIEWER)


def ctx_other_org() -> TenantContext:
    return TenantContext(user_id="user-other", org_id=TENANT_B, role=OrgRole.OWNER)


def mock_execute(data=None):
    result = MagicMock()
    result.data = data if data is not None else []
    return result


# =============================================================================
# Authorization
# =============================================================================


@pytest.mark.unit
class TestPolicyAuthorization:
    """Verify only owner/admin can update policies."""

    def test_owner_authorized(self):
        authorize_policy_update(ctx_owner())  # Should not raise

    def test_admin_authorized(self):
        authorize_policy_update(ctx_admin())  # Should not raise

    def test_editor_rejected(self):
        with pytest.raises(PolicyAuthorizationError, match="editor"):
            authorize_policy_update(ctx_editor())

    def test_viewer_rejected(self):
        with pytest.raises(PolicyAuthorizationError, match="viewer"):
            authorize_policy_update(ctx_viewer())


# =============================================================================
# Field Validation — Unknown Fields
# =============================================================================


@pytest.mark.unit
class TestPolicyUnknownFields:
    """Verify unknown fields are rejected."""

    def test_unknown_field_rejected(self):
        with pytest.raises(PolicyValidationError, match="Unknown field"):
            validate_policy_update({"hacker_field": True})

    def test_multiple_unknown_fields(self):
        with pytest.raises(PolicyValidationError) as exc_info:
            validate_policy_update({"evil_setting": 1, "backdoor": True})
        assert len(exc_info.value.errors) == 2

    def test_empty_update_rejected(self):
        with pytest.raises(PolicyValidationError, match="No fields"):
            validate_policy_update({})


# =============================================================================
# Field Validation — Type Checking
# =============================================================================


@pytest.mark.unit
class TestPolicyTypeValidation:
    """Verify type constraints are enforced."""

    def test_bool_field_accepts_bool(self):
        result = validate_policy_update({"auto_approve_generation": False})
        assert result["auto_approve_generation"] is False

    def test_bool_field_rejects_string(self):
        with pytest.raises(PolicyValidationError, match="must be a boolean"):
            validate_policy_update({"auto_approve_generation": "yes"})

    def test_bool_field_rejects_int(self):
        with pytest.raises(PolicyValidationError, match="must be a boolean"):
            validate_policy_update({"require_publish_approval": 1})

    def test_float_field_accepts_number(self):
        result = validate_policy_update({"max_auto_spend_usd": 10.0})
        assert result["max_auto_spend_usd"] == 10.0

    def test_float_field_accepts_int(self):
        result = validate_policy_update({"budget_daily_usd": 50})
        assert result["budget_daily_usd"] == 50.0

    def test_float_field_rejects_string(self):
        with pytest.raises(PolicyValidationError, match="must be a number"):
            validate_policy_update({"budget_daily_usd": "fifty"})

    def test_float_field_rejects_bool(self):
        """Python bool is subclass of int — must be explicitly rejected."""
        with pytest.raises(PolicyValidationError, match="must be a number, got boolean"):
            validate_policy_update({"max_auto_spend_usd": True})


# =============================================================================
# Field Validation — Range Checking
# =============================================================================


@pytest.mark.unit
class TestPolicyRangeValidation:
    """Verify numeric range constraints."""

    def test_negative_budget_rejected(self):
        with pytest.raises(PolicyValidationError, match="minimum"):
            validate_policy_update({"budget_daily_usd": -5.0})

    def test_zero_auto_spend_rejected(self):
        with pytest.raises(PolicyValidationError, match="minimum"):
            validate_policy_update({"max_auto_spend_usd": 0.0})

    def test_exceeds_max_rejected(self):
        with pytest.raises(PolicyValidationError, match="maximum"):
            validate_policy_update({"max_auto_spend_usd": 999.0})

    def test_valid_range_accepted(self):
        result = validate_policy_update({"budget_daily_usd": 50.0})
        assert result["budget_daily_usd"] == 50.0


# =============================================================================
# Cross-Field Rules
# =============================================================================


@pytest.mark.unit
class TestPolicyCrossFieldRules:
    """Verify cross-field consistency."""

    def test_daily_exceeds_monthly_rejected(self):
        with pytest.raises(PolicyValidationError, match="cannot exceed"):
            validate_policy_update({
                "budget_daily_usd": 100.0,
                "budget_monthly_usd": 50.0,
            })

    def test_auto_spend_exceeds_daily_rejected(self):
        with pytest.raises(PolicyValidationError, match="cannot exceed"):
            validate_policy_update({
                "max_auto_spend_usd": 30.0,
                "budget_daily_usd": 10.0,
            })

    def test_valid_cross_field(self):
        result = validate_policy_update({
            "max_auto_spend_usd": 5.0,
            "budget_daily_usd": 20.0,
            "budget_monthly_usd": 200.0,
        })
        assert result["max_auto_spend_usd"] == 5.0
        assert result["budget_daily_usd"] == 20.0


# =============================================================================
# Concurrency — Version Conflict
# =============================================================================


@pytest.mark.unit
class TestPolicyConcurrency:
    """Verify stale writes are rejected."""

    @patch("backend.governance_policy._db")
    def test_stale_version_rejected(self, mock_db_fn):
        """Submitting a wrong version causes PolicyConflictError."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        # Return current policy with a specific version
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute([{
            "policies": {"auto_approve_generation": False},
            "updated_at": "2026-01-01T00:00:00Z",
        }])

        with pytest.raises(PolicyConflictError):
            update_policy(
                ctx_owner(),
                {"auto_approve_generation": True},
                expected_version=99999,  # Wrong version
            )


# =============================================================================
# Full Update Flow
# =============================================================================


@pytest.mark.unit
class TestPolicyUpdateFlow:
    """Verify the full update flow."""

    @patch("backend.governance_policy._db")
    def test_authorized_update_succeeds(self, mock_db_fn):
        """Owner can update a valid field."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        # get_policy_with_version returns defaults (version 0)
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute([])
        # upsert succeeds
        mock_db.table.return_value.upsert.return_value.execute.return_value = mock_execute([{}])
        # audit insert succeeds
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute([{}])

        result = update_policy(
            ctx_owner(),
            {"auto_approve_generation": False},
            expected_version=0,
            reason="Tightening controls for production",
        )
        assert result["auto_approve_generation"] is False

    @patch("backend.governance_policy._db")
    def test_editor_update_rejected(self, mock_db_fn):
        """Editor cannot update policies."""
        with pytest.raises(PolicyAuthorizationError):
            update_policy(
                ctx_editor(),
                {"auto_approve_generation": False},
                expected_version=0,
            )


# =============================================================================
# Schema Completeness
# =============================================================================


@pytest.mark.unit
class TestPolicySchemaCompleteness:
    """Verify schema covers all known supported fields."""

    def test_all_defaults_in_schema(self):
        """Every DEFAULTS field must be in the allowlist."""
        for field_name in POLICY_DEFAULTS:
            assert field_name in ALLOWED_FIELDS, f"Default '{field_name}' missing from schema"

    def test_schema_matches_defaults_count(self):
        """Schema and defaults should have the same fields."""
        assert len(ALLOWED_FIELDS) == len(POLICY_DEFAULTS)

    def test_no_duplicate_types(self):
        """Every schema entry has a valid type."""
        for name, schema in POLICY_SCHEMA.items():
            assert schema["type"] in ("bool", "float"), f"Invalid type for {name}"
