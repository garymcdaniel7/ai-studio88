# RLS Comprehensive Audit Results

**Date:** 2026-08-09 04:10 UTC
**Project:** vipmjgglascthwoqqqji
**Method:** Automated query via `supabase db query --linked`
**Validates:** Requirements R6.1, R6.2, R6.5, R6.7, R2.4, R2.5

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Total tables (public schema) | 91 |
| RLS enabled | 90 |
| RLS disabled | 1 |
| Tables with at least one policy | 6 |
| Tables with RLS but NO policies | 84 |
| Tables with ineffective policies (qual=true) | 6 |
| Tables with effective policies | 0 |
| Tables with org_id column | 10 |
| Tables WITHOUT org_id column | 81 |
| Category A (tenant-scoped) tables | 83 |
| Category A tables missing org_id | 73 |

### Severity Distribution

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 19 | RLS disabled or no policies + sensitive data |
| HIGH | 58 | RLS enabled but no policies + user content |
| MEDIUM | 6 | Ineffective qual=true policies |
| LOW | 8 | Platform-wide or already protected |

---

## CRITICAL — Immediate Remediation Required

These tables either have RLS completely disabled or have RLS enabled with
no policies while containing sensitive user/tenant data.

| Table | RLS Enabled | Policies | Has org_id | Issue |
|-------|:-----------:|:--------:|:----------:|-------|
| `aios_approvals` | ✅ | 0 | ✅ | No policies — sensitive data exposed |
| `aios_decisions` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `aios_messages` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `aios_sessions` | ✅ | 0 | ✅ | No policies — sensitive data exposed |
| `assets` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `brain_memory` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `brain_messages` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `creative_dna` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `jobs` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `publishing_accounts` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `publishing_posts` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `talent` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `training_datasets` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `training_images` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `training_jobs` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `voice_datasets` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `voice_profiles` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `voice_samples` | ✅ | 0 | ❌ | No policies — sensitive data exposed |
| `workflow_dna` | ✅ | 0 | ✅ | No policies — sensitive data exposed |


## HIGH — RLS Enabled, No Policies (User Content)

These Category A tables have RLS enabled but zero policies defined.
Since the backend uses the service-role key (bypasses RLS), this provides
no actual protection. If direct client access occurs, ALL rows are denied.

| Table | Has org_id | Category | Remediation |
|-------|:----------:|:--------:|-------------|
| `aios_policies` | ✅ | A | Backfill NULL org_id → NOT NULL, then add RLS policy |
| `analytics_snapshots` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `asset_collections` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `asset_relationships` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `audio_clips` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `brain_plans` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `brain_sessions` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `brands` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `campaigns` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `cinematic_items` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `cinematic_renders` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `cinematic_timelines` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `cinematic_tracks` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `collection_items` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `collections` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `content_calendar` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `continuity_notes` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `creative_rules` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `editing_operations` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `generation_feedback` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `learning_events` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `lip_sync_jobs` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `lora_evaluations` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `lora_versions` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `models` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `music_tracks_db` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `outfits` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `performance_dna` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `performance_memory` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `production_insights` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `products` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `projects` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `prompt_history` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `prompts` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `quality_scores` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `sequences` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `series` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `songs` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `sound_effects` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `soundtrack_cues` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `storyboard_panels` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `style_preferences` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `talent_assets` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `talent_relationships` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `talent_voices` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `timeline_clips` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `timeline_exports` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `timeline_tracks` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `video_projects` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `video_renders` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `video_shots` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `visual_dna` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `voice_dna` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `voice_training_jobs` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `voice_versions` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `wardrobes` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `workflow_runs` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |
| `workflows` | ❌ | A | Add org_id NOT NULL column first, then add RLS policy |


## MEDIUM — Ineffective Policies (qual=true)

These tables have RLS policies defined but the policies use `qual = true`
which allows ALL access — providing zero actual tenant isolation.

| Table | Policy Name | qual | with_check | Remediation |
|-------|-------------|------|:----------:|-------------|
| `brain_collections` | brain_collections_all | `true` | `—` | Replace with org_members subquery USING + WITH CHECK |
| `brain_conversations` | brain_conversations_all | `true` | `—` | Replace with org_members subquery USING + WITH CHECK |
| `brain_embeddings` | brain_embeddings_all | `true` | `—` | Replace with org_members subquery USING + WITH CHECK |
| `cost_records` | cost_records_all | `true` | `—` | Replace with org_members subquery USING + WITH CHECK |
| `job_costs` | job_costs_all | `true` | `—` | Replace with org_members subquery USING + WITH CHECK |
| `social_connections` | social_connections_all | `true` | `—` | Replace with org_members subquery USING + WITH CHECK |


## LOW — Platform-Wide or Already Protected

These tables are either platform-operational (no tenant dimension),
system/shared reference data, or already have effective RLS policies.

| Table | Category | RLS | Policies | Notes |
|-------|:--------:|:---:|:--------:|-------|
| `camera_presets` | B | ✅ | 0 | System/shared — readable by all |
| `lighting_presets` | B | ✅ | 0 | System/shared — readable by all |
| `platform_packages` | B | ✅ | 0 | System/shared — readable by all |
| `pose_presets` | B | ✅ | 0 | System/shared — readable by all |
| `scene_templates` | B | ✅ | 0 | System/shared — readable by all |
| `service_settings` | C | ✅ | 0 | Platform-operational — no tenant dimension |
| `workers` | C | — | 0 | Platform-operational — no tenant dimension |
| `workflow_templates` | B | ✅ | 0 | System/shared — readable by all |


---

## Remediation Plan

### Phase 1: Fix Critical Issues (Immediate)

