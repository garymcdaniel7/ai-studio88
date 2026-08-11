# Capability Map — AI Studio (Story 132)

**Audit date:** 2026-08-05
**Auditor:** Kiro (automated)
**Repository:** garymcdaniel/ai-studio88
**Schema migrations:** 49 files (000–039)
**Backend routers:** 20 mounted
**Frontend pages:** 23
**Provider pattern:** simulation (default) ↔ production (env-toggled)

---

## Classification Legend

| Code | Meaning |
|------|---------|
| **PROD** | Production-supported — real provider connected, tested |
| **PARTIAL** | Backend exists, frontend incomplete or provider partially wired |
| **SIM** | Simulated — backend returns mock data, no real provider |
| **BACKEND-ONLY** | API exists, no frontend exposure |
| **UNUSED** | Schema/code exists, never called by any route or UI |
| **DEPRECATED** | Superseded by newer implementation |
| **UNVERIFIED** | Cannot confirm status without runtime/DB inspection |

---

## 1. Core Platform

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Talent CRUD | `talent` (001) | api_v1 `/talent` | `/talent` page | **PROD** | Supabase queries, auth-gated |
| Jobs lifecycle | `jobs` (001) | api_v1 `/jobs` | `/production` page | **PROD** | Full CRUD, status tracking |
| Assets management | `assets` (001) | api_v1 `/assets` | `/assets` page | **PROD** | B2 upload/delete, metadata |
| Projects | `projects` (028) | api_v1 `/projects` | `/projects` page | **PROD** | Tenant-scoped, detail view |
| Models registry | `models` (006) | api_v1 `/models` | `/models` page | **PROD** | Seed data, capabilities |
| Workflows | `workflows` (002) | api_v1 `/workflows` | `/workflows` page | **PARTIAL** | CRUD exists, execution via ComfyUI only when worker online |
| Workers | `workers` (007) | api_v1 `/workers` | `/admin/fleet` | **PROD** | Vast.ai integration verified |
| Organizations | `org_members` (029) | company router | `/settings` | **PARTIAL** | Schema + RLS, limited UI |

## 2. Generation & AI

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Image generation (ComfyUI) | `jobs` | engine/ + infrastructure/generate | `/create` page | **PARTIAL** | Works when GPU worker is online; simulation fallback |
| Image generation (SDXL Turbo) | — | engine/providers/ | `/create` | **PARTIAL** | Model cached in B2, needs worker |
| Image generation (Flux Dev) | — | engine/providers/ | `/create` | **PARTIAL** | Model cached, B2 cap limits |
| Video generation (WAN 2.1) | `video_projects` (009) | video/router | `/create` video tab | **SIM** | ComfyUI workflow exists, provider simulated by default |
| Video generation (LTX) | — | video/router | — | **SIM** | Workflow referenced but not cached |
| LoRA training | `training_*` (008) | training/router | `/training` page | **PARTIAL** | Full lifecycle, Vast.ai provider exists but SimulationProvider default |
| Voice synthesis (ElevenLabs) | `voice_*` (010) | audio/router | `/create` audio tab | **PARTIAL** | Provider wired, API key permission issue |
| Music generation (Suno) | — | audio/suno_provider | `/create` audio tab | **SIM** | Provider skeleton, no key |
| Brain chat (Ollama/LLM) | `brain_conversations` (013) | brain/router + aios/gateway | `/brain` page | **PROD** | Ollama local verified, AIOS gateway routes |
| Prompt engineering | — | brain modes | `/brain` prompt_engineer mode | **PROD** | System prompts, mode-based |
| Generation feedback (durable) | `generation_feedback` (003) | api_v1 `/feedback/durable` | FeedbackButtons component | **PROD** | Story 107 complete, idempotent |
| Generation feedback (legacy) | `generation_feedback` (003) | api_v1 `/feedback` | — | **DEPRECATED** | Replaced by durable feedback |

