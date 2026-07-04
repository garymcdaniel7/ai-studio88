#!/usr/bin/env python3
"""Seed B2 model cache using Vast.ai datacenter bandwidth.

Launches multiple instances in parallel — first to boot downloads models
and uploads to B2. Others are destroyed immediately.

Usage:
    python scripts/vast/seed_cache_remote.py --models sdxl-turbo,sd15-pruned,sdxl-vae --yes
    python scripts/vast/seed_cache_remote.py --models sdxl-turbo --yes
    python scripts/vast/seed_cache_remote.py --list
"""
import sys
import os
import time
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from backend.providers.vast.client import VastClient, VastClientError
from backend.providers.vast.model_cache import get_known_model, list_known_models, model_exists_in_cache

B2_KEY_ID = os.getenv("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
B2_ENDPOINT_URL = os.getenv("B2_ENDPOINT_URL", "")
B2_REGION = os.getenv("B2_REGION", "us-east-005")
MODEL_CACHE_BUCKET = os.getenv("MODEL_CACHE_BUCKET", os.getenv("B2_BUCKET_NAME", ""))
MODEL_CACHE_PREFIX = os.getenv("MODEL_CACHE_PREFIX", "models/")
HF_TOKEN = os.getenv("HF_TOKEN", "")

MODEL_SUBFOLDER = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "vae": "vae",
    "controlnet": "controlnet",
}


def build_onstart(models: list[dict]) -> str:
    """Build onstart script that downloads from HF and uploads each to B2."""
    download_blocks = []
    for m in models:
        subfolder = MODEL_SUBFOLDER.get(m["model_type"], "checkpoints")
        b2_key = f"{MODEL_CACHE_PREFIX}{subfolder}/{m['filename']}"
        block = f'''
echo "--- {m['filename']} ({m.get('size_gb','?')}GB) ---"
python3 << 'PYEOF'
from huggingface_hub import hf_hub_download
import boto3, os, glob
from boto3.s3.transfer import TransferConfig

token = os.environ.get("HF_TOKEN") or None
print("  Downloading from HuggingFace...")
path = hf_hub_download("{m['hf_repo']}", "{m['hf_filename']}", local_dir="/workspace/dl", token=token)
size = os.path.getsize(path)
print(f"  Downloaded: {{size / 1e9:.2f}} GB")

print("  Uploading to B2...")
client = boto3.client("s3",
    endpoint_url=os.environ["B2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["B2_KEY_ID"],
    aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    region_name=os.environ.get("B2_REGION", "us-east-005"))
config = TransferConfig(multipart_threshold=100*1024*1024, multipart_chunksize=100*1024*1024, max_concurrency=8)
client.upload_file(path, os.environ["MODEL_CACHE_BUCKET"], "{b2_key}", Config=config)
print("  Uploaded to B2!")
os.remove(path)
PYEOF
'''
        download_blocks.append(block)

    joined = "\n".join(download_blocks)
    return f"""#!/bin/bash
set -e
echo "=== AI Studio Model Cache Seeder ==="
pip install -q boto3 huggingface-hub
mkdir -p /workspace/dl
{joined}
echo "=== ALL DONE ==="
touch /tmp/seed_done
sleep infinity
"""


def find_offers(client: VastClient, max_price: float, min_disk: int) -> list[dict]:
    """Find rentable, reliable offers excluding Blackwell GPUs."""
    headers = {"Authorization": f"Bearer {client.api_key}"}
    resp = httpx.get(
        "https://console.vast.ai/api/v0/bundles/",
        headers=headers,
        params={"q": json.dumps({
            "dph_total": {"lte": max_price},
            "rentable": {"eq": True},
            "disk_space": {"gte": min_disk},
            "reliability2": {"gte": 0.99},
            "inet_down": {"gte": 100},
        })},
        timeout=30,
        follow_redirects=True,
    )
    offers = resp.json().get("offers", []) if resp.status_code == 200 else []
    # Exclude Blackwell (RTX 50 series) — PyTorch doesn't support yet
    blackwell = ["5090", "5080", "5070", "5060", "PRO 6000"]
    offers = [o for o in offers if not any(b in o.get("gpu_name", "") for b in blackwell)]
    offers.sort(key=lambda o: o.get("dph_total", 999))
    return offers


