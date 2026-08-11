# Domain Model Overlap Map — Story 011

**Status: DECISION REQUIRED** — overlap mapped, canonical choices need product-owner approval.

---

## 1. Brain vs AIOS

### Overlap Description

Two parallel subsystems manage AI conversations, sessions, and memory:

| Brain (migration 013+) | AIOS (migration 024+) | Overlap |
|------------------------|----------------------|---------|
| `brain_sessions` | `aios_sessions` | Session containers |
| `brain_messages` | `aios_messages` | Message history |
| `brain_memory` | — | Long-term memory |
| `brain_conversations` | — | Conversation grouping |
| `brain_collections` | — | Message collections |
| `brain_embeddings` | — | Vector search |
| `brain_plans` | — | Planning outputs |
| — | `aios_decisions` | Autonomous decisions |
| — | `aios_approvals` | Governance approvals |
| — | `aios_policies` | Policy rules |
| — | `workflow_dna` | Learned workflow patterns |

### Code References

| System | Active Code Files |
|--------|------------------|
| Brain | `brain/router.py`, `brain/rag.py`, `memory_service.py`, `conversation_models.py`, `deletion_lifecycle.py` |
| AIOS | `aios/sessions.py`, `aios/decisions.py`, `aios/governance/*` (6 files), `aios/hermes/*`, `aios/orchestration/*`, `aios/tenant_service.py`, `intelligence_runtime.py`, `governance_policy.py` |

### Analysis

- **Brain** = user-facing chat interface (Frontend "Brain" page). Stores conversations, memory, RAG embeddings.
- **AIOS** = autonomous agent system (governance, decisions, approvals, multi-agent orchestration). More complex, newer.
- **Overlap is structural**: both have sessions + messages. But they serve different purposes.
- **Key question**: Should AIOS conversations use `brain_conversations`/`brain_messages` or maintain separate `aios_sessions`/`aios_messages`?

### Options (Decision Required)

| Option | Pros | Cons |
|--------|------|------|
| A: Brain is canonical for conversations, AIOS extends it | Single message store, shared memory, unified search | AIOS governance needs different metadata per message |
| B: Both remain separate (current) | Clean separation of concerns, AIOS has governance fields | Duplicate session/message patterns, two memory systems |
| C: Merge into unified "Conversations" with type discriminator | One table, reduced schema, flexible | Migration complexity, mixed governance |

**Recommendation:** Option B (keep separate) — they serve genuinely different purposes. Brain is user-interactive chat; AIOS is autonomous agent with governance. Add a shared memory layer that both can read.

---

## 2. Timeline vs Cinematic

### Overlap Description

Two table families describe temporal content sequences:

| Video Pipeline (migration 009) | Cinematic Studio (migration 016) | Overlap |
|-------------------------------|----------------------------------|---------|
| `video_projects` | `sequences` | Project containers |
| `video_shots` | — | Individual shots |
| `video_renders` | `cinematic_renders` | Render outputs |
| `timeline_tracks` | `cinematic_tracks` | Multi-track composition |
| `timeline_clips` | `cinematic_items` | Items on tracks |
| `timeline_exports` | — | Export records |
| — | `cinematic_timelines` | Timeline metadata |
| — | `storyboard_panels` | Pre-production panels |
| — | `editing_operations` | Edit history |

### Code References

| System | Active Code Files |
|--------|------------------|
| Video | `video/router.py`, `data_access.py` |
| Cinematic | `cinematic/router.py`, `aios/learning.py`, `aios/orchestration/interceptor.py` |

### Analysis

- **Video Pipeline** = simpler, focused on rendering video from ComfyUI (WAN 2.1). Tracks → Clips → Export.
- **Cinematic Studio** = richer, production-oriented. Sequences → Timelines → Tracks → Items → Renders + storyboard panels + edit history.
- **Overlap is significant**: `timeline_tracks` vs `cinematic_tracks`, `timeline_clips` vs `cinematic_items`, `video_renders` vs `cinematic_renders`.
- The cinematic system appears to be a superset of the video pipeline.

### Options (Decision Required)

| Option | Pros | Cons |
|--------|------|------|
| A: Cinematic is canonical, video pipeline deprecated | One timeline system, richer features, storyboard integration | Video pipeline is simpler/faster for basic renders |
| B: Video is canonical for rendering, cinematic for editing | Clear boundary: render vs edit | Two render tables, confusing ownership |
| C: Merge into unified timeline with complexity flag | One system, backward compatible | Large migration, complex single table |

**Recommendation:** Option A (cinematic canonical) — it's a superset. Keep `video_projects` as a lightweight entry point that creates cinematic sequences internally. Deprecate `timeline_tracks`/`timeline_clips`/`timeline_exports`.

---

## 3. Voice/Audio Structure

### Overlap Description

Voice and audio are spread across multiple table families:

