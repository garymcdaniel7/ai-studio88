#!/bin/bash
# Try torch 2.4.0 + restart ComfyUI
set -e
echo "=== installing torch 2.4.0 (cu121) ==="
pip install --quiet "torch==2.4.0" torchvision --index-url https://download.pytorch.org/whl/cu121 2>&1 | tail -3 || true
python3 -c "import torch; print('torch', torch.__version__)" || true
echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 30
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 8)---"
tail -8 /root/comfyui.log 2>/dev/null
