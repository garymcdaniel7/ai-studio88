#!/bin/bash
# Fully guard all comfy_kitchen imports so ComfyUI boots without it (optional accel)
set -e
cd /root/ComfyUI
echo "=== patch all comfy_kitchen import sites to degrade gracefully ==="

python3 - <<'PYEOF'
import re

# 1. attention.py - already patched the is_available call; ensure import is guarded
p = "comfy/ldm/modules/attention.py"
src = open(p).read()
# The import may be bare; find it
if "import comfy_kitchen" in src and "try:" not in src.split("import comfy_kitchen")[1][:200]:
    pass  # handled below generically

# 2. quant_ops.py - wrap the import in try/except
p2 = "comfy/quant_ops.py"
s2 = open(p2).read()
s2 = s2.replace(
    "import comfy_kitchen as ck",
    "try:\n    import comfy_kitchen as ck\n    _COMFY_KITCHEN_OK = True\nexcept Exception:\n    ck = None\n    _COMFY_KITCHEN_OK = False"
)
open(p2, "w").write(s2)
print("patched quant_ops.py import")

# 3. llama.py - guard the is_available call
p3 = "comfy/text_encoders/llama.py"
s3 = open(p3).read()
s3 = s3.replace(
    "comfy_kitchen.flash_attention_decode_is_available(device)",
    "(comfy_kitchen is not None and comfy_kitchen.flash_attention_decode_is_available(device))"
)
open(p3, "w").write(s3)
print("patched llama.py")

# 4. model_management.py - ensure no bare comfy_kitchen breaks
PYEOF

echo "=== check remaining bare comfy_kitchen at import time ==="
grep -rn "^import comfy_kitchen\|^from comfy_kitchen\|import comfy_kitchen as" comfy/ --include="*.py" 2>/dev/null | head

echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 45
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 15)---"
tail -15 /root/comfyui.log 2>/dev/null
