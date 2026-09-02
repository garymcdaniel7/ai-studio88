#!/bin/bash
# Idempotent guard: start Ollama only if the API port isn't already answering.
# Used by /etc/thunder/client-extra.sh on every login/boot.
# NOTE: this script is launched fully detached (setsid+nohup) so it survives
# the SSH session that triggered the login.

LOG=/tmp/ollama_autostart.log
echo "[$(date -u +%H:%M:%S)] guard invoked" >> "$LOG"

if curl -s -m 2 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
  echo "[$(date -u +%H:%M:%S)] already serving — nothing to do" >> "$LOG"
  exit 0
fi

# Not serving. If a stale process exists, clear it first.
pkill -f "ollama serve" 2>/dev/null || true
sleep 1

# Start via the robust script (setsid + nohup + readiness wait)
sudo -u ubuntu bash /etc/thunder/start_ollama.sh >> "$LOG" 2>&1
echo "[$(date -u +%H:%M:%S)] start_ollama.sh exit=$?" >> "$LOG"
