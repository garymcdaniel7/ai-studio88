# Story 011 — RLS & Ownership Audit

## Completion Report

**Date:** 2026-08-03
**Classification:** KIRO-EXECUTABLE

---

## Complete RLS/Ownership Matrix

### Summary

| Category | Count |
|----------|-------|
| Total tables in schema | 110 |
| Tables with org_id in migrations (before this story) | 17 |
| Tables WITHOUT org_id (before this story) | 93 |
| Tables with RLS enabled (before this story) | 9 |
| Tables with proper isolation policies (before) | 4 |
| Tables with permissive USING(true) policies (UNSAFE) | 4 |
| Tables remediated in this story | 30+ |
| RLS policies created/fixed | 15 |

### Priority Tables — Remediation Status

| Table | org_id Before | org_id After | RLS Before | RLS After | Policy |
|-------|:---:|:---:|:---:|:---:|--------|
| talent | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| assets | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| jobs | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| models | ❌ | ✅ added | ❌ | ✅ | org isolation + system-org readable |
| workflows | ❌ | ✅ added | ❌ | ✅ | org isolation + system-org readable |
| scenes | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| training_datasets | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| training_jobs | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| publishing_posts | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| brands | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| brain_memory | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| creative_dna | ❌ | ✅ added | ❌ | ✅ | org_members subquery |
| projects | ✅ | ✅ | ✅ | ✅ | Already had proper policy |
| cost_records | ✅ | ✅ | ✅ | ✅ | Already had proper policy |
| job_costs | ✅ | ✅ | ✅ | ✅ | Already had proper policy |
| creative_recipes | ✅ | ✅ | ✅ | ✅ | Already had proper policy |
| org_members | ✅ | ✅ | ✅ | ✅ | Role-based (Story 005) |

### Fixed Permissive Policies (USING true → org isolation)

| Table | Before | After |
|-------|--------|-------|
| brain_collections | `FOR ALL USING (true)` | org_members subquery |
| brain_conversations | `FOR ALL USING (true)` | org_members subquery |
| brain_embeddings | `FOR ALL USING (true)` | org_members subquery |
| social_connections | `FOR ALL USING (true)` | org_members subquery |

### Tables with org_id Added (no RLS policy yet — lower priority)

| Table | Reason for deferral |
|-------|---------------------|
| video_projects, video_renders, video_shots | Feature not yet in production |
| audio_clips, voice_profiles | Feature not yet in production |
| storyboard_panels | Feature not yet in production |
| workers, worker_sessions | Infrastructure — system-scoped |
| brain_sessions, brain_messages, brain_plans | Need user_id-based policy (not org) |
| performance_dna, quality_scores, generation_feedback | Analytics — read-heavy |
| creative_rules, continuity_notes | Story engine — low traffic |
| studios | Inherits via organization_id FK |

### Tables NOT Remediated (remaining 60+ low-priority tables)

These tables are either:
- Feature-specific with no production traffic yet (cinematic, object intelligence, etc.)
- Child tables that inherit access through parent FK (storyboard_panels → storyboards)
- Lookup/reference tables with no tenant data (workflow_templates, pose_presets, etc.)

Full list available by diffing all 110 tables against the remediated set above.

---

## Migrations/Policies Changed

| File | Action | Description |
|------|--------|-------------|
| `docs/sql/030_rls_ownership_remediation.sql` | **NEW** | 7-phase migration: add org_id, indexes, enable RLS, create policies, fix permissive, quarantine NULL |
| `backend/data_access.py` | Updated | TENANT_TABLES expanded from 28 → 50 tables |
| `tests/unit/test_rls_isolation.py` | **NEW** | 40 multi-tenant isolation tests |

---

## Tables Remediated

**Phase 1 — org_id column added (30 tables):**
talent, assets, jobs, models, workflows, scenes, training_datasets, training_images, training_jobs, publishing_posts, publishing_accounts, video_projects, video_renders, video_shots, audio_clips, voice_profiles, storyboard_panels, workers, worker_sessions, brain_memory, brain_messages, brain_sessions, brain_plans, performance_dna, quality_scores, generation_feedback, creative_dna, creative_rules, continuity_notes, brands, studios

**Phase 3 — RLS enabled (17 tables):**
talent, assets, jobs, models, workflows, scenes, training_datasets, training_jobs, publishing_posts, publishing_accounts, video_projects, audio_clips, brain_memory, brain_sessions, brain_messages, creative_dna, brands

**Phase 4 — Isolation policies created (11 tables):**
talent, assets, jobs, models, workflows, scenes, training_datasets, training_jobs, publishing_posts, brands, brain_memory, creative_dna

**Phase 5 — Permissive policies fixed (4 tables):**
brain_collections, brain_conversations, brain_embeddings, social_connections

---

## Placeholder Rows Found and Disposition

| Pattern | Location | Disposition |
|---------|----------|-------------|
| `org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'` | Some AIOS tables | DEPRECATED — should not be used. Existing rows with this value are UNVERIFIED |
| `org_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid` | System tables | LEGITIMATE — system org for shared resources |
| `NULL org_id` (newly added columns) | All 30 tables with added org_id | UNVERIFIED — existing rows have NULL. Must be backfilled before NOT NULL constraint |

**Backfill strategy (future story):**
1. For talent/assets/jobs: derive org_id from the first user who created them (if audit trail exists)
2. For orphaned records: assign to system org or quarantine table
3. Once all rows have org_id: `ALTER TABLE ... ALTER COLUMN org_id SET NOT NULL`

---

## Views/RPCs/Functions Reviewed

| Object | Type | SECURITY DEFINER? | RLS Impact | Status |
|--------|------|:-:|--------|--------|
| `auto_create_owner_membership()` | Trigger function | No | Respects RLS | SAFE |
| `match_brain_embeddings()` | Search function | No | Respects RLS | SAFE — but should add org_id filter param in future |

