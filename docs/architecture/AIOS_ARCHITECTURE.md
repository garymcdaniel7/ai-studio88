# AI Studio Intelligence Operating System (AIOS)

## Architecture Design Epic

> **Status:** Architecture Design Only — Do NOT Implement  
> **Author:** Architecture Council  
> **Date:** July 2026  
> **Prerequisite:** Complete current stabilization, UAT, and infrastructure hardening phase first.

---

## 1. Executive Summary

AIOS is the intelligent operating system that powers every capability inside AI Studio. It replaces the current fragmented intelligence layer (separate Brain, Intelligence Engine, Autonomous Studio, and per-module AI) with a **unified, provider-agnostic intelligence platform** that any interface can consume.

The AI Brain becomes one client of AIOS. Claude via MCP becomes another. A mobile app becomes another. They all access the same intelligence, memory, governance, and tooling.

---

## 2. Current State Assessment

### What Exists Today (Strengths to Preserve)

| System | Location | Pattern | Status |
|--------|----------|---------|--------|
| Intelligence Engine | `backend/intelligence_engine/` | 10 agents + shared IntelligenceContext → CreativePlan | Functional (rule-based) |
| Autonomous Studio | `backend/autonomous_studio/` | 19 departments + daily briefing + approval workflow | Functional (rule-based) |
| AI Brain | `backend/brain/` | LLM chat + planner + memory + RAG + module registry | Functional (Ollama/OpenAI/Anthropic) |
| Generation Engine | `backend/engine/` | Provider interface → ComfyUI/Simulation dispatch | Real (ComfyUI proven) |
| Worker Orchestration | `backend/infrastructure/` | Connection Race + reputation + cost tracking + fleet | Real (Vast.ai/RunPod) |
| Story Engine | `backend/story_engine/` | Universe→Character→Episode→Scene→Shot hierarchy | Scaffolded |
| Creative DNA | Supabase `creative_dna` table | Per-talent learned preferences from feedback | Functional |
| Object Intelligence | `backend/object_intelligence/` | Object DNA, Product DNA, Digital Twins, Scene DNA | Scaffolded |
| Asset Intelligence | `backend/asset_intelligence/` | Visual DNA, collections, wardrobes, relationships | Scaffolded |
| Provider Reputation | `backend/infrastructure/provider_reputation.py` | Host/GPU/region scoring + blacklist | Functional (in-memory) |

### What's Missing (Gaps AIOS Addresses)

1. **No unified intelligence gateway** — Each subsystem has its own entry point
2. **No cross-system orchestration** — Intelligence Engine and Autonomous Studio don't talk
3. **No event bus** — Systems communicate via direct imports only
4. **No memory persistence for Brain** — Sessions are in-memory, lost on restart
5. **No external AI integration** — No MCP server, no way for Claude/ChatGPT to invoke tools
6. **Keyword-based planning only** — Brain planner uses string matching, not LLM reasoning
7. **No approval workflow enforcement** — Departments recommend but nothing blocks destructive actions
8. **No decision traceability** — Agent outputs are ephemeral, not logged
9. **Provider routing is static** — Brain uses one configured provider, no dynamic routing
10. **No governance framework** — Agents have no authority boundaries

---

## 3. AIOS Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENTS                                        │
│  Native UI │ MCP (Claude/ChatGPT) │ REST API │ Voice │ Mobile │ Cron   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────────┐
│                    INTELLIGENCE GATEWAY                                   │
│  Auth │ Tenant │ Session │ Rate Limit │ Budget │ Audit │ Streaming      │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────────┐
│                         AIOS CORE                                         │
│                                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  Provider    │  │   Agent      │  │   Memory &   │  │  Governance  │ │
│  │  Router     │  │   Council    │  │   Knowledge  │  │  & Approval  │ │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         │                 │                  │                  │        │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼──────┐ │
│  │  Workflow   │  │   Decision   │  │  Knowledge   │  │  Authority   │ │
│  │Intelligence │  │  Traceability│  │    Graph     │  │   Matrix     │ │
│  └─────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────────┐
│                    AI STUDIO SERVICES                                     │
│  Generation │ Training │ Video │ Audio │ Publishing │ Assets │ Storage  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Core Principle: LLM Independence

AIOS owns everything except raw reasoning. The LLM is a swappable reasoning engine:

| AIOS Owns | LLM Provides |
|-----------|-------------|
| Memory & context | Reasoning over context |
| Tool definitions | Tool selection decisions |
| Permissions & governance | Nothing — it has no authority |
| Orchestration & routing | Natural language understanding |
| Knowledge graph | Pattern recognition |
| Decision audit trail | Confidence scoring |
| Budget enforcement | Cost estimation |
| Workflow execution | Workflow recommendation |

---

## 4. Intelligence Gateway

The single entry point into AIOS for all clients.

### Responsibilities

| Responsibility | Description |
|----------------|-------------|
| Authentication | JWT validation, API key auth, MCP token verification |
| Authorization | Tenant isolation, role-based access, tool permissions |
| Session Management | Stateful conversations, context windows, session persistence |
| Provider Routing | Dynamic LLM selection based on task complexity, cost, privacy |
| Memory Retrieval | Inject relevant context from knowledge graph before reasoning |
| Tool Invocation | Secure execution of platform tools with parameter validation |
| Streaming | SSE/WebSocket for real-time progress and token streaming |
| Approval Workflows | Block destructive actions until human confirms |
| Audit Logging | Every decision, tool call, and reasoning step recorded |
| Rate Limiting | Per-tenant, per-user, per-tool rate enforcement |
| Budget Enforcement | Reject operations exceeding configured spend thresholds |
| Response Caching | Deterministic queries served from cache |
| Prompt Caching | Reuse system prompts and context injections |

### Gateway API Surface

```
POST /aios/v1/chat              — Conversational interface (streaming)
POST /aios/v1/plan              — Create execution plan from intent
POST /aios/v1/execute           — Execute an approved plan
POST /aios/v1/tools/{tool}      — Direct tool invocation
GET  /aios/v1/session/{id}      — Get session state
GET  /aios/v1/memory/search     — Search knowledge graph
POST /aios/v1/approve/{id}      — Approve a pending action
POST /aios/v1/reject/{id}       — Reject a pending action
GET  /aios/v1/decisions/{id}    — Get decision trace
GET  /aios/v1/health            — Gateway + provider health
```

### Migration Path from Current System

