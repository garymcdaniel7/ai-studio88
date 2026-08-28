#!/bin/bash
# Install required comfy-aimdo, restart ComfyUI
set -e
echo "=== install comfy-aimdo (required by main.py) ==="
pip install --quiet comfy-aimdo 2>&1 | tail -3 || true
python3 -c "import comfy_aimdo; print('comfy_aimdo import ok')" 2>&1 | tail -2 || true
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 45
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 18)---"
tail -18 /root/comfyui.log 2>/dev/null