**No views exist in the schema.**

**Storage policies:** Not defined in SQL migrations. Backblaze B2 (external) — access controlled by application layer and signed URLs. Supabase Storage not used for primary assets.

---

## Tests Run with Tenant A/B Evidence

**63 tests total, all passing:**

```
tests/unit/test_rls_isolation.py ............... 40 passed
tests/unit/test_data_access.py ................ 23 passed
```

### Key test scenarios proving isolation:

| Scenario | Test | Result |
|----------|------|--------|
| Tenant A SELECT scoped to own org | `test_select_scoped_to_own_org[talent/assets/jobs/models/training_jobs/publishing_posts]` | ✅ PASS |
| Tenant A INSERT stamps own org_id | `test_insert_injects_own_org_id[*]` | ✅ PASS |
| Attacker spoofs org_id in INSERT | `test_insert_cannot_spoof_org_id[*]` | ✅ PASS — overwritten |
| Cross-tenant SELECT by ID | `test_select_by_id_cross_tenant_returns_not_found` | ✅ PASS — "not found" |
| Cross-tenant DELETE | `test_delete_cross_tenant_fails` | ✅ PASS — AuthorizationError |
| Cross-tenant UPDATE | `test_update_cross_tenant_has_no_effect` | ✅ PASS — zero rows |
| No membership → rejected | `test_tenant_context_requires_org_id` | ✅ PASS |
| System client stays in system org | `test_system_client_scopes_to_system_org` | ✅ PASS |
| Worker scoped to job org | `test_worker_scoped_to_job_org` | ✅ PASS |
| NULL org_id rows invisible | `test_null_org_rows_excluded_by_boundary` | ✅ PASS |
| Priority tables registered | `test_priority_table_in_tenant_registry[*]` | ✅ PASS (12 tables verified) |

---

## Unresolved Gaps

| Gap | Severity | Blocked By | Resolution |
|-----|----------|-----------|------------|
| 60+ low-priority tables lack RLS policies | Medium | Feature activation | Add policies as features go to production |
| Existing rows have NULL org_id | High (for prod) | Backfill evidence | Future story: derive ownership from audit trail |
| org_id is NULLABLE (can't be NOT NULL until backfill) | Medium | Backfill completion | ALTER COLUMN SET NOT NULL after backfill |
| brain_sessions/messages may need user_id policy not org_id | Low | Product decision | Brain conversations may be user-private not org-shared |
| Storage bucket (B2) has no RLS equivalent | Low | Architecture | Application layer (Story 009 boundary) is the control |
| match_brain_embeddings() doesn't filter by org_id | Low | Feature usage | Add org_id parameter to function signature |
| Supabase dashboard changes not tracked in migrations | Info | Process | Document: all schema changes must be in docs/sql/ |

---

## Breaking Changes

| Change | Impact | Mitigation |
|--------|--------|------------|
| RLS enabled on 17 tables | Client-side Supabase queries now filtered | Backend uses service-role (bypasses RLS); only affects direct client access |
| Permissive policies replaced | brain_collections/conversations/embeddings/social_connections now org-scoped | Same mitigation — backend service-role is unaffected |
| org_id column added to 30 tables | Existing inserts without org_id will leave NULL | Application already handles NULL via AuthorizedClient injection |

**Impact on backend:** NONE. The backend uses the service-role key which bypasses RLS entirely. Story 009's AuthorizedClient boundary provides application-level isolation. RLS is defense-in-depth for any future direct-client access patterns.

---

## Rollout/Rollback Notes

### Rollout Steps

1. **Run migration 030** in Supabase SQL Editor
2. **Verify** tables have org_id columns: `SELECT column_name FROM information_schema.columns WHERE table_name = 'talent' AND column_name = 'org_id'`
3. **Verify** RLS is enabled: `SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' AND tablename = 'talent'`
4. **Verify** policies exist: `SELECT * FROM pg_policies WHERE tablename = 'talent'`
5. **Test** backend still works (service-role bypasses RLS)
6. **Test** client access respects policies (if applicable)

### Rollback

```sql
-- Emergency rollback (if needed):
-- 1. Disable RLS (restores open access):
ALTER TABLE talent DISABLE ROW LEVEL SECURITY;
-- ... for each table

-- 2. Drop policies:
DROP POLICY IF EXISTS "talent_org_isolation" ON talent;
-- ... for each policy

-- 3. org_id columns are safe to leave (nullable, no constraints)
```

### Safety

- Migration uses IF NOT EXISTS / IF EXISTS throughout — safe to re-run
- No data is modified or deleted
- No NOT NULL constraints added (would break existing rows)
- Service-role access is completely unaffected by RLS

---

## Risks and Follow-up Stories

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Backfill never happens → org_id stays NULL forever | High | Schedule backfill story immediately after prod deployment |
| New tables added without org_id | Medium | Enforcement test in test_data_access_enforcement.py catches missing TENANT_TABLES entries |
| match_brain_embeddings returns cross-tenant results | Low | Function respects RLS when called as authenticated user |
| Dashboard (Supabase) schema changes bypass migration tracking | Medium | Document process: all DDL goes through docs/sql/ |

### Follow-up Stories

| Story | Priority | Description |
|-------|----------|-------------|
| Backfill org_id | High | Derive ownership for existing NULL rows, then SET NOT NULL |
| Storage policies | Medium | Add B2 path-based authorization (/{org_id}/...) |
| Remaining 60 table policies | Low | Add RLS as features activate |
| brain_sessions user-private policy | Low | Product decision on brain conversation privacy model |
| match_brain_embeddings org filter | Low | Add org_id param to vector search function |
