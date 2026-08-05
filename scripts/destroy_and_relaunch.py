"""Destroy stuck instance and launch a fresh one."""
import sys
sys.path.insert(0, "/Users/garymcdaniel/kiro/ai-studio88")

from dotenv import load_dotenv
load_dotenv("/Users/garymcdaniel/kiro/ai-studio88/.env")

from backend.providers.vast.client import VastClient

c = VastClient()

# Destroy stuck instance
print("Destroying stuck instance 45284922...")
try:
    result = c.destroy_instance(45284922)
    print(f"Result: {result}")
except Exception as e:
    print(f"Destroy error (may already be gone): {e}")

print("\nDone. Ready to launch a new one.")
print("The Connection Race will find a better instance.")
