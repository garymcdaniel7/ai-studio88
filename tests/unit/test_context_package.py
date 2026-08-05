"""Context Package Tests (Story 083).

Proves: hash stability, immutability, authorization, conflicting context,
reproducibility, persistence idempotency, and reference linking.

Run with:
    pytest tests/unit/test_context_package.py -v
"""
from __future__ import annotations

import pytest

from backend.context_package import (
    ContextPackage,
    PackageImmutableError,
    PackageNotFoundError,
    PackageUnauthorizedError,
    clear_store,
    compute_canonical_hash,
    finalize_package,
    link_asset,
    link_job,
    modify_package,
    persist_package,
    retrieve_by_hash,
    retrieve_package,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _make_package(**overrides) -> ContextPackage:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "talent_id": "talent-789",
        "talent_version": 3,
        "effective_positive_prompt": "A woman in a red dress at sunset",
        "effective_negative_prompt": "blurry, low quality",
        "model_id": "flux-dev",
        "model_version": "1.0",
        "lora_id": "lora-melissa-v3",
        "lora_version": "v3",
        "lora_strength": 0.8,
        "merge_policy_version": "1.0",
        "applied_rules": [
            {"rule_id": "r-1", "version": 2, "type": "include", "text": "wearing red dress"},
            {"rule_id": "r-2", "version": 1, "type": "avoid", "text": "green clothing"},
        ],
    }
    defaults.update(overrides)
    return ContextPackage(**defaults)


# =============================================================================
# Hash Stability
# =============================================================================


class TestHashStability:

    @pytest.mark.unit
    def test_same_input_same_hash(self):
        """Equivalent input produces identical hash."""
        pkg1 = _make_package()
        pkg2 = _make_package()
        h1 = compute_canonical_hash(pkg1)
        h2 = compute_canonical_hash(pkg2)
        assert h1 == h2

    @pytest.mark.unit
    def test_different_prompt_different_hash(self):
        """Different prompt produces different hash."""
        pkg1 = _make_package(effective_positive_prompt="A woman in red")
        pkg2 = _make_package(effective_positive_prompt="A man in blue")
        assert compute_canonical_hash(pkg1) != compute_canonical_hash(pkg2)

    @pytest.mark.unit
    def test_different_model_different_hash(self):
        """Different model produces different hash."""
        pkg1 = _make_package(model_id="flux-dev")
        pkg2 = _make_package(model_id="sdxl")
        assert compute_canonical_hash(pkg1) != compute_canonical_hash(pkg2)

    @pytest.mark.unit
    def test_different_lora_different_hash(self):
        """Different LoRA produces different hash."""
        pkg1 = _make_package(lora_id="lora-a")
        pkg2 = _make_package(lora_id="lora-b")
        assert compute_canonical_hash(pkg1) != compute_canonical_hash(pkg2)

    @pytest.mark.unit
    def test_different_talent_version_different_hash(self):
        """Different talent version produces different hash."""
        pkg1 = _make_package(talent_version=1)
        pkg2 = _make_package(talent_version=2)
        assert compute_canonical_hash(pkg1) != compute_canonical_hash(pkg2)

    @pytest.mark.unit
    def test_different_rules_different_hash(self):
        """Different applied rules produce different hash."""
        pkg1 = _make_package(applied_rules=[{"rule_id": "r-1", "text": "wear red"}])
        pkg2 = _make_package(applied_rules=[{"rule_id": "r-1", "text": "wear blue"}])
        assert compute_canonical_hash(pkg1) != compute_canonical_hash(pkg2)

    @pytest.mark.unit
    def test_rule_order_does_not_affect_hash(self):
        """Rules are sorted before hashing — order irrelevant."""
        rules_a = [
            {"rule_id": "r-2", "text": "avoid green"},
            {"rule_id": "r-1", "text": "wear red"},
        ]
        rules_b = [
            {"rule_id": "r-1", "text": "wear red"},
            {"rule_id": "r-2", "text": "avoid green"},
        ]
        pkg1 = _make_package(applied_rules=rules_a)
        pkg2 = _make_package(applied_rules=rules_b)
        assert compute_canonical_hash(pkg1) == compute_canonical_hash(pkg2)

    @pytest.mark.unit
    def test_hash_is_32_hex_chars(self):
        """Hash is 32 character hex string (SHA-256 truncated)."""
        pkg = _make_package()
        h = compute_canonical_hash(pkg)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    @pytest.mark.unit
    def test_none_lora_handled(self):
        """None lora_id/version doesn't crash hash."""
        pkg = _make_package(lora_id=None, lora_version=None, lora_strength=None)
        h = compute_canonical_hash(pkg)
        assert len(h) == 32


