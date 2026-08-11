# Credential Security Design — Story 007

**Status: BLOCKED** — awaiting Stories 004-006. Templates and tests ready.

---

## Problem Statement

`social_connections` stores OAuth access and refresh tokens as plaintext TEXT columns, with a wildcard RLS policy (`USING (true)`) that allows any authenticated user to read any tenant's tokens.

## Current Architecture (What Exists)

| Component | Status | Notes |
|-----------|--------|-------|
| `backend/credentials.py` | Complete | CredentialService with Fernet encryption, masked views, rotation, revocation, audit |
| `backend/social_credentials.py` | Complete | Social-provider extensions (scope validation, refresh tracking) |
| `workspace_credentials` table (034) | Deployed | Encrypted column (`encrypted_secret`), proper RLS, audit log |
| `credential_audit_log` table (034) | Deployed | Audit trail for all credential operations |
| `social_connections` table (021) | **INSECURE** | Plaintext `access_token`, `refresh_token`, wildcard RLS |

## Target Architecture

```
┌────────────────────┐
│  Client / Frontend │  ← sees ONLY masked metadata (platform, status, expiry)
└────────┬───────────┘
         │
┌────────▼───────────┐
│  API Endpoints     │  ← returns masked_view(), NEVER plaintext
└────────┬───────────┘
         │
┌────────▼───────────┐
│  CredentialService │  ← encrypts on store, decrypts only for authorized ops
│  (credentials.py)  │     audit trail on every resolve()
└────────┬───────────┘
         │
┌────────▼───────────┐
│  Supabase DB       │  ← encrypted_access_token, encrypted_refresh_token
│  (social_conns)    │     org_id-scoped RLS, column-level REVOKE
└────────────────────┘
```

## Storage Design

### Encryption

- **Algorithm:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Key source:** `CREDENTIAL_ENCRYPTION_KEY` env var
- **Key derivation:** SHA-256 hash → base64url encode → Fernet key
- **Each encryption:** Fresh random IV (ciphertexts differ even for same plaintext)

### Column Layout (post-migration)

```sql
-- social_connections (after migration 041)
encrypted_access_token  TEXT    -- Fernet-encrypted blob
encrypted_refresh_token TEXT    -- Fernet-encrypted blob  
encryption_version      INT    -- Key version (for rotation)
token_encrypted_at      TIMESTAMPTZ
-- access_token          DROPPED (Phase C)
-- refresh_token         DROPPED (Phase C)
```

### Access Control (defense-in-depth)

| Layer | Control |
|-------|---------|
| RLS policy | org_id = auth.jwt() → 'org_id' (replaces `USING (true)`) |
| Column-level REVOKE | authenticated role cannot SELECT token columns |
| Application layer | CredentialService.resolve() is the only decrypt path |
| API layer | Only masked_view() returned to clients |
| Log layer | redact_secrets() applied to all error messages and logs |

## Token Lifecycle

### Store (OAuth callback)

```python
# After successful OAuth flow:
CredentialService.store(
    org_id=tenant.org_id,
    provider=ProviderType.INSTAGRAM,  # via SocialPlatform mapping
    secret=access_token,
    key_id=f"oauth:{platform}:{account_handle}",
    actor=user_id,
    metadata={"refresh_token": _encrypt(refresh_token), "scope": granted_scopes}
)
```

### Resolve (publishing job needs token)

```python
# Backend worker preparing to publish:
token = CredentialService.resolve(
    org_id=job.org_id,
    provider=ProviderType.INSTAGRAM,
    actor="publishing_worker",
    purpose=f"publish_job:{job.id}",
)
# token is plaintext — used immediately, never stored/logged
```

### Refresh (token expired)

```python
# Automated refresh flow:
new_tokens = await refresh_oauth_token(platform, encrypted_refresh_token)
CredentialService.rotate(
    org_id=org_id,
    provider=provider,
    new_secret=new_tokens.access_token,
    actor="token_refresh_worker",
)
```

### Revoke (user disconnects account)

```python
CredentialService.revoke(
    org_id=org_id,
    provider=ProviderType.INSTAGRAM,
    actor=user_id,
)
# Also call provider's revocation endpoint
```

## Migration Plan

### Phase A (SQL — non-breaking)
- Add encrypted columns to social_connections
- Replace wildcard RLS with org_id policy
- Revoke column-level access from authenticated role
- Fix UNIQUE constraint (per-org, not global)
- **Migration file:** `docs/sql/041_credential_encryption.sql`

### Phase B (Application — one-time task)
- Script iterates all rows with plaintext tokens
- Encrypts each using CredentialService._encrypt()
- Writes to encrypted_* columns, sets encryption_version=1
- Verify count matches

### Phase C (SQL — breaking, after verification)
- Drop access_token and refresh_token columns
- Update views

## Rotation Plan

### Credential Key Rotation
1. Generate new CREDENTIAL_ENCRYPTION_KEY
2. Set both old and new keys in env (comma-separated)
3. Re-encrypt all credentials with new key (background task)
4. Remove old key from env

### OAuth Token Rotation
- Automatic: refresh flow creates new version via CredentialService.rotate()
- Manual: user re-authenticates via OAuth flow
- Emergency: CredentialService.revoke() + invalidate at provider

## Redaction Rules

| Context | Mechanism |
|---------|-----------|
| API responses | CredentialRecord.masked_view() — only key_hint |
| Error messages | redact_secrets() before logging |
| Job payloads | redact_dict() on all payload dicts |
| Audit trail | Records action + actor + credential_id, never secrets |
| Database queries | Column-level REVOKE prevents SELECT on token columns |

## Unresolved Decisions (Require Gary Approval)

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Production key management | Env var / Doppler / AWS KMS / Supabase Vault | Doppler (already in security standards) |
| Key rotation frequency | Monthly / Quarterly / On-demand | Quarterly + on-demand |
| Plaintext column drop timeline | Immediate / 7 days / 30 days after Phase B | 7 days (verify no code reads old columns) |
| OAuth provider revocation | On disconnect only / On key rotation | On disconnect only |
| Backup encryption | Same key / Different key | Same key (simpler, encrypted at rest in B2) |

## Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/unit/test_credential_redaction.py` | 30 tests | All pass |
| Coverage: redact_secrets, redact_dict, encryption roundtrip, masked views, tenant isolation, audit trail, rotation, revocation | | |

## Follow-ups

1. Apply migration 041 Phase A to staging (after Story 004-006)
2. Implement Phase B migration script
3. Verify no API endpoints return plaintext tokens (scan all response schemas)
4. Apply Phase C (drop columns) after 7-day verification
5. Set up key rotation automation
6. Add provider-specific revocation calls on disconnect
