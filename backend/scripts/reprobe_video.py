#!/usr/bin/env python3
"""Mark stuck 'running' video jobs as failed, then re-enqueue fresh test jobs."""
import os
from datetime import UTC, datetime, timedelta

from supabase import create_client

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
c = create_client(url, key)
org = "c7dc65c0-a0b1-4980-9f60-884d024a19ca"

# 1. Find video jobs stuck in 'running' and mark them failed (cleanup)
cutoff = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
stuck = (
    c.table("jobs")
    .select("id,status")
    .eq("status", "running")
    .eq("type", "video_generation")
    .gte("updated_at", cutoff)
    .execute()
)
print(f"Found {len(stuck.data)} stuck running video jobs")
for j in stuck.data:
    c.table("jobs").update(
        {"status": "failed", "error": "superseded: worker restarted with fail-fast handler"}
    ).eq("id", j["id"]).execute()
    print(f"  marked {j['id'][:8]} failed")

# 2. Enqueue 2 fresh video jobs to test the fail-fast path
for i in range(2):
    c.table("jobs").insert(
        {
            "type": "video_generation",
            "status": "queued",
            "priority": 1,
            "workload_class": "video",
            "max_attempts": 2,
            "attempts": 0,
            "org_id": org,
            "input": {"prompt": f"fail-fast video test {i}", "duration_seconds": 5},
        }
    ).execute()
    print(f"  enqueued video test job {i}")
print("done")