The existing `/api/v1/brain/*` endpoints remain operational. The Gateway wraps them:

```
/api/v1/brain/chat    → forwards to → /aios/v1/chat (with enhanced context)
/api/v1/brain/plan    → forwards to → /aios/v1/plan
/api/v1/brain/health  → forwards to → /aios/v1/health
```

No breaking changes. New capabilities layer on top.

---

## 5. Provider Router

### Dynamic Provider Selection

```python
@dataclass
class RoutingDecision:
    provider: str           # "ollama", "openai", "anthropic", "openrouter"
    model: str              # "llama3.1:8b", "gpt-4o", "claude-sonnet-4-20250514"
    reasoning: str          # Why this provider was selected
    estimated_cost: float   # Projected token cost
    estimated_latency_ms: int
    confidence: float       # 0.0-1.0
    fallback_chain: list[str]  # Ordered fallback providers
```

### Routing Factors

| Factor | Weight | Source |
|--------|--------|--------|
| Task complexity | High | Analyze prompt length, tool requirements |
| Privacy sensitivity | High | Tenant config, data classification |
| Context window needed | High | Conversation length + retrieved context |
| Latency requirement | Medium | Interactive vs batch, streaming vs block |
| Token cost | Medium | Budget remaining, cost per 1K tokens |
| Provider health | High | Last health check, error rate |
| Model capabilities | High | Tool use, vision, code, reasoning |
| Tenant preference | Medium | User/org config overrides |
| Provider availability | Critical | Circuit breaker state |

### Supported Providers (Extending Current)

| Provider | Current Status | AIOS Role |
|----------|---------------|-----------|
| Ollama (local) | Implemented in `brain/llm_provider.py` | Default for interactive chat, privacy-sensitive |
| OpenAI | Implemented in `brain/llm_provider.py` | Complex reasoning, tool use |
| Anthropic | Implemented in `brain/llm_provider.py` | Long context, careful analysis |
| OpenRouter | Defined in `intelligence_engine/llm_provider.py` | Multi-model access, cost optimization |
| LM Studio | Placeholder | Local alternative to Ollama |
| Gemini | Not yet | Long context (1M tokens), multimodal |
| Ollama on GPU worker | Partially implemented | Heavy inference, batch processing |

### Automatic Fallback Chain

```
Request arrives → Primary provider healthy? → Use it
                                           → No → Try fallback[0]
                                                → No → Try fallback[1]
                                                     → No → Return degraded response
```

### Challenge: Provider Router vs Current Brain Provider

The current `backend/brain/llm_provider.py` is a simple static dispatcher. AIOS replaces it with a dynamic router that makes per-request decisions. The existing interface (`chat(messages, model, mode)`) becomes a thin wrapper around the router.

---

## 6. Yoruba Multi-Agent Architecture (Agent Council)

### Design Philosophy

The existing AI Studio agent system uses two separate patterns:
- `intelligence_engine/agents/` → 10 agents with `BaseAgent.think(context) → AgentOutput`
- `autonomous_studio/departments/` → 19 departments with `Department.analyze(context) → DepartmentOutput`

AIOS unifies these under a single **Agent Council** pattern while preserving the cultural naming system.

### Agent Council Members

| Agent | Domain | Absorbs Existing | Authority Level |
|-------|--------|------------------|-----------------|
| **Òrúnmìlà** | Chief Intelligence — planning, reasoning, strategy | Brain planner, Intelligence Engine orchestrator | Propose plans, never execute |
| **Èṣù** | Communication — routing, tool selection, coordination | Brain registry, module discovery | Route requests, invoke tools |
| **Ògún** | Infrastructure — GPU, workers, deployment, execution | Worker Orchestrator, Connection Race, Fleet | Launch/stop workers (with approval) |
| **Ọ̀ṣun** | Creative direction — visual quality, brand, coaching | Creative Director agent, Art Director dept | Recommend creative choices |
| **Ọya** | Story — narrative, continuity, adaptive creativity | Story Engine, Continuity Director agent | Evolve stories, maintain canon |
| **Yemọja** | Memory — knowledge graph, DNA, relationships, context | Brain memory, RAG, Creative DNA, all DNA systems | Read all memory, write with audit |
| **Ṣàngó** | Production — scheduling, rendering, publishing | Production Director, Publishing Director depts | Queue jobs, schedule posts |
| **Ọbalúayé** | Diagnostics — reliability, quality, verification, recovery | Provider reputation, health checks, worker orchestrator | Alert, retry, escalate |
| **Ajé** | Commerce — marketplace, billing, subscriptions | Business Director dept, cost intelligence | Track spend, enforce budgets |

### Unified Agent Interface

```python
class CouncilAgent(ABC):
    """Unified agent interface replacing both BaseAgent and Department."""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def domain(self) -> str: ...
    
    @property
    @abstractmethod
    def authority(self) -> AuthorityLevel: ...
    
    @abstractmethod
    async def reason(self, context: AIOSContext) -> AgentDecision: ...
    
    @abstractmethod
    async def execute(self, action: ApprovedAction) -> ActionResult: ...
    
    @abstractmethod
    def capabilities(self) -> list[Capability]: ...
```

### Council Orchestration Pattern

```
1. Request arrives at Intelligence Gateway
2. Èṣù (router) analyzes intent, identifies relevant agents
3. Relevant agents run in parallel: reason(context) → AgentDecision[]
4. Òrúnmìlà (chief) synthesizes decisions into unified plan
5. Governance layer checks: any decisions require approval?
6. If approval needed → hold pending, notify user
7. If pre-approved → Èṣù dispatches to executing agents
8. Results recorded in decision log + knowledge graph
```

### Challenge: 19 Departments → 9 Council Agents

The current 19 autonomous studio departments are over-fragmented. Many overlap (Photography Director vs Film Director vs Video Director). AIOS consolidates them into 9 council agents that internally specialize:

- Ọ̀ṣun (Creative) absorbs: Creative Director, Prompt Director, Photography Director, Art Director, Character Director
- Ṣàngó (Production) absorbs: Production Director, Video Director, Publishing Director
- Ọya (Story) absorbs: Film Director, Voice Director, Music Director
- Ajé (Commerce) absorbs: Business Director, Growth Director, Analytics Director
- Ọbalúayé (Diagnostics) absorbs: Operations Director, Learning Director
- Yemọja (Memory) absorbs: Research Director, Trend Director, Brand Director

