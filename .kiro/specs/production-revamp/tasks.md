# Implementation Plan: AI Studio Production Revamp

## Overview

This implementation plan converts AI Studio from a working prototype into a production-ready multi-tenant SaaS platform. It addresses 109 requirements across security, architecture, deployment, and feature completeness organized into 7 phases over ~20 weeks.

The plan follows the critical dependency ordering from A2-046:
- Consent + Rights/Takedown foundations BEFORE generation/publishing
- Connections Hub BEFORE provider-dependent integrations
- Social account connection BEFORE analytics sync
- Publishing provenance BEFORE closed-loop analytics
- Brain context provenance BEFORE Social Intelligence injection

Tech stack: Python 3.12+ / FastAPI / SQLAlchemy 2.x async / Pydantic v2 / Next.js 16 / TypeScript / Tailwind / shadcn/ui / Supabase (PostgreSQL 17)

## Tasks

---

## Phase 1: Truth and Security (P0) — Weeks 1-3

- [x] 1. Schema Reconciliation and Migration Baseline
  - [x] 1.1 Establish schema baseline via pg_dump and reconcile against 49 migration files
    - Run `pg_dump --schema-only` on live Supabase, compare against `docs/sql/` migration files
    - Document all discrepancies in `docs/architecture/SCHEMA_RECONCILIATION.md`
    - Classify each table/object as: REUSE, EXTEND, NEW, DEPRECATE, or REQUIRES_DATA_RECONCILIATION
    - _Requirements: R5.1, R5.13, R5.14, R5.15_

  - [x] 1.2 Create migrations for 8 ghost tables
    - Create CREATE TABLE migrations for: talent, assets, storyboards, fleet_settings, service_settings, story_universes, talent_loras, publishing_analytics
    - Each migration includes: id UUID PK, org_id UUID NOT NULL, created_at, updated_at, appropriate indexes
    - Place in `backend/alembic/versions/` with date-based naming
    - _Requirements: R5.2, R5.5_

  - [x] 1.3 Resolve 11 migration numbering collisions
    - Adopt linear date-based naming (e.g., `20250101_001_description.py`)
    - Ensure each numeric prefix maps to exactly one migration file
    - Verify full sequence applies cleanly to empty PostgreSQL 15+ database
    - _Requirements: R5.3, R5.5_

  - [x] 1.4 Populate migration ledger and register baseline
    - Create `_migration_ledger` table: migration_id, sha256_checksum, applied_at
    - Register baseline in Supabase migration tracking (`supabase migration list` reports accurate state)
    - Exclude template migrations containing "DO NOT APPLY"
    - _Requirements: R5.4, R5.9, R5.10_

  - [x] 1.5 Move vector extension and fix security issues
    - Move vector extension from public schema to extensions schema
    - Fix `match_brain_embeddings` function search_path from mutable to immutable
    - Enable leaked-password protection in Supabase project configuration
    - _Requirements: R5.11, R5.12, R6.8_

- [x] 2. Authentication Enforcement and Workspace Provisioning
  - [x] 2.1 Implement Auth Gateway with JWT validation
    - Create `backend/app/core/security.py` with `decode_supabase_jwt()` validating signature, exp (30s skew), non-empty sub
    - Create `backend/app/core/dependencies.py` with `CurrentUserIDDep`, `TenantContextDep`
    - Return 401 UNAUTHORIZED / TOKEN_EXPIRED / INVALID_TOKEN per R1 criteria
    - Enforce AUTH_DEV_MODE refuse-to-start when environment is production/staging
    - _Requirements: R1.1, R1.2, R1.3, R1.5, R1.8, R1.9_

  - [x] 2.2 Implement idempotent workspace provisioning
    - Create `backend/app/services/provisioning_service.py` with `ProvisioningService`
    - Implement `provision_workspace()` using INSERT...ON CONFLICT DO NOTHING for org + membership
    - Handle: new signup, OAuth first-login, retry scenarios without creating duplicates
    - Create org, org_member, onboarding_state in single transaction
    - _Requirements: R1.6, R1.11, R84.4, R84.5_

  - [x] 2.3 Implement OAuth support (Google)
    - Integrate Supabase Auth OAuth flow in frontend (`frontend/src/lib/auth.ts`)
    - Backend handles OAuth identity → no separate password required
    - Unified `/login` surface for both signup and login
    - _Requirements: R1.10, R84.1, R84.2, R84.3_

  - [x] 2.4 Implement dev mode with real org_id injection
    - When AUTH_DEV_MODE=true AND env is local/test: inject user_id/org_id from first org_members record
    - Never trust client-supplied user_id in any code path
    - _Requirements: R1.4, R1.8_

  - [x] 2.5 Write property tests for authentication enforcement
    - **Property 2: Authentication Enforcement Universality**
    - For all non-exempt endpoints, missing/invalid JWT returns 401
    - **Property 16: Workspace Provisioning Idempotency**
    - Repeated provisioning attempts yield exactly one workspace/membership
    - **Validates: Requirements R1.1, R1.2, R1.11, R84.5**

- [x] 3. RLS Comprehensive Audit and Tenant Isolation
  - [x] 3.1 Audit all Category A tables for RLS status
    - Script to check every table: RLS enabled, has at least one policy, policy uses org_members subquery
    - Document findings in `docs/architecture/RLS_AUDIT_RESULTS.md`
    - Fix `public.workers` — add RLS with appropriate policies
    - _Requirements: R6.1, R6.2, R6.5, R6.7, R2.4, R2.5_

  - [x] 3.2 Apply org_id NOT NULL constraints and backfill
    - Quarantine NULL org_id rows per R69 process (classify, review, assign/purge)
    - For founder-only tables (verified by audit): bulk assign to founder org_id
    - For ambiguous tables: quarantine with reason and date
    - Apply NOT NULL constraint only after all NULLs resolved per table
    - _Requirements: R5.6, R2.1, R69.1, R69.2, R69.5_

  - [x] 3.3 Implement tenant-scoped query enforcement
    - Ensure all repository methods include `WHERE org_id = :authenticated_org_id`
    - Never accept org_id from client request parameters
    - Cross-tenant access returns 404 (not 403)
    - Reject quarantined UUID (00000000-...) with 422
    - _Requirements: R2.2, R2.6, R2.7, R2.8, R2.9, R2.10_

  - [x] 3.4 Add RLS policies with USING + WITH CHECK separation
    - Production RLS distinguishes USING (SELECT/DELETE) from WITH CHECK (INSERT/UPDATE)
    - Prevents org_id forgery on writes
    - Template: `CREATE POLICY "tenant_isolation" ON <table> FOR ALL USING (...) WITH CHECK (...)`
    - _Requirements: R6.3, R6.6, A2-029_

  - [x] 3.5 Write property tests for tenant isolation
    - **Property 1: Tenant Isolation Invariant**
    - Insert as org A, attempt read/write as org B → never succeeds
    - One RLS test per Category A table
    - **Validates: Requirements R2.9, R2.13, R6.3**

