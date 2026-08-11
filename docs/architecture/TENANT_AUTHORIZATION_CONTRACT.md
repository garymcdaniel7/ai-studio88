# Tenant Authorization Contract — Decision Document

**Story:** 004  
**Status:** APPROVED — All 8 decisions approved by founder (2026-08-05)  
**Author:** Kiro (automated inventory + proposal)  
**Date:** 2026-08-05  

---

## 1. Executive Summary

AI Studio has ~110 database tables across 39 migrations. Ownership patterns are inconsistent:
- Core tables were created without `org_id` (added later as nullable by migration 030)
- Two placeholder UUIDs exist (`...000` quarantined, `...001` is the system org)
- Story engine tables use `project_id` without direct `org_id`
- Infrastructure tables have no tenant ownership at all
- Company OS tables use `organization_id` FK instead of `org_id`

This document proposes a canonical model and requires explicit decisions on 8 questions.

---

## 2. Current State Inventory

### 2.1 Placeholder UUIDs

| UUID | Meaning | Status |
|------|---------|--------|
| `00000000-0000-0000-0000-000000000000` | Old invalid placeholder | QUARANTINED (migration 032) |
| `00000000-0000-0000-0000-000000000001` | System org ("AI Studio System") | VALID — owns shared resources |

### 2.2 Ownership Column Patterns Found

| Pattern | Tables | Example |
|---------|--------|---------|
| `org_id UUID NOT NULL` | ~15 newer tables | projects, workspace_credentials, generation_batches |
| `org_id UUID` (nullable, added later) | ~30 core tables | talent, assets, jobs, models, workflows |
| `organization_id UUID` FK | ~8 Company OS tables | studios, brands, brand_campaigns, team_members |
| `project_id UUID` only | ~12 Story Engine tables | universes, characters, episodes, scenes, shots |
| No ownership column | ~10 Infra tables | worker_connection_attempts, worker_sessions (019) |
| `org_id DEFAULT system-UUID` | 4 cost tables | cost_records, job_costs (020), brain_collections |


### 2.3 Auth Enforcement in API Layer

| Pattern | Where | Effect |
|---------|-------|--------|
| `require_auth` | All mutations (POST/PUT/DELETE) | JWT required; org resolved from org_members |
| `optional_auth` | Read endpoints (GET talent, GET assets, GET projects) | Returns data without tenant filter if no token |
| `AUTH_DEV_MODE=true` | Dev fallback | Returns `org_id=None`, disabling all tenant filtering |
| No auth dependency | Some infrastructure/health endpoints | Public access |

### 2.4 RLS Policy Patterns

| Pattern | Tables | Issue |
|---------|--------|-------|
| Proper org_members subquery | talent, assets, jobs, models, workflows, brands | Correct |
| Hardcoded system-UUID USING | cost_records, job_costs (020) | Only system org can access |
| JWT `org_id` claim extraction | projects, batches, lifecycle, provenance | Works but fragile |
| No RLS enabled | Story engine, some performance tables | Unprotected |

---

## 3. Proposed Canonical Ownership Hierarchy

```
Organization (top-level tenant boundary)
├── Project (organizational grouping, optional)
│   ├── Asset
│   ├── Job / ContentJob
│   ├── Storyboard / Episode / Scene / Shot
│   └── PublishingPost
├── AiTalent / LoRA Model (org-scoped, optionally project-linked)
├── Workflow (org-scoped or system-shared)
├── Brain Session / Conversation / Memory
├── Credential (org-scoped, encrypted)
└── Cost Record (org-scoped billing)

System Organization ("...001")
├── Shared Models (SDXL, Flux, etc.)
├── Shared Workflows (templates)
├── Creative Recipes (public presets)
└── Platform Packages (reference data)

Infrastructure (platform-scoped, no tenant)
├── worker_connection_attempts
├── worker_sessions (019 version)
└── _migration_ledger
```

### 3.1 Ownership Derivation Rules

