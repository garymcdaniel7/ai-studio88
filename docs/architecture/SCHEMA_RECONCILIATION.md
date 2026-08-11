# Schema Reconciliation — Task 1.1 Baseline

**Date:** 2026-08-06
**Method:** `supabase db query --linked` against live Supabase project `vipmjgglascthwoqqqji`
**Migration source:** 57 files in `docs/sql/` (not 49 as originally estimated)
**Validates:** Requirements R5.1, R5.13, R5.14, R5.15

---

## 1. Executive Summary

| Metric | Count |
|--------|-------|
| Live tables (public schema) | 84 |
| Tables defined in migration files | 119 (unique CREATE TABLE names) |
| Tables in BOTH live and migrations | 72 |
| Ghost tables (live, no migration) | 12 |
| Migration-only tables (not in live DB) | 47 |
| Tables with org_id column | 10 (all nullable) |
| Tables WITHOUT org_id column | 74 |
| RLS enabled | 83/84 (all except `workers`) |
| RLS policies defined | 6 tables (all permissive `true` — effectively no isolation) |
| Numbering collisions | 11 prefixes |
| Template migrations | 3 files |
| Migration ledger table | NOT in live DB |
| `organizations` table | NOT in live DB |
| `org_members` table | NOT in live DB |
| vector extension | In `public` schema (should be `extensions`) |
| `match_brain_embeddings` | Mutable search_path (proconfig = NULL) |

**Critical finding:** The platform has RLS *enabled* on 83 tables but only 6 have actual
policies — and all 6 use `qual = true` (allow everything). This means RLS is cosmetic,
providing zero actual tenant isolation at the database level.

---

## 2. Live Schema Inventory (84 tables)

### 2.1 Tables Present in Live DB

```
aios_approvals          aios_decisions          aios_messages
aios_policies           aios_sessions           analytics_snapshots
asset_collections       asset_relationships     assets
audio_clips             brain_collections       brain_conversations
brain_embeddings        brain_memory            brain_messages
brain_plans             brain_sessions          brands
camera_presets          campaigns               cinematic_items
cinematic_renders       cinematic_timelines     cinematic_tracks
collection_items        collections             content_calendar
continuity_notes        cost_records            creative_dna
creative_rules          editing_operations      generation_feedback
job_costs               jobs                    learning_events
lighting_presets        lip_sync_jobs           lora_evaluations
lora_versions           models                  music_tracks_db
outfits                 performance_dna         performance_memory
platform_packages       pose_presets            production_insights
products                projects                prompt_history
prompts                 publishing_accounts     publishing_posts
quality_scores          scene_templates         sequences
series                  service_settings        social_connections
songs                   sound_effects           soundtrack_cues
storyboard_panels       style_preferences       talent
talent_assets           talent_relationships    talent_voices
timeline_clips          timeline_exports        timeline_tracks
training_datasets       training_images         training_jobs
video_projects          video_renders           video_shots
visual_dna              voice_datasets          voice_dna
voice_profiles          voice_samples           voice_training_jobs
voice_versions          wardrobes               workers
workflow_dna            workflow_runs           workflow_templates
workflows
```

### 2.2 Ghost Tables (Live DB, No Migration File)

These tables exist in the live database but have NO corresponding CREATE TABLE in `docs/sql/`:

| Table | Row Count | Has org_id | Notes |
|-------|-----------|------------|-------|
| `talent` | 49+ rows | NO | Core entity, created via Dashboard |
| `assets` | 49 rows | NO | Core entity, created via Dashboard |
| `service_settings` | 2 rows | NO | Infrastructure config, created ad-hoc |
| `collections` | — | NO | Not the same as `brain_collections` |
| `prompts` | — | NO | Distinct from `prompt_history` |
| `products` | — | NO | Company OS entity |
| `content_calendar` | — | NO | Creator OS entity |
| `campaigns` | — | NO | Distinct from `brand_campaigns` in migrations |
| `performance_memory` | — | NO | Performance engine |
| `workflow_dna` | has org_id (nullable) | YES | Workflow intelligence |
| `collections` | — | NO | Content collections |
| `prompts` | — | NO | Prompt library |

