# Tenant Access Matrix — Story 009

**Status: BLOCKED** — test scaffolding ready, staging verification awaits Stories 004-008.

---

## Identity Types

| Identity | Description | Auth Method |
|----------|-------------|-------------|
| `owner` | Org creator, full access | JWT with org_id + role=owner |
| `admin` | Resource management, no billing | JWT with org_id + role=admin |
| `editor` | Create/modify content | JWT with org_id + role=editor |
| `viewer` | Read-only access | JWT with org_id + role=viewer |
| `revoked` | Previously active, membership removed | JWT invalid/expired |
| `forged` | Attacker with fabricated org_id | JWT fails validation |
| `anonymous` | No authentication | No header |
| `service_role` | Backend worker/system | Supabase service key |

---

## Expected Access by Resource Type

### Legend
- **Y** = Allowed
- **N** = Denied (403 or 404)
- **R** = Read only
- **S** = Service-role only

### Talent (AI models/personas)

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon |
|-----------|-------|-------|--------|--------|-----------|---------|------|
| List own org | Y | Y | Y | Y | N | N | N |
| Read detail | Y | Y | Y | Y | N | N | N |
| Create | Y | Y | Y | N | N | N | N |
| Update | Y | Y | Y | N | N | N | N |
| Delete | Y | Y | N | N | N | N | N |

### Jobs (generation/training)

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon |
|-----------|-------|-------|--------|--------|-----------|---------|------|
| List own org | Y | Y | Y | Y | N | N | N |
| Read detail | Y | Y | Y | Y | N | N | N |
| Submit | Y | Y | Y | N | N | N | N |
| Cancel | Y | Y | Y | N | N | N | N |
| Delete | Y | Y | N | N | N | N | N |

### Assets (generated images/videos)

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon |
|-----------|-------|-------|--------|--------|-----------|---------|------|
| List own org | Y | Y | Y | Y | N | N | N |
| Read/download | Y | Y | Y | Y | N | N | N |
| Upload | Y | Y | Y | N | N | N | N |
| Delete | Y | Y | N | N | N | N | N |

### Credentials (API keys, OAuth tokens)

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon | Service |
|-----------|-------|-------|--------|--------|-----------|---------|------|---------|
| List (masked) | Y | Y | N | N | N | N | N | Y |
| Store | Y | Y | N | N | N | N | N | Y |
| Resolve (decrypt) | N | N | N | N | N | N | N | **S** |
| Rotate | Y | Y | N | N | N | N | N | Y |
| Revoke | Y | Y | N | N | N | N | N | Y |
| Validate | Y | Y | Y | N | N | N | N | Y |

### Brain (AI conversations, memory)

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon |
|-----------|-------|-------|--------|--------|-----------|---------|------|
| List conversations | Y | Y | Y | Y | N | N | N |
| Read messages | Y | Y | Y | Y | N | N | N |
| Create conversation | Y | Y | Y | N | N | N | N |
| Delete conversation | Y | Y | Y | N | N | N | N |
| Read memory | Y | Y | Y | R | N | N | N |
| Write memory | Y | Y | Y | N | N | N | N |

### Workers (GPU instances)

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon | Service |
|-----------|-------|-------|--------|--------|-----------|---------|------|---------|
| List org workers | Y | Y | Y | Y | N | N | N | Y |
| Launch | Y | Y | N | N | N | N | N | **S** |
| Terminate | Y | Y | N | N | N | N | N | **S** |
| View costs | Y | Y | Y | Y | N | N | N | Y |

### Publishing (social accounts)

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon |
|-----------|-------|-------|--------|--------|-----------|---------|------|
| List accounts | Y | Y | Y | Y | N | N | N |
| Connect | Y | Y | Y | N | N | N | N |
| Publish | Y | Y | Y | N | N | N | N |
| Disconnect | Y | Y | N | N | N | N | N |

### Organization/Admin

