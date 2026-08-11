# Story 006: Required Application Code Changes

These changes prevent future writes with placeholder org_id values.
Apply BEFORE running migration 041 (NOT NULL constraints).

---

## 1. `backend/aios/governance/policies.py` (line ~69)

**Problem:** Falls back to zero-UUID when org_id is None.

**Fix:**
```python
# BEFORE (UNSAFE):
"org_id": org_id or "00000000-0000-0000-0000-000000000000",

# AFTER (SAFE):
if not org_id:
    raise ValueError("org_id is required to save governance policies")
"org_id": org_id,
```

---

## 2. `backend/aios/governance/queue.py` (line ~43)

**Problem:** Falls back to zero-UUID when org_id is None.

**Fix:**
```python
# BEFORE (UNSAFE):
"org_id": org_id or "00000000-0000-0000-0000-000000000000",

# AFTER (SAFE):
if not org_id:
    raise ValueError("org_id is required to enqueue approvals")
"org_id": org_id,
```

---

## 3. `backend/infrastructure/cost_intelligence.py` `persist_to_db()` (~line 98)

**Problem:** Writes to cost_records WITHOUT org_id field.

**Fix:** Add org_id to the CostRecord dataclass and include in insert:
```python
# In persist_to_db:
supabase.table("cost_records").insert({
    "org_id": record.org_id,  # ADD THIS
    "session_id": record.session_id,
    "start_time": record.start_time,
    ...
}).execute()
```

This requires adding `org_id: str` to the `CostRecord` dataclass
and passing it from the caller (job dispatch context).

---

## 4. `backend/auth.py` — AUTH_DEV_MODE change

**Problem:** Dev mode returns `org_id=None`, disabling tenant filtering.

**Fix:** Dev mode should resolve to a real dev org:
```python
# BEFORE:
if _AUTH_DEV_MODE:
    return AuthUser(
        user_id="dev-user-local",
        email="dev@localhost",
        org_id=None,  # DISABLES ALL FILTERING
        role="owner",
    )

# AFTER:
if _AUTH_DEV_MODE:
    dev_org = os.getenv("DEV_ORG_ID", None)
    return AuthUser(
        user_id="dev-user-local",
        email="dev@localhost",
        org_id=dev_org,  # Tenant filtering active if DEV_ORG_ID set
        role="owner",
    )
```

Add `DEV_ORG_ID` to `.env.example`.

---

## 5. `backend/api_v1.py` — Convert `optional_auth` reads

**Problem:** GET endpoints with `optional_auth` allow unauthenticated
access and return unfiltered data.

**Fix:** Change to `require_auth`:
```python
# Lines affected:
# 114: v1_talent → require_auth
# 241: v1_list_assets → require_auth
# 4465: list_projects → require_auth
```

---

## 6. RLS Policy Fix — `cost_records` and `job_costs`

**Problem:** RLS policies hardcoded to system-UUID:
```sql
-- CURRENT (BROKEN):
CREATE POLICY "cost_records_org_isolation" ON cost_records
    FOR ALL USING (org_id = '00000000-0000-0000-0000-000000000001'::uuid);
```

**Fix:** Use proper org_members subquery (same pattern as other tables):
```sql
DROP POLICY IF EXISTS "cost_records_org_isolation" ON cost_records;
CREATE POLICY "cost_records_org_isolation" ON cost_records
    FOR ALL USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    );
```

Same for `job_costs`.

---

## Summary of Files to Modify

| File | Change |
|------|--------|
| `backend/aios/governance/policies.py` | Raise on None org_id |
| `backend/aios/governance/queue.py` | Raise on None org_id |
| `backend/infrastructure/cost_intelligence.py` | Add org_id to writes |
| `backend/auth.py` | Dev mode uses DEV_ORG_ID env var |
| `backend/api_v1.py` | Convert 3 endpoints to require_auth |
| `.env.example` | Add DEV_ORG_ID |