| Table | Migration | Purpose | Code References |
|-------|-----------|---------|-----------------|
| `voice_profiles` | 010 | Character voice definitions | `audio/router.py`, `audio/repository.py` |
| `voice_samples` | 010 | Voice sample files | `audio/router.py`, `talent_media_upload.py` |
| `audio_clips` | 010 | Generated audio output | `audio/router.py` |
| `lip_sync_jobs` | 010 | Lip sync processing | — |
| `music_tracks_db` | 010 | Music generation | — |
| `sound_effects` | 010 | SFX library | — |
| `voice_datasets` | (no RLS) | Training data | — |
| `voice_dna` | (no RLS) | Voice characteristics | — |
| `voice_training_jobs` | (no RLS) | Voice training lifecycle | — |
| `voice_versions` | (no RLS) | Voice model versions | — |
| `talent_voices` | (no RLS) | Talent ↔ voice mapping | `performance/router.py` |

### Analysis

- **Core voice** (`voice_profiles`, `voice_samples`) is actively used by `audio/` package.
- **Extended voice** (`voice_dna`, `voice_datasets`, `voice_training_jobs`, `voice_versions`) has no RLS and minimal code references — appears aspirational.
- **Audio production** (`music_tracks_db`, `sound_effects`, `lip_sync_jobs`) — referenced in knowledge graph but no active CRUD router.
- **`talent_voices`** links talent to voice profiles — used by performance engine.

### Options (Decision Required)

| Option | Pros | Cons |
|--------|------|------|
| A: Consolidate under voice_profiles + audio_clips | Simpler schema, clear ownership | Loses granular training/version tracking |
| B: Keep layered (core voice + training + production) | Supports future voice cloning pipeline | Many unused tables currently |
| C: Remove unused tables, keep only code-referenced ones | Reduces surface area | May need to re-create later |

**Recommendation:** Option B (keep layered) — voice cloning is a planned feature. Add RLS to the extended tables now, but don't remove them. Mark `lip_sync_jobs`, `music_tracks_db`, `sound_effects` as "future" and deprioritize.

---

## 4. Worker Registry/Session

### Overlap Description

| Table | Purpose | Code References |
|-------|---------|-----------------|
| `workers` | GPU worker registry (IP, status, GPU type) | `data_access.py`, `infrastructure/router.py`, `worker_lifecycle.py` |
| `worker_sessions` | Active work sessions on a worker | `data_access.py`, `worker_lifecycle.py` |
| `worker_connection_attempts` | SSH connection race log | `infrastructure/router.py` |
| `cost_records` | Cost per job/session | `data_access.py` |

### Analysis

- **No overlap** — these tables serve distinct purposes in a clear hierarchy: workers → sessions → cost records.
- `worker_connection_attempts` is infrastructure-only (connection race mode logging).
- All four are actively referenced in code.

### Conclusion

No action needed. This domain is well-structured.

---

## 5. Collections/Asset Grouping

### Overlap Description

| Table | Purpose | Code References |
|-------|---------|-----------------|
| `asset_collections` | Named groups of assets | `asset_intelligence/router.py` |
| `collection_items` | Items in a collection | `asset_intelligence/router.py` |
| `asset_relationships` | Typed relationships between assets | `data_access.py` |
| `brain_collections` | Brain message collections | `brain/router.py`, `conversation_models.py` |

### Analysis

- **`asset_collections` + `collection_items`** = generic asset grouping (albums, folders)
- **`brain_collections`** = brain-specific message organization (tagged conversations)
- **`asset_relationships`** = typed edges between assets (derived_from, variant_of, etc.)
- These serve different domains despite similar names.

### Conclusion

No true overlap — naming coincidence. Each serves a distinct purpose:
- `asset_collections` = user-facing asset organization
- `brain_collections` = brain-specific conversation organization
- `asset_relationships` = graph edges for lineage/provenance

No action needed.

---

## Summary Decision Matrix

| Domain | Overlap Type | Severity | Recommended Action | Decision Owner |
|--------|-------------|----------|-------------------|----------------|
| Brain vs AIOS | Structural (sessions/messages) | Medium | Keep separate, add shared memory layer | Gary |
| Timeline vs Cinematic | Significant (tracks/clips/renders) | High | Cinematic canonical, deprecate video timeline tables | Gary |
| Voice/Audio | Extended unused tables | Low | Keep layered, add RLS, mark unused as "future" | Gary |
| Workers | None | — | No action | — |
| Collections | None (naming coincidence) | — | No action | — |

---

## Tables Proposed for Deprecation (Pending Approval)

| Table | Superseded By | Migration Path |
|-------|--------------|----------------|
| `timeline_tracks` | `cinematic_tracks` | Add view alias, update video/router.py |
| `timeline_clips` | `cinematic_items` | Add view alias, update video/router.py |
| `timeline_exports` | `cinematic_renders` | Merge export metadata into renders |

## Tables Needing RLS (From Voice Overlap)

| Table | Status | Action |
|-------|--------|--------|
| `voice_datasets` | No RLS | Add in migration 040 wave 2 |
| `voice_dna` | No RLS | Add in migration 040 wave 2 |
| `voice_training_jobs` | No RLS | Add in migration 040 wave 2 |
| `voice_versions` | No RLS | Add in migration 040 wave 2 |
| `talent_voices` | No RLS | Add in migration 040 wave 2 |

---

## Follow-ups

1. Gary decides: Brain/AIOS separation (Option A/B/C)
2. Gary decides: Cinematic as canonical timeline (Option A/B/C)
3. Gary decides: Voice table retention strategy
4. If deprecation approved: create compatibility views + code migration
5. Add RLS to unprotected voice tables
6. Update ARCHITECTURE.md with canonical model documentation
