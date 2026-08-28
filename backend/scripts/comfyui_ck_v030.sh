#!/bin/bash
# Install comfy-kitchen for v0.30.0 + restart
set -e
echo "=== install comfy-kitchen (v0.30.0 needs it, may use older API) ==="
pip install --quiet comfy-kitchen 2>&1 | tail -3 || true
python3 -c "import comfy_kitchen; print('comfy_kitchen ok, version:', getattr(comfy_kitchen, '__version__', 'unknown'))" 2>&1 | tail -2 || true
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 50
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 20)---"
tail -20 /root/comfyui.log 2>/dev/null
