#!/bin/bash
# Ollama Watchdog — keeps Ollama running on the GPU worker.
# Checks every 10 seconds. Restarts if crashed.
#
# Deploy to GPU worker:
#   scp scripts/ollama_watchdog.sh root@worker:/workspace/
#   ssh root@worker "nohup bash /workspace/ollama_watchdog.sh &"
#
# Or add to onstart.sh for automatic start on boot.

MODEL="${OLLAMA_MODEL:-llama3.1:8b}"
CHECK_INTERVAL=10
RESTART_DELAY=3
LOG="/tmp/ollama_watchdog.log"

echo "[$(date)] Ollama Watchdog started (model: $MODEL, interval: ${CHECK_INTERVAL}s)" | tee -a $LOG

# Install Ollama if not present
if ! command -v ollama &> /dev/null; then
    echo "[$(date)] Installing Ollama..." | tee -a $LOG
    curl -fsSL https://ollama.ai/install.sh | sh
fi

while true; do
    # Check if Ollama is responding
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        # Ollama is alive — check if model is loaded
        MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(m['name'] for m in d.get('models',[])))" 2>/dev/null)
        if echo "$MODELS" | grep -q "$MODEL" 2>/dev/null; then
            : # All good — model loaded
        else
            echo "[$(date)] Model $MODEL not found. Pulling..." | tee -a $LOG
            ollama pull $MODEL >> $LOG 2>&1
        fi
    else
        # Ollama is down — restart it
        echo "[$(date)] Ollama is DOWN. Restarting..." | tee -a $LOG
        pkill -f "ollama serve" 2>/dev/null
        sleep $RESTART_DELAY
        nohup ollama serve >> /tmp/ollama.log 2>&1 &
        sleep 5
        # Pull model after restart
        echo "[$(date)] Pulling model after restart..." | tee -a $LOG
        ollama pull $MODEL >> $LOG 2>&1
        echo "[$(date)] Ollama restarted and model loaded." | tee -a $LOG
    fi

    sleep $CHECK_INTERVAL
done