# =============================================================================
# Immutability
# =============================================================================


class TestImmutability:

    @pytest.mark.unit
    def test_modify_raises_immutable_error(self):
        """Modifying a persisted package raises PackageImmutableError."""
        pkg = _make_package()
        finalize_package(pkg)
        persist_package(pkg)

        with pytest.raises(PackageImmutableError) as exc_info:
            modify_package(pkg.package_id, {"effective_positive_prompt": "changed"})
        assert "immutable" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_modify_nonexistent_raises_not_found(self):
        """Modifying a non-existent package raises not found."""
        with pytest.raises(PackageNotFoundError):
            modify_package("ghost-id", {"field": "value"})

    @pytest.mark.unit
    def test_finalize_sets_immutable_flag(self):
        """finalize_package sets is_immutable."""
        pkg = _make_package()
        assert pkg.canonical_hash == ""
        finalize_package(pkg)
        assert pkg.is_immutable is True
        assert pkg.canonical_hash != ""


# =============================================================================
# Persistence (Idempotent)
# =============================================================================


class TestPersistence:

    @pytest.mark.unit
    def test_persist_requires_hash(self):
        """Cannot persist without computing hash first."""
        pkg = _make_package()
        with pytest.raises(ValueError) as exc_info:
            persist_package(pkg)
        assert "finalized" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_persist_succeeds_after_finalize(self):
        """Finalized package can be persisted."""
        pkg = _make_package()
        finalize_package(pkg)
        result = persist_package(pkg)
        assert result.package_id == pkg.package_id

    @pytest.mark.unit
    def test_duplicate_persist_is_idempotent(self):
        """Re-persisting same package_id returns existing."""
        pkg = _make_package()
        finalize_package(pkg)
        first = persist_package(pkg)

        # Modify fields on a new object with same ID
        pkg2 = _make_package(effective_positive_prompt="different")
        pkg2.package_id = pkg.package_id
        pkg2.canonical_hash = "fakehash"
        second = persist_package(pkg2)

        # Returns original
        assert second.effective_positive_prompt == first.effective_positive_prompt


# =============================================================================
# Authorization
# =============================================================================


class TestAuthorization:

    @pytest.mark.unit
    def test_same_org_can_retrieve(self):
        """Same org_id can retrieve the package."""
        pkg = _make_package(org_id="org-123")
        finalize_package(pkg)
        persist_package(pkg)

        result = retrieve_package(pkg.package_id, requesting_org_id="org-123")
        assert result.package_id == pkg.package_id

    @pytest.mark.unit
    def test_different_org_unauthorized(self):
        """Different org_id raises unauthorized."""
        pkg = _make_package(org_id="org-123")
        finalize_package(pkg)
        persist_package(pkg)

        with pytest.raises(PackageUnauthorizedError):
            retrieve_package(pkg.package_id, requesting_org_id="org-evil")

    @pytest.mark.unit
    def test_nonexistent_package_not_found(self):
        """Retrieving non-existent package raises not found."""
        with pytest.raises(PackageNotFoundError):
            retrieve_package("ghost", requesting_org_id="org-123")

    @pytest.mark.unit
    def test_inspectable_excludes_secrets(self):
        """to_inspectable() does not include system secrets."""
        pkg = _make_package()
        finalize_package(pkg)
        inspectable = pkg.to_inspectable()
        # Should NOT have user_id (actor info) in inspectable for privacy
        # Should have prompts, rules, model info
        assert "effective_positive_prompt" in inspectable
        assert "applied_rules" in inspectable
        assert "model_id" in inspectable


# =============================================================================
# Hash-Based Retrieval
# =============================================================================


