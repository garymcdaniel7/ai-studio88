# Conversation & Execution Model Boundaries (Story 032)

## Purpose

Define the authoritative entity for each concept, eliminate ambiguity between
overlapping Brain and AIOS tables, and establish clear lifecycle boundaries.

**Principle:** User-facing conversation (presentation) is separate from agent
execution (audit/recovery). Presentation records never collapse into audit
records and vice versa.

---

## Canonical Entity Map

| Concept | Canonical Table | Disposition | Owner Domain |
|---------|----------------|-------------|--------------|
| **User Conversation** | `brain_conversations` | CANONICAL | Presentation |
| **Conversation Collection** | `brain_collections` | CANONICAL | Presentation |
| **Execution Session** | `aios_sessions` | CANONICAL | Execution |
| **Execution Message/Event** | `aios_messages` | CANONICAL | Execution |
| **AI Decision (audit)** | `aios_decisions` | CANONICAL | Execution |
| **Approval Queue** | `aios_approvals` | CANONICAL | Governance |
| **Governance Policy** | `aios_policies` | CANONICAL | Governance |
| **Execution Plan** | `brain_plans` | CANONICAL | Execution |
| **Long-term Memory** | `brain_memory` | CANONICAL | Memory |
| **RAG Embeddings** | `brain_embeddings` | CANONICAL | Memory |
| Legacy Session (old Brain) | `brain_sessions` | COMPATIBILITY | — |
| Legacy Message (old Brain) | `brain_messages` | COMPATIBILITY | — |

---

## Disposition Definitions

| Disposition | Meaning | Write Policy | Read Policy |
|-------------|---------|--------------|-------------|
| **CANONICAL** | Authoritative source of truth for this concept | New writes go here | Read from here |
| **COMPATIBILITY** | Exists for backward compatibility only | No new writes after migration | Read allowed, warn on access |
| **MIGRATED** | Data moved to canonical table | Writes blocked | Redirects to canonical |
| **RETIRED** | To be dropped after retention period | Blocked | Blocked |

---

## Entity Definitions & Boundaries

### 1. User Conversation (Presentation)

**Table:** `brain_conversations`

**Owns:** title, collection assignment, display order, summary, mode label,
talent context hint, message_count (display), metadata (UI state).

