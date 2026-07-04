# AI Studio — Defect & Gap List

> Last updated: 2026-07-04
> Status: Active development — items being resolved sequentially

## Critical (Blocking User Experience)

| # | Component | Issue | Fix Required |
|---|-----------|-------|--------------|
| 1 | Homepage | "Backend not connected" shows even when backend IS running | Frontend fetch timing + auto-retry. Need startup script. |
| 2 | Brain page | All buttons non-functional (Creative Chat, Prompt Engineer, etc.) | Wire to /api/v1/brain/llm/chat with mode-specific system prompts |
| 3 | Brain conversations | Past convos don't load, can't continue | Wire to /api/v1/brain/sessions/{id} |
| 4 | Create page | Generate button doesn't call backend | Wire to POST /api/v1/generate/image |
| 5 | Talent page | "New Talent" button doesn't create | Wire to POST /talent |
| 6 | Home KPIs | Show test data / wrong counts | Clear test data, wire to real counts |

## High (Feature Gaps)

| # | Component | Issue | Fix Required |
|---|-----------|-------|--------------|
| 7 | Brain modes | No personality per mode | Create system prompts for each mode |
| 8 | Brain suggestions | "View all" doesn't open modal | Build modal with dismiss/keep functionality |
| 9 | Brain collections | No collection/tag system for convos | Backend + UI for tagging conversations |
| 10 | Model Manager | No UI to browse/download models | Build model management page |
| 11 | Training | No UI to submit training jobs | Build training page |
| 12 | KPI hover tooltips | No detail on hover | Add tooltip component showing job name/prompt |
| 13 | Auto-start | No single command to start everything | Create start.sh / admin UI trigger |
| 14 | Ollama → B2 cache | Model not cached for GPU workers | Upload Ollama model weights to B2 |
| 15 | Ollama → GPU worker | Can't run Brain on Vast.ai worker | Script to install+serve Ollama on worker |

## Medium (Enhancement Gaps)

| # | Component | Issue | Fix Required |
|---|-----------|-------|--------------|
| 16 | Publish page | No real calendar | Build calendar component with iCal |
| 17 | Social login | No Instagram/TikTok OAuth | Meta Developer App + OAuth flow |
| 18 | Analytics (talent) | No per-talent dropdown | Add talent selector + per-talent metrics |
| 19 | Admin page | No "Launch Worker" triggered from UI properly | Wire launch button → infrastructure API |
| 20 | Self-healing agent | Not built | Backend diagnostic agent with learning |
| 21 | API docs | No comprehensive endpoint doc | Create docs/API_ENDPOINTS.md |
| 22 | ElevenLabs | 401/402 — key permissions | User needs to create new key with permissions |
| 23 | B2 storage cap | 10GB limit hit (Flux not cached) | User increases cap in Backblaze dashboard |
| 24 | Test data | Old/fake data in Supabase | Clear and start fresh |

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