- [x] 4. Configuration Safety and RBAC
  - [x] 4.1 Implement production configuration validation
    - Create `backend/app/core/config.py` with Pydantic Settings model
    - Refuse to start in production if: DEBUG=true, AUTH_REQUIRED=false, ALLOWED_ORIGINS contains "*", critical provider is simulation, URLs contain localhost
    - Validate all required secrets present and non-placeholder
    - _Requirements: R9.1, R9.2, R9.3, R9.4_

  - [x] 4.2 Implement role-based access control enforcement
    - Enforce hierarchy: owner > admin > editor > viewer
    - Viewer blocked from POST/PUT/PATCH/DELETE (403)
    - Editor blocked from DELETE on talent, model, credential, org-settings (403)
    - Resolve role from org_members table per request
    - _Requirements: R3.1, R3.2, R3.3, R3.4, R3.5, R3.6_

  - [x] 4.3 Write property tests for role hierarchy
    - **Property 5: Role Hierarchy Enforcement**
    - User with role below minimum → 403
    - **Validates: Requirements R3.1, R3.2, R3.3**

- [x] 5. CI/CD Pipeline and Input Validation
  - [x] 5.1 Set up GitHub Actions CI pipeline
    - Configure: Ruff linting, pytest (unit + integration), TypeScript compilation, ESLint, frontend build, secret scanning
    - Block merge on any failure
    - Include `pip-audit` and Bandit static analysis
    - _Requirements: R7.3, R73.4_

  - [x] 5.2 Implement comprehensive input validation
    - Create Pydantic v2 schemas with explicit constraints for all endpoints
    - UUID type for all IDs, min_length=1 for required strings, ge/le bounds for numerics
    - Whitespace-only strings rejected with 422
    - File upload: magic byte verification, size limits, MIME allowlist
    - _Requirements: R4.1, R4.2, R4.3, R4.4, R4.5, R4.8, R4.9, R4.10_

  - [x] 5.3 Implement structured error responses and logging
    - All errors: `{"detail": "...", "code": "SNAKE_CASE"}` — never stack traces
    - X-Request-ID (UUID v4) on every response, propagated to all logs
    - Structured JSON logs: timestamp, level, logger, message, request_id, org_id, user_id
    - Never log secrets/tokens/PII
    - _Requirements: R16.1, R16.2, R16.3, R16.4, R45.1, R45.2, R45.3_

- [x] 6. Checkpoint — Phase 1 verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: server starts cleanly, /health returns 200, /ready returns service status
  - Confirm: all migrations apply to empty DB without errors

---

## Phase 2: Core Infrastructure (P0/P1) — Weeks 4-6

- [x] 7. Job Leasing System
  - [x] 7.1 Create jobs table schema and leasing infrastructure
    - Create/extend `jobs` table per design: id, org_id, job_type, status, priority, idempotency_key, context_package_id, progress_percent, progress_message, error_message, output_asset_ids, cost_usd, attempt_count, max_attempts, max_duration_seconds, workload_class, started_at, completed_at
    - Add `job_leases` table: lease_id, job_id, worker_identity, lease_token, lease_expiration, heartbeat_at
    - Atomic claiming via `FOR UPDATE SKIP LOCKED`
    - _Requirements: R21.2, R21.3, R64.2, R64.4_

  - [x] 7.2 Implement JobService with leasing behavioral contract
    - Create `backend/app/services/job_service.py`
    - Submit job → status "queued", return 202 within 2 seconds
    - Claim: atomic lease with lease_token, worker_identity, lease_expiration
    - Heartbeat: extend lease at intervals <= lease_duration/3
    - Expired lease → status "lease_expired", increment attempt_count, re-queue
    - _Requirements: R21.1, R21.3, R21.4, R21.5, R21.8, R64.1, R64.3_

  - [x] 7.3 Implement idempotency, cancellation, and stale worker rejection
    - Idempotency_key dedup: same (org_id, key) for non-terminal job → return existing
    - Cancellation: revoke lease, signal worker to stop
    - Stale worker rejection: expired lease holder cannot write results
    - Progress reporting: percent, message, metadata
    - _Requirements: R21.6, R21.11, R21.12, R21.13_

  - [x] 7.4 Implement job type configurations
    - Define per-type: max_duration, retry_policy, heartbeat_interval, lease_duration, cancellation_behavior
    - Include workload_class for scheduling priority
    - Types: image_generation, video_generation, lora_training, brain_heavy_inference, batch_generation, publishing_dispatch
    - _Requirements: R64.4, R64.5_

  - [x] 7.5 Write property tests for job leasing
    - **Property 4: Job Lease Exclusivity** — at most ONE active lease per job
    - **Property 9: Idempotent Job Submission** — same key returns existing job
    - **Validates: Requirements R21.3, R21.11, R64.2**

- [x] 8. Cost Reservation and Reconciliation
  - [x] 8.1 Create cost tables and reservation system
    - Create `cost_reservations` table per design: id, org_id, job_id, operation, reserved_amount_usd, actual_amount_usd, cost_classification, status, provider, expires_at, finalized_at
    - Create `cost_entries` table: immutable cost records per job
    - Three-tier classification: customer_infrastructure, platform_expense, managed_compute
    - _Requirements: R14.1, R14.2, R14.12, R66.1_

  - [x] 8.2 Implement atomic cost reservation service
    - Create `backend/app/services/cost_service.py`
    - Single DB transaction: check budget availability AND create reservation hold
    - Reject if total reservations + actual spend > budget (daily or monthly) → 402
    - Never treat missing cost evidence as $0 — flag for manual reconciliation
    - _Requirements: R14.3, R14.4, R14.9, R14.13, R14.14, R66.2, R66.7_

  - [x] 8.3 Implement cost reconciliation and tracking endpoints
    - Post-execution: release reservation, record actual cost, log variance >20% as anomaly
    - Failed jobs: record partial GPU time consumed
    - Retry costs: independent entry per attempt
    - GET /api/v1/costs/summary: today_spend, month_spend, budgets, breakdown by provider_type
    - _Requirements: R14.5, R14.6, R14.10, R14.11, R66.3, R66.4, R66.5_

  - [x] 8.4 Write property tests for cost reservation
    - **Property 3: Cost Reservation Budget Invariant**
    - Sum of active reservations + actual spend never exceeds hard budget limit
    - **Validates: Requirements R14.9, R66.1, R66.2, R89.2**

- [x] 9. Credential Broker
  - [x] 9.1 Implement Credential Broker service
    - Create `backend/app/services/credential_broker.py`
    - `issue_job_credential()`: short-lived, scoped to job_id + org_id + allowed storage paths
    - Expiration: job max_timeout + 5 minutes grace period
    - Revoke within 60 seconds of job completion/failure/cancellation
    - _Requirements: R8.1, R8.2, R8.3, R8.4_

  - [x] 9.2 Implement credential scope enforcement and audit
    - Access outside authorized scope → rejected + violation logged (worker_id, job_id, attempted_path, timestamp)
    - Audit log: all issuances and revocations, queryable by org_id and job_id
    - Support multiple storage providers: B2 pre-signed URLs, S3 pre-signed, R2 pre-signed
    - Separate encryption authorities for production vs development
    - _Requirements: R8.5, R8.6, R8.7, R8.9_

  - [x] 9.3 Write property tests for credential isolation
    - **Property 12: Credential Scope Isolation**
    - Job credential never grants access to other jobs or orgs
    - **Property 26: External Storage Credential Scope**
    - Customer-managed storage credential limited to job's input/output scope
    - **Validates: Requirements R8.1, R8.5, A2-018**