## 3. Creative Intelligence

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Creative DNA | `creative_dna` (003) | api_v1 `/creative-dna` | — | **BACKEND-ONLY** | Schema + CRUD, no UI surface |
| Style preferences | `style_preferences` (003) | — | — | **UNUSED** | Schema exists, no router endpoint |
| Prompt history | `prompt_history` (003) | — | — | **UNUSED** | Schema exists, no router |
| Continuity notes | `continuity_notes` (004) | database.py queries | — | **BACKEND-ONLY** | Used by story engine internally |
| Creative rules | `creative_rules` (004) | database.py queries | — | **BACKEND-ONLY** | Used by generation engine |
| Creative recipes | `creative_recipes` (027) | api_v1 recipes endpoints | `/create` | **PARTIAL** | CRUD, RLS (031), used in generation |
| Agent learning (DNA) | in-memory | aios/learning.py | FeedbackButtons | **SIM** | In-memory singleton, not persisted to DB |

## 4. Story & Production

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Story engine (universes, characters, episodes, scenes, shots) | `universes`, `characters`, `episodes`, `scenes`, `shots` (005) | api_v1 story endpoints | — | **BACKEND-ONLY** | Full schema + CRUD, no dedicated UI page |
| Story memory | `story_memory` (005) | api_v1 | — | **BACKEND-ONLY** | Schema exists, wired to story endpoints |
| Storyboard production | `storyboard_*` (035 RLS) | api_v1 storyboard endpoints | — | **BACKEND-ONLY** | CRUD + RLS, generation hooks |
| Production intelligence | tables (014) | production_intelligence/router | `/production` page | **PARTIAL** | Router mounted, page exists but limited data |
| Performance engine | tables (011) | performance/router | `/analytics` page | **PARTIAL** | Router mounted, analytics page shows stats |
| Cinematic studio | tables (016) | cinematic/router | — | **BACKEND-ONLY** | Schema + router, no frontend page |

## 5. Publishing & Social

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Social publishing | `social_*` (012) | publishing/router | `/publish` page | **SIM** | Webhook-based provider, simulation default |
| Social OAuth | `social_connections` (021) | publishing/oauth router | `/publish` | **PARTIAL** | OAuth flow exists, credentials table (035) |
| Workspace credentials | `workspace_credentials` (034) | — | `/admin/keys` | **PARTIAL** | Schema + admin page, scoped storage |
| Campaign calendar | — | creator_os/router | — | **BACKEND-ONLY** | Router mounted, calendar endpoints |
| Brands & teams | — | creator_os/router | — | **BACKEND-ONLY** | Router mounted, CRUD endpoints |

## 6. Asset Intelligence

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Visual DNA | tables (015) | asset_intelligence/router | `/assets` (partial) | **PARTIAL** | Router mounted, limited UI |
| Collections | tables (015) | asset_intelligence/router | — | **BACKEND-ONLY** | CRUD exists |
| Talent relationships | tables (010) | relationship_mutations.py | — | **BACKEND-ONLY** | Mutation logic exists |
| Object DNA | tables (018) | object_intelligence/router | — | **BACKEND-ONLY** | Schema + router |
| Product DNA | tables (018) | object_intelligence/router | — | **BACKEND-ONLY** | Schema + router |
| Digital twins | tables (018) | object_intelligence/router | — | **BACKEND-ONLY** | Schema + router |
| Scene composer | — | object_intelligence/router | — | **BACKEND-ONLY** | Endpoints exist |
| Asset provenance | `asset_provenance` (039) | — | — | **UNUSED** | Schema only, no router |

## 7. Infrastructure & Operations

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Worker orchestrator (Connection Race) | tables (019) | infrastructure/router | `/admin/fleet` | **PROD** | Vast.ai + RunPod verified |
| Provider reputation | tables (019) | infrastructure/provider_reputation | `/admin/fleet` | **PROD** | Learning engine, blacklist |
| Cost intelligence | `cost_*` (020) | infrastructure/cost_intelligence | `/admin/fleet` | **PROD** | Budget tracking, per-org |
| Render fleet | — | infrastructure/render_fleet | `/admin/fleet` | **PROD** | Multi-worker dispatch |
| Status dashboard | — | infrastructure/status_dashboard | `/admin/health` | **PROD** | Aggregated health |
| Admin settings | — | infrastructure/admin_settings | `/admin` | **PROD** | Service connections toggle |
| Infrastructure authorization | tables (036) | infrastructure/authorization | — | **PROD** | Capability-based RBAC |
| Batch generation | `batch_*` (037) | — | — | **UNUSED** | Schema exists, no router |

