# AI Studio — Defect & Gap List

> Last updated: 2026-07-04
> Status: Active development — items being resolved sequentially

## Critical (Blocking User Experience)

| # | Component | Issue | Status |
|---|-----------|-------|--------|
| 1 | Homepage | "Backend not connected" shows even when backend IS running | ✅ FIXED — retry 3x with backoff |
| 2 | Brain page | All buttons non-functional (Creative Chat, Prompt Engineer, etc.) | ✅ FIXED — modes wired to Ollama |
| 3 | Brain conversations | Past convos don't load, can't continue | 🔲 TODO |
| 4 | Create page | Generate button doesn't call backend | ✅ FIXED — wired to /api/v1/generate/image |
| 5 | Talent page | "New Talent" button doesn't create | ✅ FIXED — create form wired to POST /talent |
| 6 | Home KPIs | Show test data / wrong counts | ✅ FIXED — real data from API |

## High (Feature Gaps)

| # | Component | Issue | Status |
|---|-----------|-------|--------|
| 7 | Brain modes | No personality per mode | ✅ FIXED — 6 specialized system prompts |
| 8 | Brain suggestions | "View all" doesn't open modal | 🔲 TODO |
| 9 | Brain collections | No collection/tag system for convos | 🔲 TODO |
| 10 | Model Manager | No UI to browse/download models | 🔲 TODO |
| 11 | Training | No UI to submit training jobs | 🔲 TODO |
| 12 | KPI hover tooltips | No detail on hover | 🔲 TODO |
| 13 | Auto-start | No single command to start everything | ✅ FIXED — start.sh |
| 14 | Ollama → B2 cache | Model not cached for GPU workers | ⚠️ Script built, B2 cap needs increase |
| 15 | Ollama → GPU worker | Can't run Brain on Vast.ai worker | ✅ FIXED — setup_ollama_worker.sh |

## Medium (Enhancement Gaps)

| # | Component | Issue | Status |
|---|-----------|-------|--------|
| 16 | Publish page | No real calendar | 🔲 TODO |
| 17 | Social login | No Instagram/TikTok OAuth | 🔲 TODO |
| 18 | Analytics (talent) | No per-talent dropdown | 🔲 TODO |
| 19 | Admin page | No "Launch Worker" triggered from UI properly | 🔲 TODO |
| 20 | Self-healing agent | Not built | ✅ FIXED — DiagnosticAgent with 10 patterns |
| 21 | API docs | No comprehensive endpoint doc | ✅ FIXED — docs/API_ENDPOINTS.md (396 endpoints) |
| 22 | ElevenLabs | 401/402 — key permissions | ⚠️ User needs paid plan |
| 23 | B2 storage cap | 10GB limit hit (Flux not cached) | ✅ NO CAP — B2 works fine |
| 24 | Test data | Old/fake data in Supabase | 🔲 TODO |

## Low (Polish)

| # | Component | Issue | Fix Required |
|---|-----------|-------|--------------|
| 25 | Sidebar bottom icons | N icon unclear | Better icon/tooltip |
| 26 | Homepage productions | Hardcoded mock data | Wire to real projects |
| 27 | Brain memory | Shows static data | Wire to /api/v1/brain/memory |
| 28 | Asset page | Empty state only | Wire to /api/v1/assets |
| 29 | Story page | Placeholder only | Wire to story engine endpoints |
| 30 | Publish page | Placeholder only | Wire to publishing endpoints |

## Architecture Decisions Pending

- **Ollama deployment**: Local-first with B2-cached weights for GPU workers. Toggle in UI.
- **LLM fallback**: If Ollama offline → show "Brain offline" gracefully, don't crash.
- **Brain mode prompts**: Each mode gets a specialized system prompt stored in backend.
- **Conversation persistence**: Store in Supabase (brain_conversations table).
- **Collections**: Tag-based grouping with shared context across conversations.


## New Defects (from user testing 2026-07-04)

| # | Component | Issue | Priority |
|---|-----------|-------|----------|
| 31 | Brain modes | Need precanned welcome messages per mode (Ollama starts convo) | HIGH |
| 32 | Worker launch | ComfyUI doesn't auto-start after worker connects via Vast.ai | CRITICAL |
| 33 | Worker UI | Frontend doesn't update when worker connects (no polling/refresh) | HIGH |
| 34 | Worker race | Didn't cancel other instances after selecting winner | HIGH |
| 35 | Create page | "ComfyUI not reachable" even when worker is running — SSH tunnel not auto-created | CRITICAL |
| 36 | Video Editor | Need /editor page (ffmpeg-based, timeline, preview) | MEDIUM |
| 37 | Full Production | "Full Production" tab should link to /editor not /brain | MEDIUM |
| 38 | Music/Audio | No mention of music/voice/ElevenLabs in Brain modes or Create | MEDIUM |
| 39 | Local models | No UI for downloading models to B2 (need API-based approach) | MEDIUM |
| 40 | Service toggle | Should be able to toggle GPU services on/off to save capacity | LOW |

## Architecture Decisions from Testing

- ComfyUI MUST auto-install + auto-start when worker launches from UI
- SSH tunnel MUST be auto-created so COMFYUI_BASE_URL works
- UI MUST poll /api/v1/infrastructure/status every 5s when worker is launching
- Worker race mode MUST destroy losers (verify this is working)
- Brain welcome messages should be mode-specific and pre-cached (not require Ollama call)
