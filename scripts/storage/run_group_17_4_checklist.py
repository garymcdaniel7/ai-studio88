#!/usr/bin/env python3
"""Run the safe local checklist for Phase 2 Group 17.4 storage acceptance.

This runner never contacts B2, a CDN, Supabase, an API, or a deletion worker. It
uses mocked S3 clients and an in-memory AssetService repository/provider to verify
locally testable contracts. Live acceptance remains explicitly blocked until the
runbook staging prerequisites are supplied.

Run from the repository root with::

    uv run python scripts/storage/run_group_17_4_checklist.py

Expected staging blockers are reported as ``STAGING-REQUIRED/BLOCKED`` and do
not turn local preparation green into live acceptance.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = Path(__file__).resolve().parent
for import_root in (REPOSITORY_ROOT, SCRIPT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from group_17_4_common import (
    JOB_A,
    ORG_A,
    TALENT_A,
    THRESHOLD_BYTES,
    CheckResult,
)
from group_17_4_guards import (
    run_local_cleanup_guard,
    staging_blockers,
)
from group_17_4_lifecycle import check_asset_lifecycle

from backend import storage


class MockPayload:
    """A bytes-like payload that proves threshold selection without allocation."""

    def __init__(self, size: int) -> None:
        self.size = size

    def __len__(self) -> int:
        """Return the synthetic source size."""
        return self.size

    def __getitem__(self, item: slice) -> bytes:
        """Return a small mock part for any requested slice."""
        if not isinstance(item, slice):
            raise TypeError("multipart checklist payload only supports slices")
        return b"mock-multipart-part"


def check_storage_boundary() -> list[CheckResult]:
    """Run mocked URL, metadata, key, multipart, and hard-delete checks."""
    results: list[CheckResult] = []
    key = f"{ORG_A}/images/{TALENT_A}/{JOB_A}/g17-4-small.webp"

    client = MagicMock()
    client.generate_presigned_url.return_value = (
        "https://s3.example.test/bucket/object?X-Amz-Signature=local"
    )
    with (
        patch.object(storage, "_get_client", return_value=client),
        patch.object(storage, "B2_ENDPOINT_URL", "https://b2.example.test"),
        patch.object(storage, "B2_BUCKET_NAME", "local-bucket"),
        patch.object(storage, "B2_CDN_URL", ""),
    ):
        signed_url = storage.upload_file(
            b"local-image",
            key,
            "image/webp",
            org_id=str(ORG_A),
            job_id=str(JOB_A),
        )
    metadata = client.put_object.call_args.kwargs["Metadata"]
    if "X-Amz-Signature" in signed_url and metadata == {
        "org_id": str(ORG_A),
        "job_id": str(JOB_A),
        "content_type": "image/webp",
    }:
        results.append(
            CheckResult(
                "signed delivery and metadata",
                "LOCAL-MOCK-PASS",
                "signature and required metadata preserved",
            )
        )
    else:
        results.append(
            CheckResult(
                "signed delivery and metadata",
                "FAIL",
                "mocked upload contract mismatch",
            )
        )

    cdn_client = MagicMock()
    with (
        patch.object(storage, "_get_client", return_value=cdn_client),
        patch.object(storage, "B2_CDN_URL", "https://cdn.example.test/assets"),
    ):
        cdn_url = storage.upload_file(b"local-image", key, "image/webp")
    if cdn_url == f"https://cdn.example.test/assets/{key}":
        results.append(CheckResult("CDN preference", "LOCAL-MOCK-PASS", "configured CDN selected"))
    else:
        results.append(CheckResult("CDN preference", "FAIL", "configured CDN was not selected"))

    raw_client = MagicMock()
    raw_client.generate_presigned_url.return_value = f"https://s3.example.test/bucket/{key}"
    try:
        with (
            patch.object(storage, "_get_client", return_value=raw_client),
            patch.object(storage, "B2_ENDPOINT_URL", "https://s3.example.test"),
            patch.object(storage, "B2_BUCKET_NAME", "bucket"),
            patch.object(storage, "B2_CDN_URL", ""),
        ):
            storage.upload_file(b"local-image", key, "image/webp")
    except storage.StorageUrlError:
        results.append(
            CheckResult("raw B2 URL rejection", "LOCAL-MOCK-PASS", "unsafe provider URL rejected")
        )
    else:
        results.append(
            CheckResult("raw B2 URL rejection", "FAIL", "raw provider URL escaped the boundary")
        )

    first_key = storage.generate_storage_key(
        "g17-4-small.webp",
        "images",
        org_id=str(ORG_A),
        talent_id=str(TALENT_A),
        job_id=str(JOB_A),
    )
    second_key = storage.generate_storage_key(
        "g17-4-small.webp",
        "images",
        org_id=str(ORG_A),
        talent_id=str(TALENT_A),
        job_id=str(JOB_A),
    )
    parts = first_key.split("/")
    if (
        len(parts) == 5
        and parts[:4] == [str(ORG_A), "images", str(TALENT_A), str(JOB_A)]
        and ".." not in first_key
        and "\\" not in first_key
        and first_key != second_key
    ):
        results.append(
            CheckResult(
                "immutable tenant/talent/job key",
                "LOCAL-MOCK-PASS",
                "unique five-segment key generated and sanitized",
            )
        )
    else:
        results.append(
            CheckResult(
                "immutable tenant/talent/job key",
                "FAIL",
                "key structure or uniqueness mismatch",
            )
        )

    multipart_client = MagicMock()
    multipart_client.create_multipart_upload.return_value = {"UploadId": "local-upload"}
    multipart_client.upload_part.return_value = {"ETag": '"local-etag"'}
    multipart_client.generate_presigned_url.return_value = (
        "https://signed.example.test/model?X-Amz-Signature=local"
    )
    payload = MockPayload(THRESHOLD_BYTES + 1)
    with (
        patch.object(storage, "_get_client", return_value=multipart_client),
        patch.object(storage, "B2_CDN_URL", ""),
        patch.object(storage, "MULTIPART_THRESHOLD_BYTES", THRESHOLD_BYTES),
    ):
        storage.upload_file(
            payload,  # type: ignore[arg-type]
            f"{ORG_A}/models/{TALENT_A}/{JOB_A}/g17-4-model.safetensors",
            "application/octet-stream",
            org_id=str(ORG_A),
            job_id=str(JOB_A),
        )
    if (
        len(payload) == THRESHOLD_BYTES + 1
        and multipart_client.create_multipart_upload.called
        and multipart_client.complete_multipart_upload.called
        and not multipart_client.put_object.called
    ):
        results.append(
            CheckResult(
                "strictly-over-100MiB multipart",
                "LOCAL-MOCK-PASS",
                "104857601-byte synthetic source selected multipart",
            )
        )
    else:
        results.append(
            CheckResult(
                "strictly-over-100MiB multipart",
                "FAIL",
                "threshold did not select multipart",
            )
        )

    abort_client = MagicMock()
    abort_client.create_multipart_upload.return_value = {"UploadId": "local-abort"}
    abort_client.upload_part.side_effect = ClientError(
        {"Error": {"Code": "ServiceUnavailable", "Message": "mocked"}},
        "UploadPart",
    )
    try:
        with (
            patch.object(storage, "_get_client", return_value=abort_client),
            patch.object(storage, "MULTIPART_THRESHOLD_BYTES", THRESHOLD_BYTES),
        ):
            storage.upload_file(
                MockPayload(THRESHOLD_BYTES + 1),
                "local/abort/model.bin",  # type: ignore[arg-type]
            )
    except ClientError:
        pass
    if abort_client.abort_multipart_upload.called and not abort_client.complete_multipart_upload.called:
        results.append(
            CheckResult(
                "multipart abort",
                "LOCAL-MOCK-PASS",
                "part failure aborted upload without completion",
            )
        )
    else:
        results.append(
            CheckResult(
                "multipart abort",
                "FAIL",
                "failed multipart upload was not aborted",
            )
        )

    delete_client = MagicMock()
    try:
        with patch.object(storage, "_get_client", return_value=delete_client):
            storage.delete_file(key)
    except storage.StorageDeletionRequiresLifecycleError:
        if not delete_client.delete_object.called:
            results.append(
                CheckResult(
                    "direct deletion guard",
                    "LOCAL-MOCK-PASS",
                    "request-path hard delete rejected",
                )
            )
        else:
            results.append(
                CheckResult("direct deletion guard", "FAIL", "provider delete was called")
            )
    else:
        results.append(
            CheckResult("direct deletion guard", "FAIL", "direct deletion was accepted")
        )
    return results


def print_results(results: list[CheckResult]) -> int:
    """Print a dense checklist report and return failure count."""
    failures = 0
    for result in results:
        print(f"[{result.status}] {result.name}: {result.detail}")
        if result.status == "FAIL":
            failures += 1
    return failures


async def main() -> int:
    """Execute local mocked checks and display non-promotable staging blockers."""
    local_results = check_storage_boundary()
    local_results.extend(await check_asset_lifecycle())
    local_results.append(run_local_cleanup_guard())
    print("Group 17.4 local checklist")
    failures = print_results(local_results)
    print("\nLive acceptance gates")
    print_results(staging_blockers())
    print("\nNo live B2/CDN/API/database/worker calls were attempted.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
