# ComfyUI Deployment State — handoff for Telegram continuation

## Goal
Get real image generation working via ComfyUI on the AI Studio Vast GPU worker.

## Current state (as of last working session)
- **Worker instance:** Vast RTX 4090, SSH `ssh4.vast.ai:35036`, key `~/.ssh/id_ed25519`
- **AI Studio worker running:** yes (1 process, all real handlers: ImageGeneration/VideoGeneration/LoraTraining)
- **SDXL Turbo model:** downloaded (6.9GB at `/root/ComfyUI/models/checkpoints/sd_xl_turbo_1.0_fp16.safetensors`)
- **ComfyUI version:** checked out `v0.30.0` (last version without the comfy-kitchen hard-import problem)
- **comfy-kitchen:** 0.1.6 (the version that imports cleanly on torch 2.4)
- **torch:** 2.4.0+cu121
- **comfy-aimdo:** installed (imports ok)

## The blocker (NEXT STEP)
ComfyUI now boots MOSTLY — fails at:
```
RuntimeError: Detected that PyTorch and TorchAudio were compiled with different CUDA versions.
PyTorch has CUDA version 12.1 whereas TorchAudio has CUDA version 12.4.
```
**Fix:** install a torchaudio that matches torch 2.4.0 cu121:
```
pip install torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu121
```
Then restart: `setsid bash /root/start_comfyui.sh`, check `ps aux | grep '[m]ain.py' | wc -l` and `tail /root/comfyui.log`.

## ComfyUI start script (on worker)
`/root/start_comfyui.sh` runs `cd /root/ComfyUI && nohup python3 main.py --listen 0.0.0.0 --port 8188 > /root/comfyui.log 2>&1 </dev/null &`

## Image handler (app side)
`backend/handlers/image_handler.py` — real ComfyUI→B2 handler, wired into worker `JOB_HANDLERS`, 4 tests pass (commit `d243388`).
Uses checkpoint `sd_xl_turbo_1.0_fp16.safetensors` for model `sdxl-turbo`.

## Working combo summary (the hard-won knowledge)
- ComfyUI `main`/v0.33.0 = BROKEN (hard comfy-kitchen 0.2.x dep, incompatible with torch 2.4 custom-op API)
- ComfyUI `v0.30.0` = WORKS with comfy-kitchen 0.1.6 (imports clean) — needed comfy-aimdo too
- comfy-kitchen 0.2.x = broken on torch 2.4 (infer_schema list[int] error)
- comfy-kitchen 0.1.x = imports clean on torch 2.4

## Also done this session (committed + pushed to main)
- Real image handler (d243388), RBAC sidebar (d3ef37d), logout button + 30-min idle timeout (7368a98), video fail-fast (ef620ce), DB reconcile (abb397c), scale-test tooling (46437ae)

## Google OAuth (needs Gary)
redirect_uri_mismatch — add `https://vipmjgglascthwoqqqji.supabase.co/auth/v1/callback` to Google Cloud Console authorized redirect URIs.