| Operation | Owner | Admin | Editor | Viewer | Other Org | Revoked | Anon |
|-----------|-------|-------|--------|--------|-----------|---------|------|
| View org settings | Y | Y | N | N | N | N | N |
| Update org settings | Y | N | N | N | N | N | N |
| Manage members | Y | Y | N | N | N | N | N |
| View billing | Y | N | N | N | N | N | N |
| Delete org | Y | N | N | N | N | N | N |

---

## Cross-Tenant Attack Scenarios

| # | Attack | Attacker | Target | Expected |
|---|--------|----------|--------|----------|
| 1 | Read another org's talent | Beta owner | Alpha talent | 404 / empty |
| 2 | Read another org's jobs | Beta owner | Alpha job | 404 / empty |
| 3 | Read another org's assets | Beta owner | Alpha asset | 404 / empty |
| 4 | Resolve another org's credential | Beta owner | Alpha cred | None / 403 |
| 5 | Read another org's brain memory | Beta owner | Alpha brain | 404 / empty |
| 6 | Write to another org's talent | Beta editor | Alpha talent | 403 |
| 7 | Delete another org's asset | Beta owner | Alpha asset | 403 / 404 |
| 8 | Access with revoked membership | Revoked user | Own org talent | 401 / 403 |
| 9 | Access with forged org_id | Forged user | Target org | 401 / 403 |
| 10 | Resolve credential with forged ID | Forged user | Alpha cred | 401 / 403 |
| 11 | Reverse-direction read | Alpha owner | Beta talent | 404 / empty |
| 12 | Reverse-direction credential | Alpha admin | Beta cred | None / 403 |
| 13 | Unauthenticated access | Anonymous | Any resource | 401 |

---

## Verification Layers

| Layer | Mechanism | Test Method |
|-------|-----------|-------------|
| **Transport** | HTTPS only, CORS restricted | Browser test + curl |
| **Authentication** | JWT validation, expiry check | Unit test + integration |
| **Authorization** | Role + org_id from JWT, never user input | Unit test |
| **Service Layer** | org_id filter on every query | Code scan + unit test |
| **Database (RLS)** | org_id = auth.jwt() ->> 'org_id' | SQL test + integration |
| **Column-level** | REVOKE on secret columns | SQL test |
| **Application** | redact_secrets() on all outputs | Unit test |

---

## Test Files

| File | Tests | Status |
|------|-------|--------|
| `tests/fixtures/tenant_fixtures.py` | Fixture definitions (2 orgs, 9 users, 10 resources, 13 scenarios) | Created |
| `tests/unit/test_tenant_isolation.py` | 17+ unit tests covering credential isolation, org enforcement, audit, scenarios, roles | Created |
| `tests/unit/test_credential_redaction.py` | 30 tests (redaction, encryption, masking) | Passing |
| `tests/unit/test_rls_policies.py` | 8 tests (RLS coverage, policy patterns) | Passing |
| `tests/unit/test_data_access_enforcement.py` | Raw supabase usage enforcement | Passing |

---

## Residual Risks (Cannot Verify Until Staging)

| Risk | Why Blocked |
|------|-------------|
| RLS policies actually enforced in production Supabase | Need staging DB |
| Column-level REVOKE prevents SELECT | Need staging DB |
| JWT validation rejects forged tokens | Need real Supabase auth |
| Signed URLs don't leak cross-tenant | Need real B2 storage |
| WebSocket/Realtime channels are scoped | Need staging infra |
| Background job retries respect revocation | Need Celery + staging |

---

## Follow-ups (After Stories 004-008)

1. Deploy fixtures to staging Supabase
2. Run full integration test suite against staging
3. Verify Vercel preview deployments enforce auth
4. Test signed URL isolation with real B2 objects
5. Test Realtime subscription isolation
6. Penetration testing with multiple browser sessions
7. Document results and close Story 009
