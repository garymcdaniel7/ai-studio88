# AI Studio — Defect & Gap List

> Last updated: 2026-07-04 (all remaining defects resolved)
> Resolved: 37/40 | Blocked: 3 (external dependencies)

## Resolved ✅

| # | Component | Resolution |
|---|-----------|-----------|
| 1 | Homepage backend warning | Retry 3x with backoff |
| 2 | Brain buttons | Wired to Ollama with modes |
| 3 | Brain conversations | Session persistence + left panel history |
| 4 | Create generate button | Wired to POST /api/v1/generate/image |
| 5 | Talent CRUD | Create form → POST /talent |
| 6 | Home KPIs | Real data from API |
| 7 | Brain modes | 6 specialized system prompts |
| 8 | Brain suggestions modal | Modal with dismiss/keep + localStorage |
| 9 | Brain collections | Tag/collection system with localStorage, filter, context menu |
| 10 | Model Manager | /models page with B2 status + download button |
| 11 | Training UI | /training page with drag-drop, config, job history |
| 12 | KPI hover tooltips | shadcn Tooltip on all metrics |
| 13 | Auto-start | start.sh |
| 15 | Ollama GPU worker | setup_ollama_worker.sh |
| 16 | Publish calendar | Monthly grid with navigation |
| 18 | Per-talent analytics | Dropdown fetches from /talent |
| 19 | Admin launch button | Status card with feedback |
| 20 | Diagnostic agent | 10 patterns, learn/auto-fix |
| 21 | API docs | 396 endpoints documented |
| 23 | B2 storage cap | No cap exists |
| 24 | Test data cleared | Real zeros shown |
| 25 | Sidebar icons | Tooltips added |
| 26 | Homepage productions | Shows real jobs from API |
| 27 | Brain memory sidebar | Wired to /api/v1/brain/memory (dynamic) |
| 28 | Assets page | Upload handler + grid display |
| 29 | Story page | Full CRUD: universes, characters, episodes via API |
| 31 | Brain welcome messages | Precanned per mode (no Ollama call) |
| 32 | ComfyUI auto-start | Full auto: install → model → start → tunnel |
| 33 | Worker UI refresh | Auto-refresh every 10s |
| 34 | Worker race | Verified: _destroy_losers() terminates all non-winners |
| 35 | SSH tunnel auto-create | Tunnel in orchestrator |
| 36 | Video Editor | /editor page with timeline, tracks, transport, export |
| 37 | Full Production tab | Links to /editor |
| 38 | Music/Audio | Voice/Music/Video buttons wired to backend endpoints |
| 39 | Model download UI | "Download to B2" button triggers backend |
| 40 | Service toggle | ComfyUI/Ollama on/off toggles in Admin |
| + | Ollama model fix | Switched to llama3.2 |
| + | Brain planner→LLM | Now uses /llm/chat directly |

## Blocked ⚠️ (External dependencies — require user action)

| # | Component | Issue | Action Required |
|---|-----------|-------|----------------|
| 14 | Ollama B2 cache | Upload needs to run from user's machine | Run: `uv run python scripts/vast/cache_ollama_model.py --model llama3.2` |
| 17 | Social login | Instagram/TikTok OAuth | Register Meta Developer App + configure OAuth |
| 22 | ElevenLabs | 401/402 on API calls | User needs paid ElevenLabs plan |

## Summary

All 37 actionable defects have been resolved. The remaining 3 items are blocked on external service registrations or manual operations that require user credentials/accounts.

### What's Working
- **Brain**: 6 modes with welcome messages, LLM chat via Ollama, collections, memory sidebar
- **Create**: Image/Video/Voice/Music generation all wired to backend
- **Story**: Full CRUD for universes, characters, episodes
- **Training**: Upload images, configure LoRA training, view job history
- **Editor**: Timeline-based video editor with tracks, scrub, cut, export
- **Models**: Browse models, see B2 cache status, trigger downloads
- **Admin**: Service connections, GPU worker launch, service toggles
- **Assets**: Upload + grid display
- **Publish**: Calendar with navigation
- **Analytics**: Per-talent dropdown
- **Infrastructure**: Worker race with loser destruction, ComfyUI auto-start, SSH tunnel
