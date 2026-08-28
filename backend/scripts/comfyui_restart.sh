#!/bin/bash
# Restart ComfyUI now that comfy-kitchen 0.1.x (compatible) is installed
set -e
echo "=== verify comfy-kitchen version ==="
pip show comfy-kitchen 2>/dev/null | grep -i version
python3 -c "import comfy_kitchen; print('comfy_kitchen import ok')" 2>&1 | tail -1
python3 -c "import comfy_aimdo; print('comfy_aimdo import ok')" 2>&1 | tail -1 || echo "aimdo needs handling"
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 45
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 15)---"
tail -15 /root/comfyui.log 2>/dev/null