**Does NOT own:** individual message content (that's in execution messages),
LLM provider routing, cost, latency, tool calls, or approval state.

**Lifecycle:** created → active → archived → deleted (soft).

**Tenant:** org_id (required). User sees only their workspace's conversations.

**Retention:** User-controlled. Deletion removes presentation; audit retained.

### 2. Execution Session

**Table:** `aios_sessions`

**Owns:** execution state, user_id (actor), org_id, mode, project/talent
context, message_count (actual), status (active/completed/failed).

**References:** May be linked FROM a brain_conversation via `metadata.execution_session_id`.

**Lifecycle:** created → active → completed | failed | expired.

**Tenant:** org_id + user_id (required, Story 014).

**Retention:** Audit retention (90 days minimum). Not user-deletable.

### 3. Execution Message/Event

**Table:** `aios_messages`

**Owns:** actual message content, role, timestamp, org_id (denormalized).

**Parent:** session_id FK → aios_sessions (CASCADE delete follows session).

**Lifecycle:** Immutable once written. Deleted only with parent session.

### 4. AI Decision (Audit Trail)

**Table:** `aios_decisions`

**Owns:** decision_type, provider, model, latency, tokens, cost, reasoning,
confidence, input/output summaries (truncated for storage).

**Parent:** session_id (nullable — some decisions are session-independent).

**Lifecycle:** Immutable. Never user-deletable. Audit retention.

### 5. Approval

**Table:** `aios_approvals`

**Owns:** tool, parameters, reasoning, cost estimate, status, decided_by,
decided_at, rejection_reason.

**Parent:** session_id (nullable), org_id (required).

**Lifecycle:** pending → approved | rejected | expired. Terminal states immutable.

### 6. Execution Plan

**Table:** `brain_plans`

**Owns:** request text, tasks (steps), reasoning, estimated_seconds,
confidence, modules_involved, status.

**Parent:** session_id FK → brain_sessions (legacy) or linked via metadata.

**Lifecycle:** created → executing → completed | failed | cancelled.

**Migration note:** Future plans should reference aios_sessions. Existing
brain_sessions FK is maintained for compatibility.

### 7. Long-term Memory

**Table:** `brain_memory`

**Owns:** category, key, value, confidence, source.

**Scope:** Per-workspace (org_id required after Story 030 migration).

**Lifecycle:** Created → updated (overwrite by key) → manually deleted.

**Not overlapping:** Unique concept, no equivalent in AIOS layer.

### 8. RAG Embeddings

**Table:** `brain_embeddings`

**Owns:** content, embedding vector, source_type, conversation/collection links.

**Scope:** Per-workspace (org_id required).

**Lifecycle:** Created on conversation activity. Re-embedded on content change.

---

## Legacy Tables (Compatibility Only)

### brain_sessions (COMPATIBILITY)

**Disposition:** Maintained for backward compatibility with `brain_plans` FK
and any code still reading legacy sessions.

**Migration path:**
1. New sessions are created in `aios_sessions` (Story 014+030).
2. `brain_sessions` rows with matching project_id can be linked via metadata.
3. After all callers are migrated, promote to RETIRED.

**Write policy:** No new rows after gateway migration is complete.

### brain_messages (COMPATIBILITY)

**Disposition:** Maintained for cascade integrity with brain_sessions.

**Migration path:**
1. New messages go to `aios_messages`.
2. Historical brain_messages remain readable for audit.
3. After retention period (90 days from last access), promote to RETIRED.

**Write policy:** No new rows after gateway migration.

---

## Cross-Reference Rules

| From | To | Cardinality | Constraint |
|------|----|-------------|------------|
| brain_conversations.metadata | aios_sessions.id | 0..N | Soft reference (JSONB) |
| aios_messages.session_id | aios_sessions.id | N..1 | FK CASCADE |
| aios_decisions.session_id | aios_sessions.id | N..1 | FK SET NULL |
| aios_approvals.session_id | aios_sessions.id | N..1 | Soft (TEXT, no FK yet) |
| brain_plans.session_id | brain_sessions.id | N..1 | FK SET NULL (legacy) |
| brain_embeddings.conversation_id | brain_conversations.id | N..1 | Soft reference |
| brain_embeddings.collection_id | brain_collections.id | N..1 | Soft reference |
| brain_conversations.collection_id | brain_collections.id | N..1 | FK SET NULL |

---

## Tenant Ownership Rules

| Table | org_id Required | Source |
|-------|----------------|--------|
| brain_conversations | YES | Story 030 (via RLS) |
| brain_collections | YES | Story 030 (via RLS) |
| brain_embeddings | YES | Migration 023 |
| brain_memory | YES | Migration 030 |
| aios_sessions | YES | Story 014 |
| aios_messages | YES (denormalized) | Story 014 |
| aios_decisions | YES | Story 014 |
| aios_approvals | YES | Story 014 |
| aios_policies | YES | Story 014 |
| brain_sessions | UNVERIFIED | Legacy — org_id added in 030 but not enforced |
| brain_messages | UNVERIFIED | Legacy — inherits from brain_sessions |
| brain_plans | UNVERIFIED | Legacy — inherits from brain_sessions |

---

## Status Transitions

### Execution Session (aios_sessions)
```
created → active → completed
                 → failed
                 → expired (timeout)
```

### Conversation (brain_conversations)
```
(implicit) active → archived → deleted (soft)
```

### Approval (aios_approvals)
```
pending → approved → (execution logged in aios_decisions)
        → rejected
        → expired (governance policy timeout)
```

### Plan (brain_plans)
```
created → executing → completed
                    → failed
                    → cancelled
```

---

## Migration Plan

### Phase 1: Boundary enforcement (this story)
- Define canonical entities (done — this document)
- Implement compatibility layer in application code
- Add contract tests verifying write targets

### Phase 2: Write redirection (follow-up)
- New Brain page conversations write to brain_conversations (presentation)
- Each chat interaction creates/reuses an aios_session (execution)
- Messages written to aios_messages; brain_conversations.message_count updated

### Phase 3: Legacy cleanup (future)
- brain_sessions rows without activity > 90 days → RETIRED
- brain_messages orphaned from active sessions → archive
- Remove permissive RLS policies (USING true) on brain_* tables

---

## Retention & Deletion Rules

| Record Type | User-Deletable? | Minimum Retention | Notes |
|-------------|-----------------|-------------------|-------|
| Conversation (presentation) | YES | None | User controls their history |
| Execution session | NO | 90 days | Audit requirement |
| Execution messages | NO | 90 days | Part of session audit |
| Decisions | NO | 365 days | Cost/compliance audit |
| Approvals | NO | 365 days | Governance audit |
| Memory items | YES | None | User preference data |
| Embeddings | YES (via source) | None | Derived data, re-creatable |
| Plans | NO | 90 days | Execution evidence |

---

## UNVERIFIED Items

1. `brain_sessions` org_id enforcement — column exists (migration 030) but no application code enforces it
2. `brain_plans` org_id — not present in schema, inherited only through session FK
3. Whether `brain_conversations.messages` JSONB duplicates `aios_messages` content
4. Exact mapping between legacy `brain_messages.plan_id` and `brain_plans.id`
5. Volume of legacy brain_sessions without org_id assignment