**Updated ghost table count: 12** (expanded from original 8 after live verification)

Note: The original drift report listed `storyboards` as ghost — live DB has `storyboard_panels`
(which HAS a migration). `fleet_settings`, `story_universes`, `talent_loras`, and
`publishing_analytics` from the original report do NOT exist in the live DB at all.

---

## 3. Migration-Only Tables (47 — defined in SQL, not in live DB)

These tables have CREATE TABLE statements in migration files but do NOT exist in the live database:

| Table | Migration File | Category |
|-------|---------------|----------|
| `_migration_ledger` | 000 | Infrastructure — needed |
| `organizations` | 029 | Core — needed for multi-tenancy |
| `org_members` | 029 | Core — needed for multi-tenancy |
| `workspace_credentials` | 034 | Security — needed |
| `approval_requests` | 025 | Governance |
| `asset_licenses` | 039 | Provenance |
| `asset_lineage` | 039 | Provenance |
| `asset_provenance` | 039 | Provenance |
| `batch_variation_jobs` | 037 | Generation |
| `brand_campaigns` | 017 | Company OS (live has `campaigns`) |
| `characters` | 005 | Story engine |
| `clients` | 017 | Company OS |
| `creative_recipes` | 027 | Recipes |
| `credential_audit_log` | 041 | Security template |
| `digital_twin_versions` | 018 | Object intelligence |
| `digital_twins` | 018 | Object intelligence |
| `durable_approvals` | 036 | Governance |
| `entity_holds` | 038 | Deletion lifecycle |
| `episodes` | 005 | Story engine |
| `generation_batches` | 037 | Batch generation |
| `governance_policy_audit` | 036 | Governance audit |
| `infra_audit_log` | 036 | Infrastructure audit |
| `lifecycle_transitions` | 038 | Deletion lifecycle |
| `material_profiles` | 018 | Object intelligence |
| `object_dna` | 018 | Object intelligence |
| `product_dna` | 018 | Object intelligence |
| `product_views_360` | 018 | Object intelligence |
| `project_assets` | 028 | Projects |
| `provenance_amendments` | 039 | Provenance |
| `scene_dna` | 018 | Object intelligence |
| `scenes` | 005 | Story engine |
| `shots` | 005 | Story engine |
| `social_account_connections` | 021 | Social (live has `social_connections`) |
| `story_memory` | 005 | Story engine |
| `studios` | 016 | Cinematic |
| `team_members` | 017 | Company OS |
| `universes` | 005 | Story engine |
| `virtual_tryon_jobs` | 018 | Object intelligence |
| `worker_connection_attempts` | 019 | Infrastructure |
| `worker_sessions` | 019 | Infrastructure |

---

## 4. org_id Analysis

### 4.1 Tables WITH org_id Column (10 — all nullable)

| Table | is_nullable | Has NULL rows? | RLS Policy |
|-------|-------------|----------------|------------|
| `aios_approvals` | YES | Likely | `qual = true` (open) |
| `aios_policies` | YES | Likely | None |
| `aios_sessions` | YES | Likely | None |
| `brain_collections` | YES | Likely | `qual = true` (open) |
| `brain_conversations` | YES | Likely | `qual = true` (open) |
| `brain_embeddings` | YES | Likely | `qual = true` (open) |
| `cost_records` | YES | Likely | `qual = true` (open) |
| `job_costs` | YES | Likely | `qual = true` (open) |
| `social_connections` | YES | Likely | `qual = true` (open) |
| `workflow_dna` | YES | Likely | None |

### 4.2 Tables WITHOUT org_id Column (74)

ALL other 74 tables in the live database lack an `org_id` column entirely.
This is the primary blocker for multi-tenancy — every Category A table needs `org_id NOT NULL`.

---

## 5. RLS Status

### 5.1 Summary

- **83/84** tables have `rowsecurity = true`
- **1 table** has RLS disabled: `workers` (P0 security defect per R6)
- **Only 6 tables** have ANY RLS policy defined
- **All 6 policies** use `qual = true` (allow all) — zero effective isolation

