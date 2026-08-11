# Release Decision — Story 014

**Date:** 2026-08-05  
**Release Candidate SHA:** `cdbf8d6a2ef7ed27196da2c7788d897a684f6390`  
**Branch:** main  
**Recommendation:** **NO-GO** (7 blocking issues)  

---

## 1. Release Candidate Identity

| Property | Value |
|----------|-------|
| Git SHA | `cdbf8d6a2ef7ed27196da2c7788d897a684f6390` |
| Branch | main |
| Last commit | 2026-08-05 — feat(frontend): stories 139+142 |
| Node.js | v26.4.0 |
| Python | 3.14.6 |
| uv | 0.11.26 |
| Next.js | 16.2.10 |
| FastAPI | latest (via uv) |

---

## 2. Evidence Matrix

| Gate | Status | Evidence | Blocker? |
|------|--------|----------|----------|
| Frontend builds from clean checkout | PASS | `npm ci && npm run build` → 0 errors, 28 routes | No |
| Frontend TypeScript | PASS | `tsc --noEmit` → 0 errors | No |
| Backend imports and starts | PASS | 31 routes loaded | No |
| Tenant isolation contract approved | FAIL | 8 decisions pending (Story 004) | **YES** |
| Ownership migration applied | FAIL | Scripts drafted but not executed (Story 006) | **YES** |
| Schema drift resolved | FAIL | 8 ghost tables, name mismatches (Story 010) | **YES** |
| Performance indexes applied | FAIL | Candidates ready, not applied (Story 012) | No (P2) |
| AUTH_DEV_MODE disabled in prod | FAIL | Still defaults to `true` | **YES** |
| All read endpoints require auth | FAIL | `optional_auth` on talent, assets, projects | **YES** |
| Migration ledger populated | FAIL | Table exists, no records | **YES** |
| Staging environment exists | FAIL | No staging/preview verified | **YES** |
| Rollback rehearsed | FAIL | Cannot rehearse without staging | **YES** |
| E2E tests pass | PARTIAL | Playwright specs exist but not run in CI | No |
| CI pipeline green | UNKNOWN | No recent CI run evidence | No |
| Secrets audit | PASS | `.env` in `.gitignore`, no secrets in repo | No |
| RLS policies active | PARTIAL | ~50% of tables have RLS; rest pending Story 006 | **YES** |
| Monitoring active | FAIL | No APM, no error tracking, no alerts | No (P2) |

---

## 3. Blocking Issues (Must Resolve Before Release)

| # | Issue | Owner | Dependency | Effort |
|---|-------|-------|-----------|--------|
| 1 | Tenant contract unapproved (8 decisions) | Founder | None — decisions needed | 1 hour |
| 2 | AUTH_DEV_MODE defaults to `true` | Engineering | Story 004 Decision 7 | 30 min |
| 3 | `optional_auth` on read endpoints | Engineering | Story 004 Decision 2 | 1 hour |
| 4 | Schema drift (ghost tables, name mismatches) | Engineering | Live DB access | 1-2 days |
| 5 | Ownership migration not executed | Engineering | Blocker #1 + #4 | 2 hours |
| 6 | Migration ledger empty | Engineering | Blocker #4 | 1 hour |
| 7 | No staging environment / rollback rehearsal | Infra | Supabase branch or second project | 2-4 hours |
| 8 | RLS incomplete (~50% of tenant tables) | Engineering | Blocker #1 + #5 | 1 day |


---

## 4. Residual Risks (Acceptable with Documented Exceptions)

These are NOT blocking but should be addressed in the next sprint:

| Risk | Severity | Mitigation |
|------|----------|-----------|
| ESLint has 216 errors (style, not correctness) | Low | Schedule lint cleanup sprint |
| No APM or error tracking | Medium | Add Sentry/equivalent before public launch |
| Performance indexes not applied | Low | Current data volume is tiny; apply when scale demands |
| Some Brain/Story features are stubs | Low | Document as "coming soon" in UI |
| Playwright tests not in CI | Medium | Wire into GitHub Actions |
| `npm audit` findings | Low | Review; none are runtime-exploitable |

