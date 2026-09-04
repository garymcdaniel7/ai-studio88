# PM Directive — Hermes → Kiro (read this session)

> From: Hermes (PM/Chief of Staff) · Date: 2026-09-03
> Repo: ai-studio88 (main) + lane repos (ai-studio88-*)
> Priority: HIGH — read before other work. Full steering context in
> `ai-studio88/.kiro/steering/` and `AGENTS.md`.

## State (verified, not assumed)

- **Production domain is `ai-studio88.vercel.app`** (ai-studio99 is DEAD — 404).
  Railway backend: `web-production-1f511.up.railway.app`. Supabase project
  `vipmjgglascthwoqqqji`. Google OAuth callback now correct after Gary fixed
  Site URL in Supabase (redirect URLs list contains 88, **not** 99).
- **Real generation is LIVE** on Thunder Compute A6000 (`do5u5dbx`):
  - ComfyUI public: `https://do5u5dbx-8188.thundercompute.net`
  - Ollama brain public: `https://do5u5dbx-11434.thundercompute.net`
    (model: dolphin-llama3:8b) — Brain `ready` at `/ready` (5 models).
  - Verified: flux2-klein 1024² image gen + WAN 2.2 Remix 5s video (832×480, 16fps).
  - 104 LoRAs on worker; `lora_catalog` table seeded with 87 (Supabase).
- **Auth chain now enforced**: `AUTH_REQUIRED=true` on Railway (was missing →
  dev mode). Scaffold auth has Supabase-API fallback for stale JWT secret.
- **All 4 Playwright suites green** (full-stack + auth + OAuth + live public
  surface). Test account: `hermes.uat@aistudio88.dev` (owner role).

## Active workstreams (lane ownership)

1. **Jobs↔project association is BROKEN** — every job row has `project_id: None`
   even though the table supports it. Generating content must attach to the
   project/storyboard the user is in. (Lane: creation/platform)
2. **Home page stats are stale/misleading** — shows 7 "active projects" (real:
   1), 18 jobs are OLD simulation-era jobs (`provider: simulation`,
   `worker_name: vast-worker-1`), $0 GPU spend (correct but confusing). Filter
   simulation jobs; derive counts from real tenant rows. (Lane: platform)
3. **Library asset thumbnails broken** for some tiles (simpletuner training
   outputs, Digen video stills) — DB rows exist but file is missing from B2 or
   signed URL fails. Middle-row PNGs render fine. Diagnose the URL/storage
   path. (Lane: platform)
4. **Vast.ai → Thunder Compute swap** across admin UI + provider registry:
   add a real `ThunderComputeProvider` (backend/app/providers/) implementing
   ComputeProvider protocol; replace Vast labels (15 frontend files reference
   it; settings dropdown lists `vast` as GPU provider). Historical rows keep
   vast-worker names (don't rewrite history), but NEW provisioning + UI labels
   = thundercompute. (Lane: platform/infrastructure)
5. **Fleet Demand Planner** — make it real: wire usage data, GPU cost default
   $0.35/hr (Thunder A6000), allow 2-worker split for parallel/double video,
   model-aware (all LoRAs/models on GPU), add hover tooltips + rule-of-thumb
   interactions. (Lane: platform)
6. **Admin health page** — `/aios/v1/decisions` was 500 (fixed by Hermes,
   commit 754051c — thread org_id from auth). Verify the page is fully green
   now. Worker status shows "unknown / Failed to read worker status" on the
   dashboard — that's the next visible bug (needs real Thunder status reader,
   not Vast). (Lane: platform/infrastructure)

## Backlog (design before build — PM will spec)

- **BYOLLM per tenant**: per-workspace LLM provider settings (gpu-ollama /
  openrouter / local), stored in tenant settings; Brain reads workspace key
  first, falls back to platform default. Gary wants this for every new user.
- **Competitive analytics** (IG/TikTok comparisons) — decide between direct
  Graph API, a third-party service, or Hermes/Brain research lane.
- **Prompt-engineer mode in Brain** — Hermes suggests best prompts per
  model/LoRA; inject generation skills/capabilities into Brain context.
- **New-user onboarding experience test** — what a fresh signup sees vs owner.

## Ground rules

- ai-studio99 is DEAD. Nothing new points at it. Everything = ai-studio88.
- api_v1.py is mutexed; small focused commits; components/** frozen.
- Evidence over claims: verify with tsc/pytest/Playwright before reporting done.
- If this session is in a lane repo (ai-studio88-*), own only that lane's files.