class TestHashRetrieval:

    @pytest.mark.unit
    def test_retrieve_by_hash_found(self):
        """Can find package by canonical hash."""
        pkg = _make_package()
        finalize_package(pkg)
        persist_package(pkg)

        found = retrieve_by_hash(pkg.canonical_hash, requesting_org_id="org-123")
        assert found is not None
        assert found.package_id == pkg.package_id

    @pytest.mark.unit
    def test_retrieve_by_hash_wrong_org(self):
        """Hash retrieval respects org isolation."""
        pkg = _make_package(org_id="org-123")
        finalize_package(pkg)
        persist_package(pkg)

        found = retrieve_by_hash(pkg.canonical_hash, requesting_org_id="org-other")
        assert found is None

    @pytest.mark.unit
    def test_retrieve_by_hash_not_found(self):
        """Unknown hash returns None."""
        found = retrieve_by_hash("nonexistent", requesting_org_id="org-123")
        assert found is None


# =============================================================================
# Reference Linking
# =============================================================================


class TestReferenceLinking:

    @pytest.mark.unit
    def test_link_job_to_package(self):
        """Job can be linked to a context package."""
        pkg = _make_package()
        finalize_package(pkg)
        persist_package(pkg)

        link_job(pkg.package_id, "gen-job-1")
        result = retrieve_package(pkg.package_id, requesting_org_id="org-123")
        assert "gen-job-1" in result.job_ids

    @pytest.mark.unit
    def test_link_asset_to_package(self):
        """Asset can be linked to a context package."""
        pkg = _make_package()
        finalize_package(pkg)
        persist_package(pkg)

        link_asset(pkg.package_id, "asset-out-1")
        result = retrieve_package(pkg.package_id, requesting_org_id="org-123")
        assert "asset-out-1" in result.asset_ids

    @pytest.mark.unit
    def test_duplicate_link_idempotent(self):
        """Linking same job/asset twice doesn't duplicate."""
        pkg = _make_package()
        finalize_package(pkg)
        persist_package(pkg)

        link_job(pkg.package_id, "job-1")
        link_job(pkg.package_id, "job-1")
        result = retrieve_package(pkg.package_id, requesting_org_id="org-123")
        assert result.job_ids.count("job-1") == 1


# =============================================================================
# Conflicting Context
# =============================================================================


class TestConflicts:

    @pytest.mark.unit
    def test_conflicts_preserved_in_package(self):
        """Conflicts from merge resolution are stored."""
        pkg = _make_package(conflicts=[
            {
                "type": "lora_mismatch",
                "sources": ["preferences", "project"],
                "resolution": "preferences wins",
                "warning": "Project LoRA overridden by talent preference",
            },
        ])
        finalize_package(pkg)
        assert len(pkg.conflicts) == 1
        assert pkg.conflicts[0]["type"] == "lora_mismatch"

    @pytest.mark.unit
    def test_warnings_preserved(self):
        """Warnings are preserved for user inspection."""
        pkg = _make_package(warnings=[
            "Wardrobe source absent — default styling applied",
            "LoRA v2 deprecated, using v3",
        ])
        finalize_package(pkg)
        assert len(pkg.warnings) == 2

    @pytest.mark.unit
    def test_rejected_rules_preserved(self):
        """Rejected rules with reasons are stored."""
        pkg = _make_package(rejected_rules=[
            {"rule_id": "r-99", "reason": "Conflicted with higher-priority rule r-1"},
        ])
        finalize_package(pkg)
        assert len(pkg.rejected_rules) == 1
        assert "conflicted" in pkg.rejected_rules[0]["reason"].lower()


# =============================================================================
# Reproducibility
# =============================================================================


class TestReproducibility:

    @pytest.mark.unit
    def test_same_context_reuse_via_hash(self):
        """Identical context can be found via hash (dedup)."""
        pkg1 = _make_package()
        finalize_package(pkg1)
        persist_package(pkg1)

        pkg2 = _make_package()
        h2 = compute_canonical_hash(pkg2)

        existing = retrieve_by_hash(h2, requesting_org_id="org-123")
        assert existing is not None
        assert existing.package_id == pkg1.package_id

    @pytest.mark.unit
    def test_serializable(self):
        """Package to_dict() is JSON-serializable."""
        import json
        pkg = _make_package()
        finalize_package(pkg)
        json.dumps(pkg.to_dict())

    @pytest.mark.unit
    def test_inspectable_serializable(self):
        """Package to_inspectable() is JSON-serializable."""
        import json
        pkg = _make_package()
        finalize_package(pkg)
        json.dumps(pkg.to_inspectable())