## 8. AIOS (AI Operating System)

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| AIOS Gateway (Hermes chat) | `aios_*` (024) | aios/gateway.py | `/brain` page | **PROD** | Chat routing, provider selection |
| Governance (approvals) | `durable_approvals` (036) | aios/governance/ | `/brain` ApprovalCard | **PROD** | Inline approve/reject in chat |
| Governance policies | `governance_policies` (036) | aios/governance/policies | — | **PARTIAL** | Schema + middleware, no admin UI |
| Knowledge graph | `knowledge_*` (026) | aios/knowledge/ | `/admin/knowledge` | **PARTIAL** | Schema + module, admin page exists |
| Council (Orunmila, ESU) | — | aios/council/ | — | **BACKEND-ONLY** | Agent orchestration, no direct UI |
| Agent DNA | — | aios/agent_dna.py | — | **BACKEND-ONLY** | Personality system |
| MCP server | — | aios/mcp/server.py | — | **BACKEND-ONLY** | Model Context Protocol bridge |
| Brain collections | `brain_collections` (022) | brain/router | `/brain` collections UI | **PROD** | CRUD + localStorage cache |
| Brain embeddings | `brain_embeddings` (023) | — | — | **UNUSED** | Schema exists, no implementation |
| Memory namespaces | tables (037) | — | — | **UNUSED** | Schema exists, no router |
| Ise (Obaluaye) health monitor | — | aios/obaluaye/ | `/admin/ise` | **PARTIAL** | Background monitor, UAT runner |

## 9. Company & Multi-tenant

| Capability | Schema | Backend | Frontend | Classification | Evidence |
|-----------|--------|---------|----------|---------------|----------|
| Company OS | tables (017) | company/router | — | **BACKEND-ONLY** | Multi-brand, team management |
| Org members | `org_members` (029) | — | `/settings` | **PARTIAL** | Schema + RLS, limited frontend |
| RLS policies (all tables) | (030–036) | Supabase | — | **PROD** | 12+ RLS migration files |
| Deletion lifecycle | `deletion_*` (038) | — | — | **UNUSED** | Schema for soft delete, no router |
| Tenant isolation (AIOS) | tables (032) | middleware | — | **PROD** | AIOS-specific tenant isolation |

---

## 10. Frontend Pages vs Backend Coverage

| Frontend Page | Backend Coverage | Status |
|--------------|-----------------|--------|
| `/` (Home) | Static dashboard | **PROD** |
| `/brain` | AIOS gateway + brain router | **PROD** |
| `/create` | generation engine + recipes | **PARTIAL** (needs GPU worker) |
| `/talent` | api_v1 talent CRUD | **PROD** |
| `/assets` | api_v1 assets + B2 | **PROD** |
| `/models` | api_v1 models registry | **PROD** |
| `/training` | training router (full lifecycle) | **PARTIAL** (simulation default) |
| `/production` | production_intelligence | **PARTIAL** |
| `/publish` | publishing router | **SIM** |
| `/analytics` | performance router | **PARTIAL** |
| `/workflows` | api_v1 workflows | **PARTIAL** |
| `/projects` | api_v1 projects | **PROD** |
| `/editor` | — | **UNVERIFIED** (visual editor) |
| `/settings` | company router | **PARTIAL** |
| `/login` | Supabase Auth | **PROD** |
| `/admin` | infrastructure router | **PROD** |
| `/admin/fleet` | infrastructure (launch/stop/status) | **PROD** |
| `/admin/health` | infrastructure/status_dashboard | **PROD** |
| `/admin/keys` | workspace_credentials | **PARTIAL** |
| `/admin/downloads` | — | **UNVERIFIED** |
| `/admin/ise` | aios/obaluaye | **PARTIAL** |
| `/admin/knowledge` | aios/knowledge | **PARTIAL** |

---

## 11. Orphan Schema (no API or UI consumer)

