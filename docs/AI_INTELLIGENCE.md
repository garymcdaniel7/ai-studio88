# AI Studio — AI Intelligence Layer Architecture

> Sprint 5 (design phase). This document defines the architecture for AI Studio's
> creative brain — a system of specialized AI agents, feedback loops, and
> recommendation engines that make the platform smarter over time.
>
> **Status:** Architecture only. Not yet implemented.

---

## Design Philosophy

AI Studio does NOT use a single chatbot. Instead, it deploys **specialized agents**
that each excel at one domain. These agents collaborate through a shared context
system and improve through user feedback.

```
┌─────────────────────────────────────────────────────────────────┐
│                   AI Intelligence Layer                           │
│                                                                   │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐ │
│  │   Creative    │ │    Prompt     │ │    Workflow            │ │
│  │   Director    │ │    Engineer   │ │    Optimizer           │ │
│  └───────┬───────┘ └───────┬───────┘ └───────────┬───────────┘ │
│          │                  │                     │              │
│  ┌───────┴───────┐ ┌───────┴───────┐ ┌───────────┴───────────┐ │
│  │    Model      │ │     GPU       │ │    Learning           │ │
│  │    Expert     │ │   Optimizer   │ │    Engine             │ │
│  └───────────────┘ └───────────────┘ └───────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │             Recommendation Engine                            │ │
│  │  prompts │ settings │ workflows │ LoRAs │ models │ routing  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │             Feedback + Memory Store                          │ │
│  │  ratings │ problems │ preferences │ history │ patterns      │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Specifications

### 1. Creative Director

**Purpose:** Elevates creative concepts from vague ideas to production-ready briefs.

| Capability | Description |
|---|---|
| Concept refinement | Takes rough ideas, asks clarifying questions, outputs detailed creative briefs |
| Scene composition | Suggests camera angles, lighting, environment, mood |
| Brand alignment | Ensures outputs match a talent's established visual identity |
| Art direction | Recommends colour palettes, styling, poses, expressions |
| Campaign coherence | Maintains visual consistency across a content series |

**Inputs:**
- User's rough concept (text)
- Talent profile (from DB)
- Brand guidelines (from DB)
- Historical outputs the user liked (from feedback store)

**Outputs:**
- Refined creative brief (structured JSON)
- Suggested scene description
- Recommended style tags
- Confidence score

**Integration point:** Called before Prompt Engineer to produce better raw material.

---

### 2. Prompt Engineer

**Purpose:** Converts creative briefs into model-specific, optimized prompts.

| Capability | Description |
|---|---|
| Model-aware prompts | Generates syntax appropriate for Flux, WAN, Hunyuan, SDXL |
| LoRA integration | Injects trigger words, adjusts prompt structure for LoRA compatibility |
| Prompt weighting | Uses `(word:1.3)` syntax, attention manipulation, BREAK tokens |
| Negative prompts | Generates model-appropriate negative prompts |
| ComfyUI node awareness | Knows which prompt fields map to which ComfyUI nodes |
| Iterative refinement | Adjusts prompts based on feedback from previous generations |

**Model-specific adaptations:**

```
Flux:    Natural language style, no negative prompt needed, 
         emphasis via repetition/context
