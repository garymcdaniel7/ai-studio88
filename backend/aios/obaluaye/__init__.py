"""Ọbalúayé — Platform Reliability Supervisor.

Named after the Yoruba orisha of healing and disease control.
Ọbalúayé monitors platform health, diagnoses failures, and orchestrates recovery.

## Role in AIOS

Ọbalúayé is the unified reliability supervisor. It handles both rule-based mechanics
(health checks, retries, circuit breakers) and optional LLM-powered pattern analysis
when Ollama is available. It MUST function fully without any LLM.

## Responsibilities

| Domain | Actions |
|--------|---------|
| Provider Health | Poll all providers every 30s, circuit breaker pattern |
| GPU Worker Health | SSH heartbeat to active workers |
| Queue Monitoring | Alert if jobs are stuck, retry failed jobs |
| Storage Health | Verify B2 connectivity, check quota |
| Database Health | Supabase connection pool monitoring |
| Automatic Failover | Switch providers on failure detection |
| Cost Alerting | Warn when spend approaches budget limits |
| UAT Testing | Schedule and run Playwright E2E tests via Ise |
| Diagnostics | LLM-powered root cause analysis (optional) |

## Service Health States (Circuit Breaker)

- HEALTHY: 3+ consecutive successes
- DEGRADED: 1-2 consecutive failures
- DOWN: 3+ consecutive failures
- RECOVERING: Was DOWN, now getting successes (needs 3 to become HEALTHY)

## Integration Points

- **Hermes:** Feeds health data for user queries ("is the app healthy?")
- **Ise UAT:** Runs scheduled Playwright tests, stores results, generates alerts
- **Admin Dashboard:** /aios/v1/health/* endpoints power the Ise admin page
- **@redteam:** Escalates persistent failures for strategic review
- **Recovery Engine:** Auto-retries transient failures, alerts on permanent ones
- **Cost Intelligence:** Monitors daily spend vs budget limits

## Monitored Services

| Service | Endpoint | Auto-Recovery |
|---------|----------|---------------|
| ComfyUI | GET {COMFYUI_BASE_URL}/system_stats | Restart via SSH |
| Ollama | GET {OLLAMA_BASE_URL}/api/tags | pkill + restart locally |
| Supabase | SELECT from talent LIMIT 1 | Alert only (external) |
| Backblaze B2 | Verify env vars configured | Alert only |
| ElevenLabs | GET /v1/user with API key | Alert only |
| Worker API | GET {WORKER_API_URL}/health | Restart via SSH |

## Current Status (2026-07-19)

- All P0 Red Team findings resolved (auth, tenant isolation, etc.)
- All P1 Red Team findings resolved (async gen, rate limit, dead features)
- Test baseline: 104/104 core (100%), 19/19 create-generation
- Auto-recovery: Ollama restart proven, ComfyUI restart proven
- Background monitor: runs every 30s (health), 60min (UAT)
- Alerts feed into frontend topbar bell icon

## Files in this module

- monitor.py      — HealthMonitor class, service checks, circuit breaker
- diagnostics.py  — LLM-powered failure analysis + rule-based fallback
- recovery.py     — RecoveryEngine, auto-retry, budget alerts
- background.py   — Background thread for periodic health polling
- uat_runner.py   — Playwright test execution, scheduled runs, result storage
"""