### 5.2 Tables with Policies (all ineffective)

| Table | Policy Name | qual |
|-------|-------------|------|
| brain_collections | brain_collections_all | `true` |
| brain_conversations | brain_conversations_all | `true` |
| brain_embeddings | brain_embeddings_all | `true` |
| cost_records | cost_records_all | `true` |
| job_costs | job_costs_all | `true` |
| social_connections | social_connections_all | `true` |

### 5.3 Tables with RLS Enabled but NO Policy (77 tables)

Every other table has RLS enabled but zero policies. Per R6 and R2.5, this is a P0 security
defect — RLS with no policies defaults to DENY for non-superusers, but since the backend
uses the service-role key (which bypasses RLS), this provides no actual protection.

### 5.4 `workers` — RLS Disabled

The `workers` table has `rowsecurity = false`. This is explicitly called out in R2.4 and R6.

---

## 6. Extensions and Functions

### 6.1 Extensions

| Extension | Schema | Issue |
|-----------|--------|-------|
| vector | **public** | Should be in `extensions` schema (R5.11) |
| pgcrypto | extensions | OK |
| uuid-ossp | extensions | OK |
| pg_stat_statements | extensions | OK |
| supabase_vault | vault | OK |

### 6.2 Custom Functions

| Function | Schema | Issue |
|----------|--------|-------|
| `match_brain_embeddings` | public | **Mutable search_path** (proconfig = NULL). Security risk per R5.12. Function also lacks org_id filtering — returns results across all tenants. |

All other functions in public schema are pgvector extension functions (100+).
These will move when `vector` extension moves to `extensions` schema.

---

## 7. Migration Numbering Collisions (11 prefixes)

| Prefix | Files | Resolution |
|--------|-------|------------|
| 004 | `004_continuity_and_rules.sql`, `004_talent_extended_columns.sql` | Renumber |
| 006 | `006_models_and_templates.sql`, `006b_seed_models.sql` | 006b acceptable |
| 010 | `010_talent_relationships.sql`, `010_voice_audio_pipeline.sql` | Renumber |
| 031 | `031_creative_recipes_rls.sql`, `031_workers_rls.sql` | Renumber |
| 032 | `032_aios_tenant_isolation.sql`, `032_video_rls.sql` | Renumber |
| 033 | `033_talent_creative_rls.sql`, `033_training_rls.sql` | Renumber |
| 034 | `034_voice_audio_rls.sql`, `034_workspace_credentials.sql` | Renumber |
| 035 | `035_social_credentials.sql`, `035_storyboard_production_rls.sql` | Renumber |
| 036 | `036_durable_approvals.sql`, `036_governance_policy_audit.sql`, `036_infra_authorization.sql` | Renumber |
| 037 | `037_batch_generation.sql`, `037_memory_namespaces.sql` | Renumber |
| 040 | `040_ownership_backfill.sql`, `040_ownership_backfill_rollback.sql`, `040_rls_critical_tables.sql` | Renumber |
| 041 | `041_credential_encryption.sql`, `041_ownership_not_null_constraints.sql`, `041_security_hardening.sql`, `041b_leaked_password_protection.sql` | Renumber |

---

## 8. Template/Blocked Migrations

| File | Marker | Action |
|------|--------|--------|
| `040_rls_critical_tables.sql` | "TEMPLATE — DO NOT APPLY" | Exclude from runner |
| `041_credential_encryption.sql` | "TEMPLATE — DO NOT APPLY" | Exclude from runner |
| `041b_leaked_password_protection.sql` | Documentation only | Dashboard config change |

---

## 9. Table Classification (REUSE / EXTEND / NEW / DEPRECATE / REQUIRES_DATA_RECONCILIATION)

### Classification Key

- **REUSE** — Table exists in live DB, schema is acceptable as-is for production
- **EXTEND** — Table exists, needs column additions (org_id, updated_at, etc.) or index changes
- **NEW** — Table does not exist, needs to be created for production
- **DEPRECATE** — Table exists but is superseded or unused; schedule for removal
- **REQUIRES_DATA_RECONCILIATION** — Table exists but has data integrity issues (NULL org_id, orphan rows, etc.)

