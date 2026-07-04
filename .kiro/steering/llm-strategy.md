# LLM Strategy — AI Brain Provider Architecture

## Provider Hierarchy

1. **Local Ollama** (preferred when available)
   - Model: llama3.1:8b (best quality for local)
   - URL: http://localhost:11434
   - Toggle: user can enable/disable in Admin
   - Zero cost, private, fast for short responses

2. **GPU Worker Ollama** (for heavy inference)
   - Same weights cached in Backblaze B2
   - Downloaded to Vast.ai worker on launch
   - For batch processing, long-form content, heavy reasoning
   - Cost: GPU hourly rate

3. **Cloud API Fallback** (OpenAI/Anthropic/OpenRouter)
   - Only when local + GPU both unavailable
   - Or for specific models (GPT-4o, Claude)
   - Requires API key in .env

## Brain Modes (System Prompts)

Each Brain mode has a specialized personality:

- **Creative Chat**: General creative assistant. Brainstorm, ideate, explore.
- **Prompt Engineer**: Optimize prompts for SDXL/Flux/WAN. Technical, specific, keyword-focused.
- **Story Assistant**: Develop narratives, scripts, character arcs. Story structure expert.
- **Production Advisor**: Plan workflows, estimate costs, optimize pipelines. Operations focused.
- **Research**: Search knowledge, find references, summarize findings.
- **Image Analyzer**: Describe images, suggest improvements, extract visual DNA.

## Model Caching Strategy

- Ollama model weights (.gguf) stored in B2 under models/ollama/
- On GPU worker boot: download from B2, install into Ollama
- Script: scripts/vast/setup_ollama_worker.sh
- Auto-start: Ollama serves on port 11434 on the worker

## Integration Points

- Backend: backend/brain/llm_provider.py (multi-provider client)
- API: POST /api/v1/brain/llm/chat (direct LLM call)
- API: POST /api/v1/brain/chat (full Brain pipeline with planning)
- API: GET /api/v1/brain/health (provider status)
- Frontend: Brain page calls these APIs
- Admin: Toggle local/cloud, select model, view health

## Conversation Persistence

- Store in Supabase: brain_conversations, brain_messages tables
- Sessions have tags/collections for organizing
- Conversations can be shared across modes (same context)
- Brain memory persists preferences across sessions
