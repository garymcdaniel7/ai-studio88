#!/bin/bash
# Pivot to a stable ComfyUI release (v0.33.0) with known-good deps
set -e
cd /root/ComfyUI
echo "=== checking out stable release v0.33.0 ==="
git stash 2>/dev/null || true
git checkout v0.33.0 2>&1 | tail -2
echo "=== install stable requirements ==="
pip install --quiet -r requirements.txt 2>&1 | tail -3 || true
echo "=== remove broken comfy-kitchen pin if present ==="
sed -i 's/^comfy-kitchen=/#comfy-kitchen=/' requirements.txt 2>/dev/null || true
pip uninstall -y comfy-kitchen comfy_aimdo 2>&1 | grep -i uninstall | head || true
echo "=== start ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 35
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 10)---"
tail -10 /root/comfyui.log 2>/dev/null
