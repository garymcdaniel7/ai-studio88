#!/usr/bin/env python3
"""Check Vast.ai API key authentication.

Usage:
    python scripts/vast/check_vast_auth.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from backend.providers.vast.client import VastClient, VastClientError


def main():
    try:
        client = VastClient()
    except VastClientError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print("[INFO] Validating Vast.ai API key...")
    try:
        account = client.validate_api_key()
        print(f"[OK] Authenticated as: {account.get('username', account.get('email', 'unknown'))}")
        print(f"     Balance: ${account.get('credit', 0):.2f}")
        print(f"     API key is valid.")
    except VastClientError as e:
        print(f"[ERROR] Authentication failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