| Rule | Description |
|------|-------------|
| **DIRECT** | Table has `org_id NOT NULL` — ownership is explicit |
| **INHERITED** | Table derives org from parent FK (e.g., shots → scenes → episodes → universes → projects.org_id) |
| **SYSTEM** | Table belongs to system org; readable by all, writable by service-role only |
| **PLATFORM** | Table has no tenant dimension; platform-operational data |


---

## 4. Role & Capability Matrix

Roles are stored in `org_members.role`. Hierarchy: owner > admin > editor > viewer.

| Capability | Owner | Admin | Editor | Viewer | Service | Worker |
|------------|-------|-------|--------|--------|---------|--------|
| Read own org data | Yes | Yes | Yes | Yes | — | — |
| Create content (talent, assets, jobs) | Yes | Yes | Yes | No | — | — |
| Edit content | Yes | Yes | Yes | No | — | — |
| Delete content (soft) | Yes | Yes | No | No | — | — |
| Manage credentials | Yes | Yes | No | No | — | — |
| Invite/remove members | Yes | Yes | No | No | — | — |
| Change member roles | Yes | No | No | No | — | — |
| Billing & plan management | Yes | No | No | No | — | — |
| Transfer org ownership | Yes | No | No | No | — | — |
| Access system resources (read) | Yes | Yes | Yes | Yes | Yes | — |
| Write system resources | No | No | No | No | Yes | — |
| Execute GPU jobs | — | — | — | — | — | Yes |
| Write job output/status | — | — | — | — | — | Yes |
| Access any org's data | No | No | No | No | Yes* | No |
| Platform admin operations | No | No | No | No | Yes | No |

*Service identity uses `SUPABASE_SERVICE_ROLE_KEY` which bypasses RLS.

### 4.1 Identity Types

| Identity | Auth Mechanism | org_id Source | Use Case |
|----------|---------------|---------------|----------|
| **User** | Supabase JWT | org_members table | Interactive API calls |
| **Service** | Service-role key | Explicit in code | Backend-to-DB, system ops |
| **Worker** | Instance credential | Job record's org_id | GPU job execution |
| **Platform Admin** | Supabase JWT + admin flag | All orgs (elevated) | Support, debugging |


---

## 5. Table Classification

### Category A: Tenant-Scoped (org_id NOT NULL required)

All user-generated content. Must have `org_id NOT NULL` with index and RLS.

| Table Group | Tables |
|-------------|--------|
| Core Content | talent, assets, jobs, models, workflows, scenes |
| Projects | projects, project_assets |
| Training | training_datasets, training_images, training_jobs, lora_versions, lora_evaluations |
| Video | video_projects, video_shots, video_renders, timeline_tracks, timeline_clips, timeline_exports |
| Audio | voice_profiles, voice_samples, audio_clips, lip_sync_jobs, music_tracks_db, sound_effects |
| Publishing | publishing_accounts, publishing_posts, analytics_snapshots |
| Brain | brain_sessions, brain_messages, brain_plans, brain_memory, brain_collections, brain_conversations, brain_embeddings |
| AIOS | aios_sessions, aios_messages, aios_decisions, aios_approvals, aios_policies |
| Story Engine | universes, characters, episodes, scenes (story), shots (story), story_memory |
| Creative | creative_dna, creative_rules, continuity_notes, generation_feedback, prompt_history, style_preferences |
| Performance | performance_dna, performance_memory, quality_scores, voice_dna, voice_datasets, voice_training_jobs, voice_versions |
| Object Intelligence | object_dna, product_dna, digital_twins, digital_twin_versions, virtual_tryon_jobs, product_views_360, scene_dna, material_profiles |
| Asset Intelligence | visual_dna, asset_collections, collection_items, asset_relationships, wardrobes, outfits |
| Cinematic | sequences, cinematic_timelines, cinematic_tracks, cinematic_items, storyboard_panels, cinematic_renders, editing_operations |
| Company | organizations, studios, brands, brand_campaigns, team_members, approval_requests, clients, asset_licenses |
| Credentials | workspace_credentials, credential_audit_log, social_account_connections |
| Billing | cost_records, job_costs |
| Lifecycle | lifecycle_transitions, entity_holds |
| Provenance | asset_provenance, asset_lineage, provenance_amendments |
| Batch | generation_batches, batch_variation_jobs |
| Governance | durable_approvals, governance_policy_audit, infra_audit_log |
| Recipes | creative_recipes (user-created; org-scoped) |

