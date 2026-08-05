"""Check Vast.ai instance status and balance."""
import sys
sys.path.insert(0, "/Users/garymcdaniel/kiro/ai-studio88")

from dotenv import load_dotenv
load_dotenv("/Users/garymcdaniel/kiro/ai-studio88/.env")

from backend.providers.vast.client import VastClient

try:
    client = VastClient()
    instances = client.get_instances()
    if instances:
        for i in instances:
            status = i.get("actual_status", "unknown")
            gpu = i.get("gpu_name", "?")
            ssh_host = i.get("ssh_host", "")
            ssh_port = i.get("ssh_port", "")
            price = i.get("dph_total", 0)
            iid = i.get("id", "?")
            print(f"Instance {iid}: {gpu} | Status: {status} | SSH: {ssh_host}:{ssh_port} | ${price:.3f}/hr")
    else:
        print("No active instances. Need to launch one.")

    # Check balance
    info = client.validate_api_key()
    print(f"\nBalance: ${info.get('credit', 0):.2f}")
except Exception as e:
    print(f"Error: {e}")
