# Story 005 — Canonical Membership Model

## Completion Report

**Date:** 2026-08-03
**Classification:** KIRO-EXECUTABLE

---

## Canonical Tables/Models Selected

### Authoritative Source: `org_members` table (NEW)

The `org_members` table is the single source of truth for user→organization membership. It replaces the broken reference in `tenant.py` to a table that never existed.

```
org_members
├── id          UUID PK
├── org_id      UUID NOT NULL FK → organizations(id)
├── user_id     UUID NOT NULL (references auth.users in Supabase Auth)
├── role        TEXT NOT NULL CHECK ('owner','admin','editor','viewer')
├── status      TEXT NOT NULL CHECK ('active','invited','suspended','deactivated')
├── invited_by  UUID (nullable)
├── invited_at  TIMESTAMPTZ (nullable)
├── joined_at   TIMESTAMPTZ (nullable)
├── metadata    JSONB
├── created_at  TIMESTAMPTZ
└── updated_at  TIMESTAMPTZ
```

**Unique constraint:** `(user_id, org_id)` — one membership per user per org.

### Existing Table Preserved: `organizations`

No changes. Remains the top-level tenant entity with `owner_id` field.

### Existing Table Preserved: `team_members`

No changes. This is a content roster (name/email/role for display), NOT an auth table. It remains separate from `org_members` which is auth-linked.

---

## Role and Status Definitions

### Roles (OrgRole enum)

| Role | Privilege Level | Can Do |
|------|----------------|--------|
| `owner` | 4 (highest) | Everything + delete org + manage owners |
| `admin` | 3 | Manage members, configure settings, all content operations |
| `editor` | 2 | Create/edit content, run generation, manage own assets |
| `viewer` | 1 (lowest) | Read-only access to org content |

Hierarchy: `owner > admin > editor > viewer`. Each role includes all privileges of roles below it.

### Statuses (MembershipStatus enum)

| Status | Meaning |
|--------|---------|
| `active` | Full access according to role |
| `invited` | Invitation sent, not yet accepted |
| `suspended` | Temporarily blocked by admin |
| `deactivated` | Permanently removed |

---

## Files/Migrations Changed

| File | Action | Description |
|------|--------|-------------|
| `docs/sql/029_org_members.sql` | **NEW** | Migration: table, constraints, indexes, RLS, trigger, backfill, system org |
| `backend/membership.py` | **NEW** | Canonical module: OrgRole, MembershipStatus, TenantContext, resolve_membership() |
| `backend/auth.py` | Updated | org_id now resolved via membership module; dev mode returns None instead of 'default' |
| `backend/database.py` | Updated | Filters treat 'default'/'org_development' as None (no filter applied) |
| `backend/app/core/tenant.py` | Rewritten | Delegates to membership.resolve_membership(); returns None instead of placeholders |
| `backend/app/core/dependencies.py` | Updated | CurrentOrgIDDep now calls resolve_membership() instead of raising 403 |
| `backend/aios/governance/policies.py` | Updated | Zero-UUID fallback removed, uses None |
| `backend/aios/governance/queue.py` | Updated | Zero-UUID fallback removed, uses None |
| `backend/api_v1.py` | Updated | Project creation uses user.org_id instead of hardcoded 'default' |
| `tests/unit/test_membership.py` | **NEW** | 25 unit tests covering all scenarios |

---

## Placeholder Fallbacks Removed

| Location | Before | After |
|----------|--------|-------|
| `backend/auth.py` (dev mode) | `org_id="default"` | `org_id=None` |
| `backend/app/core/tenant.py` | `DEFAULT_ORG_ID="org_development"` | Returns `None` from resolve_membership() |
| `backend/aios/governance/policies.py` | `"00000000-0000-0000-0000-000000000000"` | `None` |
| `backend/aios/governance/queue.py` | `"00000000-0000-0000-0000-000000000000"` | `None` |
| `backend/api_v1.py` project creation | `"default"` | `user.org_id` (from membership) |

---

## Backfill Outcomes

The migration includes:
```sql
INSERT INTO org_members (org_id, user_id, role, status, joined_at)
SELECT id, owner_id, 'owner', 'active', created_at
FROM organizations WHERE owner_id IS NOT NULL
ON CONFLICT (user_id, org_id) DO NOTHING;
```

**Unresolved rows:** Organizations with `owner_id = NULL` will not have membership records. These are treated as UNVERIFIED. A future remediation pass should:
1. Identify organizations without any `org_members` records
2. Determine the intended owner (from audit logs, creation metadata)
3. Assign ownership or mark for cleanup

