# Story 008 — Completion Report

**Classification:** P1 Security Implementation Story
**Status:** Ready for Application
**Date:** 2026-08-05

---

## Summary

Hardened all database functions against search_path manipulation, minimized public RPC grants, documented leaked-password protection enablement, and assessed the vector extension schema placement.

---

## Deliverables

| # | Deliverable | File | Status |
|---|---|---|---|
| 1 | Function search_path pinning | `docs/sql/041_security_hardening.sql` (Phases 1–3) | Ready |
| 2 | RPC grant minimization | `docs/sql/041_security_hardening.sql` (Phase 4) | Ready |
| 3 | Leaked-password protection | `docs/sql/041b_leaked_password_protection.sql` | Manual step |
| 4 | Vector extension decision | `docs/sql/041_security_hardening.sql` (Phase 5) | Accepted exception |
| 5 | Rollback script | `docs/sql/041_security_hardening.sql` (bottom) | Ready |

---

## Function Changes

### match_brain_embeddings(vector(768), FLOAT, INT)

| Attribute | Before | After |
|---|---|---|
| search_path | Mutable (system default) | `SET search_path = 'public'` |
| Table refs | `brain_embeddings` | `public.brain_embeddings` |
| Type refs | `vector(768)` | `public.vector(768)` |
| EXECUTE grant | PUBLIC (anyone) | authenticated + service_role only |
| SECURITY mode | INVOKER (unchanged) | INVOKER (unchanged) |

**Note:** search_path includes `public` because the `<=>` cosine distance operator is installed there by the vector extension. An empty path would break operator resolution.

### auto_create_owner_membership()

| Attribute | Before | After |
|---|---|---|
| search_path | Mutable (system default) | `SET search_path = ''` |
| Table refs | `org_members` | `public.org_members` |
| EXECUTE grant | PUBLIC | postgres only |
| SECURITY mode | INVOKER (unchanged) | INVOKER (unchanged) |

### update_updated_at_column()

| Attribute | Before | After |
|---|---|---|
| search_path | Mutable (system default) | `SET search_path = ''` |
| Table refs | None (operates on NEW) | None |
| EXECUTE grant | PUBLIC | postgres only |
| SECURITY mode | INVOKER (unchanged) | INVOKER (unchanged) |

---

## Auth Setting: Leaked-Password Protection

| Setting | Before | After |
|---|---|---|
| leaked_password_protection.enabled | false | **true** (apply manually) |
| leaked_password_protection.mode | n/a | **block** |

**Action required:** Enable via Supabase Dashboard or Management API (see `041b_leaked_password_protection.sql` for exact steps).

**Verification:** Attempt signup with `password123` — expect 422 rejection.

---

## Grant Review

| Object | Grant | Grantee | Verdict |
|---|---|---|---|
| `match_brain_embeddings()` | EXECUTE | PUBLIC | **Revoked** → authenticated + service_role |
| `auto_create_owner_membership()` | EXECUTE | PUBLIC | **Revoked** → postgres only |
| `update_updated_at_column()` | EXECUTE | PUBLIC | **Revoked** → postgres only |
| `workers_tenant_view` | SELECT | authenticated | **Correct** — no change |

---

## Vector Extension — Accepted Exception

**Finding:** `vector` extension installed in `public` schema (outside tracked migrations).

**Risk assessment:** LOW
- Adds types (`vector`) and operators (`<=>`, `<#>`, `<+>`) — no data tables
- Cannot be weaponized for cross-tenant data exfiltration
- Operator shadowing mitigated by pinning function search_path
- Supabase officially installs extensions in `public`; moving breaks tooling

**Decision:** Accept. Re-evaluate when Supabase ships native extensions schema support.

---

## Migration Execution Order

1. Apply `041_security_hardening.sql` in Supabase SQL Editor (single transaction)
2. Enable leaked-password protection via Dashboard (per `041b` instructions)
3. Verify: call `match_brain_embeddings` via RPC as authenticated user (should work)
4. Verify: call `match_brain_embeddings` as anon (should get permission denied)
5. Verify: create org → owner membership auto-created (trigger still fires)
6. Verify: update any table with `updated_at` trigger (still fires)

---

## Test Scenarios Covered by Migration Design

| Scenario | Expected Result |
|---|---|
| Authenticated user calls `match_brain_embeddings` via RPC | Works (GRANT to authenticated) |
| Anonymous/unauthenticated calls `match_brain_embeddings` | Permission denied |
| Org creation triggers `auto_create_owner_membership` | Works (trigger executes as table owner) |
| Table update fires `update_updated_at_column` | Works (trigger executes as table owner) |
| Function with manipulated search_path | Pinned path prevents resolution attacks |
| Signup with breached password | 422 rejection (after auth setting enabled) |
| Password reset with breached password | Forced to choose non-breached password |
| Existing users with weak passwords | Not locked out; blocked on next change only |

---

## Follow-ups

| # | Item | Priority | Blocked by |
|---|---|---|---|
| 1 | Add `org_id` parameter to `match_brain_embeddings` for tenant-scoped vector search | Medium | Story 009 (AuthorizedClient) |
| 2 | Track vector extension creation in migrations (`CREATE EXTENSION IF NOT EXISTS vector`) | Low | None |
| 3 | Audit any future functions added to project for search_path + grant hardening | Ongoing | None |
| 4 | Monitor leaked-password rejection rate after enabling (false positive risk) | Low | Auth setting applied |
| 5 | Consider `SECURITY INVOKER` explicit annotation on functions (PostgreSQL 15+) | Low | None |

---

## Files Modified

- `docs/sql/041_security_hardening.sql` (new)
- `docs/sql/041b_leaked_password_protection.sql` (new)
- `docs/story_008_completion_report.md` (this file)
