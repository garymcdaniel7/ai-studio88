#!/bin/bash
# v0.30.0 + comfy-kitchen 0.1.x (the version compatible with torch 2.4) + restart
set -e
echo "=== install comfy-kitchen 0.1.6 (compatible with torch 2.4) ==="
pip install --quiet "comfy-kitchen<0.2" 2>&1 | tail -2 || true
pip show comfy-kitchen 2>/dev/null | grep -i version
python3 -c "import comfy_kitchen; print('comfy_kitchen import ok')" 2>&1 | tail -2 || true
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 50
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 20)---"
tail -20 /root/comfyui.log 2>/dev/null
