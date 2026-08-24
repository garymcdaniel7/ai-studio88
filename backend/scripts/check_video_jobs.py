#!/usr/bin/env python3
"""Check final state of recent video_generation jobs."""
import os

from supabase import create_client

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
c = create_client(url, key)
r = (
    c.table("jobs")
    .select("type,status,worker_name,output,error")
    .in_("type", ["video_generation"])
    .order("created_at", desc=True)
    .limit(4)
    .execute()
)
for j in r.data:
    print(
        j["type"],
        "|",
        j["status"],
        "|",
        j.get("worker_name"),
        "| err:",
        str(j.get("error"))[:60],
        "| out:",
        str(j.get("output"))[:90],
    )
