"""Create a minimal .safetensors stub file for testing uploads."""
import json
import os
import struct

header = json.dumps({"__metadata__": {"format": "pt", "test": "true"}}).encode("utf-8")
header_size = len(header)

os.makedirs("tests/fixtures", exist_ok=True)
path = "tests/fixtures/test_model.safetensors"

with open(path, "wb") as f:
    f.write(struct.pack("<Q", header_size))
    f.write(header)
    f.write(b"\x00" * 1024)  # 1KB dummy tensor data

print(f"Created {path} ({os.path.getsize(path)} bytes)")