This reduces cognitive overhead while maintaining coverage.

---

## 7. Ọbalúayé — Platform Reliability Supervisor

Ọbalúayé is the unified reliability supervisor — handling both rule-based mechanics (health checks, retries, circuit breakers) and optional LLM-powered pattern analysis when available.

### Responsibilities

| Domain | Actions |
|--------|---------|
| Provider Health | Poll all providers every 30s, circuit breaker pattern |
| Worker Health | SSH heartbeat to active GPU workers every 60s |
| Queue Monitoring | Alert if jobs are stuck, retry failed jobs |
| Storage Health | Verify B2 connectivity, check quota |
| Database Health | Supabase connection pool monitoring |
| Automatic Failover | Switch providers on detection of failure |
| Workflow Validation | Pre-validate ComfyUI workflows before dispatch |
| Asset Verification | Confirm uploaded assets are accessible and valid |
| Cost Alerting | Warn when spend approaches budget limits |
| Log Aggregation | Structured logging with context IDs |
| Metric Export | Prometheus-compatible metrics endpoint |

### Architecture Decision: LLM-Optional

Ọbalúayé uses rule-based logic for most decisions (health checks, retries, circuit breakers). It may optionally invoke a local Ollama for:
- Analyzing error patterns to suggest root causes
- Generating human-readable incident summaries
- Recommending configuration changes

But Ọbalúayé must function fully without any LLM available.

### Builds On Existing

| Current System | Ọbalúayé Absorbs |
|----------------|----------------|
| `provider_reputation.py` | Host/GPU scoring, blacklisting |
| `cost_intelligence.py` | Budget tracking, spend alerts |
| `admin_settings.py` service checks | Periodic health polling |
| Worker orchestrator reconnect logic | Session recovery |

---

## 8. Workflow Intelligence

### Current State

The existing `intelligence_engine/agents/workflow_optimizer.py` agent recommends workflow steps. The `engine/workflow_selector.py` picks ComfyUI templates. Both are rule-based.

### AIOS Workflow Intelligence

A dedicated subsystem that automatically determines the optimal generation configuration.

### Decision Matrix

| Parameter | Decision Factors |
|-----------|-----------------|
| Provider | Availability, reputation score, cost, VRAM, model cache |
| Workflow template | Content type, model compatibility, quality target |
| Checkpoint | Talent DNA preference, content type, quality vs speed |
| LoRA selection | Talent identity LoRA + style LoRAs from Creative DNA |
| LoRA balancing | Multiple LoRA strength ratios (identity: 0.7, style: 0.4) |
| ControlNet | Pose reference available? Reference image provided? |
| IP-Adapter | Style transfer requested? Brand reference available? |
| VAE | Model default unless quality issue detected |
| Sampler/Scheduler | Model-specific defaults (Flux: euler/simple, SDXL: dpmpp_2m/karras) |
| CFG | Model-specific (Flux: 1.0, SDXL: 7.0, SD1.5: 7.5) |
| Steps | Quality target (draft: 4, standard: 20, quality: 40) |
| Resolution | Platform target (IG: 1080x1080, TikTok: 1080x1920, YouTube: 1920x1080) |
| Negative prompt | Model-specific + Creative DNA avoided_styles |
| Prompt enhancement | Inject Talent DNA trigger words, quality boosters |
| Face restoration | Auto-enable if face detected and model is not face-specialized |
| Upscaling | Auto-enable if target resolution > generation resolution |

### Workflow DNA (New Concept)

Reusable, learned workflow configurations:

```python
@dataclass
class WorkflowDNA:
    id: str
    name: str                    # "Luxury Portrait — Flux + LoRA"
    content_type: str            # "image", "video"
    checkpoint: str              # "flux-dev"
    loras: list[LoRAConfig]      # [{model_id, strength, trigger_words}]
    sampler: str
    scheduler: str
    cfg: float
    steps: int
    resolution: tuple[int, int]
    negative_prompt: str
    quality_score: float         # Learned from feedback
    success_rate: float          # Historical success
    avg_generation_time: float
    avg_cost: float
    recommended_for: list[str]   # ["portrait", "editorial", "luxury"]
    created_from: str            # "manual" | "auto_learned" | "community"
```

### Learning Loop

```
Generate → User rates (1-5 stars) → Record workflow config + rating
    → Over time: highest-rated configs become Workflow DNA recipes
    → Recommended to other users with similar Talent DNA
```

---

## 9. Knowledge Graph

### Current DNA Systems (Unified)

| DNA System | Current Location | Data |
|------------|-----------------|------|
| Creative DNA | `creative_dna` table | Per-talent preferences, styles, rules |
| Object DNA | `object_dna` table | Asset properties, geometry, materials |
| Product DNA | `product_dna` table | Commercial product profiles |
| Visual DNA | `visual_dna` table | Asset visual analysis |
| Story DNA | `story_engine/models.py` | Universe rules, character arcs |
| Workflow DNA | **NEW** | Learned workflow configurations |
| Talent DNA | Talent record fields | Identity, style, personality, associations |
| Project DNA | **NEW** | Per-project preferences, brand guidelines |

### Knowledge Graph Schema

```
Talent ──has──→ Creative DNA
       ──has──→ Identity LoRA
       ──appears_in──→ Asset
       ──acts_in──→ Story Character
       ──related_to──→ Talent (relationships)
       ──wears──→ Wardrobe (Object DNA)
       ──speaks_with──→ Voice Profile

Asset ──has──→ Visual DNA
      ──has──→ Object DNA
      ──generated_by──→ Workflow DNA
      ──part_of──→ Collection
      ──used_in──→ Campaign

Model ──trained_from──→ Talent (images)
      ──compatible_with──→ Model (base)
      ──produces──→ Asset (generation history)
      ──rated──→ Quality Score

Workflow ──uses──→ Model
         ──uses──→ LoRA
         ──rated──→ Quality Score
         ──costs──→ GPU Time
         ──produces──→ Asset
```

### Implementation: pgvector + Supabase

The knowledge graph is implemented as:
1. **Relational data** — existing Supabase tables (talent, assets, models, etc.)
2. **Vector embeddings** — `brain_embeddings` table with pgvector (already exists)
3. **Graph queries** — SQL JOINs across relational tables (no separate graph DB needed)
4. **Semantic search** — Vector similarity for natural language queries against all DNA

### Challenge: No Separate Graph Database