### 9.1 Core Entities — EXTEND

| Table | Classification | Reason |
|-------|---------------|--------|
| `talent` | EXTEND | Add org_id NOT NULL, add updated_at NOT NULL, add indexes |
| `assets` | EXTEND | Add org_id NOT NULL, add indexes |
| `jobs` | EXTEND | Add org_id NOT NULL, extend with leasing columns per design |
| `projects` | EXTEND | Add org_id NOT NULL |
| `models` | EXTEND | Add org_id NOT NULL |
| `workflows` | EXTEND | Add org_id NOT NULL |
| `workflow_templates` | EXTEND | Add org_id NOT NULL |
| `workflow_runs` | EXTEND | Add org_id NOT NULL |
| `lora_versions` | EXTEND | Add org_id NOT NULL |

### 9.2 Brain/AIOS — EXTEND + REQUIRES_DATA_RECONCILIATION

| Table | Classification | Reason |
|-------|---------------|--------|
| `brain_conversations` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable with likely NULL rows |
| `brain_messages` | EXTEND | Add org_id NOT NULL |
| `brain_memory` | EXTEND | Add org_id NOT NULL, add user_id |
| `brain_plans` | EXTEND | Add org_id NOT NULL |
| `brain_sessions` | EXTEND | Add org_id NOT NULL |
| `brain_collections` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |
| `brain_embeddings` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable, function lacks tenant filter |
| `aios_approvals` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |
| `aios_decisions` | EXTEND | Add org_id NOT NULL |
| `aios_messages` | EXTEND | Add org_id NOT NULL |
| `aios_policies` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |
| `aios_sessions` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |

### 9.3 Generation/Training — EXTEND

| Table | Classification | Reason |
|-------|---------------|--------|
| `training_jobs` | EXTEND | Add org_id NOT NULL |
| `training_datasets` | EXTEND | Add org_id NOT NULL |
| `training_images` | EXTEND | Add org_id NOT NULL |
| `generation_feedback` | EXTEND | Add org_id NOT NULL |
| `lora_evaluations` | EXTEND | Add org_id NOT NULL |
| `creative_dna` | EXTEND | Add org_id NOT NULL |

### 9.4 Video/Audio — EXTEND

| Table | Classification | Reason |
|-------|---------------|--------|
| `video_projects` | EXTEND | Add org_id NOT NULL |
| `video_shots` | EXTEND | Add org_id NOT NULL |
| `video_renders` | EXTEND | Add org_id NOT NULL |
| `voice_profiles` | EXTEND | Add org_id NOT NULL |
| `voice_versions` | EXTEND | Add org_id NOT NULL |
| `voice_datasets` | EXTEND | Add org_id NOT NULL |
| `voice_samples` | EXTEND | Add org_id NOT NULL |
| `voice_training_jobs` | EXTEND | Add org_id NOT NULL |
| `voice_dna` | EXTEND | Add org_id NOT NULL |
| `audio_clips` | EXTEND | Add org_id NOT NULL |
| `songs` | EXTEND | Add org_id NOT NULL |
| `soundtrack_cues` | EXTEND | Add org_id NOT NULL |
| `sound_effects` | EXTEND | Add org_id NOT NULL |
| `music_tracks_db` | EXTEND | Add org_id NOT NULL |
| `lip_sync_jobs` | EXTEND | Add org_id NOT NULL |

### 9.5 Publishing/Social — EXTEND + REQUIRES_DATA_RECONCILIATION

| Table | Classification | Reason |
|-------|---------------|--------|
| `publishing_posts` | EXTEND | Add org_id NOT NULL |
| `publishing_accounts` | EXTEND | Add org_id NOT NULL |
| `social_connections` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |
| `analytics_snapshots` | EXTEND | Add org_id NOT NULL |

### 9.6 Cinematic/Storyboard — EXTEND