WAN:     Frame-by-frame motion descriptions for video
Hunyuan: Chinese/English bilingual prompt support
SDXL:    Tag-based, comma-separated, (weight:1.x) syntax
ComfyUI: Node-specific text fields, clip_l vs clip_g separation
```

**Inputs:**
- Creative brief (from Creative Director or raw user input)
- Target model identifier
- LoRA references (from model registry)
- Style preferences (from user history)

**Outputs:**
- Optimized positive prompt
- Negative prompt (when applicable)
- Prompt metadata (weight map, trigger words used)
- Alternative prompt variations

---

### 3. Workflow Optimizer

**Purpose:** Designs and improves multi-step generation workflows.

| Capability | Description |
|---|---|
| Step recommendation | Suggests steps the user hasn't considered (face fix, upscale, colour grade) |
| Order optimization | Rearranges steps for quality/speed balance |
| Template matching | Recommends pre-built workflow templates for common tasks |
| Dependency analysis | Identifies which steps can run in parallel |
| Cost estimation | Estimates GPU time and cost for the full workflow |

**Inputs:**
- User's desired output description
- Available handlers (from JOB_HANDLERS registry)
- Historical workflow performance (from feedback store)
- GPU cost data

**Outputs:**
- Recommended workflow steps (ready for `POST /api/v1/workflows`)
- Estimated duration and cost
- Explanation of why each step was included

---

### 4. Model Expert

**Purpose:** Recommends the best models, LoRAs, and settings for a task.

| Capability | Description |
|---|---|
| Checkpoint selection | Recommends base model (Flux dev, SDXL, RealVis, etc.) |
| LoRA strength | Suggests optimal LoRA weight (0.0-1.0) based on training quality |
| ControlNet/IPAdapter | Recommends reference image approaches for consistency |
| Model compatibility | Warns about incompatible LoRA/checkpoint combinations |
| Quality vs speed | Trade-off recommendations (steps, CFG, sampler) |

**Knowledge base:**
- Model metadata registry (stored in Supabase)
- LoRA training parameters (from training job history)
- Community best practices (periodically updated)

**Inputs:**
- Task type (portrait, landscape, video, etc.)
- Available models in the system
- Quality requirements
- Time/cost constraints

**Outputs:**
- Recommended checkpoint
- LoRA selections with strengths
- Sampler/scheduler recommendations
- Step count and CFG suggestions

---

### 5. GPU Optimizer

**Purpose:** Routes jobs to the optimal compute resource.

| Capability | Description |
|---|---|
| Resource matching | Maps job VRAM requirements to available GPUs |
| Cost optimization | Routes to cheapest provider meeting requirements |
| Latency optimization | Routes to fastest available instance for urgent jobs |
| Provider arbitrage | Compares Vast.ai, RunPod, local GPU, Shadow PC pricing |
| Queue awareness | Considers current queue depth per provider |

**Routing decision matrix:**

| Job Type | Min VRAM | Preferred Provider | Fallback |
|---|---|---|---|
| image_generation (Flux) | 24 GB | Vast.ai RTX 4090 | RunPod A100 |
| image_generation (SDXL) | 12 GB | Local GPU / Shadow PC | Vast.ai RTX 3090 |
| video_generation (WAN) | 24 GB | Vast.ai A100 | RunPod A100 |
| lora_training | 24 GB | Vast.ai A100 (spot) | RunPod A100 |
| image_upscale | 8 GB | Local GPU | Vast.ai cheapest |

**Inputs:**
- Job type and parameters
- Current provider availability and pricing
- Job priority level
- User's cost preferences

**Outputs:**
- Recommended provider + GPU type
- Estimated cost
- Estimated wait time
- Alternative options with trade-offs

---

### 6. Learning Engine

**Purpose:** Improves all agents over time through structured user feedback.

#### Feedback Collection

Users can rate any generation output:

```
Rating: ★★★★★ (1-5 stars)

Problem tags (select multiple):
  □ Face drift          □ Bad hands
  □ Clothing issues     □ Lack of realism
  □ Poor composition    □ Prompt mismatch
  □ Poor lighting       □ Artifacting
  □ Wrong style         □ Wrong person
  □ Too similar         □ Wrong aspect ratio
```

#### Feedback Loop

```
User generates content
         │
         ▼
User rates output (stars + problem tags)
         │
         ▼
Feedback stored with full context:
  - prompt used
  - model/LoRA used
  - workflow steps
  - settings (steps, CFG, seed)
  - output asset reference
         │
         ▼
Learning Engine aggregates patterns:
  - "Flux + this LoRA at 0.8 → face drift 40% of the time"
  - "WAN + 5s duration → artifacting in last 1s"
  - "SDXL + prompt weight > 1.5 → oversaturation"
         │
         ▼
Recommendation Engine adjusts future suggestions:
  - Lower LoRA strength recommendation
  - Suggest face fix step after generation
  - Adjust prompt weighting approach