Adding Neo4j or similar would complicate infrastructure. Instead, model relationships as:
- Junction tables for explicit relationships (already used: `talent_loras`, `asset_collections`)
- pgvector for semantic similarity queries
- JSON metadata for flexible properties

This is simpler, uses existing infrastructure, and scales well for the current entity volume.

---

## 9.5. Unified Talent Model — Everything is Talent

### Problem with Current Design

The current architecture has a separate "Assets" page that's redundant. Assets are just files. The meaningful entity is always a **Talent** — whether that's a person, a background, a product, or a wardrobe item. The Assets page becomes a file browser with no creative intelligence.

### Design: Talent as Universal Entity

Every creative entity in AI Studio is a **Talent** with a type:

| Talent Type | Examples | Key Properties |
|-------------|----------|----------------|
| **Model / Person** | Melissa, Alex | Physical attributes, personality, LoRA, voice |
| **Background / Location** | Bedroom, Dubai Marina, Studio A | Lighting, mood, time of day, reference images |
| **Product** | Watch, Perfume, Handbag | Brand, materials, dimensions, commercial DNA |
| **Wardrobe** | Red Dress, Sneakers, Gold Chain | Garment type, fabric, color, season, size |
| **Object / Prop** | Camera, Car, Flowers | Material, scale, usage context |
| **Voice** | Narrator, Character voice | Provider, accent, gender, samples |

### Relationships (Talent-to-Talent)

The power comes from **associations** between talents:

| Relationship | Meaning | Used For |
|-------------|---------|----------|
| `talent ←friends→ talent` | Two models who appear together | Multi-person scenes, LoRA pairing |
| `talent ←couple→ talent` | Romantic/partner association | Couple shoots, story arcs |
| `talent ←wears→ wardrobe` | Model owns/wears this outfit | Wardrobe consistency, outfit selection |
| `talent ←uses→ product` | Model is brand ambassador for product | Product placement, commercial shoots |
| `talent ←lives_in→ background` | Model's consistent location | Background injection (bedroom, studio) |
| `talent ←holds→ object` | Model frequently poses with this prop | Scene composition |
| `wardrobe ←pairs_with→ wardrobe` | Outfit combinations that work | Styling suggestions |
| `product ←displayed_in→ background` | Product's natural setting | Product photography |
| `background ←variant_of→ background` | Same location, different lighting/time | Scene variety |

### How Relationships Power Generation

When generating content:
1. User selects Talent (Melissa)
2. AIOS loads Melissa's Creative DNA + identity LoRA
3. AIOS checks: what background is associated? → inject reference image
4. AIOS checks: what wardrobe is associated? → add to prompt
5. AIOS checks: any products associated? → include if commercial context
6. AIOS checks: other talent in the scene? → load their LoRAs too, balance strengths

### Assets Page Redesign

The current standalone "Assets" page becomes:
- **A tab within each Talent** showing all generated content FOR that talent
- **A global gallery** filtered by talent, type, date (for browsing all outputs)
- **Not a separate navigation item** — talent IS the primary entity

Generated outputs (images, videos) are associated TO a talent, not stored independently.

### Non-Human Talent: Context-Aware Fields

When adding a non-human talent, the UI adapts:
- **Background**: Shows location fields (lighting, mood, time of day) instead of physical attributes
- **Wardrobe**: Shows garment fields (fabric, color, brand, season) instead of age/height
- **Product**: Shows commercial fields (dimensions, SKU, brand, price) instead of personality

The existing `TalentEditModal` already does this (type-specific field sections). AIOS formalizes it as the canonical entity model.

### Database: Junction Table

```sql
CREATE TABLE talent_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    talent_a_id UUID NOT NULL REFERENCES talent(id),
    talent_b_id UUID NOT NULL REFERENCES talent(id),
    relationship_type TEXT NOT NULL,  -- 'friends', 'couple', 'wears', 'uses', 'lives_in', etc.
    metadata JSONB DEFAULT '{}',      -- strength, notes, context
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(talent_a_id, talent_b_id, relationship_type)
);

CREATE INDEX ix_talent_relationships_a ON talent_relationships(talent_a_id);
CREATE INDEX ix_talent_relationships_b ON talent_relationships(talent_b_id);
CREATE INDEX ix_talent_relationships_org ON talent_relationships(org_id);
```

### Content Association

Generated content links to talent via the existing `assets.talent_id` column. A global gallery view queries across all talents. Per-talent views show only that talent's content — images, videos, training data.

---

## 10. Memory Architecture

### Memory Domains

| Domain | Scope | Persistence | Current Status |
|--------|-------|-------------|----------------|
| Global | Platform-wide defaults | Supabase | Partially (env vars) |
| Tenant | Per-organization preferences | Supabase `organizations` | Table exists |
| User | Per-user preferences | Supabase `users` + `brain_conversations` | Partially |
| Session | Current conversation context | In-memory → Supabase | In-memory only |
| Project | Per-project creative direction | **NEW** `project_dna` table | Not yet |
| Story | Universe continuity, character memory | `story_memory` table | Scaffolded |
| Talent | Creative DNA, feedback history | `creative_dna` + `generation_feedback` | Functional |
| Creative | Cross-talent style evolution | **NEW** aggregate analysis | Not yet |
| Infrastructure | Provider reputation, cost history | In-memory + partial Supabase | Partial |
| Provider | LLM provider performance tracking | **NEW** `provider_metrics` | Not yet |
| Workflow | Generation config success history | **NEW** `workflow_dna` | Not yet |
| Conversation | Chat history with embeddings | `brain_conversations` + `brain_embeddings` | Functional |

### Memory Retrieval Pipeline

```
User sends message
    │
    ▼
1. Session context (last N messages)
    │
    ▼
2. Talent DNA (if talent context active)
    │
    ▼
3. Project DNA (if project context active)
    │
    ▼
4. Vector search: relevant past conversations (RAG — already implemented)
    │
    ▼
5. Workflow DNA: successful configs for similar requests
    │
    ▼
6. Assembled context injected into system prompt
    │
    ▼
7. LLM reasons over enriched context
```

### Migration from Current Memory

The existing `backend/brain/memory.py` uses in-memory dicts. AIOS moves all memory to Supabase:
- `_sessions` dict → `brain_sessions` table (already partially done)
- `_production_memory` dict → `user_preferences` table
- RAG embeddings → already in `brain_embeddings` (keep as-is)

---