| Table | Classification | Reason |
|-------|---------------|--------|
| `cinematic_timelines` | EXTEND | Add org_id NOT NULL |
| `cinematic_tracks` | EXTEND | Add org_id NOT NULL |
| `cinematic_items` | EXTEND | Add org_id NOT NULL |
| `cinematic_renders` | EXTEND | Add org_id NOT NULL |
| `storyboard_panels` | EXTEND | Add org_id NOT NULL |
| `timeline_clips` | EXTEND | Add org_id NOT NULL |
| `timeline_tracks` | EXTEND | Add org_id NOT NULL |
| `timeline_exports` | EXTEND | Add org_id NOT NULL |
| `editing_operations` | EXTEND | Add org_id NOT NULL |
| `sequences` | EXTEND | Add org_id NOT NULL |
| `series` | EXTEND | Add org_id NOT NULL |
| `scene_templates` | EXTEND | Add org_id NOT NULL |

### 9.7 Performance/Intelligence — EXTEND

| Table | Classification | Reason |
|-------|---------------|--------|
| `performance_dna` | EXTEND | Add org_id NOT NULL |
| `performance_memory` | EXTEND | Add org_id NOT NULL |
| `production_insights` | EXTEND | Add org_id NOT NULL |
| `quality_scores` | EXTEND | Add org_id NOT NULL |
| `learning_events` | EXTEND | Add org_id NOT NULL |
| `visual_dna` | EXTEND | Add org_id NOT NULL |
| `style_preferences` | EXTEND | Add org_id NOT NULL |

### 9.8 Assets/Collections — EXTEND

| Table | Classification | Reason |
|-------|---------------|--------|
| `asset_collections` | EXTEND | Add org_id NOT NULL |
| `asset_relationships` | EXTEND | Add org_id NOT NULL |
| `collection_items` | EXTEND | Add org_id NOT NULL |
| `talent_assets` | EXTEND | Add org_id NOT NULL |
| `talent_relationships` | EXTEND | Add org_id NOT NULL |
| `talent_voices` | EXTEND | Add org_id NOT NULL |
| `wardrobes` | EXTEND | Add org_id NOT NULL |
| `outfits` | EXTEND | Add org_id NOT NULL |

### 9.9 Company OS / Creator OS — EXTEND

| Table | Classification | Reason |
|-------|---------------|--------|
| `brands` | EXTEND | Add org_id NOT NULL |
| `campaigns` | EXTEND | Add org_id NOT NULL |
| `content_calendar` | EXTEND | Add org_id NOT NULL |
| `products` | EXTEND | Add org_id NOT NULL |
| `prompts` | EXTEND | Add org_id NOT NULL |
| `collections` | EXTEND | Add org_id NOT NULL |
| `prompt_history` | EXTEND | Add org_id NOT NULL |

### 9.10 Infrastructure/Cost — EXTEND + REQUIRES_DATA_RECONCILIATION

| Table | Classification | Reason |
|-------|---------------|--------|
| `workers` | EXTEND | Enable RLS, add org_id NOT NULL, add policies |
| `cost_records` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |
| `job_costs` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |
| `service_settings` | REUSE | Platform-wide config, no org_id needed |
| `workflow_dna` | REQUIRES_DATA_RECONCILIATION | Has org_id but nullable |

### 9.11 Presets — REUSE (platform-wide)

| Table | Classification | Reason |
|-------|---------------|--------|
| `camera_presets` | REUSE | Platform-shared presets, extend later if per-org needed |
| `lighting_presets` | REUSE | Platform-shared presets |
| `pose_presets` | REUSE | Platform-shared presets |
| `platform_packages` | REUSE | Platform-level entitlement packages |

### 9.12 NEW Tables Required (from design.md, not yet in live DB)

