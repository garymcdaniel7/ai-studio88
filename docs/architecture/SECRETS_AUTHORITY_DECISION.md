# Secrets Authority Decision Document

**Status:** DECISION REQUIRED — Founder Approval  
**Date:** 2026-08-05  
**Blocks:** Story 007 (Credential Encryption Production Implementation)  

---

## 1. Current State (Problems)

| Issue | Severity | Detail |
|-------|----------|--------|
| Deterministic dev key used when `CREDENTIAL_ENCRYPTION_KEY` is unset | **CRITICAL** | Any attacker who reads the source code can decrypt all credentials |
| No key rotation mechanism | HIGH | If key is compromised, all customer tokens are exposed with no remediation path |
| No key backup/recovery | HIGH | If the key is lost, all encrypted customer tokens are irrecoverable |
| Audit trail is in-memory only | MEDIUM | Lost on restart; no durable forensic evidence |
| Social tokens stored as plaintext | HIGH | `social_connections.access_token` column is unencrypted |
| Platform secrets in `.env` on disk | MEDIUM | Single point of compromise; no access logging |
| No separation between dev and prod keys | HIGH | Same code path, same fallback — environment confusion possible |

---

## 2. Secrets Classification

### Tier 1: Platform Infrastructure Secrets

These authenticate AI Studio itself to external services.

| Secret | Current Location | Access Needed By |
|--------|-----------------|------------------|
| `SUPABASE_SERVICE_ROLE_KEY` | `.env` / Vercel env | Backend only |
| `SUPABASE_JWT_SECRET` | `.env` / Vercel env | Backend only |
| `DATABASE_URL` | `.env` / Vercel env | Backend only |
| `B2_APPLICATION_KEY` | `.env` / Vercel env | Backend only |
| `STRIPE_SECRET_KEY` | `.env` / Vercel env | Backend only |
| `CREDENTIAL_ENCRYPTION_KEY` | `.env` / Vercel env | Backend only |
| `SECRET_KEY` (app signing) | `.env` / Vercel env | Backend only |

### Tier 2: Customer Provider Tokens

These belong to customers and authenticate their accounts on third-party services.

| Provider | Current Storage | Encryption |
|----------|----------------|-----------|
| Vast.ai | `workspace_credentials` table | Fernet (if key set) |
| RunPod | `workspace_credentials` table | Fernet (if key set) |
| OpenAI | `workspace_credentials` table | Fernet (if key set) |
| Anthropic | `workspace_credentials` table | Fernet (if key set) |
| ElevenLabs | `social_connections` table | **PLAINTEXT** |
| HuggingFace | `workspace_credentials` table | Fernet (if key set) |

### Tier 3: Transient/Session Secrets

| Secret | Lifecycle | Storage |
|--------|-----------|---------|
| GPU worker SSH keys | Per-job (ephemeral) | In-memory during job |
| Supabase user JWTs | Short-lived (30 min) | Client-side |
| Webhook signatures | Per-request | Verified, not stored |


---

## 3. Authority Options Evaluated

### Option A: Doppler (Recommended)

| Property | Detail |
|----------|--------|
| What it is | SaaS secrets manager with environment-aware injection |
| Tier 1 handling | All platform secrets stored in Doppler; injected at deploy time |
| Tier 2 handling | `CREDENTIAL_ENCRYPTION_KEY` stored in Doppler; customer tokens remain in DB encrypted with this key |
| Key rotation | Built-in versioning; old values accessible for decrypt during transition |
| Access control | Per-environment, per-team-member RBAC |
| Audit | Full access log with IP, user, timestamp |
| Backup/recovery | Managed by Doppler (SOC 2 Type II) |
| Integration | Vercel native integration; CLI for local dev |
| Cost | Free tier (5 users, 3 envs); Team $18/user/month |
| Break-glass | Admin dashboard, emergency key export |
| Dev/prod separation | Separate environments with different keys |

**Advantages:** Zero-config Vercel integration, RBAC, audit trail, environment separation, no infrastructure to manage, SOC 2 certified.

### Option B: AWS Secrets Manager + KMS

