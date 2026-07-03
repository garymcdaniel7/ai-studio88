# AI Studio — AI Brain

> Priority 8.5. The Creative Operating System.

---

## Overview

The AI Brain is the central orchestration layer. Users speak naturally;
the Brain plans, delegates to modules, and responds with reasoning.

```
User: "Create Melissa in Dubai"
         │
    ┌────▼────────────────────────────────────────────┐
    │                AI Brain                           │
    │                                                   │
    │  1. Parse intent                                 │
    │  2. Load context (memory, DNA, history)          │
    │  3. Identify required modules                    │
    │  4. Build execution plan                         │
    │  5. Estimate time + cost                         │
    │  6. Return plan with reasoning                   │
    └────┬────────────────────────────────────────────┘
         │
    Plan: Creative Session → Generation Engine → Asset Registration
```

---

## Key Concepts

| Concept | Purpose |
|---|---|
| Module Registry | Every subsystem registers capabilities |
| Execution Planner | Breaks requests into ordered task lists |
| Conversation Memory | Remembers session context |
| Production Memory | Learned preferences over time |
| Reasoning | Every decision is explainable |

---

## Module Registry (15 modules)

Creative Session, Story Engine, Generation Engine, Video Studio,
Voice Studio, Performance Engine, Production Studio, Model Manager,
Training Manager, Worker Manager, Publishing Engine, Creator OS,
Autonomous Studio, Asset Manager, Creative DNA

---

## API Endpoints (8)

| Method | Path | Description |
|---|---|---|
| POST | `/brain/chat` | Primary conversational interface |
| POST | `/brain/plan` | Create plan without chat context |
| GET | `/brain/sessions` | List sessions |
| GET | `/brain/sessions/{id}` | Get session with history |
| GET | `/brain/context` | What the Brain knows about |
| GET | `/brain/memory` | Production preferences |
| PUT | `/brain/memory` | Update preferences |
| GET | `/brain/modules` | Registered modules |
| GET | `/brain/reasoning/{plan_id}` | Why a plan was created |

---

## Chat Example

```bash
curl -X POST http://localhost:8000/api/v1/brain/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Create Melissa in Dubai"}'

# Returns:
{
  "session_id": "abc123",
  "response": "I'll handle this with 3 steps across 2 modules...",
  "plan": {
    "tasks": [...],
    "reasoning": "Starting with creative analysis → Visual content detected → Generation Engine",
    "modules_involved": ["Creative Session", "Generation Engine"]
  },
  "recommendations": [{"type": "model", "title": "Recommended: FLUX.1-dev", ...}]
}
```

---

## Design Principles

- The Brain plans. Workers execute.
- Every recommendation is explainable.
- All modules are independently replaceable.
- No heavy compute in the Brain.
- Provider-agnostic (supports future LLMs: OpenAI, Claude, Gemini, Ollama, etc.)
- Mobile-ready APIs (same interface for web, iOS, Android)

---

## Files

| File | Purpose |
|---|---|
| `backend/brain/__init__.py` | Package |
| `backend/brain/registry.py` | Module registration (15 modules) |
| `backend/brain/planner.py` | Execution plan builder |
| `backend/brain/memory.py` | Conversation + production memory |
| `backend/brain/router.py` | API endpoints |
| `docs/sql/013_brain.sql` | Database tables |
