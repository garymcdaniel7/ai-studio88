# AI Studio — Current-State Assessment (Phase 1)

**Date:** 2026-09-02 · **Author:** Hermes · **Source:** codebase inspection + subagent inventory + live GPU verification
**Directive:** AI Studio consolidation (H3 integration + UI update). Understand what exists, evolve it — do NOT rebuild.

---

## WORKING NOW

- **Git/repo:** `ai-studio88` on `main`, 6 commits ahead of origin, multi-worktree lanes with `AGENTS.md` lane sovereignty rules, `backend/api_v1.py` single-file mutex, `frontend/src/components/**` frozen.
- **Image generation:** FLUX.1-dev (fully wired — generate endpoints, training pipeline, workflows `flux_dev.json` + `flux_text_to_image_basic.json`), FLUX.2-dev + FLUX.2-Klein (wired inline in `infrastructure/generate.py`, frontend default), SDXL-Turbo + SD1.5 (fully wired, docker-deployed).
- **Video generation:** Wan 2.1 (fully wired, 4 workflows), Wan 2.2 (default `wan22_t2v_native` + `wan22_14b_native` + `wan22_remix_nsfw_i2v`), MiniMax H3 **hosted API adapter** (submit→poll→download, full env block), Kling v3/v2.6 (dedicated endpoints).
- **H3 local on Thunder:** ComfyUI 0.33.1, all 4 model files (FL2VA 21GB, Qwen3-VL 15.7GB, video VAE 5.2GB, audio VAE 0.6GB). **T2V test PASSED** — 5.17s clip with native AAC audio, programmatic submission (Hermes → ComfyUI API).
- **GPU stack (Thunder A6000):** Wan Remix 14B high/low restored, 20+ LoRAs restored (fix kit, iGoon, Black content, French kiss 2.2, PENISLORA), H3 live.
- **Tenancy:** Supabase org_id scoping (database.py all CRUD tenant-scoped) + RLS + job_leases. Preserve — do not touch.
- **Storage:** B2 private bucket with signed URLs (path-style). App storage layer still assumes public in places — known gap.
- **Production tools:** Lip sync (AIOS adapter), TTS (ElevenLabs + MOSS), voice clone (XTTS + moss create-voice), music (Suno), video edit (FFmpeg transform + cinematic router + EditingProvider), storyboard.

## PARTIALLY IMPLEMENTED

- **H3 local vs hosted:** local ComfyUI path just proven (this session). Backend only routes H3 via hosted API adapter — needs a local-H3 provider route to use the Thunder box.
- **Wan 2.2 Remix workflow** has NO backend route (`wan22_remix_nsfw_i2v.json` exists in workflows but nothing routes to it).
- **Image upscale:** SimulationHandler placeholder only.
- **Compositing:** interface only + archived `_archive/video_assembly.py`.
- **MCP tools:** generate_image/generate_video/search_talent real; train_lora, schedule_post, estimate_cost, continue_story, get_story_context, recommend_workflow thin/stub.
- **Model registry in UI:** mixed — some models wired, some family-option-only.

## MISSING

- **H3 local provider route** in backend (to use the box programmatically from the app).
- **Thunder Compute wiring** anywhere in backend/providers (only Vast/RunPod paths exist).
- **Frame interpolation** — not found anywhere.
- **H3 workflow JSONs** in workflows/comfyui/ (none exist — I built the API workflow programmatically from live node specs).
- **Remix/H3 LoRA dependency manifests** in job inputs (queue can't know what a job needs).

## REDUNDANT / CANDIDATES (do NOT remove yet — benchmark first per directive)

- **LTX** — capability string only, not wired. Bench vs H3 before deciding.
- **Hunyuan** — provider class exists, no ComfyUI adapter/workflow. Bench vs H3.
- **SD1.5 / SDXL-Turbo** — fully wired but superseded by FLUX for quality; keep only if a use case needs them (speed sketching).
- **FLUX.2-Klein** — hardened (never touches adult lane); keep as clean/fast lane per PIVOT.

## DO NOT TOUCH

- Multi-tenancy, auth (Supabase JWT + org membership), B2 storage layer core.
- All production tools (lip sync, TTS, voice clone, music, edit, storyboard, upscale, compositing).
- `frontend/src/components/**` (frozen); `backend/api_v1.py` (mutex — queue changes through backend lane).
- Kim's clean lane separation, PIVOT.md hard boundaries.

---

## Immediate next actions (per execution order)

1. **PHASE 3-4 ✅** — H3 local proven; add the backend local-H3 provider route.
2. **PHASE 5** — Run image (FLUX vs H3) + video (H3 vs Wan Remix) showdowns with comparable prompts.
3. **PHASE 6-8** — Pick winners; migrate capabilities; remove redundant models only after migration.
4. **PHASE 9-11** — Wire H3 into Audio/Storyboard/Edit lanes; UI update (capabilities not admin console); Message-Hermes flow.
5. **PHASE 12-13** — E2E tests + final report.
