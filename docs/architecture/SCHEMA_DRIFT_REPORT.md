# Schema Drift Report — Story 010

**Date:** 2026-08-05  
**Status:** ANALYSIS COMPLETE — Reconciliation plan requires approval  
**Scope:** All 58 committed SQL migrations vs. application code table references  

---

## 1. Executive Summary

The migration system has significant drift across three axes:

1. **Ghost tables** — 8 tables queried in code that have no CREATE TABLE migration
2. **Duplicate definitions** — 2 tables defined in multiple migrations with conflicting schemas
3. **Name mismatches** — Migration 038 references table names that don't exist in any migration
4. **Numbering collisions** — 11 migration number prefixes have multiple files
5. **Template migrations** — 3 migrations committed but marked "DO NOT APPLY"
6. **No ledger tracking** — `_migration_ledger` table defined but never populated

The system works today because tables were created manually via Supabase Dashboard 
and all migrations use `IF NOT EXISTS` patterns. But this means **no environment can 
be reliably reproduced from the migration chain alone**.

---

## 2. Ghost Tables (Queried in Code, No Migration)

These tables exist in the live database but have no CREATE TABLE statement in `docs/sql/`.

| Table | Where Queried | Likely Origin |
|-------|---------------|---------------|
| `talent` | database.py, api_v1.py, knowledge/graph.py | Created via Supabase Dashboard (pre-migration era) |
| `assets` | database.py, api_v1.py, knowledge/graph.py | Created via Supabase Dashboard (pre-migration era) |
| `storyboards` | api_v1.py, storyboard_repository.py | Created via Dashboard; confused with `storyboard_panels` |
| `fleet_settings` | infrastructure/fleet_settings.py | Created ad-hoc; single-row config pattern |
| `service_settings` | infrastructure/router.py | Created ad-hoc; single-row config pattern |
| `story_universes` | aios/knowledge/graph.py | Alias confusion — migration defines `universes` |
| `talent_loras` | aios/knowledge/graph.py | Created ad-hoc; junction table for talent ↔ LoRA |
| `publishing_analytics` | publishing/router.py | Created ad-hoc; webhook analytics storage |

**Risk:** A fresh environment built from migrations alone will fail on these queries.

---

## 3. Duplicate Table Definitions

| Table | File 1 | File 2 | Conflict |
|-------|--------|--------|----------|
| `cost_records` | 019_infrastructure_intelligence.sql | 020_cost_tracking.sql | 020 adds `org_id` column + RLS; 019 does not. Different indexes. |
| `talent_relationships` | 004_talent_extended_columns.sql | 010_talent_relationships.sql | Both define same table with `IF NOT EXISTS` — second is a no-op if first ran |

**Risk:** If executed out of order, the winning schema depends on which ran first. The `IF NOT EXISTS` pattern masks the conflict at application time but prevents schema correction.

---

## 4. Name Mismatches (Migration 038)

Migration `038_deletion_lifecycle.sql` references tables that don't match any migration:

| Referenced Name | Probable Actual Table | Evidence |
|-----------------|----------------------|----------|
| `ai_talent` | `talent` | Same columns, same purpose |
| `content_jobs` | `jobs` | Same structure |
| `lora_models` | `lora_versions` | Similar purpose |
| `campaigns` | `brand_campaigns` | Same domain |

**Risk:** Migration 038 will FAIL on any database using the migration-defined names. It only works if the Dashboard-created tables used these alternate names, or if the tables were manually renamed.


---

## 5. Migration Numbering Collisions

11 number prefixes have multiple files sharing the same sequence position:

