# Brain Wiring — One-Pager (Decision-Ready)

Status: DRAFT for Gary's call | Owner: @ai-studio | Date: 2026-09-27
Ask: Green-light "Wire the Brain" (MVP) — ~4-6 dev days, near-zero cost, flips the platform's headline promise from pitch to product.

---

## 1. THE GAP (grounded in code, not vibes)

The Brain is a beautiful storage layer with no brain. Existing and verified today:

  ALREADY BUILT:
  - backend/app/services/brain_conversation_service.py — full CRUD, per-user/org scoping (R93.1), last-20-messages context window, 200-msg cap (R25.16)
  - backend/app/services/brain_memory_service.py — COMPLETE provenance-tracked memory: USER_CONFIRMED > OBSERVED > IMPORTED > INFERRED > SUGGESTED, BrainUserMemory table, active-memory-for-context injection, upgrade-only provenance
  - backend/app/api/v1/endpoints/brain_conversations.py — list/create/get/messages endpoints
  - frontend/src/app/brain/ — substantial chat UI: ChatThread, Composer, use-brain-chat, use-brain-memory, mode-selector, context-sidebar, session-list, ApprovalCard, UseAsPromptButton
  - backend/brain/llm_provider.py — provider abstraction (ollama/openai/anthropic) + per-mode system prompts

  WHAT'S MISSING (the actual work):
  1. The message endpoint never calls an LLM. Chat is CRUD-only; "the Brain talks back" does not exist.
  2. No model routing. llm_provider.py default is OPENAI_MODEL=gpt-4o — the 25x-cost trap. Must never ship that default.
  3. No session compaction. At 200 messages the API hard-422s. The roadmap's "summarize -> brain_user_memory -> reset" is design, not code.
  4. Memory exists but is not injected into any conversation reply.

## 2. SCOPE — MVP (what "wire" means)

  A. Chat completion: POST message -> assemble context (last 20 msgs + active memory by provenance + mode prompt + AIOS persona) -> call LLM -> persist actor="brain" reply -> return.
  B. Model routing mix: simple/casual turns -> cheap path; complex creative turns -> DeepSeek Flash. NEVER gpt-4o as default.
  C. Session compaction: at 200-msg cap, LLM-summarize -> write to BrainUserMemory (provenance=INFERRED + confidence) -> reset raw convo. Never blunt-clear.
  D. Persona: inject AIOS_SOUL.md-style persona (reuse existing persona.py::inject_persona) so the Brain speaks in the product's voice, per-mode.

  OUT OF SCOPE for MVP: function calling, MCP tools, real Hermes-per-tenant embedding, BYOLLM, streaming polish (nice-to-have, not gating).

## 3. LEVEL OF EFFORT (realistic, focused dev sessions)

  Item                          | Days
  ------------------------------|------
  A. Chat completion wiring     | 1.0-1.5
  B. Router + DeepSeek provider | 0.5-1.0
  C. Session compaction         | 1.0-1.5
  D. Persona injection          | 0.5
  QA + capability reg flip      | 0.5
  TOTAL                         | ~4-6 days

  Why so small: the hard parts (memory provenance, scoping, UI, provider abstraction) already exist. This is glue + routing + compaction, not new architecture.

## 4. COST MATH (per 20-turn conversation, validated 2026-08)

  Path                          | Cost/convo | Notes
  ------------------------------|------------|-----
  Local Ollama 8B on fleet GPU  | ~$0.00     | Rides idle VRAM — but see risk: NOT on the A6000 during H3 workloads
  DeepSeek V4 Flash (routed)    | ~$0.003    | ~$0.006 with 0% cache hits; ~70% cache hits typical
  Hermes 4 70B (Nous)           | ~$0.006    |
  gpt-4o-mini                   | ~$0.008    |
  gpt-4o                        | ~$0.135    | THE TRAP — 25x the cheap path for same quality. Default today. Kill it.

  Simple-turn route: target $0 (local 8B) or ~$0.003 (DeepSeek Flash) per complex turn.
  Typical blended Brain convo target: under $0.01. At $0.01, 50k convos/mo = $500/mo. Trivial vs. the pricing envelope.

  GPU break-even: ~36k convos/mo for a dedicated brain GPU; under that, DeepSeek API is cheaper. MVP = API-only, zero GPU changes.

  RISK (important): the current fleet is ONE A6000 and H3 needs ~43GB of 48GB. There is NO idle VRAM on that box while generating. Local 8B brain must NOT run there during H3 batches (that's literally the Ollama-squat footgun we kill in h3_prep.sh). Local-8B routing only lands when the fleet grows (4090-era boxes had 12-16GB free between jobs).

## 5. WHAT "DONE" LOOKS LIKE (acceptance criteria)

  1. User sends message in Brain chat -> thoughtful production-aware reply in <5s (DeepSeek Flash), in the AI Studio persona, mode-appropriate.
  2. Reply persists as actor="brain"; conversation reloads with full history.
  3. Simple vs complex routing works; NO gpt-4o anywhere in the default path.
  4. At 200-msg cap: auto-compaction instead of 422. Summary lands in brain_user_memory with provenance=INFERRED + confidence; raw convo resets cleanly.
  5. Memory injection orders by provenance (USER_CONFIRMED surfaces first) — already built, now actually used.
  6. Capability registry: brain-chat flips PARTIAL -> PRODUCTION. Demo badge is session-stable (no flicker during presentations).
  7. Cost per convo logged and under $0.01 typical.

## 6. WHY THIS FIRST (vs. Talent UI, vs. Showrunner)

  - It is the episode-11 story made real: "persistent memory that survives episode 60" is the wedge vs. the free pipeline, and right now a creator can't even have a conversation that remembers.
  - Cheapest LOE of the three (Talent UI #200 is ~1-2 weeks; Showrunner is bigger).
  - Reuses what's already shipped — this is glue, not architecture.
  - Unlocks later phases: BYOLLM, Hermes-per-tenant, MCP tools all bolt onto the router we build here.

## 7. DECISIONS NEEDED FROM GARY

  1. Green-light Brain wiring MVP (4-6 days)? — recommend YES.
  2. Order: Brain MVP first, Talent->LoRA UI (#200) second, Showrunner third? — recommend yes.
  3. DeepSeek Flash key already in .env? (BRAIN_PROVIDER / DEEPSEEK key — verify before starting; I will not echo secrets.)
  4. Streaming (token-by-token) required for v1, or plain reply is fine? — recommend plain reply v1, streaming v1.1.

— @ai-studio, 2026-09-27