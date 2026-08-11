# Migration Renaming Map

**Created:** 2026-08-07
**Purpose:** Resolve 11 migration numbering collisions by adopting date-based naming convention
**Convention:** `YYYYMMDD_NNN_description.sql` where NNN is a sequential sub-number within a date
**Requirement:** R5.3 — each numeric prefix maps to exactly one migration file

## Naming Strategy

- Date prefix derived from git creation date of each file
- Files created on the same date receive sequential sub-numbers (_001, _002, etc.)
- Original logical ordering preserved within each date group
- Template migrations (containing "DO NOT APPLY") are marked with `[TEMPLATE]`
- SQL content inside files is NOT modified — only filenames change

## Renaming Table

| Old Name | New Name | Created | Notes |
|----------|----------|---------|-------|
| `000_migration_ledger.sql` | `20260804_001_migration_ledger.sql` | 2026-08-04 | Infrastructure |
| `001_create_jobs_table.sql` | `20260703_001_create_jobs_table.sql` | 2026-07-03 | |
| `002_create_workflows_table.sql` | `20260703_002_create_workflows_table.sql` | 2026-07-03 | |
| `003_creative_dna_and_feedback.sql` | `20260703_003_creative_dna_and_feedback.sql` | 2026-07-03 | |
| `004_continuity_and_rules.sql` | `20260703_004_continuity_and_rules.sql` | 2026-07-03 | **Collision resolved** (was 004) |
| `004_talent_extended_columns.sql` | `20260711_001_talent_extended_columns.sql` | 2026-07-11 | **Collision resolved** (was 004) |
| `005_story_engine.sql` | `20260703_005_story_engine.sql` | 2026-07-03 | |
| `006_models_and_templates.sql` | `20260703_006_models_and_templates.sql` | 2026-07-03 | |
| `006b_seed_models.sql` | `20260703_007_seed_models.sql` | 2026-07-03 | Was 006b suffix |
| `007_workers.sql` | `20260703_008_workers.sql` | 2026-07-03 | |
| `008_lora_training.sql` | `20260703_009_lora_training.sql` | 2026-07-03 | |
| `009_video_pipeline.sql` | `20260703_010_video_pipeline.sql` | 2026-07-03 | |
| `010_voice_audio_pipeline.sql` | `20260703_011_voice_audio_pipeline.sql` | 2026-07-03 | **Collision resolved** (was 010) |
| `010_talent_relationships.sql` | `20260711_002_talent_relationships.sql` | 2026-07-11 | **Collision resolved** (was 010) |
| `011_performance_engine.sql` | `20260703_012_performance_engine.sql` | 2026-07-03 | |
| `012_publishing_engine.sql` | `20260703_013_publishing_engine.sql` | 2026-07-03 | |
| `013_brain.sql` | `20260703_014_brain.sql` | 2026-07-03 | |
| `014_production_intelligence.sql` | `20260703_015_production_intelligence.sql` | 2026-07-03 | |
| `015_asset_intelligence.sql` | `20260703_016_asset_intelligence.sql` | 2026-07-03 | |
| `016_cinematic_studio.sql` | `20260703_017_cinematic_studio.sql` | 2026-07-03 | |
| `017_company_os.sql` | `20260703_018_company_os.sql` | 2026-07-03 | |
| `018_object_intelligence.sql` | `20260703_019_object_intelligence.sql` | 2026-07-03 | |
| `019_infrastructure_intelligence.sql` | `20260704_001_infrastructure_intelligence.sql` | 2026-07-04 | |
| `020_cost_tracking.sql` | `20260706_001_cost_tracking.sql` | 2026-07-06 | |
| `021_social_connections.sql` | `20260706_002_social_connections.sql` | 2026-07-06 | |
| `022_brain_collections.sql` | `20260710_001_brain_collections.sql` | 2026-07-10 | |
| `023_brain_embeddings.sql` | `20260711_003_brain_embeddings.sql` | 2026-07-11 | |
| `024_aios_gateway.sql` | `20260712_001_aios_gateway.sql` | 2026-07-12 | |
| `025_aios_governance.sql` | `20260712_002_aios_governance.sql` | 2026-07-12 | |
| `026_knowledge_graph.sql` | `20260712_003_knowledge_graph.sql` | 2026-07-12 | |
| `027_creative_recipes.sql` | `20260719_001_creative_recipes.sql` | 2026-07-19 | |
| `028_projects.sql` | `20260719_002_projects.sql` | 2026-07-19 | |
| `029_org_members.sql` | `20260804_002_org_members.sql` | 2026-08-04 | |
| `030_rls_ownership_remediation.sql` | `20260804_003_rls_ownership_remediation.sql` | 2026-08-04 | |
| `031_creative_recipes_rls.sql` | `20260804_004_creative_recipes_rls.sql` | 2026-08-04 | **Collision resolved** (was 031) |
| `031_workers_rls.sql` | `20260804_005_workers_rls.sql` | 2026-08-04 | **Collision resolved** (was 031) |
| `032_aios_tenant_isolation.sql` | `20260804_006_aios_tenant_isolation.sql` | 2026-08-04 | **Collision resolved** (was 032) |
| `032_video_rls.sql` | `20260804_007_video_rls.sql` | 2026-08-04 | **Collision resolved** (was 032) |
| `033_talent_creative_rls.sql` | `20260804_008_talent_creative_rls.sql` | 2026-08-04 | **Collision resolved** (was 033) |
| `033_training_rls.sql` | `20260804_009_training_rls.sql` | 2026-08-04 | **Collision resolved** (was 033) |
| `034_voice_audio_rls.sql` | `20260804_010_voice_audio_rls.sql` | 2026-08-04 | **Collision resolved** (was 034) |
| `034_workspace_credentials.sql` | `20260804_011_workspace_credentials.sql` | 2026-08-04 | **Collision resolved** (was 034) |
| `035_social_credentials.sql` | `20260804_012_social_credentials.sql` | 2026-08-04 | **Collision resolved** (was 035) |
| `035_storyboard_production_rls.sql` | `20260804_013_storyboard_production_rls.sql` | 2026-08-04 | **Collision resolved** (was 035) |
| `036_durable_approvals.sql` | `20260804_014_durable_approvals.sql` | 2026-08-04 | **Collision resolved** (was 036) |
| `036_governance_policy_audit.sql` | `20260804_015_governance_policy_audit.sql` | 2026-08-04 | **Collision resolved** (was 036) |
| `036_infra_authorization.sql` | `20260804_016_infra_authorization.sql` | 2026-08-04 | **Collision resolved** (was 036) |
| `037_batch_generation.sql` | `20260805_001_batch_generation.sql` | 2026-08-05 | **Collision resolved** (was 037) |
| `037_memory_namespaces.sql` | `20260804_017_memory_namespaces.sql` | 2026-08-04 | **Collision resolved** (was 037) |
| `038_deletion_lifecycle.sql` | `20260804_018_deletion_lifecycle.sql` | 2026-08-04 | |
| `039_asset_provenance.sql` | `20260804_019_asset_provenance.sql` | 2026-08-04 | |
| `040_ownership_backfill.sql` | `20260806_001_ownership_backfill.sql` | ~2026-08-06 | **Collision resolved** (was 040) |
| `040_ownership_backfill_rollback.sql` | `20260806_002_ownership_backfill_rollback.sql` | ~2026-08-06 | **Collision resolved** (was 040) |
| `040_rls_critical_tables.sql` | `20260806_003_rls_critical_tables.sql` | ~2026-08-06 | **Collision resolved** (was 040) `[TEMPLATE]` |
| `041_credential_encryption.sql` | `20260806_004_credential_encryption.sql` | ~2026-08-06 | **Collision resolved** (was 041) `[TEMPLATE]` |
| `041_ownership_not_null_constraints.sql` | `20260806_005_ownership_not_null_constraints.sql` | ~2026-08-06 | **Collision resolved** (was 041) |
| `041_security_hardening.sql` | `20260806_006_security_hardening.sql` | ~2026-08-06 | **Collision resolved** (was 041) |
| `041b_leaked_password_protection.sql` | `20260806_007_leaked_password_protection.sql` | ~2026-08-06 | **Collision resolved** (was 041b) Documentation only |