1. **Enable RLS on `workers` table** — add tenant policy or platform-admin-only policy
2. **Add effective RLS policies to sensitive tables** that already have org_id:
   - Replace `qual = true` with proper org_members subquery
   - Template: `USING (org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid()))`

### Phase 2: Add org_id Column (Prerequisite for Effective RLS)

Before RLS policies can be effective, tables need `org_id NOT NULL`:

1. **Create `organizations` and `org_members` tables** (prerequisite for all)
2. **Add org_id to all 74 tables lacking it** (phased migration)
3. **Backfill existing NULL org_id rows** → founder's org_id
4. **Apply NOT NULL constraint** after backfill verification

### Phase 3: Apply Production RLS Policies

For each Category A table with org_id NOT NULL:

```sql
-- Template for tenant isolation RLS policy
CREATE POLICY "tenant_isolation_select" ON <table>
    FOR SELECT
    USING (org_id IN (
        SELECT om.org_id FROM public.org_members om
        WHERE om.user_id = auth.uid()
        AND om.status = 'active'
    ));

CREATE POLICY "tenant_isolation_insert" ON <table>
    FOR INSERT
    WITH CHECK (org_id IN (
        SELECT om.org_id FROM public.org_members om
        WHERE om.user_id = auth.uid()
        AND om.status = 'active'
    ));

CREATE POLICY "tenant_isolation_update" ON <table>
    FOR UPDATE
    USING (org_id IN (
        SELECT om.org_id FROM public.org_members om
        WHERE om.user_id = auth.uid()
        AND om.status = 'active'
    ))
    WITH CHECK (org_id IN (
        SELECT om.org_id FROM public.org_members om
        WHERE om.user_id = auth.uid()
        AND om.status = 'active'
    ));

CREATE POLICY "tenant_isolation_delete" ON <table>
    FOR DELETE
    USING (org_id IN (
        SELECT om.org_id FROM public.org_members om
        WHERE om.user_id = auth.uid()
        AND om.status = 'active'
    ));

-- Service-role bypass (backend uses service-role key)
CREATE POLICY "service_role_bypass" ON <table>
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
```

### Phase 4: Verify and Automate

1. **Write automated tests** — one per Category A table (R6.3)
2. **Add CI check** — new migrations must include RLS policy (R6.5)
3. **Document policies** in machine-readable format (R6.6)

---

## Tables Requiring org_id Column Addition (Before RLS Can Be Effective)

The following Category A tables currently lack an `org_id` column entirely.
RLS policies cannot provide tenant isolation until this column exists with NOT NULL.

| Table | Current State | Migration Required |
|-------|--------------|-------------------|
| `aios_decisions` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `aios_messages` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `analytics_snapshots` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `asset_collections` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `asset_relationships` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `assets` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `audio_clips` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `brain_memory` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `brain_messages` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `brain_plans` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `brain_sessions` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `brands` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `campaigns` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `cinematic_items` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `cinematic_renders` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `cinematic_timelines` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `cinematic_tracks` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `collection_items` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `collections` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `content_calendar` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `continuity_notes` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `creative_dna` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `creative_rules` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `editing_operations` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `generation_feedback` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `jobs` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `learning_events` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `lip_sync_jobs` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `lora_evaluations` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `lora_versions` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `models` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `music_tracks_db` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `outfits` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `performance_dna` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `performance_memory` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `production_insights` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `products` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `projects` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `prompt_history` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `prompts` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `publishing_accounts` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `publishing_posts` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `quality_scores` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `sequences` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `series` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `songs` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `sound_effects` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `soundtrack_cues` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `storyboard_panels` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `style_preferences` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `talent` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `talent_assets` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `talent_relationships` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `talent_voices` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `timeline_clips` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `timeline_exports` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `timeline_tracks` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `training_datasets` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `training_images` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `training_jobs` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `video_projects` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `video_renders` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `video_shots` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `visual_dna` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `voice_datasets` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `voice_dna` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `voice_profiles` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `voice_samples` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `voice_training_jobs` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `voice_versions` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `wardrobes` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `workflow_runs` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |
| `workflows` | No org_id column | ADD COLUMN org_id UUID NOT NULL + backfill + index |


## Tables With Nullable org_id (Backfill Required Before NOT NULL)

These tables have the org_id column but it's nullable — existing NULL rows
must be backfilled before the NOT NULL constraint can be applied.

| Table | Current Policies | Backfill Strategy |
|-------|-----------------|-------------------|
| `aios_approvals` | 0 | Assign NULL rows to founder org_id |
| `aios_policies` | 0 | Assign NULL rows to founder org_id |
| `aios_sessions` | 0 | Assign NULL rows to founder org_id |
| `brain_collections` | 1 (qual=true) | Assign NULL rows to founder org_id |
| `brain_conversations` | 1 (qual=true) | Assign NULL rows to founder org_id |
| `brain_embeddings` | 1 (qual=true) | Assign NULL rows to founder org_id |
| `cost_records` | 1 (qual=true) | Assign NULL rows to founder org_id |
| `job_costs` | 1 (qual=true) | Assign NULL rows to founder org_id |
| `social_connections` | 1 (qual=true) | Assign NULL rows to founder org_id |
| `workflow_dna` | 0 | Assign NULL rows to founder org_id |


---

## Verification Evidence

This report was generated on 2026-08-09 04:10 UTC via automated queries:

```
supabase db query --linked "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public'"
supabase db query --linked "SELECT * FROM pg_policies WHERE schemaname='public'"
supabase db query --linked "SELECT table_name, is_nullable FROM information_schema.columns WHERE table_schema='public' AND column_name='org_id'"
```

No schema modifications were made during this audit.