## 11. MCP & External AI Integration

### AI Studio as MCP Server

Expose platform capabilities so external AI assistants (Claude, ChatGPT, Cursor) can invoke them:

```python
# MCP Tools exposed by AI Studio
AIOS_MCP_TOOLS = [
    # Talent & Creative
    "search_talent",           # Search Talent DNA by name/style/attributes
    "get_talent_dna",          # Get full Creative DNA for a talent
    "create_talent",           # Create new AI talent
    
    # Generation
    "generate_image",          # Generate an image with full parameter control
    "generate_video",          # Generate a video clip
    "recommend_workflow",      # Get optimal workflow for a request
    
    # Story
    "continue_story",          # Add to a story universe
    "get_story_context",       # Read story continuity
    
    # Project
    "create_project",          # Start a new project
    "get_project_status",      # Check project state
    
    # Training
    "train_lora",              # Submit LoRA training job
    "get_training_status",     # Check training progress
    
    # Assets
    "search_assets",           # Search generated assets
    "review_asset",            # Get AI review of an asset
    
    # Publishing
    "schedule_post",           # Schedule social media post
    "get_calendar",            # View publishing calendar
    
    # Infrastructure
    "check_gpu_status",        # Current worker state
    "estimate_cost",           # Cost estimate for a job
]
```

### Security Model for External AI

```
External AI (Claude/ChatGPT)
    │
    ▼ MCP protocol (authenticated)
    │
Intelligence Gateway
    │
    ▼ Validates: token, tenant, permissions, budget
    │
Tool Execution (same as internal)
    │
    ▼ Approval check: does this tool require human confirmation?
    │
Result returned to external AI
```

Key constraint: The external AI **never** has direct database or infrastructure access. It can only invoke defined tools through the Gateway, subject to the same governance as internal agents.

### Challenge: MCP Protocol Support

MCP is primarily designed for local tool servers (stdio transport). For a cloud-hosted AI Studio, we need:
- **HTTP/SSE transport** for MCP (Claude supports this)
- **API key authentication** per MCP connection
- **Scoped tool access** — not every MCP client gets every tool
- **Streaming results** — generation progress streamed back to the client

---

## 12. Decision Traceability

### Every AI Decision Logged

```python
@dataclass
class DecisionRecord:
    id: str
    timestamp: str
    session_id: str
    agent: str                     # Which council agent decided
    decision_type: str             # "model_selection", "workflow_choice", "approval_request"
    input_context: dict            # What the agent was given
    output: dict                   # What the agent decided
    confidence: float
    reasoning: str                 # Human-readable explanation
    alternatives_considered: list  # Other options that were evaluated
    evidence: list[str]            # Data points supporting the decision
    estimated_cost: float
    estimated_quality: float
    outcome: str | None            # "success", "failure", "pending" (filled later)
    user_feedback: int | None      # 1-5 rating (filled later)
```

### Example Decision Trace

```json
{
  "agent": "Workflow Intelligence",
  "decision_type": "model_selection",
  "reasoning": "Flux Dev selected because: highest historical success rate (87%) for portrait content, Talent DNA compatibility (trigger words registered), workflow quality score 4.2/5, GPU cache available (no download needed), lowest projected cost ($0.003/image)",
  "confidence": 0.91,
  "alternatives_considered": [
    {"model": "SDXL Turbo", "reason_rejected": "Lower quality for portraits (3.1/5 avg)"},
    {"model": "SD 1.5", "reason_rejected": "Outdated, no LoRA compatibility with this talent"}
  ],
  "estimated_cost": 0.003,
  "estimated_quality": 4.2
}
```

---

## 13. Human Approval Model

### Actions Requiring Approval

| Action | Risk Level | Default Policy |
|--------|-----------|----------------|
| Launch GPU worker | Medium | Auto-approve if within daily budget |
| Launch render fleet (3+ workers) | High | Always require approval |
| Delete assets | High | Always require approval |
| Delete models | High | Always require approval |
| Delete Talent DNA | Critical | Always require approval |
| Publish to social media | Medium | Require approval (configurable) |
| LoRA training (initiates GPU spend) | Medium | Auto-approve if within budget |
| Voice cloning (consent implications) | High | Always require approval |
| Spend > $5 single action | High | Always require approval |
| Spend > daily budget | Critical | Block until budget increased |
| Destructive admin actions | Critical | Always require approval |
| Modify Creative DNA | Low | Auto-approve (reversible) |
| Generate content | Low | Auto-approve (cheap, reversible) |

### Approval Workflow

```
Agent proposes action
    │
    ▼
Governance layer checks policy
    │
    ├── Auto-approved → Execute immediately
    │
    └── Requires approval → Create PendingApproval record
                               │
                               ▼
                            Notify user (UI badge, push, email)
                               │
                               ▼
                            User reviews: Approve / Reject / Modify
                               │
                               ▼
                            Execute or discard
```

### Configurable Thresholds

Users can adjust approval policies:
```json
{
  "auto_approve_generation": true,
  "auto_approve_training": true,
  "auto_approve_gpu_launch": false,
  "max_auto_spend_usd": 5.00,
  "require_publish_approval": true,
  "require_delete_approval": true
}
```

---

## 14. Agent Governance

### Authority Matrix

| Agent | Can Propose | Can Execute (Auto) | Requires Approval |
|-------|------------|-------------------|-------------------|
| Òrúnmìlà | Any plan | Nothing | Everything |
| Èṣù | Tool routing | Route requests, invoke read tools | Write tools |
| Ògún | Infrastructure changes | Health checks, status queries | Launch/stop workers |
| Ọ̀ṣun | Creative recommendations | Prompt enhancement | Nothing (advisory only) |
| Ọya | Story continuity | Read story context | Story mutations |
| Yemọja | Memory operations | Read memory, search | Write memory |
| Ṣàngó | Production scheduling | Queue jobs, check status | Publish, render fleets |
| Ọbalúayé | Diagnostics, retries | Health checks, retries | Blacklist providers |
| Ajé | Budget enforcement | Track costs, alert | Block overspend |

### Conflict Resolution

When agents disagree (e.g., Ọ̀ṣun recommends a high-quality slow workflow but Ajé flags it as over-budget):

1. Identify conflict type (cost vs quality, speed vs safety)
2. Apply tenant priority policy (default: quality > cost > speed)
3. If unresolvable → escalate to human with both perspectives
4. Record resolution for future learning

