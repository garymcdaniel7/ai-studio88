# GPU Worker Connection Guide

## SSH Tunnel Command (All Services)

Run this to connect your local machine to all services on the GPU worker:

```bash
ssh -i ~/.ssh/id_ed25519 \
  -o StrictHostKeyChecking=no \
  -o ServerAliveInterval=30 \
  -N \
  -L 8188:127.0.0.1:8188 \
  -L 11434:127.0.0.1:11434 \
  -L 7860:127.0.0.1:7860 \
  -L 18083:127.0.0.1:18083 \
  -p <PORT> root@<SSH_HOST>
```

Replace `<PORT>` and `<SSH_HOST>` with your Vast.ai instance details.

### What each port does:
| Port | Service | Purpose |
|------|---------|---------|
| 8188 | ComfyUI | Image/video generation |
| 11434 | Ollama | AI Brain LLM |
| 7860 | Worker API | AIOS dispatch endpoint |
| 18083 | MOSS-TTS | Voice generation |

## Starting Services on the Worker

After SSH tunnel is open, SSH into the worker and start services:

```bash
# SSH into worker (separate terminal)
ssh -i ~/.ssh/id_ed25519 -p <PORT> root@<SSH_HOST>

# Start ComfyUI
cd /workspace/ComfyUI && python main.py --listen 0.0.0.0 --port 8188 &

# Start Ollama
ollama serve &

# Start Worker API (if repo is cloned)
cd /workspace/ai-studio88 && pip install fastapi uvicorn httpx && python -m worker.api &

# Start MOSS-TTS (if installed)
cd /workspace/moss-tts && python server.py --port 18083 &
```

## Auto-Start on Worker Boot

Add to your Vast.ai "on start" script or RunPod startup:

```bash
#!/bin/bash
# Auto-start all services
cd /workspace/ComfyUI && nohup python main.py --listen 0.0.0.0 --port 8188 > /tmp/comfyui.log 2>&1 &
nohup ollama serve > /tmp/ollama.log 2>&1 &
sleep 5
ollama pull llama3.1:8b
cd /workspace/ai-studio88 && nohup python -m worker.api > /tmp/worker_api.log 2>&1 &
```

## Keeping the Worker Alive

Options:
1. **Vast.ai**: Use "Run indefinitely" option (no auto-stop timer)
2. **RunPod**: Use "Persistent Pod" (stays on, pauses when idle)
3. **Fleet Settings**: Set `FLEET_IDLE_TIMEOUT=0` in .env (disables auto-shutdown)

The AIOS Session Planner (`/aios/v1/session/should-release`) controls when to suggest releasing.
Set `auto_release_idle_minutes: 0` in session plan to keep it running indefinitely.