| Table/Migration | Schema | Risk | Recommendation |
|----------------|--------|------|----------------|
| `style_preferences` | 003 | Low | Wire to creative DNA UI or drop |
| `prompt_history` | 003 | Low | Wire to brain memory or analytics |
| `brain_embeddings` | 023 | Medium | RAG pipeline dependency — implement or document deferral |
| `memory_namespaces` | 037 | Low | Brain memory scoping — implement when memory is production |
| `batch_generation` | 037 | Medium | Planned for multi-image jobs — implement endpoint |
| `asset_provenance` | 039 | Low | Lineage tracking — wire to generation output |
| `deletion_lifecycle` | 038 | Medium | Soft-delete infrastructure — wire to all CRUD |

## 12. Orphan UI (frontend page with no or incomplete backend)

| Page | Gap | Priority |
|------|-----|----------|
| `/editor` | No backend editor API found | Low (visual tool, may be standalone) |
| `/admin/downloads` | No download management endpoint found | Low |
| `/publish` | Simulation-only provider | Medium (needs real social API integration) |

## 13. Simulated Capabilities (production-ready when provider enabled)

| Capability | Toggle Env Var | Production Provider | Status |
|-----------|---------------|-------------------|--------|
| Image generation | `GENERATION_PROVIDER=comfyui` | ComfyUI on Vast.ai | Ready (needs worker) |
| LoRA training | `TRAINING_PROVIDER=vast` | SimpleTuner on Vast.ai | Ready (needs worker) |
| Video generation | `GENERATION_PROVIDER=comfyui` | WAN 2.1 on ComfyUI | Ready (needs worker + model) |
| Voice synthesis | `VOICE_PROVIDER=elevenlabs` | ElevenLabs API | Needs key permission fix |
| Music generation | `MUSIC_PROVIDER=suno` | Suno API | Needs API key |
| Social publishing | `PUBLISHING_PROVIDER=webhook` | Platform webhooks | Needs OAuth setup |
| LLM (Brain) | `AI_PROVIDER=ollama` | Ollama (local/GPU) | **PROD** (working) |

---

## 14. Follow-Up Stories (Canonical 12-Section Format)

### FU-132-A: Wire orphan schema to product features
- Priority: Medium
- Tables: style_preferences, prompt_history, asset_provenance, deletion_lifecycle
- Action: Create API endpoints and connect to existing UI or create minimal UI

### FU-132-B: Batch generation endpoint
- Priority: Medium
- Schema: batch_generation (037)
- Action: Create router, connect to generation platform, add to Create page

### FU-132-C: Brain embeddings / RAG pipeline
- Priority: High (enables semantic search across conversations)
- Schema: brain_embeddings (023)
- Action: Implement embedding generation + vector search

### FU-132-D: Expose Story Engine in frontend
- Priority: Medium-High (major backend investment with no UI)
- Backend: Full universe/character/episode/scene/shot CRUD exists
- Action: Create `/story` page or integrate into Production

### FU-132-E: Expose Object Intelligence in frontend
- Priority: Low (niche feature)
- Backend: Product DNA, Digital Twins, Scene Composer all exist
- Action: Create admin or specialized page

### FU-132-F: Complete social publishing integration
- Priority: High (customer-facing feature)
- Backend: OAuth + webhook provider exist
- Action: Connect real platform APIs, test OAuth flow end-to-end

### FU-132-G: Fix ElevenLabs voice provider permissions
- Priority: Medium
- Status: Key exists but permissions insufficient
- Action: Regenerate API key with correct scopes

---

## 15. Risk Summary

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Agent learning is in-memory only (not persisted) | Medium | Persist to Supabase or add persistence warning in UI |
| 7 orphan schema tables may confuse future developers | Low | Document in this map, create cleanup stories |
| Story Engine has ~50 endpoints with no UI | Medium | Either expose in UI or mark as API-only in docs |
| Simulation mode hides broken integrations | Medium | Add provider health check on admin dashboard |
| Brain embeddings schema unused | Low | Mark as future/planned in schema comments |

---

*Generated by Story 132 capability audit. Re-run when schema or routers change significantly.*
