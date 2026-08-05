"""Check running Vast.ai instances and print SSH connection info."""
import sys
sys.path.insert(0, "/Users/garymcdaniel/kiro/ai-studio88")

from dotenv import load_dotenv
load_dotenv("/Users/garymcdaniel/kiro/ai-studio88/.env")

from backend.providers.vast.client import VastClient

client = VastClient()
instances = client.get_instances()
found = False

for i in instances:
    status = i.get("actual_status", "unknown")
    if status in ("running", "loading"):
        found = True
        print(f"Instance: {i.get('id')}")
        print(f"GPU: {i.get('gpu_name')}")
        print(f"Status: {status}")
        print(f"SSH Host: {i.get('ssh_host')}")
        print(f"SSH Port: {i.get('ssh_port')}")
        print(f"SSH Command: ssh -p {i.get('ssh_port')} root@{i.get('ssh_host')}")
        print(f"Price: ${i.get('dph_total', 0):.3f}/hr")
        print(f"\nTunnel command:")
        print(f"  ssh -N -L 8188:127.0.0.1:8188 -L 11434:127.0.0.1:11434 -L 7860:127.0.0.1:7860 -i ~/.ssh/id_ed25519 -p {i.get('ssh_port')} root@{i.get('ssh_host')}")
        print()

if not found:
    print("No running instances found on Vast.ai.")
