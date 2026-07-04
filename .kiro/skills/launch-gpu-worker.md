# Skill: Launch GPU Worker

## Purpose
Launch a GPU worker on Vast.ai using Connection Race Mode.

## When to Use
- Before any ComfyUI generation
- When the infrastructure dashboard shows "no worker"
- When creating images/videos from the UI

## Steps

### Via API
```bash
curl -X POST http://localhost:8000/api/v1/infrastructure/launch \
  -H "Content-Type: application/json" \
  -d '{"max_price": 1.50, "min_vram_gb": 24, "num_candidates": 3}'
```

### Via Script (manual)
```bash
python scripts/vast/launch_comfy_worker.py --gpu RTX_4090 --launch --yes
```

### After Launch
1. SSH in: `ssh -i ~/.ssh/id_ed25519 -p PORT root@HOST`
2. Install ComfyUI: clone + pip install
3. Download model from B2 (or HF with HF_TOKEN)
4. Start ComfyUI: `python main.py --listen 0.0.0.0 --port 8188`
5. Set up SSH tunnel: `ssh -N -L 8188:127.0.0.1:8188 ...`
6. Update COMFYUI_BASE_URL in .env if needed

## Important
- Avoid RTX 50 series (Blackwell) — PyTorch incompatible
- Prefer hosts with inet_down >= 2000 MB/s
- Prefer compute_cap 800-899 (Ada/Ampere architecture)
- Always destroy workers when done: `python scripts/vast/stop_vast_worker.py --all --destroy --yes`
