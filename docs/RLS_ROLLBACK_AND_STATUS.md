# RLS Policy Status & Rollback Procedure

## Story 005 — Database-Level Tenant Isolation

**Status: BLOCKED** — awaiting Story 004 approval before applying to production.

---

## Current State Summary

| Category | Count | Notes |
|----------|-------|-------|
| Tables with RLS enabled | 72 | In SQL migrations |
| Tables with RLS + policies | 68 | Proper isolation |
| Tables with RLS but NO policies | 4 | Blocks all non-service-role access |
| Tables WITHOUT RLS | 58 | No DB-level isolation |
| Tables covered by migration 040 | 16 | Template ready, not applied |

## Tables with RLS Enabled but NO Policies

These tables are effectively inaccessible to authenticated users (only service_role works):

| Table | Risk | Resolution |
|-------|------|------------|
| `_migration_ledger` | None — system table | Leave as-is (service-role only) |
| `brain_messages` | Medium — user data inaccessible | Add org_id policy (in migration 040) |
| `brain_sessions` | Medium — user data inaccessible | Add org_id policy (in migration 040) |
| `publishing_accounts` | High — publishing broken | Add org_id policy (in migration 040) |

## Critical Unprotected Tables (No RLS at All)

Addressed in `docs/sql/040_rls_critical_tables.sql`:

### Tier 1 — Customer Data (highest risk)
- `brand_campaigns`
- `digital_twins`
- `digital_twin_versions`
- `object_dna`
- `product_dna`
- `talent_assets`
- `talent_relationships`
- `project_assets`
- `workflow_runs`
- `workflow_templates`

### Tier 2 — Operational
- `approval_requests`
- `analytics_snapshots`
- `visual_dna`
- `wardrobes`

### Tier 4 — Special Cases
- `organizations` (policy uses `id` not `org_id`)
- `worker_connection_attempts` (service-role only, no policies)

## Remaining Unresolved Tables (42 more without RLS)

These require individual assessment — some may be reference tables, some may need org_id columns added:

| Category | Tables |
|----------|--------|
| Cinematic/Production | `cinematic_items`, `cinematic_renders`, `cinematic_timelines`, `cinematic_tracks`, `editing_operations`, `timeline_clips` |
| Voice/Audio | `voice_datasets`, `voice_dna`, `voice_training_jobs`, `voice_versions`, `music_tracks_db`, `songs`, `sound_effects`, `soundtrack_cues` |
| Scene/3D | `scene_dna`, `camera_presets`, `lighting_presets`, `pose_presets`, `material_profiles` |
| Story/Content | `sequences`, `series`, `episodes` (but episodes has policies?), `characters` |
| Asset/Product | `asset_collections`, `asset_licenses`, `asset_relationships`, `collection_items`, `outfits`, `product_views_360`, `virtual_tryon_jobs` |
| Workflow/Performance | `workflow_dna`, `quality_scores`, `performance_dna`, `performance_memory`, `learning_events`, `production_insights` |
| Infrastructure | `studios`, `lip_sync_jobs`, `scene_templates`, `platform_packages` |
| Organization | `clients`, `team_members`, `talent_voices` |

## Pre-existing Policy Issues (Tracked for Remediation)

| Issue | Count | Risk | Resolution |
|-------|-------|------|------------|
| Policies using `USING (true)` (wildcard) | ~5 | High — allows all access | Replace with org_id check |
| Policies using `current_setting()` | 5 | Medium — different auth pattern | Migrate to `auth.jwt()` |

---

## Rollback Procedure

### If migration 040 causes issues after application:

1. **Immediate rollback** — run the commented-out ROLLBACK section at the bottom of `docs/sql/040_rls_critical_tables.sql`
2. **Verify access** — confirm API endpoints that read affected tables still work
3. **Document** — note which table/policy caused the issue

### Step-by-step rollback:

```sql
-- Connect to Supabase SQL Editor
BEGIN;

-- Example: rollback brand_campaigns
DROP POLICY IF EXISTS brand_campaigns_select_own_org ON brand_campaigns;
DROP POLICY IF EXISTS brand_campaigns_insert_own_org ON brand_campaigns;
DROP POLICY IF EXISTS brand_campaigns_update_own_org ON brand_campaigns;
DROP POLICY IF EXISTS brand_campaigns_delete_own_org ON brand_campaigns;
ALTER TABLE brand_campaigns DISABLE ROW LEVEL SECURITY;

COMMIT;
```

### Per-table rollback safety:

- Disabling RLS on a table restores pre-migration behavior (no DB-level isolation)
- The backend service layer still enforces org_id filtering (defense-in-depth)
- No data is lost — rollback only changes access control

### Full rollback (all 16 tables):

See the commented `ROLLBACK SCRIPT` section at the bottom of `docs/sql/040_rls_critical_tables.sql`.

---

## Deployment Strategy (When Unblocked)

1. **Test in staging first** — apply migration 040 to a staging Supabase project
2. **Run API tests** — verify all endpoints still return data for authenticated users
3. **Apply to production** — during low-traffic window
4. **Monitor** — watch for 403/empty responses that indicate policy misconfiguration
5. **Keep rollback ready** — SQL editor open with rollback script loaded

## CI Integration

- `tests/unit/test_rls_policies.py` runs in CI and verifies:
  - All critical tables have RLS + policies
  - No wildcard policies introduced (warning)
  - INSERT policies use WITH CHECK
  - Backend code references org_id sufficiently
- Test will be upgraded from warning → failure after Story 005 remediation completes

---

## Follow-ups After Story 005

1. Resolve 42 remaining tables without RLS (assess each individually)
2. Replace 5 wildcard `USING (true)` policies with proper org_id checks
3. Migrate 5 `current_setting()` policies to `auth.jwt()` pattern
4. Add `workflow_dna` to RLS (has org_id but no RLS)
5. Upgrade test warnings to hard failures
6. Add integration tests that verify cross-tenant queries return empty results
