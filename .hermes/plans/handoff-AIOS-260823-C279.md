# HANDOFF — Reference AIOS-260823-C279
# Continue this work in Hermes Telegram → AI Studio thread (topic 8).
# Telegram: reference this number to load all context.

## Status: In progress — ComfyUI real image generation (one fix away)

## CURRENT BLOCKER (next step)
ComfyUI v0.30.0 boots almost fully, fails only on torchaudio CUDA mismatch:
```
RuntimeError: Detected that PyTorch and TorchAudio were compiled with different CUDA versions.
PyTorch has CUDA version 12.1 whereas TorchAudio has CUDA version 12.4.
```
FIX (on worker `ssh4.vast.ai:35036`, key ~/.ssh/id_ed25519):
```
pip install torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu121
setsid bash /root/start_comfyui.sh
# verify: ps aux | grep '[m]ain.py' | grep -v grep | wc -l  (want 1+)
#         tail /root/comfyui.log  (want no traceback; "To see the GUI go to http://0.0.0.0:8188")
# health: curl http://localhost:8188/system_stats on the worker
```

## Worker / Fleet state
- Worker instance: Vast RTX 4090, SSH `ssh4.vast.ai:35036`
- AI Studio worker: RUNNING (all real handlers: Image/Video/Lora)
- SDXL Turbo model: downloaded at `/root/ComfyUI/models/checkpoints/sd_xl_turbo_1.0_fp16.safetensors`
- ComfyUI: v0.30.0 checked out; comfy-kitchen 0.1.6; comfy-aimdo installed; torch 2.4.0+cu121
- Image handler (app): `backend/handlers/image_handler.py`, wired, 4 tests pass (commit d243388)

## Working-combo knowledge (hard-won)
- ComfyUI main/v0.33.0 = BROKEN (comfy-kitchen 0.2.x hard dep, breaks torch 2.4 custom-op)
- ComfyUI v0.30.0 = works with comfy-kitchen 0.1.x + comfy-aimdo
- comfy-kitchen 0.2.x = breaks on torch 2.4 (infer_schema list[int]); 0.1.x = clean

## After ComfyUI is up — verify real image end-to-end
1. Confirm ComfyUI health (system_stats shows SDXL turbo model)
2. Enqueue an `image_generation` job via Supabase (org c7dc65c0-a0b1-4980-9f60-884d024a19ca)
3. Watch worker claim it, ComfyUI render, B2 upload — job status completed with image_url

## Already committed + pushed to main this session
- d243388 real image handler, d3ef37d RBAC sidebar, 7368a98 logout+idle-timeout, ef620ce video fail-fast, abb397c DB reconcile, 46437ae scale-test tooling

## Google OAuth (needs Gary action)
redirect_uri_mismatch → add `https://vipmjgglascthwoqqqji.supabase.co/auth/v1/callback` to Google Cloud Console authorized redirect URIs.

## Defects open
1. Google OAuth redirect_uri_mismatch (needs Gary/console)
2. Real image gen (this ComfyUI fix)
3. Frontend dead buttons (some pages) — next after ComfyUI
4. Pre-existing test-isolation bug (documented, not blocking)