### Extensibility

New agents can be added by:
1. Implementing `CouncilAgent` interface
2. Registering in agent registry
3. Defining authority level and governance rules
4. No existing agents need modification

---

## 15. Model & Workflow Evolution (Research Intelligence)

### Tracking Sources

| Source | What to Track | Frequency |
|--------|--------------|-----------|
| ComfyUI Manager | New nodes, updates, breaking changes | Daily |
| CivitAI | Top models, new LoRAs, trending workflows | Daily |
| Hugging Face | New model releases, paper implementations | Weekly |
| GPU market | Pricing changes, new GPUs, availability | Daily |
| Academic papers | New architectures, techniques | Weekly |
| Community | Reddit, Discord best practices | Weekly |

### Recommend, Never Auto-Apply

Research Intelligence produces recommendations only:
- "New FLUX.1-schnell available — 4x faster than dev, similar quality for non-portrait"
- "ComfyUI updated: new native upscale node replaces external dependency"
- "CivitAI top LoRA this week matches your luxury portrait style"

User decides whether to integrate.

---

## 16. Session Orchestration (Multi-Worker)

### Current State

Single worker model: one GPU worker at a time, managed by WorkerOrchestrator.

### AIOS Session Orchestration

A session may span multiple specialized workers:

```
Session: "Luxury Campaign for Melissa"
    │
    ├── Image Worker (RTX 4090, Flux Dev loaded)
    │       └── 5 portrait variations
    │
    ├── Video Worker (A100, WAN 2.2 loaded)
    │       └── 2 animated clips from best portraits
    │
    ├── Training Worker (RTX 3090, SimpleTuner)
    │       └── LoRA refinement from approved outputs
    │
    └── LLM Worker (RTX 3090, Ollama llama3.1)
            └── Heavy reasoning for campaign strategy
```

### Orchestration Rules

| Decision | Criteria |
|----------|----------|
| Provision new worker | Job in queue + no suitable worker available + budget allows |
| Reuse existing worker | Model already loaded, worker idle, compatible task |
| Release worker | Idle > configured timeout, no pending jobs |
| Select provider | Task type (training→RunPod persistent, image→Vast.ai cheap) |
| Model placement | Keep hot models loaded, evict by LRU + usage frequency |

### Builds On Existing

The current `auto_provisioner.py` and `worker_registry.py` handle single-worker launch. AIOS extends to multi-worker with session-level orchestration.

---

## 17. Intelligent Model Lifecycle

### State Machine

```
Registered → Stored (B2) → Cached (Worker) → Loaded (VRAM) → Active
     ↑                                                           │
     └──────── Archived ←── Disabled ←── Unloaded ←─────────────┘
                   │
                   ▼
          Permanently Deleted (irreversible)
```

### Lifecycle Policies

| Transition | Trigger | Reversible |
|-----------|---------|-----------|
| Store → Cache | Model needed on worker | Yes |
| Cache → Load | Generation job uses this model | Yes |
| Load → Unload | Worker needs VRAM for different model | Yes |
| Any → Archive | Manual or 90-day unused | Yes |
| Archive → Restore | Manual | Yes |
| Archive → Delete | Manual (requires approval) | No |
| Active → Disabled | User disables in Model Manager | Yes |

### Intelligent Decisions

Ògún (Infrastructure agent) decides:
- Which models to pre-cache on worker boot (based on historical usage)
- When to unload from VRAM (LRU + frequency weighting)
- When to suggest archiving (90 days unused)
- When to recommend permanent deletion (archived + 180 days, no references)

---

## 18. Commercialization Architecture

### Deployment Models

| Model | Description | AIOS Impact |
|-------|------------|-------------|
| SaaS (hosted) | AI Studio hosted, multi-tenant | Default architecture |
| Enterprise | Dedicated instance, custom domain | Tenant isolation already designed |
| White-label | Rebrandable platform | UI theming + custom domain |
| BYOP (Bring Your Own Provider) | Customer provides their own LLM keys | Provider Router supports this |
| API Platform | Developer access to AIOS capabilities | Intelligence Gateway = API |
| Marketplace | Community workflows, LoRAs, presets | Workflow DNA + Model Registry |

### Tenant Isolation (Already Designed)

Every table has `org_id`. Supabase RLS enforces at DB level. AIOS Gateway adds:
- Per-tenant budget enforcement
- Per-tenant provider configuration
- Per-tenant approval policies
- Per-tenant memory isolation (knowledge graph scoped by org_id)

### Billing Integration Points

Ajé (Commerce agent) tracks:
- GPU compute time per tenant
- LLM token usage per tenant
- Storage consumption per tenant
- API call volume per tenant
- Feature tier enforcement

---

## 19. Legal & Trust Architecture

### Recommendations (Not Implementation)

| Concern | Architecture Recommendation |
|---------|---------------------------|
| Terms of Service | Store user acceptance timestamp, version tracking |
| Privacy | Data residency configuration per tenant, GDPR delete endpoint |
| Copyright | Generation metadata includes model provenance, LoRA attribution |
| DMCA | Takedown workflow: flag → review → remove → log |
| Deepfakes | Consent flag on talent records, output watermarking metadata |
| Voice cloning | Explicit consent record required before voice profile creation |
| Provider licensing | Model license field in registry, enforce usage restrictions |
| Auditability | Decision log (Section 12) provides complete audit trail |
| Compliance | Export endpoint for all user data (GDPR Article 15) |

---

## 20. Phased Implementation Plan

### Phase 0: Foundation (Current — In Progress)

- Stabilize existing platform
- Complete UAT cycle
- Harden infrastructure
- Fix remaining defects

### Phase 1: Intelligence Gateway + Provider Router

**Duration:** 2-3 weeks

- Implement Gateway as a FastAPI router (`/aios/v1/`)
- Dynamic provider routing (replace static `BRAIN_PROVIDER` env var)
- Automatic fallback chain
- Session persistence (move Brain memory to Supabase)
- Decision logging table + basic audit

### Phase 2: Unified Agent Architecture

**Duration:** 3-4 weeks

- Define `CouncilAgent` interface
- Migrate Intelligence Engine agents → Council agents
- Migrate Autonomous Studio departments → absorbed into Council
- Implement Èṣù (router/coordinator)
- Implement Òrúnmìlà (planning, replacing keyword-based planner)

### Phase 3: Governance + Approval

**Duration:** 2 weeks