| Property | Detail |
|----------|--------|
| What it is | AWS-managed secret storage with HSM-backed encryption |
| Tier 1 handling | Secrets stored in AWS SM; fetched at app startup |
| Tier 2 handling | Customer encryption key stored as KMS CMK; envelope encryption |
| Key rotation | Automatic rotation with Lambda; supports multi-version |
| Access control | IAM policies (fine-grained but complex) |
| Audit | CloudTrail (all access logged) |
| Backup/recovery | Cross-region replication |
| Integration | Requires AWS SDK; no native Vercel integration |
| Cost | $0.40/secret/month + $0.05 per 10K API calls |
| Break-glass | AWS root account |
| Dev/prod separation | Separate AWS accounts or IAM boundaries |

**Advantages:** HSM-backed, automatic rotation, cross-region, enterprise-grade.  
**Disadvantages:** Requires AWS account/infrastructure, IAM complexity, no Vercel-native integration, latency on cold starts.

### Option C: Supabase Vault (pgsodium)

| Property | Detail |
|----------|--------|
| What it is | PostgreSQL-native encryption using pgsodium extension |
| Tier 1 handling | Not applicable (Vault is for data-at-rest in DB) |
| Tier 2 handling | Customer tokens encrypted at DB layer transparently |
| Key rotation | Manual (alter key in Vault) |
| Access control | DB-role-based |
| Audit | PostgreSQL audit extension (pgaudit) |
| Backup/recovery | Part of DB backup |
| Integration | Native to Supabase; no external service |
| Cost | Free (included in Supabase) |
| Break-glass | Supabase Dashboard root access |
| Dev/prod separation | Different Supabase projects |

**Advantages:** No external dependency, included in Supabase, transparent encryption.  
**Disadvantages:** Only covers DB-stored secrets (not .env/deploy secrets), no rotation automation, limited audit, no RBAC beyond DB roles.

### Option D: App-Managed Fernet (Current — Not Recommended for Production)

| Property | Detail |
|----------|--------|
| What it is | Application-level Fernet encryption with env-var key |
| Tier 1 handling | Secrets in .env file (unmanaged) |
| Tier 2 handling | Customer tokens encrypted with single Fernet key |
| Key rotation | Manual (generate new key, re-encrypt all tokens, deploy) |
| Access control | Whoever has .env access |
| Audit | In-memory only (lost on restart) |
| Backup/recovery | Manual (export .env and hope) |
| Integration | Already implemented |
| Cost | Free |
| Break-glass | Whoever holds the .env file |
| Dev/prod separation | Depends on discipline (currently same code path) |

**Advantages:** Already working, no external dependency, zero cost.  
**Disadvantages:** No RBAC, no audit persistence, no automatic rotation, key loss = total data loss, dev key fallback is a security hole.


---

## 4. Recommendation: Doppler + App-Level Fernet (Hybrid)

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  DOPPLER (Secrets Authority)                                 │
│  Stores: CREDENTIAL_ENCRYPTION_KEY, SUPABASE_SERVICE_ROLE_  │
│          KEY, B2_APPLICATION_KEY, STRIPE_SECRET_KEY, etc.    │
│  Provides: Environment injection, RBAC, audit, rotation     │
└───────────────────────────┬─────────────────────────────────┘
                            │ inject at deploy/runtime
┌───────────────────────────▼─────────────────────────────────┐
│  APPLICATION (Backend)                                        │
│  Uses: CREDENTIAL_ENCRYPTION_KEY to encrypt/decrypt          │
│  Tier 2 customer tokens in Supabase workspace_credentials    │
└───────────────────────────┬─────────────────────────────────┘
                            │ encrypted blob
