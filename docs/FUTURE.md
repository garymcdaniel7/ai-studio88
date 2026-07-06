# Future — Deferred Features & Architecture Decisions

Items discussed but intentionally deferred. Revisit when the trigger condition is met.

---

## Workflow Template Engine (Refactor)

**What**: Replace the hardcoded `if/elif` workflow builder in `generate.py` with a template-based system. Workflow JSON templates stored per model family (SDXL, Flux 1, Flux 2, WAN, Hunyuan). New models auto-route to their family's template by filename injection.

**Why deferred**: Only 4-5 active models today. Adding a new model takes 5 minutes of code. The if/elif chain is simple and works.

**Trigger to build**: When onboarding users who upload their own models (CivitAI, HuggingFace) and expect them to work without developer intervention. Or when model count exceeds ~15.

**Architecture notes**:
- 6 families cover 95% of models: SD1.5, SDXL, Flux1, Flux2, WAN, Hunyuan
- Template = JSON with `__PLACEHOLDER__` strings for model filename, prompt, dimensions
- Model registry stores `family` field → maps to template
- LoRAs/ControlNets are additive nodes injected into any template
- "Unknown family" fallback: let user paste raw ComfyUI workflow JSON (power user mode)

---

## Multi-Tenant Onboarding

**What**: Per-org data isolation, user management, role-based access, billing per org.

**Why deferred**: Solo builder right now. Platform needs to be 100% functional before inviting others.

**Trigger to build**: When ready to onboard first external user/team.

**Architecture notes**:
- Supabase RLS policies already exist (org_id on every table)
- JWT contains org_id claim
- Need: invite flow, org creation, role assignment UI
- Need: per-org billing (track GPU costs per org)

---

## Workflow Visualizer (Mini Node Graph)

**What**: Visual representation of the ComfyUI pipeline in the UI. Shows nodes connected with arrows. Users can see what's happening and potentially add/configure nodes visually.

**Why deferred**: Complex UI component. Current text-based settings work fine for generation.

**Trigger to build**: When users ask "what's happening under the hood" or want fine-grained control beyond presets.

**Architecture notes**:
- Read-only visualization first (show the workflow that will be submitted)
- Use React Flow or similar for node rendering
- Each node shows: type, key setting, status (loading/done)
- Phase 2: click a node to edit its settings inline
- Phase 3: add/remove nodes (drag-and-drop workflow builder)

---

## XTTS (Local Voice Cloning)

**What**: Coqui XTTS running on GPU worker for free, unlimited voice cloning. Complements ElevenLabs (paid, high quality) with a local option.

**Why deferred**: ElevenLabs working well. XTTS adds complexity (model download, GPU memory sharing).

**Trigger to build**: When ElevenLabs costs become a concern, or when voice cloning (custom voices from samples) is needed.

**Architecture notes**:
- Install on GPU worker alongside ComfyUI
- Separate port (e.g., 8199)
- Voice cloning: upload 10s audio sample → creates voice profile
- Provider pattern: same interface as ElevenLabs, user picks which to use

---

## Suno Music Generation

**What**: AI music generation via Suno API. Similar pattern to ElevenLabs — API key, submit prompt, get audio back.

**Why deferred**: Need Suno API key. Lower priority than image/video/voice.

**Trigger to build**: When user has Suno API access and wants music in production pipeline.

**Architecture notes**:
- Copy ElevenLabs provider pattern
- POST prompt + style/genre → returns audio URL
- Store in B2, register as asset
- Wire into Create page "Audio" tab alongside voice

---

## Per-Org Billing & Quotas

**What**: Track GPU costs per organization, enforce monthly limits, usage dashboards.

**Why deferred**: Single user. Cost tracking exists but not per-org.

**Trigger to build**: Multi-tenant launch.

---

## Advanced Sampler Exposure

**What**: Let users pick sampler (euler, dpmpp_2m, etc.) and scheduler from the Create page advanced panel.

**Why deferred**: Current defaults work well per model. Exposing this confuses non-technical users.

**Trigger to build**: When power users request it, or when specific use cases need specific samplers.

---

## RunPod Persistent Volumes for Training

**What**: Use RunPod's persistent volumes to keep SimpleTuner installed across sessions (no reinstall on each training run).

**Why deferred**: Current Vast.ai SSH flow works. Reinstall takes <2 min.

**Trigger to build**: When training runs become frequent enough that setup time matters.

---

## Real-Time Generation Progress (WebSocket)

**What**: Live progress updates during generation (current step, ETA, preview at 50%).

**Why deferred**: Polling works. Generation is fast enough (4-17s for images) that progress isn't critical.

**Trigger to build**: Video generation (5-50 min) makes progress essential. Or when multiple users are queuing jobs.

**Architecture notes**:
- ComfyUI supports WebSocket for progress
- Backend could proxy WS from ComfyUI to frontend
- Or: Supabase Realtime channel per job

---

## Content Moderation / Safety Filters

**What**: Pre-generation prompt filtering, post-generation NSFW detection.

**Why deferred**: Solo user, not needed for personal use.

**Trigger to build**: Before any public/multi-user deployment.

---

*Last updated: 2026-07-05*