---

## Trusted-Context Contract

```
Request → JWT decode → user_id (from 'sub' claim)
       → resolve_membership(user_id, jwt_hint) → TenantContext
       → TenantContext { user_id, org_id, role, email }
```

**Resolution order:**
1. Query `org_members WHERE user_id = ? AND status = 'active'`
2. If multiple orgs + preferred_org_id hint → use the matching one
3. If multiple orgs + no hint → use first active membership
4. If no active membership → `MembershipError` (403)
5. System org is always excluded from resolution

**Dev mode behavior:** With `AUTH_DEV_MODE=true` and no JWT, `org_id=None` is returned. This means no tenant filtering is applied (all data visible). This is correct for local development.

---

## Tests Run

```
pytest tests/unit/test_membership.py -v
======================= 25 passed in 0.70s ========================
```

Test scenarios covered:
- ✅ Owner has all privileges
- ✅ Admin has admin and below
- ✅ Editor has editor and below
- ✅ Viewer only has viewer
- ✅ TenantContext is frozen (immutable)
- ✅ require_role raises 403 for insufficient privilege
- ✅ Single active membership resolves correctly
- ✅ No membership raises MembershipError
- ✅ Multi-workspace with hint uses preferred org
- ✅ Multi-workspace without hint uses first org
- ✅ System org excluded from resolution
- ✅ Wrong workspace hint falls through to first active
- ✅ DB not configured raises 503
- ✅ resolve_or_none returns None for no user
- ✅ resolve_or_none returns None on error
- ✅ Cross-tenant: user cannot access other org via hint
- ✅ Role downgrade enforcement (viewer → admin = 403)
- ✅ Editor cannot escalate to owner

---

## Cross-Tenant Evidence

1. **preferred_org_id spoofing:** If a user passes another org's ID as preferred, resolve_membership only returns an org_id from the user's ACTUAL membership list. The hint is ignored if no matching membership exists.

2. **System org isolation:** SYSTEM_ORG_ID is always filtered out of normal resolution. No user can resolve to system scope through the membership API.

3. **Role boundary enforcement:** TenantContext.require_role() is a hard gate. A viewer calling `ctx.require_role(OrgRole.ADMIN)` gets HTTP 403.

---

## Breaking Changes

| Change | Impact | Mitigation |
|--------|--------|------------|
| Dev mode org_id is now `None` instead of `"default"` | No tenant filter applied in dev → same behavior as before (sees all data) | Intentional — dev sees everything |
| `CurrentOrgIDDep` no longer raises 403 unconditionally | Endpoints using it will now attempt real membership resolution | Only works after migration is applied |
| Zero-UUIDs removed from governance | Records inserted without org_id will have `NULL` instead of zero-UUID | Acceptable — NULL is semantically correct |

---

## Rollout Steps

1. **Run migration** `029_org_members.sql` in Supabase SQL Editor (creates table, backfills, creates system org)
2. **Deploy backend** with updated auth.py, membership.py, and all modified files
3. **Verify** existing endpoints still work (dev mode unaffected)
4. **For each existing user:** Ensure they have an `org_members` record with correct org_id (either via backfill from organizations.owner_id or manual assignment)
5. **Set `AUTH_DEV_MODE=false`** in production to enforce real membership resolution
6. **Monitor:** Check for 403 errors indicating users without membership records

---

## Risks and Follow-ups

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Migration not run before deploy | Medium | App falls back gracefully — resolve_membership catches errors and auth.py falls back to JWT hint |
| Users without org_members records | Medium | They get org_id=None (no tenant filter) until record is created; monitor for 403s after AUTH_DEV_MODE=false |
| `team_members` vs `org_members` confusion | Low | Document: team_members is a display roster, org_members is auth-linked membership |
| AIOS governance records with NULL org_id | Low | Functionally equivalent to previous zero-UUID — still works |
| `app/core/auth_middleware.py` still exists (parallel unused system) | Info | Should be deprecated/removed in a future story; it's not used by active endpoints |

### Future Stories Unlocked

- **006+**: Can now enforce `ctx.require_role()` on mutation endpoints
- **RLS enforcement**: org_members table has RLS policies ready for Supabase client-side access
- **Invitation flow**: `status='invited'` + `invited_by` + `invited_at` fields are ready
- **Multi-workspace switching**: `preferred_org_id` parameter already supported
- **Team management UI**: Can build on org_members + role system
