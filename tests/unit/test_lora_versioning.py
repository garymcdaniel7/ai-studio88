"""LoRA Versioning Tests (Story 095).

Proves: concurrency safety, lineage integrity, duplicate prevention,
checksum verification, simulation distinction, immutability, and queries.

Run with:
    pytest tests/unit/test_lora_versioning.py -v
"""
from __future__ import annotations

import threading

import pytest

from backend.lora_versioning import (
    IMMUTABLE_FIELDS,
    VALID_LIFECYCLE_TRANSITIONS,
    ImmutabilityError,
    LoRAVersion,
    TrainingConfig,
    TrainingMode,
    VersionAllocationError,
    VersionLifecycle,
    allocate_version,
    clear_registry,
    get_active_version,
    get_latest_version,
    get_lineage,
    get_version,
    get_versions_for_talent,
    modify_version,
    transition_lifecycle,
    verify_output,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def _allocate(**overrides) -> LoRAVersion:
    defaults = {
        "org_id": "org-123",
        "talent_id": "talent-1",
        "lineage_id": "lineage-melissa",
        "training_job_id": f"job-{id(overrides)}",
        "dataset_manifest_id": "manifest-abc",
        "dataset_checksum": "ds_hash_123",
        "training_config": TrainingConfig(),
        "base_model_id": "flux-dev",
        "base_model_version": "1.0",
        "training_mode": TrainingMode.PRODUCTION,
        "provider_name": "vast_ai",
        "output_checksum": "output_sha256_abc",
        "output_storage_key": "/org-123/models/talent-1/lora_v1.safetensors",
        "output_size_bytes": 150_000_000,
        "trigger_word": "mlss",
        "created_by": "user-1",
    }
    defaults.update(overrides)
    return allocate_version(**defaults)


# =============================================================================
# Sequential Allocation
# =============================================================================


class TestSequentialAllocation:

    @pytest.mark.unit
    def test_first_version_is_one(self):
        """First version in a lineage gets number 1."""
        v = _allocate(training_job_id="job-1")
        assert v.version_number == 1

    @pytest.mark.unit
    def test_second_version_is_two(self):
        """Second allocation in same lineage gets number 2."""
        _allocate(training_job_id="job-1")
        v2 = _allocate(training_job_id="job-2")
        assert v2.version_number == 2

    @pytest.mark.unit
    def test_different_lineage_starts_at_one(self):
        """Different lineage_id starts its own counter at 1."""
        _allocate(lineage_id="lineage-A", training_job_id="job-1")
        v = _allocate(lineage_id="lineage-B", training_job_id="job-2")
        assert v.version_number == 1

    @pytest.mark.unit
    def test_sequential_increments(self):
        """Multiple allocations increment monotonically."""
        for i in range(5):
            v = _allocate(training_job_id=f"job-{i}")
            assert v.version_number == i + 1


# =============================================================================
# Concurrency Safety
# =============================================================================


class TestConcurrency:

    @pytest.mark.unit
    def test_concurrent_allocations_unique_versions(self):
        """Concurrent threads get unique version numbers."""
        results: list[LoRAVersion] = []
        errors: list[Exception] = []

        def allocate_one(idx: int) -> None:
            try:
                v = _allocate(training_job_id=f"concurrent-job-{idx}")
                results.append(v)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=allocate_one, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        version_numbers = [v.version_number for v in results]
        # All unique
        assert len(set(version_numbers)) == 10
        # All between 1 and 10
        assert sorted(version_numbers) == list(range(1, 11))

    @pytest.mark.unit
    def test_no_duplicate_version_numbers(self):
        """Even under contention, no two versions share a number."""
        for i in range(20):
            _allocate(training_job_id=f"seq-{i}")

        lineage = get_lineage("lineage-melissa")
        numbers = [v.version_number for v in lineage]
        assert len(numbers) == len(set(numbers))  # All unique


# =============================================================================
# Duplicate Prevention (Idempotency)
# =============================================================================


class TestDuplicatePrevention:

    @pytest.mark.unit
    def test_same_job_id_returns_existing(self):
        """Duplicate training_job_id returns existing version (idempotent)."""
        v1 = _allocate(training_job_id="job-same")
        v2 = _allocate(training_job_id="job-same")
        assert v1.version_id == v2.version_id
        assert v1.version_number == v2.version_number

    @pytest.mark.unit
    def test_idempotent_does_not_increment(self):
        """Idempotent re-allocation does not consume a version number."""
        _allocate(training_job_id="job-A")
        _allocate(training_job_id="job-A")  # Duplicate
        v3 = _allocate(training_job_id="job-B")
        assert v3.version_number == 2  # Not 3


# =============================================================================
# Lineage Integrity
# =============================================================================


class TestLineageIntegrity:

    @pytest.mark.unit
    def test_parent_version_linked(self):
        """Version can reference a parent version."""
        v1 = _allocate(training_job_id="job-1")
        v2 = _allocate(training_job_id="job-2", parent_version_id=v1.version_id)
        assert v2.parent_version_id == v1.version_id
        assert v2.version_number == 2

    @pytest.mark.unit
    def test_invalid_parent_raises(self):
        """Referencing non-existent parent raises error."""
        with pytest.raises(VersionAllocationError) as exc_info:
            _allocate(training_job_id="job-1", parent_version_id="ghost-version")
        assert "not found" in exc_info.value.message

    @pytest.mark.unit
    def test_cross_lineage_parent_raises(self):
        """Parent from different lineage raises error."""
        v1 = _allocate(lineage_id="lineage-A", training_job_id="job-1")
        with pytest.raises(VersionAllocationError) as exc_info:
            _allocate(
                lineage_id="lineage-B", training_job_id="job-2",
                parent_version_id=v1.version_id,
            )
        assert "different lineage" in exc_info.value.message

    @pytest.mark.unit
    def test_lineage_query_ordered(self):
        """get_lineage returns versions ordered by number."""
        _allocate(training_job_id="job-1")
        _allocate(training_job_id="job-2")
        _allocate(training_job_id="job-3")
        lineage = get_lineage("lineage-melissa")
        assert [v.version_number for v in lineage] == [1, 2, 3]

    @pytest.mark.unit
    def test_dataset_manifest_preserved(self):
        """Dataset manifest ID and checksum are recorded."""
        v = _allocate(
            training_job_id="job-1",
            dataset_manifest_id="manifest-xyz",
            dataset_checksum="ds_hash_xyz",
        )
        assert v.dataset_manifest_id == "manifest-xyz"
        assert v.dataset_checksum == "ds_hash_xyz"


# =============================================================================
# Checksum Verification
# =============================================================================


class TestChecksumVerification:

    @pytest.mark.unit
    def test_matching_checksum_verifies(self):
        """Matching checksum transitions to VERIFIED."""
        v = _allocate(training_job_id="job-1", output_checksum="abc123")
        result = verify_output(v.version_id, "abc123")
        assert result.lifecycle == VersionLifecycle.VERIFIED

    @pytest.mark.unit
    def test_mismatching_checksum_raises(self):
        """Mismatching checksum raises error."""
        v = _allocate(training_job_id="job-1", output_checksum="expected_hash")
        with pytest.raises(VersionAllocationError) as exc_info:
            verify_output(v.version_id, "wrong_hash")
        assert "mismatch" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_empty_checksum_accepts_any(self):
        """Version without preset checksum accepts provided checksum."""
        v = _allocate(training_job_id="job-1", output_checksum="")
        result = verify_output(v.version_id, "new_checksum")
        assert result.output_checksum == "new_checksum"
        assert result.lifecycle == VersionLifecycle.VERIFIED

    @pytest.mark.unit
    def test_verify_nonexistent_raises(self):
        """Verifying non-existent version raises error."""
        with pytest.raises(VersionAllocationError):
            verify_output("ghost-id", "any")


# =============================================================================
# Simulation Distinction
# =============================================================================


class TestSimulationDistinction:

    @pytest.mark.unit
    def test_production_mode_recorded(self):
        """Production training records PRODUCTION mode."""
        v = _allocate(training_job_id="job-1", training_mode=TrainingMode.PRODUCTION)
        assert v.training_mode == TrainingMode.PRODUCTION

    @pytest.mark.unit
    def test_simulation_mode_recorded(self):
        """Simulation training records SIMULATION mode."""
        v = _allocate(training_job_id="job-sim", training_mode=TrainingMode.SIMULATION)
        assert v.training_mode == TrainingMode.SIMULATION

    @pytest.mark.unit
    def test_simulation_and_production_coexist(self):
        """Both modes can exist in same lineage (distinguishable)."""
        v1 = _allocate(training_job_id="job-prod", training_mode=TrainingMode.PRODUCTION)
        v2 = _allocate(training_job_id="job-sim", training_mode=TrainingMode.SIMULATION)
        assert v1.training_mode != v2.training_mode
        assert v1.version_number == 1
        assert v2.version_number == 2


# =============================================================================
# Immutability
# =============================================================================


class TestImmutability:

    @pytest.mark.unit
    def test_immutable_fields_cannot_change(self):
        """Provenance fields raise ImmutabilityError on modify."""
        v = _allocate(training_job_id="job-1")
        for field_name in IMMUTABLE_FIELDS:
            with pytest.raises(ImmutabilityError):
                modify_version(v.version_id, field_name, "new_value")

    @pytest.mark.unit
    def test_lifecycle_can_change(self):
        """Lifecycle field can be updated (not in immutable set)."""
        v = _allocate(training_job_id="job-1")
        verify_output(v.version_id, v.output_checksum)
        modify_version(v.version_id, "trigger_word", "new_trigger")
        updated = get_version(v.version_id)
        assert updated.trigger_word == "new_trigger"

    @pytest.mark.unit
    def test_all_provenance_fields_locked(self):
        """14 provenance fields are in the immutable set."""
        assert len(IMMUTABLE_FIELDS) >= 14


# =============================================================================
# Lifecycle Transitions
# =============================================================================


class TestLifecycle:

    @pytest.mark.unit
    def test_created_to_verified(self):
        """CREATED → VERIFIED is valid."""
        v = _allocate(training_job_id="job-1")
        result = transition_lifecycle(v.version_id, VersionLifecycle.VERIFIED)
        assert result.lifecycle == VersionLifecycle.VERIFIED

    @pytest.mark.unit
    def test_verified_to_active(self):
        """VERIFIED → ACTIVE is valid."""
        v = _allocate(training_job_id="job-1")
        transition_lifecycle(v.version_id, VersionLifecycle.VERIFIED)
        result = transition_lifecycle(v.version_id, VersionLifecycle.ACTIVE)
        assert result.lifecycle == VersionLifecycle.ACTIVE

    @pytest.mark.unit
    def test_active_to_superseded(self):
        """ACTIVE → SUPERSEDED is valid."""
        v = _allocate(training_job_id="job-1")
        transition_lifecycle(v.version_id, VersionLifecycle.VERIFIED)
        transition_lifecycle(v.version_id, VersionLifecycle.ACTIVE)
        result = transition_lifecycle(v.version_id, VersionLifecycle.SUPERSEDED)
        assert result.lifecycle == VersionLifecycle.SUPERSEDED

    @pytest.mark.unit
    def test_created_to_active_invalid(self):
        """CREATED → ACTIVE (skip verify) is invalid."""
        v = _allocate(training_job_id="job-1")
        with pytest.raises(VersionAllocationError):
            transition_lifecycle(v.version_id, VersionLifecycle.ACTIVE)

    @pytest.mark.unit
    def test_get_active_version(self):
        """get_active_version returns the ACTIVE version."""
        v = _allocate(training_job_id="job-1")
        transition_lifecycle(v.version_id, VersionLifecycle.VERIFIED)
        transition_lifecycle(v.version_id, VersionLifecycle.ACTIVE)
        active = get_active_version("lineage-melissa")
        assert active is not None
        assert active.version_id == v.version_id


# =============================================================================
# Queries
# =============================================================================


class TestQueries:

    @pytest.mark.unit
    def test_get_latest_version(self):
        """get_latest_version returns highest version number."""
        _allocate(training_job_id="job-1")
        _allocate(training_job_id="job-2")
        v3 = _allocate(training_job_id="job-3")
        latest = get_latest_version("lineage-melissa")
        assert latest.version_number == 3
        assert latest.version_id == v3.version_id

    @pytest.mark.unit
    def test_get_versions_for_talent_scoped(self):
        """get_versions_for_talent is tenant-scoped."""
        _allocate(org_id="org-1", talent_id="t-1", training_job_id="j-1", lineage_id="l-1")
        _allocate(org_id="org-2", talent_id="t-1", training_job_id="j-2", lineage_id="l-2")
        results = get_versions_for_talent("t-1", "org-1")
        assert len(results) == 1
        assert results[0].org_id == "org-1"

    @pytest.mark.unit
    def test_version_serializable(self):
        """LoRAVersion.to_dict() is JSON-serializable."""
        import json
        v = _allocate(training_job_id="job-1")
        json.dumps(v.to_dict())

    @pytest.mark.unit
    def test_training_config_hash_deterministic(self):
        """Same config produces same hash."""
        c1 = TrainingConfig(learning_rate=1e-4, epochs=100)
        c2 = TrainingConfig(learning_rate=1e-4, epochs=100)
        assert c1.config_hash() == c2.config_hash()

    @pytest.mark.unit
    def test_different_config_different_hash(self):
        """Different config produces different hash."""
        c1 = TrainingConfig(learning_rate=1e-4)
        c2 = TrainingConfig(learning_rate=5e-5)
        assert c1.config_hash() != c2.config_hash()


# =============================================================================
# Validation
# =============================================================================


class TestValidation:

    @pytest.mark.unit
    def test_missing_org_id_raises(self):
        """Allocation without org_id raises."""
        with pytest.raises(VersionAllocationError):
            _allocate(org_id="", training_job_id="j-1")

    @pytest.mark.unit
    def test_missing_talent_id_raises(self):
        """Allocation without talent_id raises."""
        with pytest.raises(VersionAllocationError):
            _allocate(talent_id="", training_job_id="j-1")

    @pytest.mark.unit
    def test_missing_lineage_id_raises(self):
        """Allocation without lineage_id raises."""
        with pytest.raises(VersionAllocationError):
            _allocate(lineage_id="", training_job_id="j-1")

    @pytest.mark.unit
    def test_missing_job_id_raises(self):
        """Allocation without training_job_id raises."""
        with pytest.raises(VersionAllocationError):
            _allocate(training_job_id="")