---

## 5. Critical Path to Release

If the founder approves all 8 decisions from Story 004 today, the critical path is:

```
Day 1 (2-3 hrs):
  ├── Approve Story 004 decisions (founder — 1 hr)
  ├── Apply AUTH_DEV_MODE fix + optional_auth conversion (30 min + 1 hr)
  └── Set up Supabase branch for staging (1 hr)

Day 2 (4-6 hrs):
  ├── Inspect live schema (pg_dump --schema-only) to resolve drift
  ├── Write ghost table migrations
  ├── Fix migration 038 name references
  └── Backfill migration ledger

Day 3 (3-4 hrs):
  ├── Execute ownership backfill migration (Story 006)
  ├── Apply NOT NULL constraints
  ├── Verify RLS policies cover all tenant tables
  └── Rehearse rollback on staging

Day 4 (2 hrs):
  ├── Run full E2E test suite
  ├── Verify Vercel preview deployment
  └── Final go/no-go with evidence
```

**Estimated calendar time to release-ready:** 4 working days after Story 004 approval.

---

## 6. What IS Working (Positive Evidence)

| Capability | Status |
|------------|--------|
| Frontend builds and serves all 28 routes | Verified |
| Backend starts with all 31 routes (15+ routers) | Verified |
| Authentication module (JWT validation + membership resolution) | Code complete |
| Membership model (org_members, roles, TenantContext) | Code complete |
| Cost ledger with budget enforcement | Code complete |
| Batch generation with durable state | Code complete |
| Workspace credentials (encrypted storage) | Code complete |
| Governed confirmation dialogs (accessibility) | Code complete |
| Semantic design tokens (WCAG AA contrast) | Code complete |
| Brain/AIOS tenant isolation migration | Ready to apply |
| Deletion lifecycle (soft delete + holds) | Ready to apply |
| Asset provenance tracking | Ready to apply |

---

## 7. Recommendation

### **NO-GO for production release.**

**Rationale:** The application compiles and runs, but critical security controls (tenant isolation enforcement, auth requirements, schema integrity) are incomplete. Releasing without these would violate the product's non-negotiable: "per-tenant data isolation is absolute."

### Path Forward

The fastest path to release is:

1. **Founder approves Story 004 decisions** (unblocks everything else)
2. **Engineering executes the 4-day critical path** above
3. **Re-run this gate** with updated evidence

### Exceptions That Could Enable Earlier Release

If the founder accepts these risks explicitly:

| Exception | Risk Accepted | Enables |
|-----------|---------------|---------|
| "Single-tenant for now" — no other orgs will use the system | Cross-tenant leakage is impossible if there's only one tenant | Skip RLS completion, skip optional_auth conversion |
| "Dev-mode auth is acceptable" — founder is only user | Auth bypass is safe for single-user system | Skip AUTH_DEV_MODE fix |
| "Schema drift accepted" — will fix post-launch | Ghost tables work (they exist in live DB) | Skip migration reconciliation |

**If all three exceptions are granted:** Release could proceed today with residual risk documented. However, these exceptions MUST be revoked before any second tenant is onboarded.

---

## 8. Approvals

| Role | Decision | Signature | Date |
|------|----------|-----------|------|
| Founder / Product Owner | ☐ GO / ☐ NO-GO / ☐ GO WITH EXCEPTIONS | | |
| Security Owner | ☐ Approved / ☐ Exceptions Noted | | |

---

## 9. Post-Release Obligations (If GO With Exceptions)

If released with single-tenant exceptions:

1. **Before second tenant:** Complete Stories 004-006, 010 (hard gate)
2. **Within 2 weeks:** Wire Playwright tests into CI
3. **Within 1 month:** Add APM/error tracking
4. **Within 1 month:** Apply performance indexes
5. **Before public launch:** Full security audit with penetration testing

---

*This document is the final output of Story 014. No production deployment should occur without an approved decision above.*
