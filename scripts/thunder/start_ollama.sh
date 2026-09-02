#!/bin/bash
# Reliable Ollama start for the Thunder ComfyUI worker (AI Studio Brain).
# Usage: sudo -u ubuntu bash /home/ubuntu/start_ollama.sh
set -e
export OLLAMA_HOST=0.0.0.0
export OLLAMA_MODEL=dolphin-llama3:8b

pkill -f "ollama serve" 2>/dev/null || true
sleep 2

# Full detachment: setsid + nohup + all fds redirected
setsid nohup ollama serve >> /tmp/ollama.log 2>&1 < /dev/null &
disown || true

# Wait for the API to actually come up (up to 60s)
for i in $(seq 1 30); do
  if curl -s -m 2 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
    echo "Ollama API is UP after ${i}x2s"
    curl -s -m 3 http://127.0.0.1:11434/api/tags | head -c 200
    echo ""
    exit 0
  fi
  sleep 2
done

echo "ERROR: Ollama did not come up in 60s"
tail -10 /tmp/ollama.log
exit 1
