"""Post-generation output safety scanning and quarantine gate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.compliance.quarantine import (
    compute_perceptual_hash,
    quarantine_asset,
    record_violation,
)
from backend.compliance.repository import get_compliance_repository

NSFW_QUARANTINE_THRESHOLD = 0.85


@dataclass(frozen=True, slots=True)
class OutputScanResult:
    """Safe/unsafe decision for one generated output."""

    asset_id: str | None
    nsfw_score: float
    quarantined: bool
    perceptual_hash: str


class OutputQuarantinedError(ValueError):
    """Raised when a generated output must not reach a client."""

    def __init__(self, asset_id: str | None, score: float) -> None:
        super().__init__("Generated output quarantined by the safety classifier.")
        self.asset_id = asset_id
        self.nsfw_score = score


def scan_generated_output(
    content: bytes,
    *,
    asset_id: str | None,
    org_id: str,
    metadata: dict[str, Any] | None = None,
    classifier: Callable[[bytes], float] | None = None,
) -> OutputScanResult:
    """Scan output and raise before upload/return when unsafe."""
    details = metadata or {}
    score = float(details.get("nsfw_score", 0.0))
    if classifier is not None:
        score = float(classifier(content))
    if details.get("nsfw_detected") is True:
        score = max(score, 1.0)

    perceptual_hash = compute_perceptual_hash(content)
    if score >= NSFW_QUARANTINE_THRESHOLD:
        if asset_id is not None:
            quarantine_asset(
                asset_id,
                org_id,
                reason="post-generation-nsfw-classifier",
                perceptual_hash=perceptual_hash,
            )
        else:
            record_violation(
                org_id=org_id,
                reason="post-generation-nsfw-classifier",
                source_type="generated_output",
                perceptual_hash=perceptual_hash,
            )
        raise OutputQuarantinedError(asset_id, score)

    if asset_id is not None:
        get_compliance_repository().register_asset(asset_id, org_id, perceptual_hash)

    return OutputScanResult(
        asset_id=asset_id,
        nsfw_score=score,
        quarantined=False,
        perceptual_hash=perceptual_hash,
    )
