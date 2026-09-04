#!/bin/bash
# Start ComfyUI on the worker, detached, logging to /tmp/comfyui.log
cd /workspace/ComfyUI || exit 1
pkill -f 'main.py.*8188' 2>/dev/null || true
sleep 1
# Fresh log
: > /tmp/comfyui.log
setsid nohup python3 main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch >> /tmp/comfyui.log 2>&1 &
echo "launched pid $!"
sleep 20
echo "=== log tail ==="
tail -15 /tmp/comfyui.log
echo "=== proc ==="
ps aux | grep 'main.py' | grep -v grep | head -2
echo "=== listening ==="
(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep ':8188' | head -2
