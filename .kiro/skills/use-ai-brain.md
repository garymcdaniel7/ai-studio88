# Skill: Use AI Brain

## Purpose
Interact with the AI Brain for creative planning, prompt engineering, and production advice.

## Provider Configuration
```env
BRAIN_PROVIDER=ollama          # ollama | openai | anthropic
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

## Check Brain Health
```bash
curl http://localhost:8000/api/v1/brain/health
```

## Direct LLM Chat
```bash
curl -X POST http://localhost:8000/api/v1/brain/llm/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Help me create a luxury watch commercial"}'
```

## Brain Chat (with planning)
```bash
curl -X POST http://localhost:8000/api/v1/brain/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Create Melissa in a Dubai luxury campaign"}'
```

## Brain Modes
Each mode has a specialized system prompt:
- **Creative Chat** — General creative brainstorming
- **Prompt Engineer** — Optimize prompts for SDXL/Flux/WAN
- **Story Assistant** — Develop narratives, scripts, arcs
- **Production Advisor** — Plan workflows, estimate costs
- **Research** — Find references, summarize info
- **Image Analyzer** — Describe images, suggest improvements

## Starting Ollama
```bash
brew install ollama
ollama serve
ollama pull llama3.1:8b
```

## Brain Architecture
- `backend/brain/llm_provider.py` — Multi-provider LLM client
- `backend/brain/router.py` — API endpoints
- `backend/brain/planner.py` — Execution plan builder
- `backend/brain/memory.py` — Conversation + production memory
- `backend/brain/registry.py` — Module registry