```

---

## Database Proposals

### `generation_feedback`

Stores user ratings and problem reports for generated content.

```sql
CREATE TABLE generation_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    job_id UUID REFERENCES jobs(id),
    asset_id UUID REFERENCES assets(id),
    talent_id UUID REFERENCES talent(id),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    problems TEXT[],            -- ['face_drift', 'bad_hands', ...]
    comment TEXT,
    context JSONB DEFAULT '{}', -- snapshot of settings used
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_gen_feedback_org ON generation_feedback(org_id);
CREATE INDEX ix_gen_feedback_job ON generation_feedback(job_id);
CREATE INDEX ix_gen_feedback_rating ON generation_feedback(rating);
```

### `workflow_feedback`

Stores feedback on workflow execution quality.

```sql
CREATE TABLE workflow_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    workflow_id UUID REFERENCES workflows(id),
    workflow_run_id UUID REFERENCES workflow_runs(id),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    problems TEXT[],
    suggestions TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `prompt_history`

Tracks prompts and their outcomes for learning.

```sql
CREATE TABLE prompt_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    talent_id UUID REFERENCES talent(id),
    job_id UUID REFERENCES jobs(id),
    model TEXT NOT NULL,          -- flux-dev, sdxl, wan, etc.
    positive_prompt TEXT NOT NULL,
    negative_prompt TEXT,
    prompt_metadata JSONB DEFAULT '{}',  -- weights, trigger words, etc.
    result_rating INTEGER,        -- from generation_feedback
    result_problems TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_prompt_history_org ON prompt_history(org_id);
CREATE INDEX ix_prompt_history_model ON prompt_history(model);
CREATE INDEX ix_prompt_history_rating ON prompt_history(result_rating);
```

### `assistant_memory`

Per-tenant agent memory for context continuity.

```sql
CREATE TABLE assistant_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent TEXT NOT NULL,           -- creative_director, prompt_engineer, etc.
    talent_id UUID REFERENCES talent(id),
    memory_type TEXT NOT NULL,     -- preference, learning, context
    content JSONB NOT NULL,
    relevance_score FLOAT DEFAULT 1.0,
    expires_at TIMESTAMPTZ,        -- optional TTL
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_assistant_memory_org_agent ON assistant_memory(org_id, agent);
CREATE INDEX ix_assistant_memory_talent ON assistant_memory(talent_id);
```

### `style_preferences`

Per-talent/per-org style preferences learned over time.

```sql
CREATE TABLE style_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    talent_id UUID REFERENCES talent(id),
    category TEXT NOT NULL,        -- lighting, composition, colour, mood, etc.
    preference_key TEXT NOT NULL,  -- e.g. "lighting_style"
    preference_value TEXT NOT NULL, -- e.g. "dramatic_rembrandt"
    confidence FLOAT DEFAULT 0.5,  -- 0.0 to 1.0, increases with more data
    sample_count INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, talent_id, category, preference_key)
);

CREATE INDEX ix_style_prefs_org_talent ON style_preferences(org_id, talent_id);
```

---

## Recommendation Engine

The Recommendation Engine sits between the agents and the user, surfacing
proactive suggestions based on accumulated data.

### What it recommends

| Domain | Example recommendation |
|---|---|
| Prompts | "For Melissa portraits, adding 'soft rim lighting' improved ratings by 0.8 stars" |
| Settings | "LoRA strength 0.65 produces fewer face-drift issues than your current 0.85" |
| Workflows | "Adding a face-fix step after generation reduced 'face_drift' reports by 60%" |
| LoRA strengths | "This LoRA works best at 0.7 weight based on 23 generations" |
| Model selection | "Flux-dev produces higher-rated outputs for this talent than SDXL" |
| GPU routing | "Vast.ai RTX 4090 is 40% cheaper than RunPod for this job type right now" |

### How it works