| Prefix | Files |
|--------|-------|
| 004 | `004_continuity_and_rules.sql`, `004_talent_extended_columns.sql` |
| 010 | `010_talent_relationships.sql`, `010_voice_audio_pipeline.sql` |
| 031 | `031_creative_recipes_rls.sql`, `031_workers_rls.sql` |
| 032 | `032_aios_tenant_isolation.sql`, `032_video_rls.sql` |
| 033 | `033_talent_creative_rls.sql`, `033_training_rls.sql` |
| 034 | `034_voice_audio_rls.sql`, `034_workspace_credentials.sql` |
| 035 | `035_social_credentials.sql`, `035_storyboard_production_rls.sql` |
| 036 | `036_durable_approvals.sql`, `036_governance_policy_audit.sql`, `036_infra_authorization.sql` |
| 037 | `037_batch_generation.sql`, `037_memory_namespaces.sql` |
| 040 | `040_ownership_backfill.sql`, `040_ownership_backfill_rollback.sql`, `040_rls_critical_tables.sql` |
| 041 | `041_credential_encryption.sql`, `041_ownership_not_null_constraints.sql`, `041_security_hardening.sql`, `041b_leaked_password_protection.sql` |

**Risk:** No defined execution order within a number prefix. Automated migration runners cannot determine correct sequence. Human operators must know the implicit dependency graph.

---

## 6. Template/Blocked Migrations

These files are committed but explicitly marked as not ready to apply:

| File | Status | Reason |
|------|--------|--------|
| `040_rls_critical_tables.sql` | "TEMPLATE — DO NOT APPLY" | Blocked on Story 004 approval |
| `041_credential_encryption.sql` | "TEMPLATE — DO NOT APPLY" | Blocked on Stories 004-006 |
| `041b_leaked_password_protection.sql` | Documentation only | Not SQL — Supabase Dashboard config change |

**Risk:** An operator who runs "all migrations" will apply templates prematurely. No file-level gate prevents this.

---

## 7. Migration Ledger Status

- `_migration_ledger` table is defined in `000_migration_ledger.sql`
- It has columns for `migration_id`, `checksum`, `environment`, `status`, `applied_at`
- **No evidence** that any migration runner populates this table
- **No evidence** that any CI/CD step checks it before deploying

**Risk:** There is no authoritative record of which migrations have been applied to which environment.

---

## 8. Tables Defined in Migrations but NOT Queried in Code

These tables exist in migrations but have zero `.table("...")` references in backend code:

| Table | Migration | Possible Status |
|-------|-----------|-----------------|
| `brain_plans` | 013 | Feature not yet wired |
| `brain_sessions` | 013 | Superseded by `brain_conversations` (022) |
| `learning_events` | 014 | Feature stub |
| `production_insights` | 014 | Feature stub |
| `quality_scores` | 014 | Wired via different query pattern |
| `creative_recipes` | 027 | Accessed via frontend direct Supabase calls |
| `workspace_credentials` | 034 | Accessed via `CredentialService` (not raw table query) |
| `generation_batches` | 037 | Accessed via `batch_generation.py` module |
| `batch_variation_jobs` | 037 | Accessed via `batch_generation.py` module |

Note: Some of these ARE queried but via helper modules not caught by simple `.table("` grep. 
The first few (brain_plans, learning_events, production_insights) are genuinely unwired stubs.


---

## 9. Reconciliation Plan

### Phase 1: Create Missing Migrations (Ghost Tables)

Write CREATE TABLE migrations for the 8 ghost tables. Priority order:

| Priority | Table | Action |
|----------|-------|--------|
| P0 | `talent` | Write migration matching live schema (inspect via Dashboard) |
| P0 | `assets` | Write migration matching live schema |
| P1 | `storyboards` | Write migration OR rename code to use `storyboard_panels` |
| P1 | `fleet_settings` | Write simple config-table migration |
| P1 | `service_settings` | Write simple config-table migration |
| P2 | `story_universes` | Fix code to use `universes` (the migration-defined name) |
| P2 | `talent_loras` | Write junction-table migration |
| P2 | `publishing_analytics` | Write analytics-table migration |

### Phase 2: Resolve Name Mismatches (Migration 038)

**Option A:** Rename migration 038 references to match migration-defined names:
- `ai_talent` → `talent`
- `content_jobs` → `jobs`
- `lora_models` → `lora_versions`
- `campaigns` → `brand_campaigns`

