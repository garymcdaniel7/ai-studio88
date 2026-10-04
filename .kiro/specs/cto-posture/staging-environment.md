# Staging / Test Environment — Non-Destructive Verification

**Purpose:** Safe sandbox for destructive acceptance tests (F5 tenant isolation, RLS probes, auth enforcement) that MUST NOT touch production data.

---

## Primary: Local Docker Compose (no Supabase dependency)

The fastest path for most tests. Runs a self-contained stack with local Redis and connected services.

```bash
cd ~/kiro/ai-studio88

# Start the stack
docker compose up -d redis nginx api

# Verify health
curl -f http://localhost:8000/health

# Run acceptance tests locally
cd backend
python -m pytest tests/ -v --tb=short
```

**What it covers:** All unit/integration tests that don't require Supabase RLS (133 tests pass per audit). Auth-guard tests, route-level enforcement, and wiring verification all run here without touching prod.

**Limitation:** No real Supabase RLS enforcement — uses the local `.env` `SUPABASE_*` values, which in `development` mode point at the production Supabase instance. ⚠️ **Do NOT run F5 (tenant isolation) or RLS-disabled tests against this setup without the staging Supabase project below.**

---

## Secondary: Supabase Staging Project (for RLS / tenant-isolation tests)

**CURRENT STATE:** ✅ Staging project created 2026-10-03.

- **Project ref:** `xvafacjfhosvoowotztz`
- **Dashboard:** https://supabase.com/dashboard/project/xvafacjfhosvoowotztz
- **URL:** `https://xvafacjfhosvoowotztz.supabase.co`
- **JWT secret:** Set via Management API (stored in `.env.staging`)
- **Pooler URL:** `postgresql://postgres.xvafacjfhosvoowotztz@aws-0-us-west-2.pooler.supabase.com:5432/postgres`

**Setup steps:**

1. **Retrieve API keys** from the Supabase dashboard (Settings → API → Project API keys):
   - `anon` key (JWT, starts with `eyJhbG...`)
   - `service_role` key (JWT, starts with `eyJhbG...`)
   
   These cannot be retrieved via CLI/API — the Supabase API masks JWT keys by design. Copy them from the dashboard into `.env.staging`.

2. Link the project (already linked in `~/kiro/ai-studio88`):
   ```bash
   supabase link --project-ref xvafacjfhosvoowotztz
   ```

3. Source the staging env:
   ```bash
   export $(grep -v '^#' .env.staging | xargs)
   ```

4. Apply migrations:
   ```bash
   supabase db push
   ```

5. Disable RLS on the staging project (as required by F5 test spec) to verify the application-layer enforcement without the RLS safety net:
   ```sql
   ALTER TABLE social_connections DISABLE ROW LEVEL SECURITY;
   ALTER TABLE analytics_snapshots DISABLE ROW LEVEL SECURITY;
   -- (repeat for all RLS tables)
   ```

6. Run F5 test:
   ```bash
   APP_ENV=staging python -m pytest tests/unit/test_rls_isolation.py -v --tb=long
   ```

7. Re-enable RLS after test:
   ```sql
   ALTER TABLE social_connections ENABLE ROW LEVEL SECURITY;
   -- (repeat for all tables)
   ```

---

## Credentials Storage

- **Production Supabase creds:** Live in `~/kiro/ai-studio88/.env` (local; never committed)
- **Staging Supabase creds:** `~/kiro/ai-studio88/.env.staging` (created 2026-10-03) — contains URL, pooler URL, JWT secret. **Missing:** anon + service_role JWT keys (retrieve from Supabase dashboard → Settings → API → Project API keys)
- **Railway deployment:** Managed via Railway dashboard (production `main` branch auto-deploys)
- **Kiro access:** Kiro sources the staging env before test runs:
  ```bash
  export $(grep -v '^#' .env.staging | xargs)
  ```

---

## Test matrix by environment

| Test Suite | Docker Compose (local) | Supabase Staging | Production | Notes |
|---|---|---|---|---|
| Unit tests (auth wiring) | ✅ Run here | ✅ Can run | ❌ No | No Supabase needed |
| F1 — legacy route guard | ✅ Run here | ✅ Run here | ❌ No | `curl` against local API |
| F2 — publishing auth | ✅ Run here | ✅ Run here | ❌ No | Requires app-layer enforcement |
| F5 — tenant isolation | ❌ Can't test RLS | ✅ **Must run here** | ❌ No | RLS disabled on staging only |
| F6 — `is_production` guard | ❌ Can't test | ❌ Can't test | ✅ Verify in prod | Verify dev fallback blocked |
| F7 — permission sweep | ✅ Run here | ✅ Run here | ✅ Verify in prod | Already verified |
| F8 — migration verify | ❌ Can't apply | ✅ Apply here | ✅ Verify in prod | Migration applied first to staging |
| End-to-end flow | ❌ Requires real API | ❌ Partial | ✅ Final verify | Smoke test key flows in prod |

---

## Acceptance criteria for staging readiness

- [ ] Staging Supabase project created (`ai-studio-staging`)
- [ ] `.env.staging` written with `APP_ENV=staging` credentials
- [ ] Kiro can source `.env.staging` and run `pytest tests/unit/test_rls_isolation.py` without touching production data
- [ ] All migrations applied and verified against staging DB
- [ ] Production `.env` has `APP_ENV=production` guard (already verified in audit)

---

## Note to Kiro

The only supported testing paths are:
1. **Local Docker Compose** — safe for all non-RLS tests
2. **Supabase Staging project** — for RLS/tier-isolation/destructive tests

Never run `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` or DELETE/UPDATE on the production Supabase project. The production `SUPABASE_SERVICE_ROLE_KEY` has full DDL access and there is no undo.