```
┌──────────────────────────────────────────────────────┐
│              Recommendation Engine                     │
│                                                       │
│  1. Aggregate feedback by (org, talent, model, type) │
│  2. Identify patterns:                                │
│     - Which settings correlate with high ratings?     │
│     - Which settings correlate with specific problems?│
│  3. Generate recommendations:                         │
│     - Per-talent style guides (auto-updated)         │
│     - Per-model optimal settings                      │
│     - Workflow templates ranked by success rate       │
│  4. Surface via API:                                  │
│     GET /api/v1/recommendations?talent_id=X&type=Y   │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### Confidence scoring

Recommendations have a confidence score (0.0 to 1.0):
- < 5 data points: `confidence = 0.2` (show as "suggestion")
- 5-20 data points: `confidence = 0.5` (show as "recommended")
- 20+ data points: `confidence = 0.8+` (show as "best practice")

---

## Multi-Tenant Isolation

All intelligence data is scoped by `org_id`:

| Data | Isolation |
|---|---|
| Feedback | `org_id` column, RLS enforced |
| Prompt history | `org_id` column, RLS enforced |
| Style preferences | `org_id` column, per-talent |
| Assistant memory | `org_id` column, per-agent |
| Recommendations | Generated per-org from org-specific data |

**No cross-tenant learning.** Organisation A's feedback never influences
Organisation B's recommendations. This is a hard constraint for SaaS licensing.

Global model knowledge (e.g. "Flux works best at 20 steps") is stored
separately as platform-level defaults, not derived from tenant data.

---

## Agent Communication Pattern

Agents don't call each other directly. They communicate through the job
and workflow system:

```
User request → Creative Director → produces creative brief
                                       │
Creative brief → Prompt Engineer → produces optimized prompt
                                       │
Prompt + settings → Model Expert → validates model/LoRA selection
                                       │
Full config → GPU Optimizer → selects execution target
                                       │
Workflow → Workflow Optimizer → validates step order, suggests additions
                                       │
Execute → Job Engine → runs on GPU → produces output
                                       │
Output → User → rates → Learning Engine → updates recommendations
```

Each agent is a stateless function that takes context in and produces
a structured response. State lives in the database (assistant_memory,
style_preferences, prompt_history).

---

## Implementation Phases

| Phase | What | Sprint |
|---|---|---|
| 1 | Database tables for feedback/memory | 6 |
| 2 | Feedback API (rate outputs, report problems) | 6 |
| 3 | Prompt history tracking (auto-captured on job completion) | 7 |
| 4 | Style preferences auto-extraction from feedback | 7 |
| 5 | Basic Prompt Engineer (template-based, no LLM) | 8 |
| 6 | LLM-powered Creative Director | 9 |
| 7 | Recommendation Engine v1 (rule-based) | 10 |
| 8 | Full agent orchestration | 11+ |

---

## Future: LLM Integration

Agents will be powered by LLMs (GPT-4o, Claude, or open-source):

```python
class CreativeDirectorAgent:
    def __init__(self, llm_client, memory_store):
        self.llm = llm_client
        self.memory = memory_store

    async def refine_concept(self, concept: str, talent_id: str) -> CreativeBrief:
        # Load talent profile
        # Load style preferences
        # Load recent high-rated outputs
        # Construct system prompt with agent role
        # Call LLM with context
        # Parse structured response
        # Store in assistant_memory
        ...
```

LLM provider will be configurable (supports OpenAI, Anthropic, local models).
Agent prompts stored in the database for A/B testing and iteration.

---

## Future: UI Integration

The dashboard will expose agent capabilities as:

| UI Element | Agent | Interaction |
|---|---|---|
| "Improve this prompt" button | Prompt Engineer | Rewrites prompt, shows diff |
| "Suggest workflow" panel | Workflow Optimizer | Shows recommended steps |
| Creative brief wizard | Creative Director | Multi-step Q&A dialog |
| "Why this model?" tooltip | Model Expert | Explains recommendation |
| Cost estimate badge | GPU Optimizer | Shows $/estimated-time |
| Star rating + problem tags | Learning Engine | Post-generation feedback |
| "Based on your history" cards | Recommendation Engine | Proactive suggestions |

---

*This is a design document. Implementation begins in Sprint 6+.*