┌───────────────────────────▼─────────────────────────────────┐
│  SUPABASE (Database)                                          │
│  Stores: encrypted_secret column (never plaintext)            │
│  Protects: RLS prevents cross-tenant access to blobs          │
└─────────────────────────────────────────────────────────────┘
```

### Why Hybrid?

- **Doppler** manages Tier 1 secrets (platform keys) — proper authority, RBAC, audit
- **Fernet** continues to encrypt Tier 2 secrets (customer tokens) — keeps encryption app-managed and portable
- **Supabase** stores the encrypted blobs — RLS provides tenant isolation
- **Doppler** holds the Fernet master key — key itself is managed, rotatable, backed up

This preserves the existing `CredentialService` code while adding a proper authority behind the key.

---

## 5. Governance Rules (Proposed)

### 5.1 Key Access Roles

| Role | Access | Permissions |
|------|--------|-------------|
| **Founder (Security Owner)** | Full Doppler admin | Create/rotate/revoke any secret; break-glass |
| **Lead Engineer** | Doppler dev + staging | Read secrets for dev/staging; cannot access production |
| **CI/CD Service** | Doppler machine token | Read-only for deployment injection |
| **GPU Workers** | None (receive job-specific tokens via backend) | Never see master keys |
| **Frontend** | None | Never has access to any Tier 1 or Tier 2 secret |

### 5.2 Rotation Cadence

| Secret Type | Rotation Frequency | Trigger |
|-------------|-------------------|---------|
| `CREDENTIAL_ENCRYPTION_KEY` | Annually + on compromise | Manual initiation → re-encrypt all tokens |
| `SUPABASE_SERVICE_ROLE_KEY` | Annually | Regenerate in Supabase → update Doppler |
| `B2_APPLICATION_KEY` | Annually | Regenerate in B2 → update Doppler |
| `STRIPE_SECRET_KEY` | On compromise only | Stripe does not require routine rotation |
| Customer provider tokens | Per-customer decision | Customer revokes in provider; re-enters in UI |

### 5.3 Rotation Procedure (CREDENTIAL_ENCRYPTION_KEY)

1. Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Store new key in Doppler as `CREDENTIAL_ENCRYPTION_KEY_V2`
3. Deploy backend with both keys available (MultiFernet supports multiple)
4. Run migration script: decrypt all tokens with old key, re-encrypt with new key
5. Verify all tokens decrypt successfully with new key
6. Remove old key from Doppler
7. Audit: record rotation event with timestamp, actor, affected credential count

### 5.4 Backup & Recovery

| Component | Backup Method | Recovery |
|-----------|--------------|----------|
| Doppler secrets | Doppler's built-in versioning + SOC 2 infrastructure | Restore from Doppler history |
| Encryption key (emergency export) | Founder exports key → encrypted USB → physical safe | Break-glass: retrieve from safe |
| Customer tokens (encrypted blobs) | Supabase database backup (pg_dump) | Restore DB + have encryption key |

### 5.5 Emergency Revocation

| Scenario | Action | Owner | Timeline |
|----------|--------|-------|----------|
| Key compromise suspected | Rotate immediately; re-encrypt all tokens | Founder | < 1 hour |
| Employee departure | Remove from Doppler; rotate if they had prod access | Founder | Same day |
| Customer reports token leak | Revoke specific credential in DB; notify customer | Engineering | < 30 min |
| Provider breach (e.g., OpenAI leaked) | Bulk-revoke all credentials for that provider | Engineering | < 1 hour |

### 5.6 Audit Requirements

| Event | Logged | Retention |
|-------|--------|-----------|
| Secret accessed (read) | Doppler audit log | 1 year |
| Secret rotated | Doppler + app audit table | Indefinite |
| Customer token stored | `credential_audit_log` table | Indefinite |
| Customer token resolved (decrypted) | `credential_audit_log` table | 90 days |
| Customer token revoked | `credential_audit_log` table | Indefinite |
| Failed decrypt attempt | Application logs | 90 days |

### 5.7 Dev/Prod Key Separation

| Environment | Key Source | Value |
|-------------|-----------|-------|
| Development | Doppler "dev" environment | Unique dev key (not deterministic!) |
| Staging | Doppler "staging" environment | Unique staging key |
| Production | Doppler "production" environment | Unique production key |
| CI/Test | Generated per-run (`Fernet.generate_key()`) | Ephemeral |

**Critical rule:** The deterministic dev fallback in `credentials.py` MUST be removed. Application MUST fail to start if `CREDENTIAL_ENCRYPTION_KEY` is not set.


---

## 6. Rejected Alternatives & Rationale

| Option | Rejected Because |
|--------|-----------------|
| **AWS Secrets Manager + KMS** | Requires AWS account/infrastructure the project doesn't have; IAM complexity disproportionate for current team size (1 founder); no native Vercel integration adds deployment friction; cost is marginal but operational overhead is significant |
| **Supabase Vault (pgsodium)** | Only covers Tier 2 (DB-stored) secrets; does not manage Tier 1 platform secrets (.env); no RBAC; no rotation automation; audit is minimal; doesn't solve the "where does the master key live?" problem |
| **HashiCorp Vault** | Self-hosted infrastructure requirement; operational burden of running + upgrading Vault cluster; overkill for < 5 team members; significant setup time |
| **App-Managed Fernet (status quo)** | No authority, no audit, no RBAC, no backup, no rotation, deterministic dev key is a P0 vulnerability; explicitly marked "not for production" in existing code comments |
| **1Password Secrets Automation** | Limited API integration; primarily designed for team password management, not runtime secret injection; no native Vercel integration |
| **Infisical** | Similar to Doppler but less mature ecosystem; fewer Vercel-native integrations; smaller SOC 2 track record |

---

## 7. Implementation Instructions (For Story 007)

Once this decision is approved:

### Step 1: Create Doppler Account & Project

```bash
# Install Doppler CLI
brew install dopplerhq/cli/doppler
doppler login