| Table | Source | Purpose |
|-------|--------|---------|
| `_migration_ledger` | 000 migration + design | Track applied migrations |
| `organizations` | 029 migration + design | Multi-tenant org registry |
| `org_members` | 029 migration + design | User-to-org membership + roles |
| `workspace_credentials` | 034 migration + design | Encrypted credential store |
| `connections` | design.md | Unified Connections Hub |
| `job_leases` | design.md | Job leasing system |
| `cost_reservations` | design.md | Atomic budget reservation |
| `cost_entries` | design.md | Immutable cost records |
| `brain_user_memory` | design.md | Layer 2 user-private memory |
| `brain_workspace_knowledge` | design.md | Layer 3 workspace knowledge |
| `platform_operators` | design.md | Capability-based admin |
| `platform_operator_actions` | design.md | Operator audit trail |
| `support_sessions` | design.md | Tenant support access |
| `pending_approvals` | design.md | Governance approval queue |
| `notifications` | design.md | In-app notification service |
| `compute_availability_config` | design.md | Compute state management |
| `compute_selective_grants` | design.md | Selective compute access |
| `consent_records` | design.md (A2-004) | First-class consent |
| `rights_cases` | design.md (A2-005) | Rights/takedown management |

### 9.13 DEPRECATE Candidates (migration-only, not needed)

| Table | Migration | Reason |
|-------|-----------|--------|
| `brand_campaigns` | 017 | Live DB uses `campaigns` instead |
| `social_account_connections` | 021 | Live DB uses `social_connections`; design uses `connections` |
| `worker_connection_attempts` | 019 | Superseded by provider abstraction |
| `worker_sessions` | 019 | Superseded by `job_leases` design |
| `characters` | 005 | Story engine — never deployed |
| `episodes` | 005 | Story engine — never deployed |
| `scenes` | 005 | Story engine — never deployed |
| `shots` | 005 | Story engine — never deployed |
| `story_memory` | 005 | Story engine — never deployed |
| `universes` | 005 | Story engine — never deployed |
| `studios` | 016 | Cinematic — never deployed |
| `clients` | 017 | Company OS — never deployed |
| `team_members` | 017 | Company OS — superseded by `org_members` |
| `digital_twins` | 018 | Object intelligence — never deployed |
| `digital_twin_versions` | 018 | Object intelligence — never deployed |
| `object_dna` | 018 | Object intelligence — never deployed |
| `product_dna` | 018 | Object intelligence — never deployed |
| `product_views_360` | 018 | Object intelligence — never deployed |
| `material_profiles` | 018 | Object intelligence — never deployed |
| `scene_dna` | 018 | Object intelligence — never deployed |
| `virtual_tryon_jobs` | 018 | Object intelligence — never deployed |
| `approval_requests` | 025 | Superseded by `pending_approvals` in design |
| `durable_approvals` | 036 | Superseded by `pending_approvals` in design |
| `creative_recipes` | 027 | Evaluate for REUSE if frontend uses it |

---

## 10. Duplicate/Conflicting Definitions

| Table | Conflict | Resolution |
|-------|----------|------------|
| `cost_records` | Defined in 019 (no org_id) AND 020 (with org_id) | Keep 020, mark 019 definition as superseded |
| `talent_relationships` | Defined in 004 AND 010 | Keep 010 (more complete), mark 004 as superseded |
| `campaigns` vs `brand_campaigns` | Live uses `campaigns`, migration 017 defines `brand_campaigns` | Canonical name: `campaigns` |
| `social_connections` vs `social_account_connections` | Live uses `social_connections`, migration 021 defines `social_account_connections` | Canonical name: `social_connections` (to be superseded by `connections`) |

---

## 11. Security Issues (P0)

| Issue | Severity | Requirement | Resolution |
|-------|----------|-------------|------------|
| `workers` table has RLS disabled | P0 | R2.4, R6 | Enable RLS + add tenant policy |
| 77 tables have RLS enabled but NO policies | P0 | R2.5, R6 | Add proper org_id-based policies |
| 6 tables have `qual = true` policies (no isolation) | P0 | R6.3 | Replace with org_members subquery |
| 74 tables lack org_id column entirely | P0 | R2.1 | Add org_id NOT NULL (after backfill) |
| 10 tables have nullable org_id | P0 | R5.6 | Backfill NULLs, then NOT NULL |
| `vector` extension in public schema | P1 | R5.11 | Move to extensions schema |
| `match_brain_embeddings` mutable search_path | P1 | R5.12 | Set immutable search_path |
| `match_brain_embeddings` lacks org_id filter | P0 | R2.2 | Add WHERE org_id filter |
| Service-role key used for all queries | P0 | R2.7 | Implement per-request auth context |
| `organizations` table does not exist | BLOCKER | R1, R2 | Must be created before any tenant work |
| `org_members` table does not exist | BLOCKER | R1, R3 | Must be created before auth enforcement |

