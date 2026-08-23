"""Tests for the canonical integer credit cost registry."""

from __future__ import annotations

import pytest
from engine.preset_packs import PRESET_PACKS

from billing.credit_costs import CREDIT_COSTS


@pytest.mark.unit
def test_every_preset_has_cost() -> None:
    """Every canonical generation preset must be priced before it can ship."""
    preset_ids = {preset["id"] for preset in PRESET_PACKS}

    assert preset_ids <= CREDIT_COSTS.keys()