- Authority matrix enforcement
- Pending approval queue (UI + API)
- Budget enforcement (block over-spend)
- Configurable policies per tenant

### Phase 4: Knowledge Graph + Memory

**Duration:** 3-4 weeks

- Unified DNA query interface
- Workflow DNA creation + learning
- Project DNA
- Memory retrieval pipeline
- Enhanced RAG (multi-source context injection)

### Phase 5: MCP + External Integration

**Duration:** 2-3 weeks

- MCP server implementation
- Tool definitions (read + write)
- Authentication for MCP clients
- Streaming support
- Documentation for external AI integration

### Phase 6: Ọbalúayé + Reliability

**Duration:** 2 weeks

- Background supervisor process
- Health polling for all providers
- Circuit breaker pattern
- Auto-retry with backoff
- Alerting (email, webhook)

### Phase 7: Workflow Intelligence

**Duration:** 3-4 weeks

- Intelligent parameter selection
- Workflow DNA learning from feedback
- Multi-LoRA balancing
- Cost-quality optimization
- Auto-configuration for new talents

### Phase 8: Multi-Worker Session Orchestration + Vercel Parity

**Duration:** 3-4 weeks

- Session-level worker management
- Multi-worker coordination
- Intelligent model placement
- Cross-worker pipeline (image → video → audio)
- Voice Sequencer: long-form audio stitching (see Section 26)

**Vercel Full Parity (Critical for SaaS):**

The web server on Vercel must be 100% stateless. All execution happens on GPU workers or via external APIs.

| Current (broken on Vercel) | Fix |
|---------------------------|-----|
| SSH commands from web server | Worker API: GPU workers expose HTTP endpoints, web server calls them |
| Background threads (training, generation) | Async job system: submit to Supabase job queue, worker picks up |
| Local ffmpeg | FFmpeg runs on GPU worker, results uploaded to B2 |
| Local file saves | All saves go to B2, served via signed URLs |
| In-memory state (sessions, costs) | All state in Supabase (already partially done) |
| Ollama on localhost | Remote Ollama on GPU worker via tunnel, or cloud LLM fallback |

Architecture for Vercel:
```
Vercel (Frontend + API)
    │
    ├── Supabase (DB + Realtime + Auth)
    │       └── Job queue table (status polling via Realtime)
    │
    ├── GPU Worker(s) (Vast.ai / RunPod)
    │       └── HTTP API on worker: /generate, /train, /ffmpeg, /tts
    │       └── Results → B2
    │       └── Status → Supabase job record
    │
    └── External APIs (ElevenLabs, OpenAI, Anthropic)
            └── Direct calls from Vercel (no GPU needed)
```

Key principle: Vercel serverless functions have a 60s timeout. Any operation that takes longer MUST be dispatched to a worker and polled via Supabase.

---

## 21. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Over-engineering before product-market fit | High | Phase 0 (stabilize) must complete first. Build only what users demand. |
| LLM costs scaling with usage | Medium | Provider Router optimizes for cost. Local Ollama for most requests. Budget enforcement. |
| Governance too restrictive (user friction) | Medium | Sensible defaults. Make everything configurable. Default to permissive for solo users. |
| Agent architecture too complex to debug | Medium | Decision traceability provides full audit. Start with 3 agents, grow to 9. |
| MCP protocol immaturity | Low | Build as HTTP API first, add MCP transport layer later. |
| Knowledge graph performance at scale | Medium | pgvector handles millions of embeddings. Relational queries are fast with indexes. |
| Multi-worker cost explosion | High | Budget guard blocks overspend. Auto-shutdown idle workers. Daily cap. |
| Single point of failure (Gateway) | Medium | Stateless design. Can run multiple instances behind load balancer. |
| Migration disruption to existing users | Medium | No breaking changes. Gateway wraps existing APIs. Old endpoints remain. |

---

## 22. Architecture Challenges & Open Questions

### Challenge 1: Agent Council Size

9 agents may still be too many for initial implementation. Consider starting with 3:
- Èṣù (routing + coordination)
- Òrúnmìlà (planning + reasoning)
- Ògún (infrastructure + execution)

Add others as specific needs arise.

### Challenge 2: LLM Quality for Planning

The current keyword-based planner is fast but crude. Moving to LLM-based planning requires:
- Reliable tool-use support from the LLM
- Structured output parsing
- Graceful degradation when LLM is unavailable

Recommendation: Keep keyword planner as fallback. LLM planner as upgrade path.

### Challenge 3: Real-Time vs Batch Intelligence

Some decisions are real-time (model selection during generation). Others are batch (workflow DNA learning from historical feedback). The architecture must support both without blocking the hot path.

### Challenge 4: Multi-Tenant Knowledge Isolation

The knowledge graph must never leak information across tenants. Even vector similarity search must be scoped by `org_id`. This is already handled by Supabase RLS but must be explicitly designed into every new table and query.

### Challenge 5: Ọbalúayé — Unified Reliability Supervisor

Ọbalúayé is the single reliability supervisor. It uses rule-based logic for mechanics (health checks, retries, circuit breakers) and can optionally invoke an LLM for pattern analysis when available. One system, not two overlapping ones.

### Challenge 6: Session Planning UX — Ask Before Allocating

The system should not silently spin up expensive GPU workers. Before a heavy session, the AI should ask:

> "What kind of session are we having today? Image generation, video, training? Which model do you prefer? This helps me allocate the right resources and keep costs down."

Based on the answer:
- Image-only session → load appropriate checkpoint, keep video models cold
- Video session → provision video-capable worker, pre-load WAN 2.2
- Training session → provision training worker (RunPod persistent preferred)
- Mixed → explain tradeoffs, let user decide priority

The AI also scales DOWN proactively:
- Detects reduced need (user switches from generation to browsing/editing)
- Suggests releasing GPU worker after N minutes idle
- Archives models not needed for current session type

### Challenge 7: Unified Brain vs Separate Modes

The current Brain has 6 modes (Creative Chat, Prompt Engineer, Script Writer, Story Assistant, Production Advisor, Image Analyzer). These should remain as **specialized personas within one unified Brain**, not separate bots.

The user selects a mode to focus the Brain's personality and expertise. Under the hood, the same AIOS intelligence powers all modes — the mode just changes the system prompt and which tools are surfaced prominently.