### Category B: System/Shared (org_id = system org, readable by all)

Platform-provided reference data. Writable only by service-role.

| Table | Content |
|-------|---------|
| models (system rows) | SDXL, Flux, WAN model definitions |
| workflows (system rows) | Default workflow templates |
| workflow_templates | Template library |
| creative_recipes (system rows) | Built-in presets |
| platform_packages | Content package definitions |
| scene_templates | Pre-built scene configurations |
| camera_presets | Camera angle library |
| lighting_presets | Lighting setup library |
| pose_presets | Pose reference library |

### Category C: Platform-Operational (no tenant dimension)

Infrastructure data not tied to any organization.

| Table | Content |
|-------|---------|
| _migration_ledger | Schema version tracking |
| worker_connection_attempts | GPU provisioning telemetry |
| worker_sessions (019) | Active GPU instances |
| workers | Worker registry |
| workflow_runs | Execution history (cross-tenant aggregate) |

### Category D: Tenant-Root (the org itself)

| Table | Content |
|-------|---------|
| organizations | Tenant definitions |
| org_members | Membership + roles |


---

## 6. Enforcement Responsibility Split

### 6.1 Two-Layer Defense

| Layer | Responsibility | Mechanism |
|-------|---------------|-----------|
| **Backend Service Layer** (primary) | Validate org_id on every query, enforce role checks, reject cross-tenant access | `TenantContext` from `membership.py`, passed to all DB functions |
| **Supabase RLS** (secondary) | Prevent direct client access, catch service-layer bugs | RLS policies on all Category A/B tables |

### 6.2 Enforcement Rules

1. **Backend is the source of truth** — RLS is defense-in-depth, not the primary gate
2. **Service-role bypasses RLS** — backend always uses service-role key
3. **RLS protects against direct-client access** — frontend Supabase SDK calls (Realtime, direct queries)
4. **Every DB query function receives org_id** — never optional for Category A tables
5. **org_id is NEVER trusted from client** — always derived from `TenantContext`

### 6.3 What Changes Are Required

| Change | Scope | Priority |
|--------|-------|----------|
| Make `org_id` NOT NULL on all Category A tables | Migration + backfill | P0 |
| Rename `organization_id` → `org_id` on Company OS tables | Migration | P1 |
| Add `org_id` to Story Engine tables (or enforce inherited ownership) | Migration | P1 |
| Add `org_id` to Infrastructure tables (019) for multi-tenant cost tracking | Migration | P2 |
| Remove `AUTH_DEV_MODE` bypass for production | Config | P0 |
| Convert all `optional_auth` read endpoints to `require_auth` | Code | P0 |
| Fix cost_records/job_costs RLS (hardcoded to system org) | Migration | P1 |
| Backfill NULL org_id rows or quarantine them | Data migration | P1 |


---

## 7. Edge Cases

### 7.1 Cross-Project Sharing

**Question:** Can a talent or asset belong to multiple projects within the same org?

**Proposed answer:** Yes. `project_id` on content tables is a *soft grouping*, not an ownership boundary. The tenant boundary is always `org_id`. Cross-project sharing within the same org is unrestricted.

### 7.2 Owner Departure

**Proposed rule:** If an org owner leaves, ownership must be explicitly transferred to another admin before deactivation. An org cannot have zero owners. If the last owner is deactivated without transfer, the org enters a "suspended" state.

### 7.3 Suspended Membership

**Proposed rule:** `status=suspended` in org_members means the user cannot authenticate into that org. Their data remains intact. An admin can reinstate them.

