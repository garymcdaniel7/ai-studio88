#!/bin/bash
# Start the Worker HTTP API on a GPU instance.
# Run this after ComfyUI and Ollama are started.
#
# Usage: bash worker/start.sh
# Or via SSH: ssh worker "cd /workspace && bash worker/start.sh"

set -e

PORT=${WORKER_API_PORT:-7860}

echo "=== AI Studio Worker API ==="
echo "Port: $PORT"
echo ""

# Install dependencies if needed
pip install fastapi uvicorn httpx 2>/dev/null || true

# Start the API
cd /workspace/ai-studio88 2>/dev/null || cd /workspace

echo "Starting Worker API on port $PORT..."
nohup python -m worker.api > /tmp/worker_api.log 2>&1 &
echo $! > /tmp/worker_api.pid

sleep 2

# Verify it started
if curl -s http://localhost:$PORT/health > /dev/null 2>&1; then
    echo "Worker API running on port $PORT"
    echo "Health: $(curl -s http://localhost:$PORT/ | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"status\",\"unknown\"))' 2>/dev/null)"
else
    echo "WARNING: Worker API may not have started. Check /tmp/worker_api.log"
    tail -5 /tmp/worker_api.log 2>/dev/null
fi
