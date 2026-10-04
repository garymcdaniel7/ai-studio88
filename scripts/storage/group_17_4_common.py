"""Shared result and synthetic identity definitions for Group 17.4 checks."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

THRESHOLD_BYTES = 100 * 1024 * 1024
ORG_A = UUID("00000000-0000-0000-0000-000000000001")
ORG_B = UUID("00000000-0000-0000-0000-000000000002")
TALENT_A = UUID("00000000-0000-0000-0000-000000000011")
JOB_A = UUID("00000000-0000-0000-0000-000000000021")
ASSET_A = UUID("00000000-0000-0000-0000-000000000031")
DELETION_A = UUID("00000000-0000-0000-0000-000000000041")


@dataclass(frozen=True)
class CheckResult:
    """One local or staging checklist result."""

    name: str
    status: str
    detail: str