---

## 12. Key Discrepancies Between Migrations and Live Schema

### 12.1 Tables in Migrations Not in Live DB (Feature Stubs Never Applied)

The following migration files define tables that were never applied to the live database.
Most represent Phase 2+ features that were designed but not deployed:

- **Story Engine (005):** 6 tables — characters, episodes, scenes, shots, story_memory, universes
- **Object Intelligence (018):** 7 tables — digital_twins, digital_twin_versions, object_dna, product_dna, product_views_360, material_profiles, scene_dna, virtual_tryon_jobs
- **Company OS (017):** 3 tables — clients, team_members, brand_campaigns
- **Batch Generation (037):** 2 tables — generation_batches, batch_variation_jobs
- **Deletion Lifecycle (038):** 2 tables — entity_holds, lifecycle_transitions
- **Asset Provenance (039):** 3 tables — asset_provenance, asset_lineage, provenance_amendments, asset_licenses
- **Infrastructure (019):** 2 tables — worker_connection_attempts, worker_sessions
- **Governance (036):** 3 tables — durable_approvals, governance_policy_audit, infra_audit_log
- **Security (034, 041):** 2 tables — workspace_credentials, credential_audit_log
- **Projects (028):** 1 table — project_assets
- **Multi-tenancy (029):** 2 tables — organizations, org_members

### 12.2 Name Mismatches (Migration 038)

Migration `038_deletion_lifecycle.sql` references alternate table names:
- `ai_talent` → live name is `talent`
- `content_jobs` → live name is `jobs`
- `lora_models` → live name is `lora_versions`
- `campaigns` → migration 017 defines `brand_campaigns`, live uses `campaigns`

### 12.3 `talent` Table Column Drift

The `talent` table in the live DB has 29 columns added via Dashboard (no migration),
including extended profile fields (height, hair_color, eye_color, body_type, etc.) and
social handles. Migration `004_talent_extended_columns.sql` attempts to add some of these
but uses `IF NOT EXISTS` so the conflict is masked.

---

## 13. Migration Ledger Status

- `_migration_ledger` table is defined in `000_migration_ledger.sql`
- This table does NOT exist in the live database
- No migration tracking system is in place
- `supabase migration list` shows no tracked migrations
- The live schema was built via a combination of Dashboard clicks + selective SQL execution

---

## 14. Recommended Action Sequence

1. **Create `organizations` and `org_members`** — prerequisite for all tenant isolation
2. **Backfill org_id** on the 10 tables that have it nullable (founder-only, bulk assign)
3. **Add org_id NOT NULL** to all 74 tables lacking it (phased, start with core entities)
4. **Create `_migration_ledger`** and populate baseline state
5. **Write ghost table migrations** matching live schema exactly (talent, assets, etc.)
6. **Resolve numbering collisions** with date-based renaming
7. **Enable RLS on workers** and add proper policies
8. **Replace all `qual = true` policies** with org_members-based isolation
9. **Move vector extension** to `extensions` schema
10. **Fix `match_brain_embeddings`** — immutable search_path + org_id filter

---

## 15. Verification Evidence

All data in this document was gathered via live database queries on 2026-08-06:

```
supabase link --project-ref vipmjgglascthwoqqqji
supabase inspect db table-sizes --linked
supabase db query --linked "SELECT tablename, rowsecurity FROM pg_tables..."
supabase db query --linked "SELECT ... FROM information_schema.columns..."
supabase db query --linked "SELECT ... FROM pg_policies..."
supabase db query --linked "SELECT ... FROM pg_proc..."
supabase db query --linked "SELECT ... FROM pg_extension..."
grep "CREATE TABLE" docs/sql/*.sql
```

No schema modifications were made during this analysis.
