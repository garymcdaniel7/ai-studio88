# AI Studio — Product Vision (Updated July 2026)

## What AI Studio Is

AI Studio is a **commercial multi-tenant SaaS platform** for AI-powered content production at scale. It orchestrates the entire lifecycle: persona creation → identity training → content generation → production assembly → multi-platform publishing.

Unlike point tools (KLING, Runway, Midjourney), AI Studio is a **full production operating system** — the creative team doesn't just generate one image, they produce entire campaigns with consistent characters, brand voice, and automated workflows.

## Core Architecture (Production)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js 16)                        │
│  Home · Brain · Create · Editor · Talent · Assets · Models · Admin  │
└────────────────────────────────────┬────────────────────────────────┘
                                     │ REST API
┌────────────────────────────────────┴────────────────────────────────┐
│                     BACKEND (FastAPI, 310+ endpoints)                 │
│                                                                      │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌────────────┐            │
│  │ Brain   │ │ Generate │ │ Training  │ │ Publishing │            │
│  │ (LLM)  │ │ (ComfyUI)│ │ (LoRA)    │ │ (Social)   │            │
│  └─────────┘ └──────────┘ └───────────┘ └────────────┘            │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌────────────┐            │
│  │ Infra   │ │ Object   │ │ Asset     │ │ Company    │            │
│  │ (GPU)   │ │ Intel    │ │ Intel     │ │ OS         │            │
│  └─────────┘ └──────────┘ └───────────┘ └────────────┘            │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
┌──────────────┐  ┌────────────────┐ │ ┌──────────────┐
│   Supabase   │  │  Backblaze B2  │ │ │  GPU Workers │
│  (Database)  │  │   (Storage)    │ │ │ (Vast/RunPod)│
└──────────────┘  └────────────────┘   └──────────────┘
```

## What's Working Today (July 4, 2026)

### Generation Pipeline
- **Image Generation** via ComfyUI (Flux Dev, SDXL Turbo, SD 1.5)
- **Video Generation** via WAN 2.1 (text-to-video, image-to-video)
- **Voice Generation** via ElevenLabs (TTS, clone)
- **Music Generation** (simulated, Suno integration planned)
- **GPU Workers** on Vast.ai + RunPod with Connection Race Mode

### Talent System
- Full CRUD with Creative DNA (visual style, persona, trigger words)
- Multi-photo upload for training data
- LoRA association (identity + always-on style LoRAs)
- Dynamic type system (model, character, voice, wardrobe, background)
- Avatar/hero image with hover-to-change
- DNA auto-injection into generation prompts

### Storyboard Sequencer
- Shot planning with drag-reorder
- Per-shot model/duration/camera/transition/aspect settings
- Talent DNA injection (select talent → auto-enrich prompts)
- Save/load storyboards to/from database
- Batch generation + video assembly

### Model Management
- Upload models (.safetensors, .ckpt) to B2 + registry
- LoRA-specific flow (trigger words, base model, strength)
- ComfyUI path mapping (auto-assigns worker paths)
- "Free GPU Space" / "Re-upload to GPU" workflow
- Model deduplication

### AI Brain
- 6 specialized modes (Creative, Prompt Engineer, Story, Production, Research, Image Analyzer)
- Mode-specific welcome messages
- Conversation persistence (localStorage + backend sessions)
- Collections & tagging
- Brain memory (preferences learned over time)
- Share conversations (copy, email, SMS, download)
- Memory & suggestions expand modals

### Infrastructure
- Dual GPU provider (Vast.ai + RunPod)
- Auto-reconnect on backend restart
- Connection Race Mode (parallel boot, first SSH wins)
- Provider reputation learning
- Cost intelligence tracking
- Render fleet (multi-worker parallel)
- Diagnostic agent (self-healing)

### Admin & Config
- API Keys page (persist to .env, show connection status)
- Service connections dashboard
- Multi-provider GPU balance display
- Service toggle (ComfyUI/Ollama on/off)

### AI Auto-Fix (Code Quality)
- Pattern-based fixer (Tier 1: lint rules)
- LLM-assisted fixer (Tier 2: via Ollama)
- POST /api/v1/brain/fix endpoint

## Competitive Positioning

| Feature | AI Studio | KLING | Runway | Midjourney |
|---------|-----------|-------|--------|------------|
| Image generation | ✅ | ✅ | ✅ | ✅ |
| Video generation | ✅ | ✅ | ✅ | ❌ |
| Character consistency (LoRA) | ✅ | ❌ | ❌ | ❌ |
| Multi-talent management | ✅ | ❌ | ❌ | ❌ |
| Storyboard → Production | ✅ | ❌ | ❌ | ❌ |
| Creative DNA / Identity lock | ✅ | ❌ | ❌ | ❌ |
| Multi-platform publishing | ✅ | ❌ | ❌ | ❌ |
| Own infrastructure (BYOG) | ✅ | ❌ | ❌ | ❌ |
| AI Brain co-pilot | ✅ | ❌ | ❌ | ❌ |
| Multi-tenant SaaS | ✅ | ❌ | ❌ | ❌ |
| Object intelligence | ✅ | ❌ | ❌ | ❌ |
| Cost per image | $0 (own GPU) | $$$ | $$$ | $$ |

## What's Next (Priority Order)

### Phase 1: Production Readiness (2-3 weeks)
1. Authentication + tenant isolation (security critical)
2. Background job system (Celery/Redis for async training/generation)
3. Real-time progress (WebSocket for generation status)
4. Worker session persistence (survive restarts)

### Phase 2: Feature Surface (2-3 weeks)
5. Publishing workflow UI (scheduling + approval + multi-platform)
6. Company OS UI (brands, campaigns, clients)
7. Object Intelligence UI (product photography, virtual try-on)
8. Asset Intelligence UI (visual DNA, presets, recommendations)

### Phase 3: Scale (ongoing)
9. Autonomous Studio (AI departments, brief-to-production)
10. Celery workers for training + generation queue
11. Social API integrations (Instagram, TikTok, YouTube)
12. Multi-user onboarding flow + billing

## Business Model

- Self-hosted: Users bring their own GPU (Vast.ai/RunPod accounts)
- SaaS: Platform fee + pass-through GPU costs
- Per-org: strict data isolation, quota enforcement
- Pricing tiers: Starter (1 talent, 100 gen/mo) → Pro (unlimited) → Enterprise (custom)
