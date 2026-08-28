#!/bin/bash
# Install the required comfy acceleration packages on torch 2.4, then start ComfyUI
set -e
echo "=== install comfy-kitchen + comfy-aimdo (required, torch is now 2.4) ==="
pip install --quiet comfy-kitchen comfy-aimdo 2>&1 | tail -3 || true
python3 -c "import comfy_kitchen; import comfy_aimdo; print('both import ok')" 2>&1 | tail -3 || true
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 40
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 12)---"
tail -12 /root/comfyui.log 2>/dev/null