- [x] 10. Compute Provider Abstraction
  - [x] 10.1 Define ComputeProvider interface and registry
    - Create `backend/app/providers/compute.py` with Protocol: provision, terminate, health_check, get_status, list_available, estimate_cost
    - Create `ComputeProviderCapabilities` dataclass per design
    - Provider registry: RunPod (primary), FluidStack, Lambda Labs, TensorDock, Vast.ai (legacy)
    - _Requirements: R13.1, R13.3, R13.4_

  - [x] 10.2 Implement compute availability modes (DISABLED/SELECTIVE/ENABLED)
    - Create `compute_availability_config` and `compute_selective_grants` tables
    - State changes via configuration alone (no code deploy, no restart, propagates within 60s)
    - DISABLED: UI hidden, Brain/Hermes doesn't recommend, API rejects 403 PLATFORM_COMPUTE_DISABLED
    - SELECTIVE: Founder enables by workspace, plan, cohort, workload, provider, or promotion
    - _Requirements: R13.14, R13.15, R13.16, R86.1, R86.2, R86.3, R86.5_

  - [x] 10.3 Implement Worker Orchestrator with provider abstraction
    - Refactor `backend/infrastructure/worker_orchestrator.py` to use ComputeProvider interface
    - Terminate instances in finally block, track state in Supabase (not in-memory)
    - Health checks every 60s, 3 consecutive failures → terminate + re-queue job
    - Fleet limits: fleet_max_instances per org, fleet_idle_timeout (15 min default)
    - _Requirements: R13.5, R13.6, R13.7, R13.8, R13.9, R13.10, R13.11, R13.12_

  - [x] 10.4 Write property tests for compute availability enforcement
    - **Property 14: Compute Availability Enforcement**
    - DISABLED state → API returns 403 regardless of request origin
    - **Property 23: Compute Provider Neutrality**
    - Core contracts contain no provider-specific identifiers
    - **Validates: Requirements R86.2, R13.15, R13.1, R13.2**

- [x] 11. Storage Provider Abstraction
  - [x] 11.1 Define StorageProvider interface and implementations
    - Create `backend/app/providers/storage.py` with Protocol: upload, download, delete, get_signed_url, list_objects, exists
    - Implement B2StorageProvider (default), S3CompatibleProvider, R2Provider
    - Key structure: `/{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}`
    - Never return raw URLs — always signed (3600s default) or CDN
    - _Requirements: R11.1, R11.2, R11.4, R11.7, R11.12_

  - [x] 11.2 Implement asset metadata and lifecycle management
    - Asset metadata in Supabase: id, org_id, storage_provider, storage_key, content_type, file_size_bytes, talent_id, job_id
    - Soft-delete DB record, schedule async storage deletion
    - Store org_id, job_id, content_type as object metadata on upload
    - Multipart upload for files > 100 MB
    - _Requirements: R11.3, R11.5, R11.6, R11.7, R11.9, R11.10_

- [x] 12. Realtime Event Delivery and Notification Service
  - [x] 12.1 Implement event delivery layer
    - Create `backend/app/services/event_service.py` with EventBus Protocol
    - Canonical event envelope: event_type, event_id, version, correlation_id, causation_id, sequence/cursor, timestamp, org_id, payload
    - Supabase Realtime as primary adapter
    - Tenant authorization on all subscriptions
    - _Requirements: R63.1, R63.2, R63.3_

  - [x] 12.2 Implement notification service
    - Create `notifications` table per design: id, org_id, user_id, category, title, body, action_url, is_read, is_mandatory, metadata
    - Categories: job_completed, job_failed, approval_requested, approval_resolved, connection_expired, provider_unavailable, publishing_result, budget_threshold, safety_action, hermes_needs_input
    - In-app delivery canonical; adapter interface for future channels
    - Mandatory notifications (safety, takedown) cannot be disabled
    - _Requirements: R101.1, R101.2, R101.3_

  - [x] 12.3 Implement frontend EventClient with connection states
    - Create `frontend/src/hooks/useEventClient.ts`
    - Track states: CONNECTED, RECONNECTING, DEGRADED, STALE, OFFLINE
    - Cursor-based resumption on reconnect, deduplication by event_id
    - Notification bell/badge updates via realtime events
    - _Requirements: R63.4, R63.5, R63.6_

- [x] 13. Checkpoint — Phase 2 verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: job submission returns 202, cost reservation blocks over-budget, credential broker issues/revokes correctly

---

## Phase 3: AI Runtime & Memory (P1/P2) — Weeks 7-9

- [x] 14. Governance Boundary Implementation
  - [x] 14.1 Implement canonical Governance Boundary
    - Create `backend/aios/governance_boundary.py` with `GovernanceBoundary.evaluate()`
    - Single enforcement point evaluating: identity, trust_domain, tenant_context, role, entitlement, consent, safety_policy, budget, resource_ownership, risk_classification, required_approvals, provider_capability, environment_restrictions, autonomy_profile, privacy_restrictions, compute_availability_state, feature_rollout_status
    - High-impact actions fail closed when indeterminate
    - Read-only may degrade safely
    - _Requirements: R59.1, R59.2, R59.3, R59.4, R59.5_

  - [x] 14.2 Implement approval workflow
    - Create `pending_approvals` table: action_type, estimated_cost_usd, parameters, requesting_user_id
    - Require approval for: delete permanent, spend > $5, launch 3+ workers, publish to social, clone voice, any "destructive" tool
    - POST /aios/v1/approvals/{id}/approve and /reject
    - Approvals expire after 24 hours without action
    - _Requirements: R30.1, R30.2, R30.3, R30.4, R30.5, R30.6, R30.7_

  - [x] 14.3 Implement governance logging and audit
    - Log every evaluation: request_id, identity, trust_domain, action_type, risk_classification, result, denial_reason
    - All AI-initiated side effects must have governance_evaluation record before execution
    - _Requirements: R59.6, R59.7_

  - [x] 14.4 Write property tests for governance boundary
    - **Property 7: Governance Boundary Completeness**
    - No side effect executes without governance check
    - **Validates: Requirements R59.1, R59.6**

