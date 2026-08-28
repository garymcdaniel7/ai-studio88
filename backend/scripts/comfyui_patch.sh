#!/bin/bash
# Patch ComfyUI to tolerate the comfy-kitchen API mismatch, then restart
set -e
cd /root/ComfyUI
echo "=== patch attention.py to tolerate missing comfy_kitchen API ==="
python3 - <<'PYEOF'
import re
p = "comfy/ldm/modules/attention.py"
src = open(p).read()
old = "COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE = comfy_kitchen.int8_attention_is_available()"
new = """try:
    COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE = comfy_kitchen.int8_attention_is_available()
except (AttributeError, NotImplementedError):
    COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE = False"""
if old in src:
    src = src.replace(old, new)
    open(p, "w").write(src)
    print("patched attention.py")
else:
    print("pattern not found (already patched or changed)")
PYEOF
echo "=== also patch any other bare comfy_kitchen calls that break import ==="
grep -rn "comfy_kitchen\." comfy/ --include="*.py" 2>/dev/null | grep -v "def \|try\|except" | grep -iE "is_available|import " | head
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 45
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 15)---"
tail -15 /root/comfyui.log 2>/dev/null