### 7.4 Service Accounts

**Proposed rule:** Service operations (GPU workers, background jobs, system seeding) use the Supabase service-role key, which bypasses RLS. They operate on behalf of a specific org only when the triggering job carries a valid `org_id`. Service code must explicitly set `org_id` on every write — no defaults.

### 7.5 Background Jobs / Workers

**Proposed rule:** A GPU worker inherits `org_id` from the job record that spawned it. When writing outputs (assets, cost records), it must include the job's `org_id`. Worker infrastructure tables (connection attempts, sessions) remain platform-scoped because they are shared GPU resources.

### 7.6 Platform Administrators

**Question:** How is platform admin access granted?

**Proposed answer:** A separate `is_platform_admin` flag on org_members (or a dedicated "platform" org membership) that grants read-only access to all orgs for support/debugging. Platform admins cannot mutate other orgs' data through the API — only via direct DB access with service-role.

### 7.7 Public/Shared Assets

**Proposed rule:** A talent or recipe can be marked `is_public=true`. Public resources are readable by all authenticated users regardless of org. They remain owned by their original org for mutation purposes. The system org `...001` owns platform-provided shared resources.

### 7.8 Orphaned Rows

**Proposed rule:** Rows with `org_id IS NULL` are invisible to all tenant queries. They are flagged as `UNVERIFIED` and accessible only via service-role for backfill. After backfill, the `org_id` column becomes NOT NULL.

### 7.9 Imported / Legacy Data

**Proposed rule:** When migrating from the current single-tenant state to multi-tenant, all existing data is assigned to the founder's organization. A one-time migration script handles this.

### 7.10 Legal Holds

**Proposed rule:** `entity_holds` table (migration 038) prevents permanent deletion even when lifecycle_state transitions to `purge_eligible`. A hold overrides the retention policy.


---

## 8. Decisions Required (Founder Approval Needed)

These questions cannot be resolved by engineering alone. Each requires a product/business decision.

### Decision 1: Story Engine Ownership Strategy

**Options:**
- **A) Add `org_id` directly to all story tables** (universes, characters, episodes, scenes, shots, story_memory) — simple, consistent, some denormalization
- **B) Inherit from project** (universe→project.org_id) — normalized but requires JOINs for every RLS check and breaks if project_id is NULL

**Recommendation:** Option A. Consistency > normalization for a security boundary.

---

### Decision 2: `optional_auth` on Read Endpoints

**Options:**
- **A) Convert all reads to `require_auth`** — strictest; breaks any public/unauthenticated access
- **B) Keep `optional_auth` for reads but require org_id filtering when authenticated** — current pattern; allows dev convenience but risky in production
- **C) Remove `optional_auth` in production, keep for dev only** via environment flag

**Recommendation:** Option A for production. Option C as a transitional step.

---

### Decision 3: Infrastructure Tables — Tenant-Scope or Platform-Scope?

Worker connection attempts and sessions currently have no org_id. Should per-org cost attribution require adding org_id?

**Options:**
- **A) Add org_id** — enables per-org cost views, but shared workers serve multiple orgs
- **B) Keep platform-scoped** — cost attribution done via job_costs table (already org-scoped)
- **C) Hybrid** — worker_sessions stays platform, but link to org via job records

**Recommendation:** Option C. Workers are shared resources; cost attribution is via jobs.

---

### Decision 4: `organization_id` vs `org_id` Naming

Company OS tables use `organization_id` as a FK to `organizations(id)`. All other tables use `org_id`.

**Options:**
- **A) Rename all to `org_id`** — consistent, simpler RLS, but breaking migration
- **B) Keep both, add `org_id` as a separate column** — redundant
- **C) Keep `organization_id` only in Company OS, treat as the same concept** — document the alias

**Recommendation:** Option A. One name for one concept. Create a migration to rename.

---

### Decision 5: NULL org_id Backfill Strategy

~30 core tables have nullable org_id with existing NULL rows.

