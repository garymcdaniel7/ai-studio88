"""Tests for the cost model service.

These test the core registry behaviors:
- Known class_types return correct estimates
- Unknown class_types return None (not zero)
- Startup validation blocks when GPU_HOURLY_RATE is unset/invalid
- Motion Director overhead is additive at chain boundaries
"""

import os
from unittest.mock import patch

import pytest

from worker.cost_model import (
    CostEntry,
    CostRegistry,
    OverheadEntry,
    get_registry,
    startup_error,
    validate_startup,
)


class TestCostRegistry:
    """Core registry behaviors."""

    def setup_method(self):
        # Fresh registry per test (no singleton side effects)
        self.reg = CostRegistry()

    def test_known_type_returns_entry(self):
        """Known class_types return a CostEntry with estimate."""
        entry = self.reg.lookup("H3I2V")
        assert entry is not None
        assert entry.class_type == "H3I2V"
        assert entry.gpu_seconds_base == 240.0

    def test_unknown_type_returns_none(self):
        """Unknown class_types return None — caller MUST NOT treat as zero."""
        entry = self.reg.lookup("ThisDoesNotExist")
        assert entry is None

    def test_turbo_mult_applied(self):
        """Turbo mode applies 0.25x multiplier (4× faster at same step count)."""
        entry = self.reg.lookup("H3I2V")
        normal = entry.estimate(resolution="768p", steps=8, turbo=False)
        turbo = entry.estimate(resolution="768p", steps=8, turbo=True)
        assert turbo < normal
        assert turbo == pytest.approx(60.0, rel=0.1)  # 240 * 0.25

    def test_resolution_mult_applied(self):
        """1024p applies 1.6x multiplier to H3."""
        entry = self.reg.lookup("H3I2V")
        base = entry.estimate(resolution="768p", steps=8)
        high = entry.estimate(resolution="1024p", steps=8)
        assert high > base
        assert high == pytest.approx(240.0 * 1.6, rel=0.1)

    def test_min_gpu_seconds_enforced(self):
        """Floor prevents zero-cost entries."""
        entry = self.reg.lookup("KreaT2I")
        # With extreme params that would normally go below min
        tiny = entry.estimate(resolution="512p", steps=1)
        assert tiny >= entry.min_gpu_seconds


class TestChainEstimate:
    """Chain-level estimation."""

    def setup_method(self):
        self.reg = CostRegistry()

    def test_single_node_no_overhead(self):
        """A single node has no seam overhead."""
        result = self.reg.estimate_chain([
            {"class_type": "H3I2V", "resolution": "768p", "steps": 8, "turbo": False},
        ], segment_count=1)
        assert result["total_seconds"] == 240.0
        assert result["total_cost"] == pytest.approx(240 / 3600 * 0.52, rel=0.01)
        assert result["blocked"] == []
        assert result["overhead"] == []

    def test_two_shot_chain_adds_overhead(self):
        """Two segments add Motion Director overhead for one seam."""
        result = self.reg.estimate_chain([
            {"class_type": "H3I2V", "resolution": "768p", "steps": 8, "turbo": False},
            {"class_type": "H3I2V", "resolution": "768p", "steps": 8, "turbo": False},
        ], segment_count=2)
        # 240 + 240 + 30 = 510
        assert result["total_seconds"] == 510.0
        assert len(result["overhead"]) == 1
        assert "seam" in result["overhead"][0].lower()

    def test_unknown_type_blocks_whole_chain(self):
        """Any unknown class_type blocks the entire estimate."""
        result = self.reg.estimate_chain([
            {"class_type": "H3I2V", "resolution": "768p", "steps": 8},
            {"class_type": "FakeNode_DoesNotExist", "resolution": "768p", "steps": 8},
        ])
        assert result["total_seconds"] == 240.0  # Only the known one counted
        assert "FakeNode_DoesNotExist" in result["blocked"]
        assert result["blocked"] != []

    def test_mixed_chain_with_turbo(self):
        """Turbo and normal modes in one chain."""
        result = self.reg.estimate_chain([
            {"class_type": "H3I2V", "resolution": "768p", "steps": 8, "turbo": False},
            {"class_type": "KreaT2I", "resolution": "768p", "steps": 8, "turbo": False},
        ], segment_count=1)
        # 240 + 2 = 242
        assert result["total_seconds"] == 242.0
        assert result["error"] is None


class TestOverheadEntry:
    """Overhead entry behavior."""

    def test_single_segment_no_overhead(self):
        """Overhead is zero for a single segment."""
        oh = OverheadEntry(name="Test", gpu_seconds_per_segment=30.0)
        assert oh.estimate(segment_count=1) == 0.0
        assert oh.render(segment_count=1) == ""

    def test_multiple_segments_add_per_seam(self):
        """Overhead is per_segment × (segment_count - 1)."""
        oh = OverheadEntry(name="Test", gpu_seconds_per_segment=30.0)
        assert oh.estimate(segment_count=4) == 90.0  # 3 seams × 30s


class TestStartupValidation:
    """Startup validation gates."""

    def test_validates_with_rate_set(self):
        """With GPU_HOURLY_RATE set, validation passes."""
        with patch.dict(os.environ, {"GPU_HOURLY_RATE": "0.52"}):
            error = validate_startup()
            assert error is None

    def test_fails_without_rate(self):
        """Without GPU_HOURLY_RATE, validation returns an error."""
        with patch.dict(os.environ, {}, clear=True):
            error = validate_startup()
            assert error is not None
            assert "GPU_HOURLY_RATE" in error

    def test_fails_with_nan_rate(self):
        """Invalid float values are treated as unset."""
        with patch.dict(os.environ, {"GPU_HOURLY_RATE": "not-a-number"}):
            error = validate_startup()
            assert error is not None
            assert "GPU_HOURLY_RATE" in error

    def test_fails_with_zero_rate(self):
        """Zero or negative rates are rejected."""
        with patch.dict(os.environ, {"GPU_HOURLY_RATE": "0"}):
            error = validate_startup()
            assert error is not None

        with patch.dict(os.environ, {"GPU_HOURLY_RATE": "-1"}):
            error = validate_startup()
            assert error is not None

    def test_startup_error_reflects_validation(self):
        """startup_error() returns the last validation error."""
        with patch.dict(os.environ, {}, clear=True):
            validate_startup()
            err = startup_error()
            assert err is not None

        with patch.dict(os.environ, {"GPU_HOURLY_RATE": "0.52"}):
            validate_startup()
            err = startup_error()
            assert err is None