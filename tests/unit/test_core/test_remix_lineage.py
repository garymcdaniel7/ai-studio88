"""Remix lineage tests — Story 108.

Tests prove:
  - Source deleted → SourceUnavailable
  - Context incomplete → SourceUnavailable
  - Model unavailable → CompatibilityError (with guidance)
  - Consent revoked → ConsentError
  - Cross-tenant source → RemixDenied
  - Multi-generation ancestry traversal
  - Duplicate submission idempotent
  - Partial reset: some fields inherit, some override, some reset
  - Full lifecycle: create → validate → submit → complete
  - Lineage link created on completion
  - Effective values computed correctly per action
"""

import pytest

from backend.remix_lineage import (
    CompatibilityError,
    ConsentError,
    FieldAction,
    RemixDenied,
    RemixStatus,
    SourceUnavailable,
    _inject_condition,
    _register_source,
    _reset_store,
    complete_remix,
    create_remix,
    fail_remix,
    get_ancestry,
    get_children,
    get_remix_details,
    submit_remix,
    validate_remix,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-001"
SOURCE_ASSET = "ast-source-001"

SOURCE_SNAPSHOT = {
    "job_id": "job-orig-001",
    "snapshot_id": "snap-001",
    "context_package_id": "pkg-001",
    "prompt": "a sunset over mountains, photorealistic, 8k",
    "negative_prompt": "blurry, low quality",
    "model_id": "flux_dev",
    "model_version": "1.0.0",
    "lora_ids": ["lora-face-001"],
    "lora_versions": ["v2.1"],
    "lora_strengths": [0.8],
    "seed": 42,
    "width": 1024,
    "height": 1024,
    "steps": 25,
    "cfg": 7.5,
    "talent_id": "talent-001",
    "workflow_id": "wf-001",
    "recipe_id": None,
}


def _setup_source():
    _register_source(SOURCE_ASSET, ORG, SOURCE_SNAPSHOT)


# =============================================================================
# Full Lifecycle
# =============================================================================


@pytest.mark.unit
class TestFullLifecycle:

    def test_create_validate_submit_complete(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "prompt": {"action": "override", "value": "a sunrise over ocean"},
            "seed": {"action": "reset"},
        })
        assert spec.status == RemixStatus.DRAFT
        assert spec.source_asset_id == SOURCE_ASSET

        validate_remix(spec.remix_id, ORG)
        assert spec.status == RemixStatus.VALIDATED

        submit_remix(spec.remix_id, ORG, "job-remix-001")
        assert spec.status == RemixStatus.SUBMITTED

        complete_remix(spec.remix_id, ORG, "ast-result-001")
        assert spec.status == RemixStatus.COMPLETED
        assert spec.result_asset_id == "ast-result-001"


# =============================================================================
# Field Actions
# =============================================================================


@pytest.mark.unit
class TestFieldActions:

    def test_inherit_uses_source_value(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "model_id": {"action": "inherit"},
        })
        assert spec.fields["model_id"].effective_value == "flux_dev"

    def test_override_uses_new_value(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "prompt": {"action": "override", "value": "new prompt"},
        })
        assert spec.fields["prompt"].effective_value == "new prompt"

    def test_reset_uses_default(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "seed": {"action": "reset"},
        })
        assert spec.fields["seed"].effective_value is None  # Default = random

    def test_partial_reset_mixed_actions(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "prompt": {"action": "override", "value": "different scene"},
            "model_id": {"action": "inherit"},
            "seed": {"action": "reset"},
            "width": {"action": "override", "value": 512},
        })
        assert "prompt" in spec.overridden_fields
        assert "model_id" in spec.inherited_fields
        assert "seed" in spec.reset_fields
        assert spec.fields["width"].effective_value == 512
        assert spec.fields["model_id"].effective_value == "flux_dev"

    def test_default_action_is_inherit(self):
        """Fields not specified default to INHERIT."""
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {})
        assert spec.fields["prompt"].action == FieldAction.INHERIT
        assert spec.fields["prompt"].effective_value == SOURCE_SNAPSHOT["prompt"]


# =============================================================================
# Source Deleted
# =============================================================================


@pytest.mark.unit
class TestSourceDeleted:

    def test_deleted_source_raises(self):
        _setup_source()
        _inject_condition("source_deleted")
        with pytest.raises(SourceUnavailable, match="deleted"):
            create_remix(ORG, USER, SOURCE_ASSET, {})


# =============================================================================
# Context Incomplete
# =============================================================================


@pytest.mark.unit
class TestContextIncomplete:

    def test_incomplete_context_raises(self):
        # Don't register source snapshot
        _inject_condition("context_incomplete")
        from backend.remix_lineage import _asset_orgs
        _asset_orgs[SOURCE_ASSET] = ORG
        with pytest.raises(SourceUnavailable, match="incomplete"):
            create_remix(ORG, USER, SOURCE_ASSET, {})


# =============================================================================
# Model Unavailable
# =============================================================================


