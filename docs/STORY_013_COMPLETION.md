# Story 013 — Creative Recipes RLS Hardening

## Completion Report

**Date:** 2026-08-03
**Classification:** KIRO-EXECUTABLE

---

## Summary

Replaced the broad `FOR ALL USING (org_id = jwt_org OR is_public = true)` policy on `creative_recipes` with four operation-specific policies that enforce:
- Public recipes are readable but not client-writable
- Tenant recipes are restricted to the owning workspace
- Ownership (org_id) is immutable via client access
- `is_public` cannot be escalated by ordinary users
- System recipes (`created_by = 'system'`) are protected from client modification

Also fixed seeded data: migrated zero-UUID org_id to canonical system org.

---

## Files and Migrations Changed

| File | Action | Description |
|------|--------|-------------|
| `docs/sql/031_creative_recipes_rls.sql` | **NEW** | Operation-specific RLS migration |
| `tests/unit/test_creative_recipes_rls.py` | **NEW** | 22 policy tests covering all actor classes |

---

## Policies Added/Removed

| Policy | Operation | Action |
|--------|-----------|--------|
| `recipe_org_isolation` | FOR ALL | **REMOVED** — was too broad |
| `creative_recipes_org_isolation` | FOR ALL | **REMOVED** — from Story 030 sweep if present |
| `recipes_select` | SELECT | **ADDED** — public OR own org |
| `recipes_insert` | INSERT | **ADDED** — own org, private only, no system claim |
| `recipes_update` | UPDATE | **ADDED** — own org, non-system, immutable org_id/is_public |
| `recipes_delete` | DELETE | **ADDED** — own org, private only, non-system |

---

## Grants Changed

None. Existing grants are unchanged. RLS policies are the enforcement mechanism.

---

## Data Backfill Impact

| Change | Rows Affected | Risk |
|--------|--------------|------|
| `org_id '...000' → '...001'` for seeded recipes | 10 system recipes | LOW — corrects placeholder to canonical system org |
| Existing tenant recipes (if any) | 0 expected | Already have correct org_id (NOT NULL constraint in schema) |

**UNVERIFIED rows:** The `creative_recipes` table has `org_id UUID NOT NULL` in its original schema (migration 027), so there should be no NULL org_id rows. Any rows with the zero-UUID (`...000`) are corrected to system org by Phase 1 of this migration.

---

## Tests Added and Results

```
pytest tests/unit/test_creative_recipes_rls.py -v
======================= 22 passed in 0.21s ========================
```

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| TestRecipeSelect | 3 | Own org read, cross-org blocked, system read |
| TestRecipeInsert | 4 | Editor create, spoof blocked, viewer blocked, system claim |
| TestRecipeUpdate | 4 | Editor update, cross-org blocked, viewer blocked, ownership immutable |
| TestRecipeDelete | 4 | Owner delete private, cross-org blocked, system protected, viewer blocked |
| TestSystemRecipeManagement | 3 | System create/update/delete public recipes |
| TestAnonymousAccess | 2 | Empty user_id/org_id rejected |
| TestPolicyContract | 2 | Table registered, system org correct |

---

## Access Matrix

| Actor | SELECT public | SELECT own private | INSERT own | UPDATE own private | DELETE own private | Write public/system |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| Owner (same org) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Editor (same org) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Viewer (same org) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Other org user | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Anonymous | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| System (service-role) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Security Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| RLS bypassed by service-role | By design | Story 009 AuthorizedClient boundary enforces app-level authorization |
| `created_by` field is TEXT (not FK) | Low | WITH CHECK prevents 'system' claim; value is informational |
| API endpoints use hardcoded list, not DB | Info | Existing behavior preserved; future story should query DB with AuthorizedClient |
| `is_public` toggle requires service-role | By design | Admin action via SystemContext; no self-service public publishing |

---

## Rollback Steps

```sql
-- Emergency rollback:
DROP POLICY IF EXISTS "recipes_select" ON creative_recipes;
DROP POLICY IF EXISTS "recipes_insert" ON creative_recipes;
DROP POLICY IF EXISTS "recipes_update" ON creative_recipes;
DROP POLICY IF EXISTS "recipes_delete" ON creative_recipes;

-- Restore original broad policy:
CREATE POLICY "recipe_org_isolation" ON creative_recipes
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid OR is_public = true);

-- Revert org_id fix (if needed):
UPDATE creative_recipes
SET org_id = '00000000-0000-0000-0000-000000000000'::uuid
WHERE org_id = '00000000-0000-0000-0000-000000000001'::uuid
AND created_by = 'system';
```

---

## Unresolved UNVERIFIED Rows

None for `creative_recipes`. The table was created with `org_id UUID NOT NULL` (migration 027), so all rows have a valid org_id. The only issue was the deprecated zero-UUID placeholder on seeded rows, which this migration corrects.

---

## Follow-up Tasks

| Task | Priority | Description |
|------|----------|-------------|
| Migrate API endpoints to query DB | Medium | Replace hardcoded `_SYSTEM_RECIPES` in api_v1.py with AuthorizedClient query |
| Add auth to recipe endpoints | Medium | GET /recipes currently requires no auth |
| Recipe publishing workflow | Low | Admin UI for toggling `is_public` on tenant recipes |
| Recipe versioning | Low | Track changes to system recipes over time |

---

## Confirmation: Unrelated Recipe Behavior Preserved

The existing API endpoints (`GET /recipes`, `GET /recipes/{id}`, `POST /recipes/{id}/use`) are **completely unaffected** by this change because:
1. They read from a hardcoded Python list (`_SYSTEM_RECIPES`), not from the database
2. They have no auth requirement (unchanged)
3. The RLS policies only affect direct database access (Supabase client or service-role queries)

The `aios/knowledge/workflow_dna.py` module writes to `workflow_dna` table (separate from `creative_recipes`) — also unaffected.
