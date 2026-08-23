"""Canonical integer credit costs for generation presets.

The existing :mod:`backend.cost_ledger` records USD infrastructure spend and
must remain separate from this consumer-facing credit ledger. These costs use
the companion pricing plan's unit-economics bands:

* still-image presets charge one credit, with heavier utility/identity passes
  charging two credits;
* short WAN video presets charge 16 credits, within the documented 12–20 band;
* long WAN video charges 60 credits, within the documented 40–80 band.

The plan does not define exact GPU classes or active-second estimates for each
preset, so those values are explicit conservative estimates here and can be
revised without changing the consumer-credit API.
"""

from __future__ import annotations

from typing import TypedDict


class CreditCost(TypedDict):
    """Metering metadata required to price one preset execution."""

    model_id: str
    gpu_class: str
    est_active_seconds: int
    credits: int


# Keep this mapping explicit rather than deriving it from preset defaults. A
# newly added preset must be priced deliberately and is caught by the tripwire
# test in backend/tests/billing/test_credit_costs.py.
CREDIT_COSTS: dict[str, CreditCost] = {
    "cinematic-portrait": {
        "model_id": "flux-dev",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 10,
        "credits": 1,
    },
    "product-shot": {
        "model_id": "flux-dev",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 8,
        "credits": 1,
    },
    "fast-draft": {
        "model_id": "sdxl-turbo",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 2,
        "credits": 1,
    },
    "anime-illustration": {
        "model_id": "sdxl-turbo",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 5,
        "credits": 1,
    },
    "landscape-environment": {
        "model_id": "flux-dev",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 12,
        "credits": 1,
    },
    "text-to-video-short": {
        "model_id": "wan-2.1-t2v",
        "gpu_class": "h100-class",
        "est_active_seconds": 240,
        "credits": 16,
    },
    "image-to-video-animate": {
        "model_id": "wan-2.1-i2v",
        "gpu_class": "h100-class",
        "est_active_seconds": 240,
        "credits": 16,
    },
    "upscale-4x": {
        "model_id": "sdxl-turbo",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 30,
        "credits": 2,
    },
    "inpaint-edit": {
        "model_id": "flux-dev",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 10,
        "credits": 2,
    },
    "lora-portrait": {
        "model_id": "flux-dev",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 12,
        "credits": 2,
    },
    "controlnet-pose": {
        "model_id": "sdxl-turbo",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 8,
        "credits": 1,
    },
    "ip-adapter-style": {
        "model_id": "sdxl-turbo",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 8,
        "credits": 1,
    },
    "long-video": {
        "model_id": "wan-2.1-t2v",
        "gpu_class": "h100-class",
        "est_active_seconds": 900,
        "credits": 60,
    },
    "fashion-lookbook": {
        "model_id": "flux-dev",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 12,
        "credits": 1,
    },
    "film-grain-vintage": {
        "model_id": "sdxl-turbo",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 5,
        "credits": 1,
    },
    "hdr-luxury": {
        "model_id": "flux-dev",
        "gpu_class": "rtx4090-class",
        "est_active_seconds": 15,
        "credits": 1,
    },
}


def get_credit_cost(preset_id: str) -> CreditCost:
    """Return the immutable pricing metadata for a preset.

    Raises:
        KeyError: If the preset has not been priced in the registry.
    """
    return CREDIT_COSTS[preset_id]