**Options:**
- **A) Assign all NULL rows to founder's org** — simple, correct for single-tenant history
- **B) Assign to system org** — marks them as "nobody's data"
- **C) Delete orphaned rows** — data loss

**Recommendation:** Option A. This is a single-founder product currently — all existing data is the founder's.

---

### Decision 6: Platform Admin Model

**Options:**
- **A) Dedicated `platform_admins` table** — explicit, auditable
- **B) Flag on org_members** (`is_platform_admin=true`) — leverages existing membership
- **C) Membership in a "platform" org** grants admin rights — simple but conflates concepts

**Recommendation:** Option A. Platform admin is a fundamentally different privilege level.

---

### Decision 7: `AUTH_DEV_MODE` Disposition

Currently, `AUTH_DEV_MODE=true` (default) returns a dev user with `org_id=None`, which disables ALL tenant filtering.

**Options:**
- **A) Remove entirely** — auth always required, even in dev
- **B) Keep but default to `false`** — opt-in for local development only
- **C) Keep but inject a real dev org_id** — dev still works but with tenant filtering active

**Recommendation:** Option C. Dev convenience without security bypass.

---

### Decision 8: Cross-Org Resource Sharing (Future)

Should orgs be able to share specific resources (talent, models) with other orgs?

**Options:**
- **A) Never** — strict isolation, period
- **B) Via system org** — "shared" resources promoted to system org
- **C) Explicit share grants** (future `resource_shares` table) — most flexible

**Recommendation:** Option A for now. Option C can be added later without schema changes. Design for it but don't build it yet.

---

## 9. Implementation Implications

If all decisions follow recommendations:

1. **Migration 040:** Add `org_id NOT NULL` to story engine tables (backfill from project.org_id)
2. **Migration 041:** Rename `organization_id` → `org_id` on Company OS tables
3. **Migration 042:** Backfill NULL org_id on core tables → founder's org_id
4. **Migration 043:** ALTER all Category A tables to make org_id NOT NULL
5. **Migration 044:** Fix cost_records/job_costs RLS policies
6. **Code change:** Convert `optional_auth` → `require_auth` on all endpoints
7. **Code change:** `AUTH_DEV_MODE` injects real dev org, not None
8. **Code change:** Create `platform_admins` table + admin middleware
9. **RLS audit:** Ensure all Category A tables have proper org_members-based RLS

Estimated effort: 2-3 days of migration work, 1 day of code changes, 1 day of testing.

---

## 10. Unresolved / Deferred

| Item | Reason |
|------|--------|
| Cross-org sharing mechanics | Deferred to future story |
| Rate limiting per-org | Requires Redis; separate story |
| Audit log of cross-tenant access attempts | Requires instrumentation |
| Supabase Realtime channel scoping | Frontend story |
| Worker credential rotation | Infrastructure story |

---

## Approval

| Decision | Approved? | Owner | Date |
|----------|-----------|-------|------|
| 1. Story Engine ownership | ✅ Option A (add org_id directly) | Gary | 2026-08-05 |
| 2. optional_auth disposition | ✅ Option A (require_auth everywhere in prod) | Gary | 2026-08-05 |
| 3. Infrastructure tables scope | ✅ Option C (platform-scoped, cost via jobs) | Gary | 2026-08-05 |
| 4. organization_id rename | ✅ Option A (rename all to org_id) | Gary | 2026-08-05 |
| 5. NULL backfill strategy | ✅ Option A (assign to founder's org) | Gary | 2026-08-05 |
| 6. Platform admin model | ✅ Option A (dedicated platform_admins table) | Gary | 2026-08-05 |
| 7. AUTH_DEV_MODE disposition | ✅ Option C (inject real dev org_id) | Gary | 2026-08-05 |
| 8. Cross-org sharing | ✅ Option A (never, for now) | Gary | 2026-08-05 |

**All 8 decisions approved as recommended. Stories 005-009 are unblocked for implementation.**