Key UX requirement: Users need **discoverability of capabilities**. When they select "Creative Chat" they should see hints about what the Brain can do in prompt engineer mode, script mode, etc. A capabilities panel or contextual suggestions ensures users don't miss features just because they're in the wrong mode.

Start with 3 Council agents. Scale to 9 as specific needs arise and prove themselves in production.

---

## 23. Migration Strategy

### Principle: Additive, Never Destructive

```
Phase 1: Add Gateway alongside existing Brain endpoints (both work)
Phase 2: New features built on Gateway (existing features untouched)
Phase 3: Gradually migrate existing consumers to Gateway
Phase 4: Deprecate old endpoints (90-day notice)
Phase 5: Remove old endpoints
```

### Backward Compatibility Guarantees

- `/api/v1/brain/*` endpoints continue working throughout migration
- `/api/v1/generate/*` endpoints continue working
- All current frontend code works without changes until explicitly migrated
- Database schema changes are additive (new tables/columns only)

---

## 24. Documentation Update Plan

| Document | Update Needed |
|----------|--------------|
| `ARCHITECTURE.md` | Add AIOS layer to system diagram |
| `.kiro/steering/architecture-principles.md` | Add AIOS principles |
| `.kiro/steering/llm-strategy.md` | Update with Provider Router |
| `docs/AI_INTELLIGENCE.md` | Mark as superseded by AIOS spec |
| `docs/AUTONOMOUS_STUDIO.md` | Mark departments as absorbed into Council |
| New: `docs/architecture/AIOS_GATEWAY.md` | Detailed Gateway spec |
| New: `docs/architecture/AIOS_AGENTS.md` | Agent Council specifications |
| New: `docs/architecture/AIOS_MCP.md` | MCP integration guide |
| New: `docs/architecture/AIOS_GOVERNANCE.md` | Approval & authority model |

---

## 25. Success Criteria

AIOS is successful when:

1. Any LLM provider can be swapped without changing application logic
2. External AI (Claude, ChatGPT) can perform all operations a native user can
3. Every AI decision has a traceable reasoning chain
4. Destructive actions are impossible without explicit human approval
5. The system degrades gracefully when all LLM providers are unavailable
6. New agents can be added without modifying existing ones
7. Cost never exceeds configured budgets regardless of AI behavior
8. Multi-tenant isolation is absolute — verified by automated tests
9. The platform runs with zero LLM dependency for core operations (generation, storage, training still work — only intelligence features degrade)

---

## 26. Voice Sequencer — Long-Form Audio from Short Chunks

### Problem

MOSS-TTS (and most TTS models) generate best in short segments (6-30 seconds). Users need 5+ minute narrations for videos, podcasts, and long-form content.

### Architecture: Chunk → Generate → Stitch

```
User inputs full script (5 min narration)
    │
    ▼
1. Text Splitter: break at sentence boundaries into 20-30s chunks
    │
    ▼
2. Per-chunk generation (parallel where possible):
   - Same voice reference for consistency
   - Per-chunk emotion/speed annotations (optional)
   - Retry individual chunks on quality failure
    │
    ▼
3. Audio Stitcher: concatenate with 50ms crossfade between chunks
    │
    ▼
4. Final output: one continuous audio file
    │
    ▼
5. Timeline mapping: each chunk maps to video timecodes
   - Enables per-sentence lip sync
   - Enables per-sentence editing (change one line, regenerate one chunk)
```

### Voice Consistency Guarantee

All chunks use the same:
- Voice reference (B2 URL to the voice sample)
- Speed setting
- Language
- Provider settings

This ensures the voice doesn't drift between chunks.

### Video Association

```python
@dataclass
class VoiceSequence:
    id: str
    talent_id: str
    total_duration: float
    chunks: list[VoiceChunk]
    final_audio_url: str  # B2 URL to stitched output

@dataclass  
class VoiceChunk:
    index: int
    text: str
    start_time: float      # Position in final audio
    end_time: float
    audio_url: str         # Individual chunk B2 URL
    emotion: str           # neutral, excited, serious, etc.
    speed: float           # 0.8-1.3
```

### User Experience

- User pastes/writes full script
- Selects voice (from talent's assigned voices)
- Optionally annotates emotions per paragraph
- Clicks "Generate Full Narration"
- Progress bar shows chunk-by-chunk progress
- Preview plays stitched result
- "Save to Library" persists to B2 + links to talent/project

---

## 27. Ìṣẹ́ — Quality & UAT Intelligence Agent

### Purpose

Ìṣẹ́ (Yoruba: "work/craft/quality") is an autonomous quality agent that learns how the app should behave and continuously verifies it.

### Responsibilities

| Domain | Actions |
|--------|---------|
| Automated UAT | Run Playwright test suites on demand |
| Regression Detection | Compare current behavior to "last known good" |
| UX Audit | Crawl all pages, check for dead buttons, missing feedback, broken links |
| Research | Monitor CivitAI, HuggingFace, GitHub for new models/tools/nodes |
| Recommendations | "New FLUX Schnell available — 10x faster for drafts" |
| Code Health | Scan for dead code, unused endpoints, simulation fallbacks |
| Learning | Build knowledge base of expected behavior over time |

### How It Works

```
On demand (user clicks "Run UAT" or scheduled weekly):
    │
    ▼
1. Run Playwright suite → collect pass/fail results
    │
    ▼
2. Compare to previous run → identify new failures (regressions)
    │
    ▼
3. For each regression: use LLM to analyze the error context
    │
    ▼
4. Produce report:
   - "Training page submit now returns 400 — was 201 last week"
   - "3-dot menu on talent page still non-functional"
   - "New ComfyUI node 'UNETLoader2' available — supports FLUX Schnell"
    │
    ▼
5. Store findings in Supabase for tracking over time
```

### Research Feed

Ìṣẹ́ periodically checks (configurable: daily/weekly):
- CivitAI trending models API
- HuggingFace new model releases (diffusion, TTS, video)
- ComfyUI Manager node list updates
- GPU pricing changes on Vast.ai and RunPod
- Community best practices (curated RSS/feeds)

Produces recommendations — never auto-installs anything.

### Not a Replacement for Human Testing

Ìṣẹ́ catches regressions and obvious issues. It doesn't replace:
- Creative quality judgment (is this image good?)
- Business logic validation (is the billing correct?)
- Security review

### Authority Level

- Can: Run tests, read code, search internet, produce reports
- Cannot: Modify code, deploy changes, install models, spend money

---

*End of Architecture Design Epic*
