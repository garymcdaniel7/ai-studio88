#!/usr/bin/env python3
"""List available Vast.ai GPU offers filtered by project defaults.

Usage:
    python scripts/vast/list_offers.py
    python scripts/vast/list_offers.py --gpu RTX_4090 --max-price 1.00 --min-vram 20
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from backend.providers.vast.client import VastClient, VastClientError


def main():
    parser = argparse.ArgumentParser(description="List Vast.ai GPU offers")
    parser.add_argument("--gpu", default=os.getenv("VAST_DEFAULT_GPU", ""), help="GPU name filter")
    parser.add_argument("--max-price", type=float, default=float(os.getenv("VAST_MAX_PRICE_PER_HOUR", "1.50")), help="Max $/hr")
    parser.add_argument("--min-vram", type=float, default=0, help="Min VRAM in GB")
    parser.add_argument("--min-disk", type=float, default=float(os.getenv("VAST_DISK_GB", "80")), help="Min disk GB")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    args = parser.parse_args()

    try:
        client = VastClient()
    except VastClientError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(f"[INFO] Searching offers: GPU={args.gpu or 'any'}, max=${args.max_price}/hr, VRAM>={args.min_vram}GB, disk>={args.min_disk}GB")
    try:
        offers = client.filter_offers(
            gpu_name=args.gpu or None,
            min_vram_gb=args.min_vram,
            max_price_per_hour=args.max_price,
            min_disk_gb=args.min_disk,
        )
    except VastClientError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    if not offers:
        print("[WARN] No offers match your criteria. Try relaxing filters.")
        sys.exit(0)

    print(f"\n[OK] Found {len(offers)} offers (showing top {args.limit}):\n")
    print(f"{'ID':<10} {'GPU':<20} {'VRAM':<8} {'$/hr':<8} {'Disk':<8} {'Score'}")
    print("-" * 70)
    for o in offers[:args.limit]:
        print(
            f"{o.get('id', '?'):<10} "
            f"{o.get('gpu_name', '?'):<20} "
            f"{o.get('gpu_ram', 0) / 1024:<8.1f} "
            f"{o.get('dph_total', 0):<8.3f} "
            f"{o.get('disk_space', 0):<8.0f} "
            f"{o.get('score', 0):.2f}"
        )


if __name__ == "__main__":
    main()
