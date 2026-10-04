"""Fail-closed staging and cleanup guards for Group 17.4."""

from __future__ import annotations

import os
import tempfile

from group_17_4_common import CheckResult


def staging_prerequisite_errors(environment: dict[str, str]) -> list[str]:
    """Return fail-closed errors without contacting any live service."""
    required = (
        "ENVIRONMENT",
        "STAGING_API_BASE",
        "STAGING_B2_ENDPOINT",
        "STAGING_B2_BUCKET",
        "STAGING_DB_URL",
        "STAGING_TOKEN_A",
        "STAGING_TOKEN_B",
        "STAGING_APPROVAL_ID",
    )
    errors = [
        f"missing secret-manager variable: {name}"
        for name in required
        if not environment.get(name)
    ]
    if environment.get("ENVIRONMENT") and environment["ENVIRONMENT"] != "staging":
        errors.append("ENVIRONMENT must equal staging; refusing provider/database/API access")
    if environment.get("STAGING_B2_BUCKET") == environment.get("PRODUCTION_B2_BUCKET"):
        errors.append("staging B2 bucket matches production bucket; refusing destructive checks")
    if environment.get("STAGING_DB_URL") == environment.get("PRODUCTION_DB_URL"):
        errors.append("staging database matches production database; refusing destructive checks")
    return errors


def staging_blockers() -> list[CheckResult]:
    """Report live checks that cannot be promoted from local mocked evidence."""
    prerequisite_text = "; ".join(staging_prerequisite_errors({}))
    return [
        CheckResult(
            "live B2/CDN delivery and metadata",
            "STAGING-REQUIRED/BLOCKED",
            f"isolated staging identity unavailable: {prerequisite_text}",
        ),
        CheckResult(
            "real >100MiB object and multipart abort",
            "STAGING-REQUIRED/BLOCKED",
            "no approved isolated provider harness and no live staging bucket; local payload is synthetic",
        ),
        CheckResult(
            "staging Org A/B API isolation",
            "STAGING-REQUIRED/BLOCKED",
            "no isolated staging API, database, disposable identities, or bearer tokens",
        ),
        CheckResult(
            "deletion-worker evidence",
            "STAGING-REQUIRED/BLOCKED",
            "no verified staging queue/worker command, run ID, or read-only DB/provider evidence",
        ),
        CheckResult(
            "rollback and cleanup evidence",
            "STAGING-REQUIRED/BLOCKED",
            "no authorized staging approval, resource inventory, or worker rollback evidence",
        ),
    ]


def run_local_cleanup_guard() -> CheckResult:
    """Verify local fixture cleanup is bounded and provider-independent."""
    with tempfile.TemporaryDirectory(prefix="aios-g17-4-") as directory:
        marker = os.path.join(directory, "synthetic-fixture")
        with open(marker, "wb") as handle:
            handle.write(b"local-only")
        exists_during_run = os.path.exists(marker)
    if exists_during_run and not os.path.exists(directory):
        return CheckResult(
            "rollback/local cleanup guard",
            "LOCAL-MOCK-PASS",
            "temporary fixture removed without provider/database calls",
        )
    return CheckResult(
        "rollback/local cleanup guard",
        "FAIL",
        "temporary fixture cleanup did not complete",
    )
