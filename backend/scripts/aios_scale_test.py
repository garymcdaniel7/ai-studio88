"""AIOS full-scale tenant-scoped load test.

Enqueues a mixed batch of jobs across priorities and workload classes,
then watches the live fleet worker(s) claim and process them.

Usage (from backend):
    python scripts/aios_scale_test.py --org-id <UUID> [--jobs N] [--watch SECONDS]

Connects directly to Supabase (env SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY).
"""
from __future__ import annotations

import argparse
import os
import time
import uuid
from uuid import UUID

from supabase import create_client

# workload_class / priority tiers (mirrors fleet scheduler)
TIERS = [
    ("image_generation", "image", 2, "P0-image"),
    ("video_generation", "video", 1, "P1-video"),
    ("voice_generation", "voice", 2, "P0-voice"),
]


def _org_id_argument(value: str) -> str:
    """Parse the required organization UUID before creating a database client."""
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("--org-id must be a valid UUID") from exc


def main() -> None:
    """Enqueue and observe jobs for one explicitly selected organization."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", required=True, type=_org_id_argument)
    parser.add_argument("--jobs", type=int, default=6, help="total jobs to enqueue")
    parser.add_argument("--watch", type=int, default=90, help="seconds to watch")
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")

    client = create_client(url, key)
    org_id = args.org_id

    print(f"=== AIOS scale test: enqueueing {args.jobs} jobs ===")
    job_ids = []
    for index in range(args.jobs):
        job_type, workload_class, priority, label = TIERS[index % len(TIERS)]
        job = {
            "type": job_type,
            "status": "queued",
            "priority": priority,
            "workload_class": workload_class,
            "max_attempts": 3,
            "attempts": 0,
            "org_id": org_id,
            "idempotency_key": f"scale-{uuid.uuid4().hex[:12]}",
            "input": {"prompt": f"scale test {label} job {index}", "width": 512, "height": 512},
        }
        result = client.table("jobs").insert(job).execute()
        job_id = result.data[0]["id"]
        job_ids.append(job_id)
        print(f"  enqueued {job_id[:8]} type={job_type} pri={priority} ({label})")

    print(f"\n=== Watching {args.watch}s for fleet to drain the queue ===")
    deadline = time.time() + args.watch
    last_status = {}
    while time.time() < deadline:
        result = (
            client.table("jobs")
            .select("id,status,worker_name")
            .in_("id", job_ids)
            .eq("org_id", org_id)
            .execute()
        )
        done = 0
        for job in result.data:
            job_id = job["id"]
            status = job["status"]
            worker = job.get("worker_name")
            if last_status.get(job_id) != f"{status}|{worker}":
                print(f"  {job_id[:8]} -> {status}" + (f" by {worker}" if worker else ""))
                last_status[job_id] = f"{status}|{worker}"
            if status in ("completed", "failed"):
                done += 1
        if done == len(job_ids):
            print("\n=== ALL JOBS SETTLED ===")
            break
        time.sleep(4)

    print("\n=== Final state ===")
    result = (
        client.table("jobs")
        .select("id,type,status,worker_name,priority")
        .in_("id", job_ids)
        .eq("org_id", org_id)
        .execute()
    )
    for job in sorted(result.data, key=lambda item: item["priority"], reverse=True):
        print(
            f"  {job['type']:20} pri={job['priority']} "
            f"status={job['status']:10} worker={job.get('worker_name') or '-'}"
        )


if __name__ == "__main__":
    main()
