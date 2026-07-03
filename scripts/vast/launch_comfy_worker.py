#!/usr/bin/env python3
"""Launch a ComfyUI worker on Vast.ai.

Safety: prints cost estimate and requires --yes to proceed.

Usage:
    python scripts/vast/launch_comfy_worker.py --gpu RTX_4090
    python scripts/vast/launch_comfy_worker.py --gpu RTX_4090 --yes
    python scripts/vast/launch_comfy_worker.py --offer-id 12345 --yes
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from backend.providers.vast.client import VastClient, VastClientError

BOOTSTRAP_SCRIPT = """#!/bin/bash
set -e
apt-get update && apt-get install -y git wget
cd /workspace
git clone https://github.com/comfyanonymous/ComfyUI.git || true
cd ComfyUI
pip install -r requirements.txt
# Install ComfyUI Manager
cd custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git || true
cd ..
# Create standard directories
mkdir -p models/checkpoints models/loras models/vae models/controlnet models/upscale_models input output
# Start ComfyUI
python main.py --listen 0.0.0.0 --port 8188 &
echo "ComfyUI starting on 0.0.0.0:8188"
"""


def main():
    parser = argparse.ArgumentParser(description="Launch ComfyUI on Vast.ai")
    parser.add_argument("--gpu", default=os.getenv("VAST_DEFAULT_GPU", "RTX_4090"), help="GPU filter")
    parser.add_argument("--max-price", type=float, default=float(os.getenv("VAST_MAX_PRICE_PER_HOUR", "1.50")))
    parser.add_argument("--disk", type=int, default=int(os.getenv("VAST_DISK_GB", "80")))
    parser.add_argument("--offer-id", type=int, default=None, help="Specific offer ID to use")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--launch", action="store_true", help="Actually launch (safety flag)")
    args = parser.parse_args()

    if not args.launch:
        print("[SAFETY] Pass --launch to actually create a paid instance.")
        print("         This is a dry-run showing what would happen.")
        print()

    try:
        client = VastClient()
    except VastClientError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # Select offer
    if args.offer_id:
        offer = {"id": args.offer_id, "gpu_name": "specified", "dph_total": 0, "disk_space": args.disk}
        print(f"[INFO] Using specified offer ID: {args.offer_id}")
    else:
        print(f"[INFO] Finding best {args.gpu} offer under ${args.max_price}/hr...")
        offers = client.filter_offers(
            gpu_name=args.gpu,
            max_price_per_hour=args.max_price,
            min_disk_gb=args.disk,
        )
        if not offers:
            print("[ERROR] No matching offers found. Try different filters.")
            sys.exit(1)
        offer = offers[0]

    # Print cost estimate
    price = offer.get("dph_total", 0)
    gpu = offer.get("gpu_name", "unknown")
    disk = offer.get("disk_space", args.disk)
    print(f"\n{'='*50}")
    print(f"  GPU:          {gpu}")
    print(f"  Price:        ${price:.3f}/hr")
    print(f"  Disk:         {disk} GB")
    print(f"  Offer ID:     {offer.get('id', '?')}")
    print(f"  Est. daily:   ${price * 24:.2f}")
    print(f"{'='*50}")

    if not args.launch:
        print("\n[DRY-RUN] Would launch this instance. Pass --launch --yes to proceed.")
        sys.exit(0)

    if not args.yes:
        confirm = input("\nLaunch this instance? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("[ABORT] Not launching.")
            sys.exit(0)

    print("\n[INFO] Launching instance...")
    try:
        result = client.launch_instance(
            offer_id=offer["id"],
            disk_gb=args.disk,
            onstart=BOOTSTRAP_SCRIPT,
        )
        instance_id = result.get("new_contract")
        print(f"[OK] Instance launched! ID: {instance_id}")
        print(f"     Waiting for startup...")
        print(f"\n     To check status:  python scripts/vast/check_comfy_health.py --instance {instance_id}")
        print(f"     To stop:          python scripts/vast/stop_vast_worker.py --instance {instance_id}")
    except VastClientError as e:
        print(f"[ERROR] Launch failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
