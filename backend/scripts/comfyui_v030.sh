#!/bin/bash
# Check out ComfyUI v0.30.0 (last version WITHOUT comfy-kitchen dependency) + start
set -e
cd /root/ComfyUI
echo "=== checkout v0.30.0 (no comfy-kitchen dep) ==="
git checkout -- . 2>/dev/null || true  # revert all my broken patches
git checkout v0.30.0 2>&1 | tail -2
echo "=== install requirements ==="
pip install --quiet -r requirements.txt 2>&1 | tail -3 || true
echo "=== ensure comfy-kitchen is GONE (would break import) ==="
pip uninstall -y comfy-kitchen comfy-aimdo 2>&1 | grep -i uninstall | head || true
echo "=== verify no comfy_kitchen refs at import-time ==="
grep -rc "comfy_kitchen" comfy/ldm/modules/attention.py 2>/dev/null | tail -1
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 45
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 15)---"
tail -15 /root/comfyui.log 2>/dev/null