## Collisions Resolved (11 total)

| Original Prefix | Files | Resolution |
|----------------|-------|------------|
| 004 | continuity_and_rules + talent_extended_columns | Separated by actual creation date (Jul 3 vs Jul 11) |
| 010 | voice_audio_pipeline + talent_relationships | Separated by actual creation date (Jul 3 vs Jul 11) |
| 031 | creative_recipes_rls + workers_rls | Sequential sub-numbers on same date (004, 005) |
| 032 | aios_tenant_isolation + video_rls | Sequential sub-numbers on same date (006, 007) |
| 033 | talent_creative_rls + training_rls | Sequential sub-numbers on same date (008, 009) |
| 034 | voice_audio_rls + workspace_credentials | Sequential sub-numbers on same date (010, 011) |
| 035 | social_credentials + storyboard_production_rls | Sequential sub-numbers on same date (012, 013) |
| 036 | durable_approvals + governance_policy_audit + infra_authorization | Sequential sub-numbers (014, 015, 016) |
| 037 | batch_generation + memory_namespaces | Separated by actual creation date (Aug 5 vs Aug 4) |
| 040 | ownership_backfill + ownership_backfill_rollback + rls_critical_tables | Sequential sub-numbers on same date (001, 002, 003) |
| 041 | credential_encryption + ownership_not_null_constraints + security_hardening + leaked_password_protection | Sequential sub-numbers on same date (004, 005, 006, 007) |

## Template Migrations (DO NOT APPLY automatically)

| File | Marker |
|------|--------|
| `20260806_003_rls_critical_tables.sql` | "TEMPLATE — DO NOT APPLY until Story 004 approval" |
| `20260806_004_credential_encryption.sql` | "TEMPLATE — DO NOT APPLY until Stories 004-006 are approved" |
| `20260806_007_leaked_password_protection.sql` | Documentation only (Dashboard config change, not SQL execution) |

## Pre-Existing Files (already date-based, from Task 1.2 ghost table migrations)

These files were already created with the date-based naming convention and did not require renaming:

| File | Notes |
|------|-------|
| `20260808_001_ghost_table_talent.sql` | Ghost table migration |
| `20260808_002_ghost_table_assets.sql` | Ghost table migration |
| `20260808_003_ghost_table_service_settings.sql` | Ghost table migration |
| `20260808_004_ghost_table_collections.sql` | Ghost table migration |
| `20260808_005_ghost_table_prompts.sql` | Ghost table migration |
| `20260808_006_ghost_table_products.sql` | Ghost table migration |
| `20260808_007_ghost_table_content_calendar.sql` | Ghost table migration |
| `20260808_008_ghost_table_campaigns.sql` | Ghost table migration |
| `20260808_009_ghost_table_performance_memory.sql` | Ghost table migration |
| `20260808_010_ghost_table_workflow_dna.sql` | Ghost table migration |

## Verification

After renaming, the full sequence has:
- 68 SQL migration files total (57 renamed + 10 pre-existing ghost tables + 1 additional)
- 0 duplicate prefixes (verified via `uniq -d` check)
- Each `YYYYMMDD_NNN` combination is unique
- Chronological ordering preserved (sorts correctly by filename)
- All SQL content unchanged — only filenames were modified