- [x] 15. Trust Domain Separation
  - [x] 15.1 Implement trust domain model and enforcement
    - Create `backend/app/core/trust_domains.py` with domain hierarchy
    - Domains: FOUNDER_PRIVATE > PLATFORM_ADMIN > WORKSPACE_ADMIN > CUSTOMER_USER > SERVICE_WORKER > SYSTEM_AUTOMATION
    - Each domain resolves to: knowledge sources, memory scopes, system instructions, tools, credentials, approval capabilities
    - Enforce filtering: FOUNDER_PRIVATE content NEVER visible in customer Brain sessions
    - _Requirements: R57.1, R57.2, R57.3, R57.4, R57.5_

  - [x] 15.2 Implement workspace relationship context model
    - Create `WorkspaceRelationshipContext` dataclass per design
    - Brain/Hermes understands: user, workspace, projects, Talent, connections, preferences, knowledge
    - Filter retrieved knowledge through requesting user's trust domain
    - Log trust domain boundary crossings with full audit trail
    - _Requirements: R57.6, R57.7, R57.8_

  - [x] 15.3 Write property tests for trust domain filtering
    - **Property 6: Trust Domain Content Filtering**
    - CUSTOMER_USER session → zero FOUNDER_PRIVATE or PLATFORM_ADMIN items
    - **Validates: Requirements R57.3, R57.4, R57.5**

- [x] 16. Brain Memory 4-Layer Architecture
  - [x] 16.1 Create memory layer tables
    - Create `brain_user_memory` table: id, org_id, user_id, memory_type, content JSONB, provenance, confidence, is_active, source_conversation_id
    - Create `brain_workspace_knowledge` table: id, org_id, knowledge_type, content JSONB, promoted_by, promoted_from, provenance
    - Create `brain_conversations` and `brain_messages` tables per design
    - Indexes: (org_id, user_id), (org_id), (conversation_id, created_at)
    - _Requirements: R93.1, R94.1, R29.1_

  - [x] 16.2 Implement memory service with provenance tracking
    - Create `backend/app/services/brain_memory_service.py`
    - Provenance hierarchy: USER_CONFIRMED > OBSERVED > IMPORTED > INFERRED > SUGGESTED
    - Never silently promote LLM output to canonical truth
    - INFERRED/SUGGESTED items clearly indicate source and confidence when surfaced
    - _Requirements: R29.6, R29.7, R29.8, R29.11_

  - [x] 16.3 Implement private-to-workspace promotion workflow
    - POST /api/v1/brain/memory/{id}/promote — explicit user action required
    - Private memory never auto-promotes to workspace knowledge
    - Record promotion: promoted_by, promoted_from, timestamp
    - Users can inspect, correct, delete, disable any durable personalization
    - _Requirements: R29.12, R29.13, R93.5, R94.2, R94.3_

  - [x] 16.4 Implement Brain conversation management
    - Per-user sessions: org_id, user_id, conversation_id, trust_domain
    - Multiple resumable conversations per user
    - Max 200 messages per conversation, inject 20 most recent as context
    - GET /api/v1/brain/conversations, POST, DELETE (archive)
    - _Requirements: R25.7, R25.15, R25.16, R93.1, R93.2_

  - [x] 16.5 Write property tests for memory isolation
    - **Property 13: Brain Memory User Isolation**
    - User U session → zero items from user V's private memory
    - **Property 24: Private Memory Promotion Boundary**
    - Private item in workspace knowledge only with recorded promotion action
    - **Validates: Requirements R93.4, R94.1, R25.18, R29.12, R93.5**

- [x] 17. Cross-Tenant Learning Isolation
  - [x] 17.1 Implement cross-tenant learning boundary
    - Enforce: zero cross-tenant creative content in Brain/Hermes context retrieval
    - Forbidden: prompts, campaigns, stories, Talent data, Creative DNA, assets, conversations, workflows, generated media
    - Permitted for Layer 4: aggregated/de-identified signals only (UX patterns, routing optimization, success rates)
    - Platform learning disabled until pipeline approved (PLATFORM_LEARNING_DISABLED)
    - _Requirements: R95.1, R95.2, R95.3, R95.4, A2-034_

  - [x] 17.2 Write property tests for cross-tenant isolation
    - **Property 15: Cross-Tenant Learning Boundary**
    - Org O context retrieval → zero items from org P's proprietary creative content
    - Cross-tenant retrieval = P0 security incident
    - **Validates: Requirements R95.1, R95.2**

- [x] 18. LLM Provider Routing and Fallback Preferences
  - [x] 18.1 Implement LLM provider routing with fallback
    - Create `backend/app/providers/llm.py` with LanguageModelProvider Protocol
    - Implement: OllamaProvider, OpenAIProvider, AnthropicProvider, OpenRouterProvider
    - Route based on: provider health (5s timeout), task complexity, privacy sensitivity, cost budget, latency requirement, model capabilities
    - Dynamic priority chain: attempt providers in order, select first healthy
    - _Requirements: R26.1, R26.2, R26.5_

  - [x] 18.2 Implement workspace fallback preferences
    - Per-workspace: AUTO (route to next), ASK (confirm before switching), STRICT (fail/queue)
    - Privacy policies override fallback: if AUTO would violate privacy → treat as STRICT
    - GET/PUT /api/v1/workspace/fallback
    - Log every routing decision: provider, model, routing_reason, estimated_cost, fallback_chain
    - _Requirements: R26.3, R26.4, R26.9, R102.1, R102.2, R102.3_

  - [x] 18.3 Write property tests for privacy restriction enforcement
    - **Property 17: Privacy Restriction Enforcement**
    - Workspace with denied_providers list → selected provider never in denied list
    - **Validates: Requirements R103.2, R26.9**

- [x] 19. Application Context and Per-User Sessions
  - [x] 19.1 Implement Application Context envelope
    - Create `backend/app/schemas/application_context.py`
    - Contains: workspace, current page/route, active project, selected Talent, selected assets, active job, active Brain mode, capabilities, workflow state, UI state
    - Authorization fields (org_id, user_id, role) ALWAYS server-derived from JWT
    - Validate all referenced IDs against authenticated org_id
    - _Requirements: R58.1, R58.2, R58.3, R58.4_

  - [x] 19.2 Implement Brain modes and streaming
    - Modes: creative, prompt_engineer, story_assistant, production_advisor, research, image_analyzer, business_strategy
    - SSE streaming: token-by-token, keepalive every 15s, close after 120s inactivity
    - Per-request output token budget: 4096 tokens
    - Failover to next provider if active fails mid-response
    - _Requirements: R25.1, R25.6, R25.9, R25.11, R25.12_

- [x] 20. Checkpoint — Phase 3 verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: governance boundary blocks unauthorized side effects, memory isolation per user, trust domain filtering works

---

## Phase 4: Connections & Operations (P1/P2) — Weeks 10-12

