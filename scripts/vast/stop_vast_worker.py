#!/usr/bin/env python3
"""Stop or destroy Vast.ai worker instances.

Usage:
    python scripts/vast/stop_vast_worker.py --instance 12345
    python scripts/vast/stop_vast_worker.py --instance 12345 --destroy
    python scripts/vast/stop_vast_worker.py --all
    python scripts/vast/stop_vast_worker.py --all --destroy
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from backend.providers.vast.client import VastClient, VastClientError


def main():
    parser = argparse.ArgumentParser(description="Stop Vast.ai workers")
    parser.add_argument("--instance", type=int, help="Instance ID to stop")
    parser.add_argument("--all", action="store_true", help="Stop all instances")
    parser.add_argument("--destroy", action="store_true", help="Permanently destroy (not just stop)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not args.instance and not args.all:
        print("[ERROR] Provide --instance ID or --all")
        sys.exit(1)

    try:
        client = VastClient()
    except VastClientError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    action = "destroy" if args.destroy else "stop"

    if args.all:
        try:
            instances = client.get_instances()
        except VastClientError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)

        if not instances:
            print("[INFO] No active instances found.")
            sys.exit(0)

        print(f"[INFO] Found {len(instances)} instance(s):")
        for inst in instances:
            iid = inst.get("id", "?")
            gpu = inst.get("gpu_name", "?")
            status = inst.get("actual_status", inst.get("status_msg", "?"))
            print(f"       ID={iid} GPU={gpu} Status={status}")

        if not args.yes:
            confirm = input(f"\n{action.title()} ALL instances? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("[ABORT]")
                sys.exit(0)

        for inst in instances:
            iid = inst.get("id")
            try:
                if args.destroy:
                    client.destroy_instance(iid)
                else:
                    client.stop_instance(iid)
                print(f"[OK] {action.title()}ed instance {iid}")
            except VastClientError as e:
                print(f"[WARN] Failed to {action} {iid}: {e}")
    else:
        if not args.yes:
            confirm = input(f"{action.title()} instance {args.instance}? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("[ABORT]")
                sys.exit(0)
        try:
            if args.destroy:
                client.destroy_instance(args.instance)
            else:
                client.stop_instance(args.instance)
            print(f"[OK] {action.title()}ed instance {args.instance}")
        except VastClientError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