def launch_instance(client: VastClient, offer: dict, onstart: str, env_vars: dict, disk: int) -> int | None:
    """Try to launch an instance. Returns instance_id or None."""
    headers = {"Authorization": f"Bearer {client.api_key}"}
    try:
        resp = httpx.put(
            f"https://console.vast.ai/api/v0/asks/{offer['id']}/",
            headers=headers,
            json={
                "client_id": "me",
                "image": "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime",
                "disk": disk,
                "runtype": "ssh_proxy",
                "onstart": onstart,
                "env": env_vars,
            },
            timeout=30,
            follow_redirects=True,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("new_contract")
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Seed B2 cache via Vast.ai (multi-instance race)")
    parser.add_argument("--models", help="Comma-separated model names")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--max-price", type=float, default=1.50, help="Max $/hr")
    parser.add_argument("--race", type=int, default=3, help="How many instances to launch in parallel")
    parser.add_argument("--list", action="store_true", help="List known models")
    args = parser.parse_args()

    if args.list:
        for m in list_known_models():
            cached = "CACHED" if model_exists_in_cache(m["model_type"], m["filename"]) else "      "
            print(f"  {cached} {m['name']:<14} {m['size_gb']:<6} GB  {m['description']}")
        return

    if not args.models:
        print("[ERROR] --models required. Use --list to see options.")
        sys.exit(1)

    if not B2_KEY_ID or not B2_APPLICATION_KEY:
        print("[ERROR] B2 credentials not in .env")
        sys.exit(1)

    # Resolve models
    model_names = [n.strip() for n in args.models.split(",")]
    models = []
    total_gb = 0
    for name in model_names:
        m = get_known_model(name)
        if not m:
            print(f"[ERROR] Unknown: '{name}'. Use --list.")
            sys.exit(1)
        if model_exists_in_cache(m["model_type"], m["filename"]):
            print(f"[SKIP] '{name}' already cached in B2")
            continue
        models.append(m)
        total_gb += m.get("size_gb", 0)

    if not models:
        print("[OK] All models already in B2 cache!")
        return

    print(f"[INFO] Bulk model cache seeder (multi-instance race)")
    print(f"       Models: {', '.join(m['filename'] for m in models)}")
    print(f"       Total: {total_gb:.1f} GB")
    print(f"       Strategy: launch {args.race} instances, first to boot wins")
    print(f"       Max price: ${args.max_price}/hr")
    print()

    if not args.yes:
        confirm = input("Proceed? (yes/no): ").strip().lower()
        if confirm != "yes":
            sys.exit(0)

    client = VastClient()
    disk_needed = max(50, int(total_gb * 1.5))

    # Find offers
    print("[INFO] Finding available instances...")
    offers = find_offers(client, args.max_price, disk_needed)
    if not offers:
        print("[ERROR] No suitable instances found.")
        sys.exit(1)
    # Prefer offers > $0.10/hr (cheap ones don't boot) and with high bandwidth
    preferred = [o for o in offers if o.get("dph_total", 0) >= 0.10 and o.get("inet_down", 0) >= 200]
    if preferred:
        offers = preferred
    print(f"       {len(offers)} candidates found.")

    # Build onstart
    onstart = build_onstart(models)
    env_vars = {
        "B2_KEY_ID": B2_KEY_ID,
        "B2_APPLICATION_KEY": B2_APPLICATION_KEY,
        "B2_ENDPOINT_URL": B2_ENDPOINT_URL,
        "B2_REGION": B2_REGION,
        "MODEL_CACHE_BUCKET": MODEL_CACHE_BUCKET,
    }
    if HF_TOKEN:
        env_vars["HF_TOKEN"] = HF_TOKEN

    # Launch multiple instances (race)
    print(f"\n[INFO] Launching up to {args.race} instances...")
    launched = []
    for offer in offers[:args.race * 3]:  # Try more than needed
        if len(launched) >= args.race:
            break
        iid = launch_instance(client, offer, onstart, env_vars, disk_needed)
        if iid:
            print(f"       Launched {iid}: {offer.get('gpu_name','?')} @ ${offer.get('dph_total',0):.3f}/hr ({offer.get('geolocation','?')})")
            launched.append(iid)

    if not launched:
        print("[ERROR] Could not launch any instances.")
        sys.exit(1)

    print(f"\n[OK] {len(launched)} instances racing. First to boot wins.")
    print(f"     Polling every 20s...\n")

    # Race: wait for first to come online, destroy the rest
    winner = None
    start_time = time.time()
    max_wait = 480  # 8 min to boot

    while time.time() - start_time < max_wait and not winner:
        time.sleep(20)
        elapsed = int(time.time() - start_time)
        for iid in launched:
            try:
                info = client.get_connection_info(iid)
                status = info.get("status", "unknown")
                if status == "running":
                    winner = iid
                    print(f"       [{elapsed}s] WINNER: instance {iid} is RUNNING!")
                    break
            except Exception:
                pass
        if not winner:
            print(f"       [{elapsed}s] Waiting for boot...")

    if not winner:
        print(f"\n[WARN] No instance booted in {max_wait}s. Destroying all.")
        for iid in launched:
            try:
                client.destroy_instance(iid)
            except Exception:
                pass
        sys.exit(1)

    # Destroy losers
    losers = [iid for iid in launched if iid != winner]
    if losers:
        print(f"       Destroying {len(losers)} runner-up instance(s)...")
        for iid in losers:
            try:
                client.destroy_instance(iid)
            except Exception:
                pass

    # Now wait for models to appear in B2
    print(f"\n[INFO] Winner ({winner}) is running. Waiting for downloads + B2 uploads...")
    print(f"       Checking B2 every 30s. Max wait: 15 min.\n")

    start_time = time.time()
    max_wait = 900

    while time.time() - start_time < max_wait:
        time.sleep(30)
        elapsed = int(time.time() - start_time)
        cached_count = sum(1 for m in models if model_exists_in_cache(m["model_type"], m["filename"]))
        print(f"       [{elapsed}s] B2 cache: {cached_count}/{len(models)} models")
        if cached_count == len(models):
            print(f"\n[OK] ALL {len(models)} MODELS CACHED IN B2!")
            break

    # Final report
    print(f"\n{'='*55}")
    for m in models:
        status = "OK" if model_exists_in_cache(m["model_type"], m["filename"]) else "--"
        print(f"  [{status}] {m['filename']} ({m.get('size_gb','?')} GB)")
    print(f"{'='*55}")

    # Destroy winner
    print(f"\n[INFO] Destroying seeder instance {winner}...")
    try:
        client.destroy_instance(winner)
        print("[OK] Done. No ongoing charges.")
    except Exception as e:
        print(f"[WARN] {e}")
        print(f"       Run: python scripts/vast/stop_vast_worker.py --instance {winner} --destroy --yes")


if __name__ == "__main__":
    main()