**Option B:** If live database actually uses `ai_talent`, `content_jobs`, etc., write 
alias/rename migrations to consolidate.

**Recommended:** Inspect live Supabase schema to determine which names are canonical, 
then fix the other side (migrations or code) to match.

### Phase 3: Resolve Duplicate Definitions

| Table | Resolution |
|-------|-----------|
| `cost_records` | Keep 020 (has org_id). Add comment to 019 marking it as superseded. |
| `talent_relationships` | Keep 010. Add comment to 004 marking its version as superseded. |

### Phase 4: Fix Numbering

Renumber migrations to establish a single linear sequence. Proposed scheme:

```
000   → 000  (ledger bootstrap)
001-018 → keep as-is (no conflicts)
019   → 019  (infra, remove cost_records definition)
020   → 020  (cost tracking — canonical cost_records)
021-029 → keep as-is
030   → 030  (RLS remediation)
031a  → 031  (creative_recipes_rls)
031b  → 032  (workers_rls)
032a  → 033  (aios_tenant_isolation)
032b  → 034  (video_rls)
...etc
```

**Alternative:** Adopt a date-based naming convention (e.g., `20260801_001_batch_generation.sql`) 
that eliminates number collisions entirely.

### Phase 5: Populate Migration Ledger

1. Inspect live Supabase to determine which migrations are actually applied
2. Backfill `_migration_ledger` with status records for all applied migrations
3. Add a pre-deploy CI step that checks ledger before applying new migrations
4. Add post-deploy step that records applied migrations with checksums

### Phase 6: Gate Template Migrations

Either:
- Move templates to a `docs/sql/templates/` directory (excluded from runners)
- Add a `-- STATUS: TEMPLATE` header check to migration runners that skips them
- Remove the `040_rls_critical_tables.sql` template (superseded by Story 006 output)

---

## 10. Verification Steps

Before any reconciliation is applied:

1. **Take a full Supabase database backup** (pg_dump or Supabase Dashboard)
2. **Run dry-run on a disposable project** (Supabase branch or local Postgres)
3. **Compare live schema** (`\dt` + `\d tablename`) against migration expectations
4. **Verify application still starts** after each migration phase
5. **Run existing test suite** to confirm no regressions

### CI Integration (Future)

```yaml
# .github/workflows/schema-validation.yml
- name: Check migration chain
  run: |
    # Verify all migrations apply cleanly to empty DB
    docker run -d --name pg postgres:15
    for f in docs/sql/0*.sql; do
      psql -f "$f" || exit 1
    done
    # Verify all queried tables exist
    python scripts/verify_schema_coverage.py
```

---

## 11. Environment Map (Known)

| Environment | Database | Migration State | Notes |
|-------------|----------|-----------------|-------|
| Production (Vercel) | Supabase project | Unknown | Ghost tables exist from Dashboard; ledger unpopulated |
| Local dev | Same Supabase project | Same as production | Single-env development |
| CI | No database | Skipped | Tests mock all DB calls |
| Staging | None | — | Does not exist yet |

---

## 12. Unresolved Drift (Cannot Fix Without Live Access)

| Issue | Blocker |
|-------|---------|
| Which migrations are actually applied in production? | Need `_migration_ledger` backfill or live schema inspection |
| Do ghost tables match expected schema? | Need `\d talent`, `\d assets` from live DB |
| Are migration 038 names the real table names? | Need live schema verification |
| Are there Dashboard-created columns not in any migration? | Need full `pg_dump --schema-only` comparison |

---

## 13. Follow-ups

| Item | Story |
|------|-------|
| Write migrations for ghost tables | New story |
| Fix migration 038 name references | Story 010 implementation |
| Renumber migration chain | Story 010 implementation |
| Backfill migration ledger | Story 010 implementation |
| Add schema validation to CI | New story |
| Create disposable staging environment | Infra story |
| Drift detection automated check | CI story |