# Create project
doppler projects create ai-studio

# Create environments
doppler environments create --project ai-studio dev
doppler environments create --project ai-studio staging  
doppler environments create --project ai-studio production
```

### Step 2: Populate Secrets

Move all values from `.env` into Doppler's production environment:
- `CREDENTIAL_ENCRYPTION_KEY` (generate fresh: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`
- `B2_APPLICATION_KEY`
- `STRIPE_SECRET_KEY`
- All other Tier 1 secrets from `.env.example`

### Step 3: Integrate with Vercel

```bash
doppler integrations create vercel --project ai-studio
```

Or via Doppler Dashboard → Integrations → Vercel.

### Step 4: Remove Deterministic Dev Key

In `backend/credentials.py`, change `_get_fernet_key()`:

```python
def _get_fernet_key() -> bytes:
    if not _RAW_KEY:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPTION_KEY is not set. "
            "Cannot start without encryption key. "
            "Set via Doppler or environment variable."
        )
    raw = _RAW_KEY.encode()
    if len(raw) == 44:
        return raw
    derived = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(derived)
```

### Step 5: Persist Audit Trail to Database

Replace in-memory `_credential_audit` with writes to `credential_audit_log` table (already defined in migration 034).

### Step 6: Migrate Social Tokens

Execute migration `041_credential_encryption.sql` Phase A to encrypt existing plaintext tokens in `social_connections`.

---

## 8. Decisions Required (Founder Approval)

| # | Decision | Recommendation | Approved? |
|---|----------|---------------|-----------|
| 1 | Select Doppler as production secrets authority | Yes | ☐ |
| 2 | Founder is sole production key admin (initially) | Yes — expand when team grows | ☐ |
| 3 | Remove deterministic dev key fallback | Yes — hard fail on missing key | ☐ |
| 4 | Annual rotation cadence for CREDENTIAL_ENCRYPTION_KEY | Yes | ☐ |
| 5 | Physical backup of master key (encrypted USB in safe) | Yes | ☐ |
| 6 | Migrate social_connections tokens to encrypted storage | Yes (Story 007 scope) | ☐ |

---

## 9. Cost Summary

| Item | Monthly Cost |
|------|-------------|
| Doppler (Team plan, 1-2 users) | $0-18/month |
| AWS KMS (rejected) | ~$5/month + operational time |
| Supabase Vault (rejected) | $0 (included) but insufficient |
| Current approach | $0 but insecure |

---

## 10. Post-Approval Obligations

1. **Before second customer:** Doppler must be configured and deterministic key removed
2. **Before public launch:** Complete rotation rehearsal documented
3. **Within 30 days of approval:** Social token encryption migration complete
4. **Quarterly:** Review Doppler audit logs for anomalous access

---

*This document must be approved before Story 007 production implementation can proceed.*
