#!/usr/bin/env python3
"""Mark scoped stuck video jobs failed and enqueue fresh test jobs."""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from supabase import create_client


def _org_id_argument(value: str) -> str:
    """Parse the required organization UUID before creating a database client."""
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("--org-id must be a valid UUID") from exc


def main() -> None:
    """Reset stale video jobs and enqueue two tenant-scoped probes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=True, type=_org_id_argument)
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")

    client = create_client(url, key)
    org_id = args.org_id

    cutoff = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    stuck = (
        client.table("jobs")
        .select("id,status")
        .eq("status", "running")
        .eq("type", "video_generation")
        .eq("org_id", org_id)
        .gte("updated_at", cutoff)
        .execute()
    )
    print(f"Found {len(stuck.data)} scoped stuck running video jobs")
    for job in stuck.data:
        (
            client.table("jobs")
            .update({"status": "failed", "error": "superseded: worker restarted"})
            .eq("id", job["id"])
            .eq("org_id", org_id)
            .execute()
        )
        print(f"  marked {job['id'][:8]} failed")

    for index in range(2):
        (
            client.table("jobs")
            .insert(
                {
                    "type": "video_generation",
                    "status": "queued",
                    "priority": 1,
                    "workload_class": "video",
                    "max_attempts": 2,
                    "attempts": 0,
                    "org_id": org_id,
                    "input": {"prompt": f"fail-fast video test {index}", "duration_seconds": 5},
                }
            )
            .execute()
        )
        print(f"  enqueued video test job {index}")
    print("done")


if __name__ == "__main__":
    main()