- [x] 21. Connections Hub
  - [x] 21.1 Create connections data model
    - Create `connections` table per design: id, org_id, user_id, ownership (user/workspace), category, provider_name, display_name, lifecycle_state, auth_method, oauth_token_ref, capabilities JSONB, allowed_roles, tool_policy JSONB, last_health_check_at, health_status
    - Indexes: (org_id), (user_id WHERE NOT NULL), (org_id, category)
    - RLS: tenant isolation + user_id filter for USER_CONNECTIONs
    - _Requirements: R85.1, R85.3, R85.4, R92.1, R92.2, R92.3_

  - [x] 21.2 Implement connection lifecycle and OAuth flow
    - Create `backend/connections/connection_service.py`
    - OAuth flow: POST /api/v1/connections/initiate → redirect_url → callback → token exchange → store encrypted → discover capabilities
    - Lifecycle states: CONNECTING, CONNECTED, DEGRADED, REAUTH_REQUIRED, DISCONNECTED, REVOKED
    - API key connections: accept once, validate, discover, store, never redisplay
    - _Requirements: R85.2, R85.4, R85.5, R85.6, R27.4, R27.6, R92.6_

  - [x] 21.3 Implement connection permissions and member departure
    - WORKSPACE_CONNECTION: admin/owner to create, remains when members leave
    - USER_CONNECTION: any authenticated member creates, revoked on workspace departure
    - Access governed by allowed_roles + tool_policy
    - Member departure: personal connections revoked, workspace connections stay, scheduled ops pause
    - _Requirements: R85.6, R85.7, R92.4, R92.5, R92.7, R96.2_

  - [x] 21.4 Write property tests for connection authorization
    - **Property 18: Connection Authorization Invariant**
    - Connection existence alone never grants capabilities without explicit permission configuration
    - **Validates: Requirements R27.4, R85.7, A2-013**

