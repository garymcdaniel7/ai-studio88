# Readiness & Promotion Gates — Story 013

**Status: BLOCKED** — readiness infrastructure exists and tests pass. Full deployment verification awaits prerequisite stories.

---

## Existing Infrastructure

The readiness system is already implemented:

| Component | Location | Status |
|-----------|----------|--------|
| Liveness probe | `GET /health` | Deployed (always 200) |
| Readiness probe | `GET /ready` | Deployed (503 if required cap fails) |
| Capability detail | `GET /ready/capabilities` | Deployed (full breakdown) |
| Capability checks | `backend/app/core/capability_readiness.py` | 9 checks implemented |
| Readiness router | `backend/app/core/readiness.py` | Mounted in main.py |
| Failure-injection tests | `tests/unit/test_readiness_gates.py` | 29 tests passing |

---

## Capability Matrix

### Required Capabilities (block promotion if unavailable)

| Capability | Check | What It Verifies | Failure Impact |
|------------|-------|------------------|----------------|
| `configuration` | `check_configuration()` | Settings validate for profile | App cannot operate safely |
| `database` | `check_database()` | Supabase SELECT query succeeds | No data access possible |
| `auth` | `check_auth()` | JWT secret configured (DEGRADED if dev mode) | No authentication |
| `routers` | `check_routers()` | All routers loaded at startup | Missing API endpoints |

### Optional Capabilities (degrade gracefully if unavailable)

| Capability | Check | What It Verifies | Degraded Behavior |
|------------|-------|------------------|-------------------|
| `storage` | `check_storage()` | B2 bucket accessible | No file upload/download |
| `gpu` | `check_gpu()` | Vast.ai or RunPod key present | No GPU job dispatch |
| `generation` | `check_generation()` | ComfyUI reachable (or simulation mode) | No image/video generation |
| `llm` | `check_llm()` | Ollama/OpenAI/Anthropic available | No Brain chat, no AIOS |
| `queue` | `check_queue()` | Redis ping succeeds | No background job processing |
| `voice` | (future) | ElevenLabs API key valid | No voice generation |
| `training` | (future) | Training pipeline operational | No LoRA training |

---

## Promotion Gate Rules

### Deployment Promotion (CI → Staging → Production)

| Gate | Condition | Evidence |
|------|-----------|----------|
| **Build gate** | `npm run build` exits 0 + `tsc --noEmit` exits 0 | CI artifact |
| **Test gate** | `pytest tests/unit/` 0 failures | CI job result |
| **Readiness gate** | `GET /ready` returns 200 post-deploy | HTTP check from deployment orchestrator |
| **Promotion hold** | If `/ready` returns 503 for >60s after deploy, rollback | Railway/Vercel health check |

### Readiness Response Interpretation

| HTTP Status | `ready` | Meaning | Action |
|-------------|---------|---------|--------|
| 200 | `true` | All required capabilities ready | Accept traffic |
| 200 | `true` (degraded) | Required ready, some optional degraded | Accept traffic, alert ops |
| 503 | `false` | Required capability failed | Block traffic, investigate |

### Railway Integration

```toml
# railway.toml
[deploy]
healthcheckPath = "/ready"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### Vercel Integration

Vercel doesn't support readiness probes directly. Instead:
- Build must succeed (`next build` exit 0)
- Preview deployment URL is tested via CI after deploy

---

## Check Behavior

### Timeout Policy
- Each check: max 5 seconds
- If a check hangs, TIMEOUT state returned (treated as UNAVAILABLE)
- Thread-based timeout (daemon thread killed after deadline)

### Caching Policy
- Results cached for 30 seconds
- Prevents thundering herd on rapid `/ready` polling
- Cache cleared on startup and test teardown

### Sanitization
- No secrets in readiness responses
- Key/token/password values replaced with `***`
- URL credentials redacted (`://***@`)
- Messages truncated to 300 chars

### Startup Failure Tracking
- `register_startup_failure()` called when router import fails
- Failures surfaced in `/ready` response under `startup_failures`
- Router failures make `routers` capability UNAVAILABLE

---

## Failure-Injection Test Coverage

| Category | Tests | What's Proven |
|----------|-------|---------------|
| Required capability blocking | 5 | DB/auth/router/config/timeout failures → ready=false |
| Optional capability degradation | 3 | GPU/generation/all-optional down → still ready |
| Timeout handling | 3 | Slow checks bounded, exceptions caught |
| Sanitization | 5 | No secrets leak in responses |
| Startup failures | 4 | Router failures tracked and surfaced |
| Cache behavior | 2 | Cached results reused, TTL respected |
| Policy verification | 7 | Required/optional classified, no overlap, timeouts bounded |

**Total: 29 tests, all passing**

---

## What Cannot Be Proven Until Deployed

| Verification | Reason Blocked |
|--------------|----------------|
| Live database check in staging | Need staging Supabase configured |
| B2 storage connectivity in prod | Need prod B2 credentials |
| ComfyUI reachable from deployed instance | Need GPU worker running |
| Redis queue check in prod | Need prod Redis |
| End-to-end promotion rollback | Need Railway deployment |
| Vercel preview build gate | Need Vercel project configured |

---

## Follow-ups (After Prerequisites)

1. Add `voice` and `training` capability checks
2. Configure Railway health check to use `/ready` (already in railway.toml)
3. Add Vercel preview test step to CI (post-deploy check)
4. Implement promotion-hold automation (if `/ready` 503 for >60s → rollback)
5. Add `/ready` to monitoring/alerting (PagerDuty/Opsgenie)
6. Add deployment evidence retention (log each deploy's readiness snapshot)
