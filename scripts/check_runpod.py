"""Check RunPod connection and list pods."""
import sys
sys.path.insert(0, "/Users/garymcdaniel/kiro/ai-studio88")

from dotenv import load_dotenv
load_dotenv("/Users/garymcdaniel/kiro/ai-studio88/.env")

from backend.providers.runpod.client import RunPodClient

c = RunPodClient()
info = c.validate_api_key()
print(f"RunPod connected! Credits: ${info.get('credits', 0):.2f}")
print(f"Current spend: ${info.get('currentSpendPerHr', 0):.4f}/hr")

pods = c.get_pods()
print(f"Active pods: {len(pods)}")
for p in pods:
    gpu = p.get("machine", {}).get("gpuDisplayName", "?") if p.get("machine") else "?"
    print(f"  - {p.get('name')} ({p.get('desiredStatus')}) GPU: {gpu}")

# List available GPU types under $1/hr
print("\nAvailable GPUs under $1/hr:")
gpus = c.filter_gpu_types(min_vram_gb=12, max_price_per_hour=1.0)
for g in gpus[:8]:
    print(f"  {g.get('displayName')} — {g.get('memoryInGb')}GB VRAM — ${g.get('price_per_hour', '?')}/hr")