- [x] 22. Platform Operator Capability Model
  - [x] 22.1 Create Platform Operator tables and service
    - Create `platform_operators` table: id, user_id, capability_grants TEXT[], granted_by, granted_at, revoked_at
    - Create `platform_operator_actions` table: id, operator_user_id, capability_used, target_org_id, action_type, action_detail JSONB
    - Capability groups: Platform Observe, Tenant Support, Tenant Access Escalation, Platform Configuration, Financial Controls, Safety & Rights, Security Administration, Deployment/Operations, Release Management, Destructive Platform Actions, Founder Authority
    - _Requirements: R33.5, R33.6, R33.7, R97.1, R97.2, R97.3, R97.4_

  - [x] 22.2 Implement support sessions with time-limited access
    - Create `support_sessions` table per design: operator_user_id, target_org_id, reason, requested/approved_capabilities, permitted_surfaces, permitted_actions, approved_by, started_at, expires_at, ended_at, status
    - Auto-expires at expires_at, revocable immediately
    - Scope-limited: queries/actions limited to permitted_surfaces and permitted_actions
    - Full audit trail: all actions during session logged
    - _Requirements: R33.8, R33.9, R97.5, R97.6, A2-006_

  - [x] 22.3 Implement Platform Operator API routes
    - Route: /platform-admin/* — returns 404 for users without capability grants
    - GET /platform-admin/operators, POST (grant), DELETE (revoke)
    - GET/POST /platform-admin/support-sessions, /approve, /revoke
    - All actions logged with: actor, capability, target tenant, action, timestamp
    - _Requirements: R33.9, R33.10_

  - [x] 22.4 Write property tests for support session scope
    - **Property 20: Support Session Scope**
    - Active session queries/actions never exceed approved_capabilities, permitted_surfaces, permitted_actions
    - Expired/revoked session grants zero access
    - **Validates: Requirements R33.8, R97.5, A2-006**

- [x] 23. Agent Autonomy Profiles and Activity Feed
  - [x] 23.1 Implement autonomy profiles
    - Configurable per workspace: ADVISORY (recommend only), ASSISTED (low-risk auto-execute), AUTONOMOUS_WITHIN_LIMITS (delegated within limits)
    - Default: ADVISORY for new workspaces
    - Mandatory safety/security/consent/budget/destructive controls enforced regardless of profile
    - _Requirements: R98.1, R98.2, R30.12, R30.13_

  - [x] 23.2 Implement delegated permissions
    - Create `delegated_permissions` table: id, org_id, delegated_by, action_class, connection_scope, max_cost_usd, expires_at, revoked_at
    - Capability-specific, connection-specific, revocable, auditable, role-scoped, subject to Governance Boundary
    - _Requirements: R30.14, R98.3_

  - [x] 23.3 Implement agent activity feed
    - Create `agent_activity` table: id, org_id, user_id, session_id, activity_type, summary, detail JSONB, outcome, cost_usd
    - Types: recommendation, tool_call, job_dispatch, approval_request, connection_use, change_made, failure, cost_incurred
    - GET /api/v1/brain/activity — scoped to requesting user's sessions and workspace
    - _Requirements: R99.1, R99.2, R99.3, R99.4, R30.15_

- [x] 24. Feature Rollout Engine and Workspace Privacy
  - [x] 24.1 Implement feature rollout engine
    - Create `feature_rollouts` table: id, capability_name, rollout_scope, scope_target, enabled, expires_at, created_by
    - Rollout scopes: global, plan, workspace, cohort, user, workload, provider
    - DISABLED capabilities inaccessible through ALL surfaces: UI, API, Brain/Hermes, MCP, direct paths
    - No code deployment required for state changes
    - _Requirements: R106.1, R106.2, R106.3, R19.9, R19.10_

  - [x] 24.2 Implement workspace privacy restrictions
    - Create `workspace_privacy_config` table: id, org_id, restriction_type, restriction_target, allowed_providers TEXT[], denied_providers TEXT[]
    - Types: local_models_only, customer_compute_only, approved_llm_only, no_external_llm_for_project, approved_storage_only, talent_provider_restriction, project_privacy
    - Brain/Hermes, LLM routing, job dispatch all check restrictions
    - GET/PUT /api/v1/workspace/privacy
    - _Requirements: R103.1, R103.2, R103.3_

  - [x] 24.3 Write property tests for disabled feature universality
    - **Property 22: Disabled Feature Universality**
    - DISABLED capability not invocable through any surface
    - **Validates: Requirements R19.9, R86.2, R106.3**

- [x] 25. Workspace Content Ownership
  - [x] 25.1 Implement content ownership and member departure protocol
    - Content created in workspace belongs to organization (Talent, projects, assets, LoRAs, DNA, recipes, workflows, knowledge)
    - Member departure: workspace material stays, personal connections revoked, workspace connections remain
    - Account deletion requires ownership transfer first
    - Unfinished jobs by departing user: reassign or pause
    - _Requirements: R96.1, R96.2, R96.3, R96.4_

- [x] 26. Checkpoint — Phase 4 verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: connections create/revoke correctly, platform operator actions are audited, autonomy profiles enforce boundaries

---

## Phase 5: Production Features (P1/P3) — Weeks 13-15

- [x] 27. Consent Subsystem and Rights/Takedown (DEPENDENCY: before generation/publishing)
  - [x] 27.1 Implement first-class consent subsystem
    - Create `consent_records` table per design: id, org_id, talent_id, scopes TEXT[], evidence_type, evidence_url, grantor_identity, granted_at, expires_at, revoked_at, revocation_reason, restrictions JSONB, provenance, version, verification_state
    - Scopes: LIKENESS, VOICE, TRAINING, GENERATION, ADULT_CONTENT, COMMERCIAL, PUBLISHING, CLIENT_WORK
    - Scope-specific evaluation: only relevant scopes checked per operation type
    - Missing/expired/revoked consent → 403 CONSENT_REQUIRED or CONSENT_REVOKED
    - _Requirements: R10.2, R10.3, R10.11, R10.12, A2-004_

  - [x] 27.2 Implement consent API endpoints
    - GET /api/v1/consent — workspace's talent consent records
    - POST /api/v1/consent — create consent record
    - PUT /api/v1/consent/{id} — update
    - POST /api/v1/consent/{id}/revoke — revocation (prevents future use, preserves audit)
    - Fictional talent exemption: FICTIONAL identity_classification doesn't require consent for generation
    - _Requirements: R10.2, R10.3, A2-004_

  - [x] 27.3 Implement rights and takedown case management
    - Create `rights_cases` table per design: id, case_type, status, priority, reporter_contact, target_org_id, target_talent_ids, target_asset_ids, reported_urls, evidence_refs, assigned_operator, actions_taken JSONB, resolution, legal_hold_active
    - Case lifecycle: RECEIVED → TRIAGED → ACTION_REQUIRED/NO_ACTION → RESTRICTED/REMOVED/RESOLVED → CLOSED (with APPEALED branch)
    - CSAM auto-escalates to critical + immediate restriction
    - POST /api/v1/takedowns, GET/PATCH /platform-admin/rights-cases
    - _Requirements: R40.1, R40.2, R40.3, R40.4, R40.5, R40.6, R40.7, R40.8, R40.9, A2-005_

  - [x] 27.4 Write property tests for consent enforcement
    - **Property 19: Consent Enforcement**
    - Operation requiring consent with absent/expired/revoked scope → blocked
    - **Validates: Requirements R10.2, R10.12, R39.6, A2-004**

- [x] 28. Talent Graph and Identity Classification
  - [x] 28.1 Implement talent CRUD with identity classification
    - POST /api/v1/talent: name (1-100), type enum, identity_classification (FICTIONAL, REAL_PERSON_SELF, REAL_PERSON_AUTHORIZED)
    - Soft-delete on DELETE, 404 for cross-tenant access
    - Typed relationships: POST /api/v1/talent/{id}/relationships
    - talent_loras junction: talent_id, lora_model_id, type, strength (0-1), always_on, max 5 per talent
    - _Requirements: R10.1, R10.4, R10.5, R10.6, R10.7, R10.8_

  - [x] 28.2 Implement adult content safety gate
    - Three-layer policy: Safety Kernel (mandatory) → Platform Policy → Workspace Policy (stricter only)
    - FICTIONAL: workspace allows + adult_status=VERIFIED_18_PLUS
    - REAL_PERSON_SELF: above + consent scope 'adult_content' from real person
    - REAL_PERSON_AUTHORIZED: above + consent with explicit adult-content authorization + grantor identity + evidence
    - Age ambiguity fails closed: cannot confirm adulthood → blocked
    - _Requirements: R39.1, R39.2, R39.3, R39.4, R39.5, R39.6, R39.7, R10.11, A2-024, A2-025_

- [x] 29. Generation Pipeline with Context Packages and Model Promotion
  - [x] 29.1 Implement Generation Context Package
    - Create `generation_context_packages` table: id, org_id, version, talent_record, creative_dna_version, source_assets, model_lora_selections, prompt_instructions, consent_verification_result, safety_evaluation_result, workflow_template, project_constraints
    - Immutable after creation (assigned version ID, stored in Supabase, never modified)
    - All generation surfaces (Brain, API, MCP, scheduled, batch) use same canonical boundary
    - Stale references → job rejected
    - _Requirements: R60.1, R60.2, R60.3, R60.4, R60.5, R60.6_

  - [x] 29.2 Implement image generation pipeline
    - POST /api/v1/generate/image: prompt (max 2000), model, dimensions (256-2048px), optional talent_id
    - Create job (queued), return 202 within 2 seconds
    - Dispatch to ComputeProvider meeting requirements (VRAM, model, cost limit)
    - Workflow error → fail immediately; transient error → retry 3x with backoff (10s, 20s, 40s)
    - Timeout 30 min → fail, terminate instance
    - _Requirements: R12.1, R12.2, R12.3, R12.6, R12.7, R12.8, R12.9, R12.10_

  - [x] 29.3 Implement model/LoRA promotion gates
    - Lifecycle: IMPORTED/TRAINED → INTEGRITY_VERIFIED → EVALUATED → APPROVED → ACTIVE → DEPRECATED → QUARANTINED
    - Two risk classes: STANDARD (auto-promote through integrity/compatibility), HIGH_RISK (human approval required)
    - Quarantine: immediately unavailable for all operations regardless of prior state
    - Log all transitions: model_id, from_state, to_state, actor, evidence, timestamp
    - _Requirements: R67.1, R67.2, R67.3, R67.4, R67.5, R67.6, R67.7, R67.8, R34.8_

  - [x] 29.4 Write property tests for context packages and model lifecycle
    - **Property 8: Immutable Context Package Integrity**
    - Once created, no field modified; stale references → job rejected
    - **Property 10: Model Lifecycle Monotonicity**
    - State only advances through defined sequence or jumps to quarantined
    - **Validates: Requirements R60.2, R60.5, R67.1, R67.2**

- [x] 30. Provider Reputation and Workload Scheduling
  - [x] 30.1 Implement provider reputation system
    - Persist per-provider metrics to Supabase: startup_latency, queue_latency, generation_duration, failure_rate (24h rolling), cost_variance, availability (7d rolling), model_cache_readiness, quality_acceptance_rate
    - Negative signals: cleanup_failures, cost_overruns, timeout_rate, connection_failures
    - Auto-quarantine: failure rate > 30% over 24h → excluded until recovered/reviewed
    - Dynamic ranking: learned ranking, not hardcoded list
    - _Requirements: R65.1, R65.2, R65.3, R65.4, R65.5, R65.6_

  - [x] 30.2 Implement workload scheduler with capacity isolation
    - Create `backend/app/services/workload_scheduler.py`
    - Workload classes: interactive_language, image_generation, video_generation, training, voice_audio, batch, production_stages, publishing
    - Heavy workloads cannot exhaust interactive capacity
    - Customer multi-GPU: select best worker considering VRAM, cache readiness, utilization, health, queue depth, priority, concurrency limits
    - Queue fairness: workspace concurrency limit, weighted fairness by plan, anti-starvation
    - _Requirements: R65.8, R65.9, R65.10, R87.1, R87.2, R87.5, R88.1, R88.2, R88.3, R88.4, A2-039_

- [x] 31. Capability Registry Extension
  - [x] 31.1 Extend capability registry with DISABLED state and rollout
    - Classifications: PRODUCTION, PARTIAL, SIMULATED, MISSING, DEPRECATED, DISABLED, UNVERIFIED
    - GET /api/v1/capabilities: all capabilities with classification, required provider, health
    - DISABLED capabilities: inaccessible through ALL surfaces
    - MISSING → 501 CAPABILITY_NOT_IMPLEMENTED
    - Transitions logged: timestamp, actor, reason
    - _Requirements: R19.1, R19.2, R19.3, R19.6, R19.7, R19.8, R19.9_

- [x] 32. Frontend Core Patterns
  - [x] 32.1 Implement SWR data fetching and error boundaries
    - SWR with stale-while-revalidate (30s stale), background revalidation on focus, retry with backoff (max 3)
    - Page-level Error Boundary: heading, truncated message (200 chars), Try Again, Go Home
    - Skeleton placeholders during first load
    - Offline banner + disabled mutations when disconnected
    - _Requirements: R17.1, R17.2, R17.3, R17.4, R17.5, R23.1, R23.2, R23.3, R23.6_

  - [x] 32.2 Implement capability-driven UI and connections hub frontend
    - Use Capability_Registry to show/hide/badge features
    - DISABLED: not rendered; SIMULATED: show badge; plan-gated: hidden if inaccessible
    - Connections Hub page: unified surface for all connection types
    - OAuth flows: user clicks Connect, backend handles OAuth dance, user only sees consent screen
    - Progressive disclosure: basic flows visible by default, Advanced sections expandable
    - _Requirements: R77.1, R77.2, R77.3, R77.4, R77.5, R77.7, R85.1, R85.2_

- [x] 33. Checkpoint — Phase 5 verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: consent blocks unauthorized generation, context packages are immutable, model promotion gates enforce lifecycle

---

## Phase 6: Intelligence & Scale (P2-P4) — Weeks 16-18

- [x] 34. Social Intelligence Data Model (DEPENDENCY: connections hub complete)
  - [x] 34.1 Create social analytics tables
    - Create tables per design: `social_accounts`, `social_content`, `social_metric_snapshots`, `social_watchlists`, `social_watchlist_members`, `social_derived_insights`, `social_experiments`
    - All tenant-scoped with org_id + indexes
    - RLS: workspace-scoped access
    - _Requirements: R107.1, R107.2, R43.7, A2-007_

  - [x] 34.2 Implement SocialIntelligenceProvider interface and sync lifecycle
    - Create `backend/publishing/social_intelligence.py` with Protocol
    - Methods: get_capabilities, get_connected_account, get_owned_content, get_owned_metrics, get_public_profile, sync_metrics
    - Sync state per account: last_sync, cursor, rate_limit_state, connection_state, data_freshness, partial_sync
    - Analytics failure does NOT disable publishing; publishing failure does NOT destroy analytics
    - _Requirements: R107.11, A2-008, A2-012_

  - [x] 34.3 Implement social analytics API endpoints
    - GET /api/v1/social/accounts, /content, /metrics, /watchlists, /intelligence, /experiments
    - POST /api/v1/social/watchlists, /experiments, /sync (trigger manual sync)
    - Data provenance: FIRST_PARTY_CONNECTED, PUBLIC_PLATFORM_DATA, THIRD_PARTY_DATA, USER_IMPORTED, DERIVED_ANALYSIS
    - Missing metrics represented as UNAVAILABLE — never fabricate values
    - _Requirements: R107.2, R107.3, R107.4, R107.10, R43.11, R43.12_

  - [x] 34.4 Write property tests for social provenance integrity
    - **Property 21: Social Provenance Integrity**
    - DERIVED_ANALYSIS and PUBLIC_PLATFORM_DATA never presented as FIRST_PARTY_CONNECTED
    - **Validates: Requirements R43.13, R107.10, A2-009**

- [x] 35. Market Intelligence Architecture
  - [x] 35.1 Implement competitive intelligence and watchlists
    - Watchlist types: creator, brand, competitor, topic, hashtag
    - Support publicly available metrics: followers, growth rate, posting frequency, engagement, formats
    - Brain/Hermes answers competitive questions identifying source of each insight
    - Never represent estimates as private analytics
    - Respect platform ToS, API permissions, rate limits
    - _Requirements: R108.1, R108.2, R108.3, R108.4, R108.5, R108.6, R108.7, R108.8, R108.10_

- [x] 36. Publishing Pipeline with Approval Integrity
  - [x] 36.1 Implement publishing approval binding
    - Approval binds to exact package: asset version (checksum), caption, destination, schedule, targeting, consent state, disclosure settings, policy state
    - Any bound element changes after approval → invalidation, require re-evaluation
    - Store approved package snapshot as immutable record
    - Verify current state matches approved package at publish time
    - _Requirements: R79.1, R79.2, R79.3, R79.4, R79.5, R79.6_

  - [x] 36.2 Implement disclosure hooks and publishing flow
    - Configurable policy hooks: AI/synthetic disclosure, sponsorship/commercial, provenance metadata (C2PA attachment points), platform-specific policy
    - Per-workspace disclosure configuration: which disclosures enabled, text/tags, platform requirements
    - Disclosure preview before publishing
    - Evaluate applicable hooks at dispatch time, include in published content
    - _Requirements: R80.1, R80.2, R80.3, R80.4, R80.5, R80.6_

  - [x] 36.3 Implement core publishing service
    - Schedule posts: platform, asset_id, scheduled_at (min 5 min future)
    - Dispatch within ±60 seconds of schedule, status update within 120 seconds
    - OAuth token refresh on expired; if refresh fails → connection "disconnected" + post "failed"
    - Platform-specific resize: 9:16 TikTok, 4:5 IG, 16:9 YouTube
    - _Requirements: R38.1, R38.2, R38.3, R38.4, R38.5, R38.6, R38.7, R38.8_

- [x] 37. Training Pipeline with Dataset Manifests
  - [x] 37.1 Implement dataset manifest system
    - Create immutable Dataset_Manifest: file references, checksums (SHA-256), asset role per file, provenance, consent references, Talent relationship
    - Assign unique version ID, store in Supabase, never modify
    - Worker verifies downloaded files match manifest checksums before starting
    - Deleted/consent-revoked files → reject training job with specific error
    - _Requirements: R61.1, R61.2, R61.3, R61.4, R61.5, R61.6_

  - [x] 37.2 Implement training pipeline with cost estimation
    - POST /api/v1/training/jobs: talent_id + 10-200 training images → 202
    - Cost estimation: GET /api/v1/training/estimate
    - On completion: create model record with provenance, link to talent, create talent_loras association
    - 4-hour timeout, terminate instance in finally block
    - Cancellation support for queued/running jobs
    - _Requirements: R35.1, R35.2, R35.3, R35.4, R35.5, R35.6, R35.7, R35.8, R35.10, R35.11_

- [x] 38. Data Portability and External Deletion
  - [x] 38.1 Implement workspace data export
    - POST /api/v1/workspace/export → 202 (async export job)
    - GET /api/v1/workspace/export/{id} → status, download_url
    - Export includes: Talent metadata, Creative DNA, recipes, projects, prompts, provenance, workflows, model metadata, asset references, consent records, workspace knowledge
    - Export SHALL NOT expose: provider secrets, other users' private Brain memory, internal platform config
    - _Requirements: R104.1, R104.2, R104.3_

  - [x] 38.2 Implement external deletion propagation
    - Track deletion states: REMOVED_FROM_STUDIO, EXTERNAL_DELETION_REQUESTED, EXTERNAL_DELETION_CONFIRMED, EXTERNAL_DELETION_FAILED, RETAINED_LEGAL_HOLD, RETAINED_BACKUP
    - Never claim deleted unless confirmed where technically possible
    - Failed external deletion → retry with backoff → surface to Platform Operators
    - _Requirements: R105.1, R105.2, R105.3_

- [x] 39. Capacity Management and Telemetry
  - [x] 39.1 Implement capacity telemetry and graceful degradation
    - Track: active users, API request rate, Brain streams, realtime connections, queue depth per workload class, active jobs per provider, GPU utilization, platform compute liability
    - Queue on overload (not reject) unless budget exceeded
    - Graceful degradation: read-only navigation stays usable when generation capacity exhausted
    - Provide queue position + estimated wait time where reliable
    - _Requirements: R90.1, R90.2, R90.3, R90.4_

- [x] 40. Checkpoint — Phase 6 verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: social sync works with provenance, publishing approvals bind correctly, training manifests are immutable, export produces valid output

---

## Phase 7: Release (P0-B) — Weeks 19-20

- [x] 41. Release Identity and Production Gate
  - [x] 41.1 Implement Release Identity system
    - Create `release_identities` table: id, git_commit_sha, frontend_artifact, backend_artifact, migration_set, config_version, model_manifest, deployment_ids
    - Surface in: /ready response, structured logs, job records, error reports, asset metadata
    - Immutable record created during deployment, never modified
    - Reject deployments that cannot produce complete Release_Identity
    - _Requirements: R72.1, R72.2, R72.3, R72.4, R72.5, R72.6_

  - [x] 41.2 Implement production gate checks
    - Gate checks: clean frontend build (zero errors), clean backend build, CI green, frontend deploys to Vercel, backend deploys, schema matches migrations, tenant isolation adversarial tests pass, PRODUCTION capabilities healthy, security evidence present, rollback documented, DB restore rehearsed, monitoring active, deployment repeatable, no suppressed errors
    - Record gate passage: Release_Identity, evidence links, timestamp, approving actor
    - Emergency release path: reduced gate + full verification within 24 hours
    - _Requirements: R83.1, R83.2, R83.6, R83.7, R83.8, R83.9_

- [x] 42. Deployment Repeatability Verification
  - [x] 42.1 Verify deployment repeatability from canonical branch
    - Multiple successful deployments from main branch on demand
    - Zero TypeScript/ESLint/Next.js errors without manual intervention
    - Zero suppressed or disabled build checks
    - Track deployment success rate over time
    - Classify as "repeatable and stable" only when proven
    - _Requirements: R109.1, R109.2, R109.3, R109.4, R109.5, R82.7, R82.8_

- [x] 43. Independent Verification
  - [x] 43.1 Execute independent verification against running system
    - Automated test suites AND at minimum one of: human review, Hermes inspection, adversarial testing
    - Verify per requirement: coverage, correctness, schema integrity, deployment success, log integrity, security posture, tenant isolation, runtime capability, completion evidence
    - Verification evidence record per feature: requirement ID, method, evidence location, date, verifier identity
    - Developer assertion alone insufficient for PRODUCTION classification
    - _Requirements: R82.1, R82.2, R82.3, R82.4, R82.5, R82.6_

- [x] 44. Performance Optimization and Scalability
  - [x] 44.1 Verify performance targets
    - Page navigation (cached): < 100ms
    - Fresh data load: < 500ms for lists < 100 items
    - Brain first token: < 2 seconds
    - Job submission: < 2 seconds (202 response)
    - Realtime event delivery: < 1 second
    - Evidence-based optimization: EXPLAIN ANALYZE for slow queries
    - _Requirements: R76.1, R76.2, R76.3, R76.4, R76.5, R76.6_

  - [x] 44.2 Scalability architecture verification
    - User growth independent of GPU scaling
    - Job transport replaceable without API contract change
    - Backend stateless behind load balancer
    - Document horizontal vs vertical scaling per component
    - _Requirements: R91.1, R91.3, R91.4, R76.8, R76.10_

- [x] 45. Final Production Gate
  - Ensure all tests pass, ask the user if questions arise.
  - All gate checks from 41.2 pass
  - Release_Identity created and recorded
  - Independent verification complete with evidence
  - Feature classified as PRODUCTION in Capability_Registry with evidence
  - _Requirements: R55.1, R55.6, R83.6_

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at phase boundaries
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Critical dependency ordering preserved: consent before generation, connections before providers, provenance before analytics
- The design specifies Python (FastAPI/SQLAlchemy/Pydantic v2) for backend and TypeScript (Next.js/React) for frontend — all tasks use these languages
- Hypothesis library for property-based tests (minimum 100 iterations per property)
- All Phase 1 work is P0 (required for security baseline) and blocks all subsequent phases
- Phases 2-4 can have internal parallelism per the dependency graph below
- Phase 5 requires Phase 4 (Connections Hub) to be complete
- Phase 6 requires Phase 5 (consent, generation pipeline) to be complete
- Phase 7 requires all prior phases

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "3.1"] },
    { "id": 4, "tasks": ["2.5", "3.2", "3.3", "4.1"] },
    { "id": 5, "tasks": ["3.4", "3.5", "4.2", "4.3", "5.1", "5.2"] },
    { "id": 6, "tasks": ["5.3", "7.1"] },
    { "id": 7, "tasks": ["7.2", "8.1", "9.1", "11.1"] },
    { "id": 8, "tasks": ["7.3", "7.4", "8.2", "9.2", "10.1", "11.2", "12.1"] },
    { "id": 9, "tasks": ["7.5", "8.3", "8.4", "9.3", "10.2", "10.3", "12.2", "12.3"] },
    { "id": 10, "tasks": ["10.4", "14.1", "15.1"] },
    { "id": 11, "tasks": ["14.2", "14.3", "15.2", "16.1"] },
    { "id": 12, "tasks": ["14.4", "15.3", "16.2", "16.3", "16.4", "17.1"] },
    { "id": 13, "tasks": ["16.5", "17.2", "18.1", "19.1"] },
    { "id": 14, "tasks": ["18.2", "18.3", "19.2", "21.1"] },
    { "id": 15, "tasks": ["21.2", "21.3", "22.1", "23.1"] },
    { "id": 16, "tasks": ["21.4", "22.2", "22.3", "23.2", "23.3", "24.1"] },
    { "id": 17, "tasks": ["22.4", "24.2", "24.3", "25.1"] },
    { "id": 18, "tasks": ["27.1", "27.2", "28.1"] },
    { "id": 19, "tasks": ["27.3", "27.4", "28.2", "29.1"] },
    { "id": 20, "tasks": ["29.2", "29.3", "30.1"] },
    { "id": 21, "tasks": ["29.4", "30.2", "31.1", "32.1"] },
    { "id": 22, "tasks": ["32.2", "34.1"] },
    { "id": 23, "tasks": ["34.2", "34.3", "35.1", "36.1"] },
    { "id": 24, "tasks": ["34.4", "36.2", "36.3", "37.1"] },
    { "id": 25, "tasks": ["37.2", "38.1", "38.2", "39.1"] },
    { "id": 26, "tasks": ["41.1", "41.2"] },
    { "id": 27, "tasks": ["42.1", "43.1"] },
    { "id": 28, "tasks": ["44.1", "44.2"] }
  ]
}
```
