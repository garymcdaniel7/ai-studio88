# Simulators & Placeholders Audit

> Generated: July 2026  
> Policy: No new simulators. All new features must connect to real services.

## Quick Activation (Already Built — Just Need Env Vars)

| Feature | Env Var | Notes |
|---------|---------|-------|
| Image Generation | `GENERATION_PROVIDER=comfyui` | Requires GPU worker with ComfyUI |
| LoRA Training (Vast.ai) | `TRAINING_VAST_LIVE=true` | Requires Vast.ai balance + SSH key |
| LoRA Training (SimpleTuner) | `SIMPLETUNER_LIVE=true` | Requires RunPod persistent volume |
| Voice (ElevenLabs) | `ELEVENLABS_LIVE=true` | Requires valid ElevenLabs API key |
| Voice (XTTS) | `XTTS_LIVE=true` | Requires XTTS server on GPU worker |
| Voice (MOSS-TTS) | `MOSS_TTS_ENABLED=true` | Requires MOSS-TTS on GPU worker |
| Publishing | `PUBLISHING_LIVE=true` | Requires webhook URL configured |

## Simulation Providers (Return Fake Data)

| File | Class | What It Fakes |
|------|-------|---------------|
| `backend/engine/providers/simulation.py` | SimulationProvider | Image/video bytes (SHA256) |
| `backend/execution/provider_registry.py` | SimulatedExecutionProvider | All generation types |
| `backend/audio/provider.py` | SimulatedVoiceProvider | Audio bytes |
| `backend/audio/provider.py` | SimulatedMusicProvider | Music bytes |
| `backend/audio/provider.py` | SimulatedSFXProvider | Sound effects bytes |
| `backend/audio/provider.py` | SimulatedLipSyncProvider | Lip sync video bytes |
| `backend/audio/suno_provider.py` | SunoMusicProvider | Music (always simulated) |
| `backend/video/provider.py` | SimulatedVideoProvider | Video bytes |
| `backend/video/provider.py` | SimulatedEditingProvider | Video editing ops |
| `backend/training/provider.py` | SimulatedTrainingProvider | LoRA .safetensors |
| `backend/training/captioning.py` | _caption_simulated() | Image captions |
| `backend/engine/generation_engine.py` | GPUStatus | Fake GPU metrics |

## Dead Endpoints (501 Not Implemented)

These exist in `backend/app/api/v1/endpoints/` and duplicate working routes in `api_v1.py`:

| File | Endpoint | Status |
|------|----------|--------|
| `talent.py` | POST/GET /talents | 501 |
| `assets.py` | POST /assets/upload | 501 |
| `jobs.py` | POST /jobs | 501 |
| `campaigns.py` | POST /campaigns | 501 |
| `organizations.py` | GET/POST /organizations | 501/404 |
| `users.py` | GET /users/me | 404 |
| `dependencies.py` | get_current_org_id() | Always raises 403 |

**Recommendation**: Delete `backend/app/api/v1/endpoints/` entirely. All functionality exists in the flat routers.

## Not Yet Connected (Needs Real Provider)

| Feature | What Exists | What's Needed |
|---------|-------------|---------------|
| Music generation | Suno stub (simulated) | Stable Audio Open / MusicGen on GPU |
| Sound effects | SimulatedSFXProvider | Stable Audio / AudioCraft |
| Lip sync | SimulatedLipSyncProvider | Wav2Lip / SadTalker on GPU |
| Voice training | Simulation only | XTTS/RVC fine-tuning pipeline |
| Video editing (ffmpeg) | Simulated no-ops | FFmpeg on GPU worker |
| GPU metrics | Hardcoded fake values | nvidia-smi via SSH on active worker |
| Social publishing | Webhook stub | Platform-specific OAuth + APIs |
| Talent import | Toast "coming soon" | Backend CSV/JSON import endpoint |

## Priority for Removal

1. **Remove dead endpoints** — they confuse the codebase
2. **Default to real providers** — change defaults from "simulation" to "comfyui"/"elevenlabs" when keys are present
3. **Make simulation explicit** — when simulation is used, show a banner in the UI: "⚠️ Simulated — no GPU worker connected"
