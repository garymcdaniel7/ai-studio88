#!/bin/bash
# Persistent SSH tunnel to GPU worker.
# Auto-reconnects on disconnect. Run this on your Mac.
#
# Usage: bash scripts/ssh_tunnel.sh
# Stop:  pkill -f "ssh_tunnel"
#
# Tunnels:
#   localhost:8188 → ComfyUI
#   localhost:11434 → Ollama (GPU)
#   localhost:7860 → Worker API

WORKER_SSH="${WORKER_SSH:-ssh2.vast.ai}"
WORKER_PORT="${WORKER_SSH_PORT:-18228}"
KEY="${SSH_KEY:-~/.ssh/id_ed25519}"
RETRY_INTERVAL=10

echo "=== AI Studio SSH Tunnel (persistent) ==="
echo "Worker: $WORKER_SSH:$WORKER_PORT"
echo "Tunnels: 8188 (ComfyUI), 11434 (Ollama), 7860 (Worker API)"
echo "Press Ctrl+C to stop."
echo ""

while true; do
    echo "[$(date)] Connecting..."
    ssh -N -o ServerAliveInterval=30 \
           -o ServerAliveCountMax=3 \
           -o ExitOnForwardFailure=yes \
           -o ConnectTimeout=10 \
           -i "$KEY" \
           -p "$WORKER_PORT" \
           -L 8188:127.0.0.1:8188 \
           -L 11434:127.0.0.1:11434 \
           -L 7860:127.0.0.1:7860 \
           root@"$WORKER_SSH"

    EXIT_CODE=$?
    echo "[$(date)] Tunnel dropped (exit $EXIT_CODE). Reconnecting in ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done
