#!/bin/bash
# Start all AI Studio services on a GPU worker.
# Run this after the worker boots.
#
# Usage: bash worker/start.sh
# Or via SSH: ssh worker "cd /workspace && bash worker/start.sh"

PORT=${WORKER_API_PORT:-7860}
MODEL=${OLLAMA_MODEL:-llama3.1:8b}

echo "=== AI Studio Worker Bootstrap ==="
echo "Worker API Port: $PORT"
echo "Ollama Model: $MODEL"
echo ""

# Install dependencies
pip install fastapi uvicorn httpx 2>/dev/null || true

# --- Start Ollama ---
echo "Starting Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.ai/install.sh | sh
fi
pkill -f "ollama serve" 2>/dev/null || true
sleep 1
nohup ollama serve > /tmp/ollama.log 2>&1 &
sleep 5
# Pull model in background
ollama pull $MODEL >> /tmp/ollama.log 2>&1 &

# --- Start ComfyUI (if installed) ---
if [ -d "/workspace/ComfyUI" ]; then
    echo "Starting ComfyUI..."
    pkill -f "main.py.*8188" 2>/dev/null || true
    cd /workspace/ComfyUI
    nohup python main.py --listen 0.0.0.0 --port 8188 > /tmp/comfyui.log 2>&1 &
    cd /workspace
fi

# --- Start Worker API ---
echo "Starting Worker API on port $PORT..."
pkill -f "worker_api" 2>/dev/null || true
if [ -f "/workspace/worker_api.py" ]; then
    nohup python /workspace/worker_api.py > /tmp/worker_api.log 2>&1 &
else
    nohup python -m worker.api > /tmp/worker_api.log 2>&1 &
fi

# --- Start Ollama Watchdog (keeps Ollama alive, auto-restarts on crash) ---
if [ -f "/workspace/ollama_watchdog.sh" ]; then
    echo "Starting Ollama watchdog..."
    pkill -f "ollama_watchdog" 2>/dev/null || true
    nohup bash /workspace/ollama_watchdog.sh > /tmp/ollama_watchdog.log 2>&1 &
fi

sleep 4

# --- Status Report ---
echo ""
echo "=== Service Status ==="
curl -s http://localhost:11434/api/tags > /dev/null 2>&1 && echo "Ollama: RUNNING" || echo "Ollama: STARTING (check /tmp/ollama.log)"
curl -s http://localhost:8188/system_stats > /dev/null 2>&1 && echo "ComfyUI: RUNNING" || echo "ComfyUI: STARTING or not installed"
curl -s http://localhost:$PORT/ > /dev/null 2>&1 && echo "Worker API: RUNNING on port $PORT" || echo "Worker API: FAILED (check /tmp/worker_api.log)"
echo ""
echo "Bootstrap complete. Logs: /tmp/ollama.log /tmp/comfyui.log /tmp/worker_api.log"