@pytest.mark.unit
class TestModelUnavailable:

    def test_inherited_unavailable_model_raises(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "model_id": {"action": "inherit"},
        })
        _inject_condition("model_unavailable")
        with pytest.raises(CompatibilityError, match="no longer deployable"):
            validate_remix(spec.remix_id, ORG)

    def test_overridden_model_not_checked(self):
        """If model is OVERRIDE, unavailability of source model doesn't matter."""
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "model_id": {"action": "override", "value": "sdxl"},
        })
        _inject_condition("model_unavailable")
        # Should not raise — model_id is overridden, not inherited
        result = validate_remix(spec.remix_id, ORG)
        assert result.status == RemixStatus.VALIDATED


# =============================================================================
# Consent Revoked
# =============================================================================


@pytest.mark.unit
class TestConsentRevoked:

    def test_inherited_talent_consent_revoked_raises(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "talent_id": {"action": "inherit"},
        })
        _inject_condition("consent_revoked")
        with pytest.raises(ConsentError, match="Consent revoked"):
            validate_remix(spec.remix_id, ORG)

    def test_reset_talent_avoids_consent_check(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "talent_id": {"action": "reset"},
        })
        _inject_condition("consent_revoked")
        # RESET means no talent — consent check not triggered
        result = validate_remix(spec.remix_id, ORG)
        assert result.status == RemixStatus.VALIDATED


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_source_rejected(self):
        _register_source(SOURCE_ASSET, OTHER_ORG, SOURCE_SNAPSHOT)
        with pytest.raises(RemixDenied, match="different workspace"):
            create_remix(ORG, USER, SOURCE_ASSET, {})

    def test_same_tenant_source_accepted(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {})
        assert spec.org_id == ORG


# =============================================================================
# Multi-Generation Ancestry
# =============================================================================


@pytest.mark.unit
class TestMultiGenerationAncestry:

    def test_ancestry_chain(self):
        _setup_source()
        # Gen 1: remix from source
        r1 = create_remix(ORG, USER, SOURCE_ASSET, {"prompt": {"action": "override", "value": "v2"}})
        submit_remix(r1.remix_id, ORG, "j1")
        complete_remix(r1.remix_id, ORG, "ast-gen2")

        # Gen 2: remix from gen2 result
        _register_source("ast-gen2", ORG, {**SOURCE_SNAPSHOT, "prompt": "v2"})
        r2 = create_remix(ORG, USER, "ast-gen2", {"prompt": {"action": "override", "value": "v3"}})
        submit_remix(r2.remix_id, ORG, "j2")
        complete_remix(r2.remix_id, ORG, "ast-gen3")

        # Check ancestry of gen3
        ancestry = get_ancestry("ast-gen3", ORG)
        assert len(ancestry) == 2
        assert ancestry[0]["asset_id"] == "ast-gen2"  # Parent
        assert ancestry[1]["asset_id"] == SOURCE_ASSET  # Grandparent

    def test_children_query(self):
        _setup_source()
        r1 = create_remix(ORG, USER, SOURCE_ASSET, {})
        submit_remix(r1.remix_id, ORG, "j1")
        complete_remix(r1.remix_id, ORG, "child-1")

        r2 = create_remix(ORG, USER, SOURCE_ASSET, {"seed": {"action": "reset"}})
        submit_remix(r2.remix_id, ORG, "j2")
        complete_remix(r2.remix_id, ORG, "child-2")

        children = get_children(SOURCE_ASSET, ORG)
        assert len(children) == 2
        child_ids = {c["asset_id"] for c in children}
        assert "child-1" in child_ids
        assert "child-2" in child_ids


# =============================================================================
# Duplicate (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicate:

    def test_duplicate_idempotency_key_returns_existing(self):
        _setup_source()
        r1 = create_remix(ORG, USER, SOURCE_ASSET, {}, idempotency_key="key-001")
        r2 = create_remix(ORG, USER, SOURCE_ASSET, {}, idempotency_key="key-001")
        assert r1.remix_id == r2.remix_id

    def test_submit_already_submitted_idempotent(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {})
        submit_remix(spec.remix_id, ORG, "j1")
        result = submit_remix(spec.remix_id, ORG, "j1")
        assert result.status == RemixStatus.SUBMITTED


# =============================================================================
# Remix Details
# =============================================================================


@pytest.mark.unit
class TestRemixDetails:

    def test_details_include_all_field_actions(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {
            "prompt": {"action": "override", "value": "new"},
            "seed": {"action": "reset"},
        })
        details = get_remix_details(spec.remix_id, ORG)
        assert details is not None
        assert details["source_asset_id"] == SOURCE_ASSET
        assert "prompt" in details["overridden_fields"]
        assert "seed" in details["reset_fields"]
        assert details["fields"]["prompt"]["action"] == "override"

    def test_cross_tenant_details_returns_none(self):
        _setup_source()
        spec = create_remix(ORG, USER, SOURCE_ASSET, {})
        assert get_remix_details(spec.remix_id, OTHER_ORG) is None
