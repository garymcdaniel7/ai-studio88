# AI Studio — Creative Session

> Sprint 6. The AI-guided content creation experience.

---

## Overview

The Creative Session replaces technical configuration with natural language.
Instead of asking users to set prompts, models, and GPU settings upfront,
it guides them through a conversational flow and generates a production plan
powered by the Intelligence Layer.

---

## User Flow (6 Stages)

```
┌────────────────────────────────────────────────────────┐
│  Stage 1: WHO                                          │
│  Select talent, project, campaign, platform            │
├────────────────────────────────────────────────────────┤
│  Stage 2: WHAT                                         │
│  Choose content type (image, video, carousel, etc.)    │
├────────────────────────────────────────────────────────┤
│  Stage 3: DESCRIBE                                     │
│  Natural language idea ("luxury hotel in Dubai")       │
├────────────────────────────────────────────────────────┤
│  Stage 4: INTELLIGENCE PANEL                           │
│  5 agents provide recommendations                     │
├────────────────────────────────────────────────────────┤
│  Stage 5: PRODUCTION PLAN                              │
│  Prompt, workflow, estimates, expected outputs         │
├────────────────────────────────────────────────────────┤
│  Stage 6: LAUNCH                                       │
│  Create job/workflow → execute via backend             │
└────────────────────────────────────────────────────────┘
```

---

## Intelligence Panel

Five recommendation providers produce contextual suggestions:

| Agent | What it provides |
|---|---|
| Creative Director | Scene composition, platform tips, brand alignment |
| Prompt Engineer | Optimized prompt, negative prompt, motion descriptions |
| Workflow Optimizer | Recommended workflow steps (generate → fix → upscale) |
| Model Expert | Model/LoRA selection, VRAM requirements |
| GPU Optimizer | Provider routing, cost/time estimates |

Each recommendation has a **confidence score** (🟢 high, 🟡 medium, 🔴 low).

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────────────┐
│  Creative Session   │     │  backend/intelligence.py      │
│  (Streamlit page)   │────►│                              │
│                     │     │  RecommendationProvider (ABC) │
│  Stages 1-3:       │     │    ├─ SimulatedCreativeDirector│
│    collect context  │     │    ├─ SimulatedPromptEngineer │
│                     │     │    ├─ SimulatedWorkflowOptimizer│
│  Stage 4:          │     │    ├─ SimulatedModelExpert    │
│    intelligence     │     │    └─ SimulatedGPUOptimizer  │
│                     │     │                              │
│  Stage 5:          │     │  build_production_plan()      │
│    production plan  │     │    → prompt, workflow, cost   │
│                     │     │                              │
│  Stage 6:          │     └──────────────────────────────────┘
│    create job       │                    │
│         │           │                    │
└─────────┼───────────┘                    │
          │                                │
          ▼                                ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (/api/v1)                    │
│  POST /workflows → POST /workflows/{id}/run             │
│  POST /jobs                                              │
└─────────────────────────────────────────────────────────┘
```

---

## Provider Interface

```python
class RecommendationProvider(ABC):
    @property
    @abstractmethod
    def agent_name(self) -> str: ...

    @abstractmethod
    def recommend(self, context: CreativeContext) -> list[Recommendation]: ...
```

**To add a real LLM agent**, implement this interface:

```python
class LLMCreativeDirector(RecommendationProvider):
    def __init__(self, llm_client):
        self.llm = llm_client  # GPT, Claude, OpenRouter, local

    @property
    def agent_name(self) -> str:
        return "Creative Director"

    def recommend(self, context: CreativeContext) -> list[Recommendation]:
        response = self.llm.chat(
            system="You are a creative director for AI influencer content...",
            user=f"Talent: {context.talent_name}. Idea: {context.user_idea}. Platform: {context.platform}.",
        )
        return [Recommendation(agent=self.agent_name, title="Direction", content=response)]
```

Then register it:
```python
RECOMMENDATION_PROVIDERS = [
    LLMCreativeDirector,    # replaces SimulatedCreativeDirector
    SimulatedPromptEngineer,
    ...
]
```

---

## Content Types Supported

| Type | Description |
|---|---|
| image | Single generated image |
| video | Short-form video clip (5-15s) |
| carousel | Multiple images for swipe galleries |
| story | Vertical format for Instagram/TikTok stories |
| reel | Short vertical video with motion |
| talking_head | AI talent speaking (voice + lip sync) |
| ad | Commercial/advertising content |
| campaign | Multi-asset campaign package |

---

## How Jobs Are Created

**Single-step content** (image): Creates one job via `POST /api/v1/jobs`

**Multi-step content** (image with face-fix + upscale): Creates a workflow via
`POST /api/v1/workflows` then executes via `POST /api/v1/workflows/{id}/run`

The Creative Session never bypasses the API — it uses the same endpoints
as any other client.

---

## Future: LLM Integration

| Provider | Integration Point |
|---|---|
| OpenAI GPT-4o | Creative Director, Prompt Engineer |
| Anthropic Claude | Creative Director (alternative) |
| OpenRouter | Multi-model routing |
| Local LLMs (Ollama) | Development, cost-free iterations |

LLM provider configured via `.env`:
```
AI_PROVIDER=openai          # openai | anthropic | openrouter | local
AI_MODEL=gpt-4o
AI_API_KEY=sk-...
```

---

## Future: Memory and Learning

As the Learning Engine (Sprint 5 architecture) is implemented:

- Previous successful prompts for a talent influence new suggestions
- Style preferences auto-update based on ratings
- The Creative Director remembers past briefs
- Workflow Optimizer learns which steps improve quality for each talent

---

## Running the Creative Session

```bash
# Terminal 1: Backend
uv run uvicorn backend.main:app --reload

# Terminal 2: Dashboard
uv run streamlit run dashboard/app.py

# Navigate to: ✨ Creative Session in sidebar
```

---

## Files

| File | Purpose |
|---|---|
| `backend/intelligence.py` | Recommendation providers + interfaces |
| `dashboard/pages/7_Creative_Session.py` | Streamlit UI (6 stages) |
| `docs/CREATIVE_SESSION.md` | This documentation |
