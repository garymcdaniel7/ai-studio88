"""AIOS full-scale load test.

Enqueues a mixed batch of jobs across priorities and workload classes,
then watches the live fleet worker(s) claim and process them. Demonstrates
queue prioritization, fleet worker pickup, and completion in a real run.

Usage (from backend/):
    python scripts/aios_scale_test.py [--jobs N] [--watch SECONDS]

Connects directly to Supabase (env SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY).
"""
from __future__ import annotations

import argparse
import os
import time
import uuid
from datetime import UTC, datetime

from supabase import create_client

ORG_ID = os.getenv("AIOS_TEST_ORG_ID", "c7dc65c0-a0b1-4980-9f60-884d024a19ca")

# workload_class / priority tiers (mirrors fleet scheduler)
TIERS = [
    # (job_type, workload_class, priority, label)
    ("image_generation", "image", 2, "P0-image"),
    ("video_generation", "video", 1, "P1-video"),
    ("voice_generation", "voice", 2, "P0-voice"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=6, help="total jobs to enqueue")
    parser.add_argument("--watch", type=int, default=90, help="seconds to watch")
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")

    client = create_client(url, key)

    print(f"=== AIOS scale test: enqueueing {args.jobs} jobs ===")
    job_ids = []
    for i in range(args.jobs):
        job_type, wl_class, priority, label = TIERS[i % len(TIERS)]
        job = {
            "type": job_type,
            "status": "queued",
            "priority": priority,
            "workload_class": wl_class,
            "max_attempts": 3,
            "attempts": 0,
            "org_id": ORG_ID,
            "idempotency_key": f"scale-{uuid.uuid4().hex[:12]}",
            "input": {
                "prompt": f"scale test {label} job {i}",
                "width": 512,
                "height": 512,
            },
        }
        res = client.table("jobs").insert(job).execute()
        jid = res.data[0]["id"]
        job_ids.append(jid)
        print(f"  enqueued {jid[:8]} type={job_type} pri={priority} ({label})")

    print(f"\n=== Watching {args.watch}s for fleet to drain the queue ===")
    deadline = time.time() + args.watch
    last_status = {}
    while time.time() < deadline:
        res = client.table("jobs").select("id,status,worker_name").in_("id", job_ids).execute()
        done = 0
        for j in res.data:
            jid = j["id"]
            status = j["status"]
            worker = j.get("worker_name")
            if last_status.get(jid) != f"{status}|{worker}":
                print(f"  {jid[:8]} -> {status}" + (f" by {worker}" if worker else ""))
                last_status[jid] = f"{status}|{worker}"
            if status in ("completed", "failed"):
                done += 1
        if done == len(job_ids):
            print("\n=== ALL JOBS SETTLED ===")
            break
        time.sleep(4)

    print("\n=== Final state ===")
    res = client.table("jobs").select("id,type,status,worker_name,priority").in_("id", job_ids).execute()
    for j in sorted(res.data, key=lambda x: x["priority"], reverse=True):
        print(f"  {j['type']:20} pri={j['priority']} status={j['status']:10} worker={j.get('worker_name') or '-'}")


if __name__ == "__main__":
    main()
