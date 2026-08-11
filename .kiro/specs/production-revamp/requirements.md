# Requirements Document

## AI Studio Production Requirements — Revision 4 FINAL

## Introduction

This document defines the requirements for converting AI Studio from a working prototype into a production-ready multi-tenant SaaS platform. It supersedes Revision 3 based on Founder decisions addressing compute ownership models, connection management, user/workspace data boundaries, platform administration, authentication, analytics intelligence, and operational scalability.

This is the CANONICAL FINAL version of the production requirements. All Rev 3 and Rev 4 amendments have been integrated into a single coherent document. R84-R109 are canonical requirements, not detached amendments.

**Key architectural changes from Revision 3:**
- Customer-managed compute as PREFERRED model; platform-managed as Founder-controlled (DISABLED/SELECTIVE/ENABLED)
- Unified Connections Hub with OAuth-preferred flows and connection ownership (USER vs WORKSPACE)
- Platform Operator capability model replacing undifferentiated Super Admin
- Unified Signup/Login experience with workspace provisioning
- Brain user-specific sessions and memory layers with explicit promotion boundaries
- Agent autonomy profiles (ADVISORY/ASSISTED/AUTONOMOUS_WITHIN_LIMITS)
- Social Performance Analytics and Market/Competitor Intelligence
- Customer multi-GPU load balancing and workload isolation
- Cross-tenant learning isolation as security boundary
- Workspace content ownership and data portability
- Capacity management, graceful load shedding, and scalability verification
- Feature rollout controls (by plan, workspace, cohort, user, workload, provider)

**Key architectural changes from Revision 2 (preserved):**
- Canonical AI Runtime Hierarchy (Brain → AIOS → Hermes → Execution Adapters)
- Explicit Trust-Domain Separation (founder, platform, workspace, customer, service, system)
- Mandatory single governance boundary for ALL AI-initiated side effects
- Immutable Generation Context Packages and Training Dataset Manifests
- Realtime/Event Delivery Architecture (provider-neutral)
- Job Leasing & Durable Execution (implementation-agnostic)
- Cost Reservation & Reconciliation (atomic budget enforcement)
- Model/LoRA Promotion Gates (lifecycle beyond import)
- Release Security & Supply-Chain Security requirements
- Full Correlation/Observability spanning browser to asset
- Production Stage Graph for multi-step workflows
- Independent Verification and Final Production Gate

**Product Principle:** Simple for beginners, progressively configurable for experts. Normal users should not need to understand GPUs, model files, storage providers, MCP, APIs, or inference infrastructure. Advanced users must be able to configure when desired.

## Revision Traceability

| Previous Req | Status | Notes |
|---|---|---|
| R1: Authentication Enforcement | **AMENDED Rev 4** | Added provisioning flow, OAuth, idempotent workspace creation |
| R2: Tenant Isolation | **AMENDED Rev 3** | Added multi-surface verification scope, evidence independence |
| R3: Role-Based Access Control | **PRESERVED** | Superseded conceptually by R68/R97 canonical identity model but criteria retained |
| R4: Input Validation | **PRESERVED** | No changes needed |
| R5: Database Schema Reconciliation | **AMENDED Rev 3** | Added generated-type reconciliation, manual-object identification |
| R6: RLS Comprehensive Audit | **PRESERVED** | No changes needed |
| R7: Production Deployment Pipeline | **PRESERVED** | No changes needed |
| R8: Secure Credential Broker | **AMENDED Rev 3** | Added encryption authority separation |
| R9: Configuration Safety | **PRESERVED** | No changes needed |
| R10: Talent Graph | **PRESERVED** | No changes needed |
| R11: Storage Provider Abstraction | **PRESERVED** | No changes needed |
| R12: Image Generation Pipeline | **PRESERVED** | No changes needed |
| R13: Compute Provider Abstraction | **AMENDED Rev 4** | Added availability states, customer multi-GPU, load balancing |
| R14: Cost Tracking | **AMENDED Rev 4** | Added platform compute cost protections, cost classification |
| R15: Project Management | **PRESERVED** | No changes needed |
| R16: API Error Handling | **PRESERVED** | No changes needed |
| R17: Frontend State Management | **PRESERVED** | No changes needed |
| R18: Frontend Auth Flow | **PRESERVED** | No changes needed |
| R19: Capability Registry | **AMENDED Rev 4** | Added disabled state handling, feature rollout controls |
| R20: Onboarding | **PRESERVED** | No changes needed |
| R21: Background Job Processing | **AMENDED Rev 3** | Replaced with Job Leasing behavioral contract (implementation-agnostic) |
| R22: Pagination | **PRESERVED** | No changes needed |
| R23: Frontend Error Boundary | **PRESERVED** | No changes needed |
| R24: Simulation Transparency | **PRESERVED** | No changes needed |
| R25: Brain + Hermes/AIOS | **AMENDED Rev 4** | Added user-specific sessions, per-user learning, memory isolation |
| R26: LLM Routing | **AMENDED Rev 4** | Added fallback preferences, privacy/data-location policies |
| R27: MCP Integration Fabric | **AMENDED Rev 4** | Added Connections Hub concept, OAuth-preferred flows |
| R28: MCP/Agent Governance | **PRESERVED** | Strengthened by R59 single governance boundary |
| R29: Knowledge/Memory | **AMENDED Rev 4** | Added Brain memory layers, private-to-workspace promotion |
| R30: AIOS Governance | **AMENDED Rev 4** | Added autonomy profiles, delegated permissions, activity history |
| R31: Creative Recipes | **PRESERVED** | No changes needed |
| R32: Repository Intelligence | **PRESERVED** | No changes needed |
| R33: Super Admin → Platform Operator | **AMENDED Rev 4** | Replaced with capability-based Platform Operator model |
| R34: Model/LoRA Import | **AMENDED Rev 3** | Added promotion gates lifecycle |
| R35: LoRA Training Pipeline | **PRESERVED** | No changes needed |
| R36: Video Generation | **PRESERVED** | No changes needed |
| R37: Voice/Audio Pipeline | **PRESERVED** | No changes needed |
| R38: Publishing Pipeline | **PRESERVED** | No changes needed |
| R39: Adult Content Policy | **PRESERVED** | No changes needed |
| R40: Rights and Takedown | **PRESERVED** | No changes needed |
| R41: Entitlements/Plans | **AMENDED Rev 4** | Added workload privacy restrictions, plan cannot weaken isolation |
| R42: Data Lifecycle | **PRESERVED** | No changes needed |
| R43: Product Analytics | **AMENDED Rev 4** | Expanded to include Social Performance Analytics and Market Intelligence |
| R44: Local Connector | **PRESERVED** | Architecture-only |
| R45: Structured Logging | **PRESERVED** | Extended by R75 correlation |
| R46: CORS/Security Headers | **PRESERVED** | No changes needed |
| R47: Rate Limiting | **PRESERVED** | No changes needed |
| R48: Webhook Security | **PRESERVED** | No changes needed |
| R49: Frontend Accessibility | **PRESERVED** | No changes needed |
| R50: Dead Code Cleanup | **PRESERVED** | No changes needed |
| R51: Testing Infrastructure | **PRESERVED** | No changes needed |
| R52: Layered Architecture | **PRESERVED** | No changes needed |
| R53: Design System | **PRESERVED** | No changes needed |
| R54: Kiro/Code Execution Workflow | **PRESERVED** | No changes needed |
| R55: Production Readiness Gate | **PRESERVED** | Extended by R82/R83/R109 |
| R56-R83 | **ADDED Rev 3** | Architectural requirements from Rev 3 amendment |
| R57: Trust Domains | **AMENDED Rev 4** | Added authorized relationship model |
| R65: Provider Reputation | **AMENDED Rev 4** | Added workload classes and capacity isolation |
| R68: Authority Model | **AMENDED Rev 4** | Aligned to Platform Operator capability model |
| R76: Performance | **AMENDED Rev 4** | Added scalability verification and load testing targets |
| R77: Beginner/Advanced UX | **AMENDED Rev 4** | Added Connections Hub, OAuth-preferred flows |
| R82: Independent Verification | **AMENDED Rev 4** | Updated deployment reality |
| R83: Final Production Gate | **AMENDED Rev 4** | Updated deployment evidence requirements |
| NEW: R84-R109 | **ADDED Rev 4** | Founder decision requirements from Rev 4 amendment |


## Current State Assessment (Evidence-Based)

### What Works (PROD classification per CAPABILITY_MAP.md)
- Talent CRUD (Supabase queries, auth-gated)
- Jobs lifecycle (full CRUD, status tracking)
- Assets management (B2 upload/delete, metadata)
- Projects (tenant-scoped, detail view)
- Models registry (seed data, capabilities)
- Worker orchestration (Vast.ai + RunPod verified)
- Provider reputation (learning engine, blacklist)
- Cost intelligence (budget tracking, per-org)
- Brain chat (Ollama local verified, AIOS gateway routes)
- AIOS Gateway (chat routing, provider selection)
- Governance approvals (inline approve/reject in chat)
- Generation feedback (durable, idempotent)
- RLS policies (12+ migration files)
- Governed confirmation dialogs + semantic design tokens
- Infrastructure RBAC + audit events
- Capability-aware readiness probes

### What Is Simulated or Incomplete
- Image generation: works only when GPU worker is online; simulation fallback
- Video generation (WAN 2.1): provider simulated by default
- LoRA training: full lifecycle exists but SimulationProvider is default
- Voice synthesis (ElevenLabs): provider wired but API key permission issue
- Music generation (Suno): provider skeleton only, no key
- Social publishing: webhook-based simulation only
- Agent learning (DNA): in-memory singleton, not persisted to DB
- Knowledge graph: schema + module exists, limited UI
- Brain embeddings: schema exists, no implementation
- Batch generation: schema exists, no router

### Critical Gaps — P0 (from Supabase + Vercel + Repo audit)
1. **Vercel deployments ERROR** — production not deployable
2. **public.workers lacks RLS entirely** — unprotected table
3. **Many tables have RLS enabled but NO policies** — false sense of security
4. **Supabase reports no tracked migrations** despite repo having 49 migration files
5. **AUTH_DEV_MODE=true by default** — returns org_id=None, disabling tenant filtering
6. **8 ghost tables** (queried in code, no CREATE TABLE migration)
7. **11 migration number collisions** (no deterministic ordering)
8. **~30 core tables have nullable org_id with existing NULL rows**
9. **optional_auth on read endpoints** allows unauthenticated access
10. **Service-role key used for all queries** (bypasses Supabase RLS)
11. **match_brain_embeddings has mutable function search path** (security risk)
12. **vector extension in public schema** (should be in extensions schema)
13. **Leaked-password protection disabled** in Supabase project


## Glossary

- **Platform**: The AI Studio web application (backend + frontend + infrastructure)
- **Tenant**: An organization (org_id) that owns data and resources within the Platform
- **Workspace**: A tenant's working environment within the Platform (synonymous with Tenant for MVP)
- **Auth_Gateway**: The authentication and authorization middleware that validates JWTs and resolves tenant membership
- **ComputeProvider**: An abstraction representing any GPU compute backend (RunPod, FluidStack, Lambda Labs, TensorDock, customer-managed)
- **StorageProvider**: An abstraction representing any persistent file storage backend (B2, S3-compatible, R2, Google Drive, local NAS)
- **Credential_Broker**: The subsystem that issues short-lived, job-scoped credentials to workers and revokes them on completion
- **Generation_Engine**: The subsystem that dispatches image/video generation to ComfyUI on compute workers
- **Training_Pipeline**: The subsystem that manages LoRA training jobs on compute workers
- **Brain_Service**: The customer-facing conversational AI interface (user-visible modes, personality, chat UX)
- **AIOS**: The canonical AI runtime and control plane — authorization, policy, routing, approvals, memory, cost, execution records
- **Hermes**: The planning and orchestration layer inside AIOS — reasoning, task decomposition, context retrieval, tool selection
- **Execution_Adapter**: A connector between AIOS and an external system (LLM, MCP server, API, GPU provider, storage, media system)
- **Worker_Orchestrator**: The subsystem that provisions, monitors, and terminates compute instances
- **Publishing_Service**: The subsystem that schedules and dispatches content to social platforms
- **Tenant_Context**: The resolved org_id + role for an authenticated request, derived from JWT + org_members table
- **RLS**: Row-Level Security policies enforced at the PostgreSQL level in Supabase
- **Simulation_Provider**: A mock provider that returns fake data instead of calling a real external service
- **Capability_Registry**: The single source of truth for what features are PRODUCTION, PARTIAL, SIMULATED, MISSING, DEPRECATED, or UNVERIFIED
- **Safety_Kernel**: The mandatory, non-disableable safety layer that enforces CSAM detection, legal obligations, and absolute content restrictions
- **Creative_Policy**: The configurable content policy layer managed by Platform Operator (platform-wide) and workspace admin (stricter-only)
- **Super_Admin**: SUPERSEDED — see Platform Operator (R97). Previously: platform-level operator with visibility and control over all tenants, system health, and configuration
- **Local_Connector**: A future authenticated bridge between AI Studio and a user's local machine (GPU, ComfyUI, LM Studio, Ollama, files)
- **MCP**: Model Context Protocol — a standard for LLM tool integration
- **Talent_Graph**: The typed relationship model connecting talent entities (people, products, wardrobe, locations, voices) to each other
- **Creative_DNA**: Per-talent learned preferences stored in Supabase and used to enhance generation quality
- **Entitlement**: A feature or resource allowance granted by a subscription plan
- **Trust_Domain**: An explicit security boundary defining what knowledge, tools, credentials, and approval capabilities are accessible to an identity class
- **Generation_Context_Package**: A versioned, immutable snapshot of all inputs (Talent, DNA, assets, models, LoRAs, prompts, consent, policy, workflow) resolved before job execution
- **Dataset_Manifest**: An immutable record of exact files, checksums, roles, and provenance used for a training job
- **Governance_Boundary**: The single canonical enforcement point through which ALL AI-initiated side effects must pass
- **Cost_Reservation**: An atomic pre-execution hold against a tenant's budget/entitlement, reconciled after completion
- **Promotion_Gate**: A lifecycle checkpoint that a model/LoRA must pass before advancing to the next production state
- **Release_Identity**: An immutable composite identifier linking commit, artifacts, migrations, config, and deployment evidence for a production release
- **Application_Context**: A server-validated envelope containing current workspace, page, project, talent, assets, job, mode, capabilities, and UI state for Brain/Hermes sessions
- **Platform_Operator**: An authenticated user with one or more platform administration capability grants (replacing undifferentiated Super Admin)
- **Connections_Hub**: The unified surface for managing all workspace integrations (AI providers, storage, social, compute, MCP, developer tools)
- **USER_CONNECTION**: A connection owned by an individual user that follows them across workspaces they access
- **WORKSPACE_CONNECTION**: A connection owned by the organization that stays with the workspace when members leave
- **Autonomy_Profile**: A workspace-configurable setting determining how much autonomous authority Brain/Hermes has (ADVISORY, ASSISTED, AUTONOMOUS_WITHIN_LIMITS)
- **Workload_Class**: An independently schedulable capacity category (interactive language, image generation, video generation, training, voice/audio, batch, production stages, publishing)
- **Compute_Availability_State**: Founder-controlled global state for platform-managed compute (DISABLED, SELECTIVE, ENABLED)


## Requirements

---

## PRIORITY TIER P0: Truth, Security, Deployability

---

### Requirement 1: Authentication Enforcement

**Status:** AMENDED in Rev 4 — added provisioning flow, OAuth, idempotent workspace creation

**User Story:** As a platform operator, I want all API endpoints to require valid authentication in production, so that unauthenticated users cannot access or mutate tenant data.

#### Acceptance Criteria

1. THE Auth_Gateway SHALL require a Supabase JWT (Authorization: Bearer header) that passes signature verification against the Supabase JWT secret, contains a non-empty `sub` claim, and has not exceeded its `exp` timestamp (with a maximum clock skew tolerance of 30 seconds), on all endpoints except GET /health, GET /ready, and GET /
2. WHEN a request lacks an Authorization header or provides a token that cannot be decoded as a valid JWT structure, THE Auth_Gateway SHALL return HTTP 401 with body `{"detail": "Authentication required", "code": "UNAUTHORIZED"}`
3. WHEN a JWT signature is valid but the `exp` claim indicates the token has expired beyond the 30-second clock skew tolerance, THE Auth_Gateway SHALL return HTTP 401 with body `{"detail": "Token expired", "code": "TOKEN_EXPIRED"}`
4. WHILE AUTH_DEV_MODE is true AND the environment is "local" or "test", WHEN a request arrives without a JWT, THE Auth_Gateway SHALL inject a dev user using the user_id and org_id from the first record in org_members ordered by created_at ascending
5. WHEN AUTH_DEV_MODE is true AND the environment is "production" or "staging", THE Platform SHALL refuse to start and log a configuration error indicating that dev mode is not permitted in this environment
6. WHEN a newly authenticated user has no org_members record AND is eligible for workspace provisioning (new signup or OAuth first-login), THE Auth_Gateway SHALL initiate authorized workspace provisioning (creating user identity, workspace/org, membership, and onboarding state) rather than rejecting with NO_MEMBERSHIP
7. IF an established identity without valid membership attempts access AND is not eligible for workspace provisioning, THEN THE Auth_Gateway SHALL return HTTP 403 with body `{"detail": "No organization membership found", "code": "NO_MEMBERSHIP"}`
8. THE Auth_Gateway SHALL extract user_id exclusively from the validated JWT `sub` claim and never trust client-supplied user_id values in request bodies, query parameters, or headers
9. IF a JWT passes signature verification but does not contain a `sub` claim or the `sub` claim is empty, THEN THE Auth_Gateway SHALL return HTTP 401 with body `{"detail": "Invalid token claims", "code": "INVALID_TOKEN"}`
10. WHEN a user authenticates via OAuth (Google or future providers), THE Platform SHALL NOT require a separate AI Studio password — the OAuth identity SHALL be sufficient for full platform access
11. THE Platform SHALL ensure workspace provisioning is idempotent — retrying the signup or OAuth flow SHALL NOT create duplicate workspaces, users, or memberships; if a workspace already exists for the identity, THE Platform SHALL resume the existing provisioning state

---

### Requirement 2: Tenant Isolation and RLS Enforcement

**Status:** AMENDED in Rev 3 — added multi-surface verification scope

**User Story:** As a platform operator, I want absolute data isolation between organizations with verified RLS policies on every tenant-scoped table, so that no tenant can ever access another tenant's resources even via direct database access.

#### Acceptance Criteria

1. THE Platform SHALL include org_id as a NOT NULL column on all tenant-scoped tables (Category A per Tenant Authorization Contract)
2. WHEN a database query is executed for tenant-scoped data, THE Platform SHALL include a WHERE org_id = :authenticated_org_id filter on every query, where authenticated_org_id is derived exclusively from TenantContext (resolved via org_members lookup from the validated JWT subject) and never from client-supplied request parameters
3. THE Platform SHALL enforce Supabase RLS policies on all Category A tables as a secondary defense layer, with each policy using an org_members subquery to restrict row access to the authenticated user's organization
4. THE Platform SHALL have RLS ENABLED on the public.workers table with appropriate policies restricting access by org_id or platform-admin identity
5. THE Platform SHALL verify that every table with RLS enabled also has at least one explicit RLS policy defined — tables with RLS enabled but zero policies SHALL be flagged as a P0 security defect
6. IF a request attempts to access a resource belonging to a different org_id, THEN THE Platform SHALL return HTTP 404 (not 403) to prevent information leakage about resource existence
7. WHEN the service-role key is used for backend-to-DB queries, THE Platform SHALL explicitly set org_id on every write operation and filter by org_id on every read
8. THE Platform SHALL never use the quarantined placeholder UUID (00000000-0000-0000-0000-000000000000) as an org_id value in any query or record, and SHALL reject any request that attempts to reference it with an HTTP 422 response
9. THE Platform SHALL ensure that all tenant-scoped list endpoints return items and total counts reflecting only the authenticated organization's data (isolation invariant)
10. THE Platform SHALL never accept org_id as a client-supplied request parameter on tenant-scoped endpoints; org_id SHALL be resolved solely from TenantContext
11. THE Platform SHALL maintain an automated RLS audit that verifies: (a) every Category A table has RLS enabled, (b) every table with RLS enabled has at least one policy, (c) every policy correctly references org_members or equivalent tenant resolution
12. THE Platform SHALL fix the match_brain_embeddings function to use an immutable search path (not mutable) to prevent search path injection
13. THE Platform SHALL verify tenant isolation across ALL system surfaces including: browser/frontend state, API responses, database queries, GPU worker execution boundaries, job outputs, asset storage paths, Brain/Hermes memory and conversation context, MCP tool invocations and responses, provider credentials and signed URLs, publishing dispatch, voice synthesis, video generation, LoRA training data, and Platform Operator actions
14. Implementation evidence (code review, developer assertion, automated test passage) alone SHALL NOT constitute proof of tenant isolation — independent adversarial verification against running system surfaces is required (see R82)

---

### Requirement 3: Role-Based Access Control

**Status:** PRESERVED from Rev 2 R3

**User Story:** As an organization owner, I want to control what team members can do, and as a platform operator I want Platform Operator access for platform-wide management, so that permissions are enforced at all levels.

#### Acceptance Criteria

1. THE Platform SHALL enforce the workspace role hierarchy owner > admin > editor > viewer on all endpoints that perform POST, PUT, PATCH, or DELETE operations
2. IF a user with the "viewer" role attempts a POST, PUT, PATCH, or DELETE operation, THEN THE Platform SHALL reject the request with HTTP 403 and body `{"detail": "Insufficient permissions", "code": "FORBIDDEN"}`
3. IF a user with the "editor" role attempts a DELETE operation on a talent, model, credential, or organization-settings resource, THEN THE Platform SHALL reject the request with HTTP 403
4. WHEN a request is received, THE Platform SHALL resolve the user's role by querying the org_members table for the authenticated user_id and org_id where membership status is "active"
5. IF no active membership record exists for the authenticated user and org_id, THEN THE Platform SHALL reject the request with HTTP 403
6. WHILE a user has the "owner" role, THE Platform SHALL allow all operations including adding members, removing members, changing member roles, and managing billing settings
7. THE Platform SHALL support a Platform_Operator identity (stored in a dedicated platform_operators table) with read access to all tenants, platform configuration, capability registry, and system health — but Platform_Operator SHALL NOT mutate tenant data through normal API endpoints without explicit capability grants and audit
8. THE Platform SHALL enforce that Platform_Operator operations are logged with full audit trail including actor, target tenant, action, capability used, and timestamp


---

### Requirement 4: Input Validation

**Status:** PRESERVED from Rev 2 R4

**User Story:** As a developer, I want all API inputs validated through Pydantic schemas, so that invalid data is rejected at the boundary with clear error messages.

#### Acceptance Criteria

1. THE Platform SHALL validate all request bodies through Pydantic v2 schemas with explicit field constraints: min_length=1 for required strings, maximum length per field type (100 characters for names, 1000 for descriptions, 5000 for free-text content), UUID type for all ID fields, and ge/le bounds for all numeric fields
2. WHEN a request body fails validation, THE Platform SHALL return HTTP 422 with body `{"detail": [{"loc": [...], "msg": "...", "type": "..."}], "code": "VALIDATION_ERROR"}`
3. THE Platform SHALL use UUID type annotations for all ID path parameters, rejecting non-UUID strings with HTTP 422
4. THE Platform SHALL validate file uploads by: reading the first 8 bytes to verify magic bytes match the declared MIME type, enforcing per-asset-type size limits, and rejecting content types not in the allowlist
5. WHEN a file upload exceeds the size limit, THE Platform SHALL return HTTP 413 with an error message indicating the asset type, the submitted file size, and the configured maximum size
6. THE Platform SHALL validate pagination parameters (limit: 1-100 with default 20, offset: >= 0 with default 0) using a shared PaginationParams schema
7. IF an enum field receives a value not in the allowed set, THEN THE Platform SHALL return HTTP 422 listing the valid options
8. IF a file upload's magic bytes do not match the declared content type, THEN THE Platform SHALL reject the upload with HTTP 422
9. THE Platform SHALL enforce a maximum request body size of 10 MB for JSON payloads (excluding file upload endpoints), rejecting oversized requests with HTTP 413
10. IF a required string field contains only whitespace characters, THEN THE Platform SHALL reject the input with HTTP 422

---

### Requirement 5: Database Schema Reconciliation and Migration Baseline

**Status:** AMENDED in Rev 3 — added generated-type reconciliation and manual-object identification

**User Story:** As a developer, I want a reproducible migration chain that matches the deployed schema, so that new environments can be reliably provisioned and schema drift is eliminated.

#### Acceptance Criteria

1. THE Platform SHALL establish a migration baseline by inspecting the live Supabase schema (pg_dump --schema-only) and reconciling it against the 49 migration files in docs/sql/
2. THE Platform SHALL create CREATE TABLE migrations for all 8 ghost tables identified in SCHEMA_DRIFT_REPORT.md (talent, assets, storyboards, fleet_settings, service_settings, story_universes, talent_loras, publishing_analytics)
3. THE Platform SHALL resolve all 11 migration numbering collisions by adopting a linear, non-conflicting sequence where each numeric prefix maps to exactly one migration file
4. THE Platform SHALL populate the _migration_ledger table with the current state of the deployed schema, recording migration_id, a SHA-256 checksum of each migration file, and applied_at timestamp
5. WHEN migrations are applied in sequence to an empty PostgreSQL 15+ database, THE Platform SHALL produce a schema where all application queries succeed without "relation does not exist" or column-mismatch errors
6. THE Platform SHALL make org_id NOT NULL on all Category A tables — NULL rows SHALL be resolved via the quarantine process defined in R69 (classify, review, then assign/purge) before the NOT NULL constraint is applied. For tables where the founder is the ONLY org that has ever existed (verified by audit), bulk assignment to the founder's org_id is acceptable without per-row review. For tables where multiple orgs exist or ownership is ambiguous, R69's quarantine-then-classify process SHALL apply.
7. THE Platform SHALL rename organization_id to org_id on all Company OS tables via an additive migration
8. IF a migration fails during application, THEN THE Platform SHALL roll back that single migration's transaction and record the failure in _migration_ledger
9. THE Platform SHALL exclude template migrations (files containing "DO NOT APPLY") from automated execution
10. THE Platform SHALL register the migration baseline in Supabase's migration tracking system so that `supabase migration list` reports accurate state
11. THE Platform SHALL move the vector extension from the public schema to the extensions schema
12. THE Platform SHALL enable leaked-password protection in the Supabase project configuration
13. THE Platform SHALL reconcile generated TypeScript types and Python/Pydantic schemas against the live database schema as a fourth source of truth — any type mismatch between migration SQL, application code, generated types, and live schema SHALL be flagged as drift
14. THE Platform SHALL explicitly identify and document all manually-created database objects (tables, functions, triggers, extensions) that exist in the live schema but have no corresponding migration file, classifying each as: needs-migration, deprecated, or scheduled-for-removal
15. THE Platform SHALL identify overlapping domain models across subsystems (see R70) and document which schema objects are canonical vs compatibility-only vs deprecated

---

### Requirement 6: Supabase RLS Comprehensive Audit

**Status:** PRESERVED from Rev 2 R6

**User Story:** As a security engineer, I want every tenant-sensitive table verified to have RLS enabled with correct policies and automated tests proving isolation, so that I can certify the platform is secure.

#### Acceptance Criteria

1. THE Platform SHALL have RLS enabled on every Category A table (as defined in Tenant Authorization Contract) — currently public.workers is identified as lacking RLS entirely
2. THE Platform SHALL verify that every table with ALTER TABLE ... ENABLE ROW LEVEL SECURITY also has at least one CREATE POLICY statement that correctly restricts access
3. THE Platform SHALL include automated tests (one per Category A table) that: (a) insert a row with org_id=A, (b) attempt to read it with a JWT for org_id=B, (c) verify the row is not returned
4. THE Platform SHALL include automated tests that verify: (a) unauthenticated access to tenant-scoped tables returns zero rows, (b) the quarantined UUID cannot be used to access any data
5. WHEN a new table is created via migration, THE Platform SHALL include RLS enablement and at least one policy in the same migration file
6. THE Platform SHALL document the RLS policy for every Category A table in a machine-readable format that can be validated by CI
7. IF a table has RLS enabled but zero policies, THEN THE Platform SHALL treat this as equivalent to having no RLS (all access denied by default in Supabase, which may cause silent failures)
8. THE Platform SHALL fix the match_brain_embeddings function search_path from mutable to immutable


---

### Requirement 7: Production Deployment Pipeline

**Status:** PRESERVED from Rev 2 R7

**User Story:** As a platform operator, I want the application to deploy successfully to Vercel (frontend) and Railway/Render (backend) with passing CI, so that the product is actually usable in production.

#### Acceptance Criteria

1. THE Platform frontend SHALL build with zero TypeScript errors, zero ESLint errors, and zero Next.js build errors when running the CI build command, producing a deployable artifact
2. THE Platform backend SHALL start successfully on Railway/Render with all required environment variables set, passing the GET /ready health check within 30 seconds of boot
3. THE Platform SHALL include CI/CD configuration (GitHub Actions) that runs: Python linting (Ruff), Python tests (pytest), TypeScript compilation check, ESLint, frontend build, secret scanning, and blocks merge on any failure
4. WHEN a Vercel deployment fails, THE Platform SHALL have a documented diagnostic path that identifies the failure cause within the build logs
5. THE Platform backend SHALL be fully stateless — all persistent state stored in Supabase, storage providers, or Redis; no in-memory singletons that cause data loss on process restart
6. IF an API request requires processing longer than 55 seconds, THEN THE Platform SHALL dispatch to a background worker and return HTTP 202
7. THE Platform SHALL include a Dockerfile for the backend that installs all Python dependencies via uv, exposes port 8000, and runs uvicorn
8. WHEN the Platform backend receives SIGTERM, THE Platform SHALL stop accepting new requests, allow in-flight requests up to 30 seconds to complete, then exit with code 0
9. THE Platform SHALL resolve all current Vercel deployment errors as a prerequisite to any feature being classified as "production-ready"
10. THE Platform SHALL include smoke tests that run post-deployment verifying: GET / returns 200, GET /ready returns 200 with service status, and one authenticated endpoint returns 200 with a valid test JWT

---

### Requirement 8: Secure Credential Broker

**Status:** AMENDED in Rev 3 — added encryption authority separation

**User Story:** As a security engineer, I want compute workers to receive only short-lived, job-scoped credentials so that a compromised worker cannot access data beyond its assigned job.

#### Acceptance Criteria

1. WHEN a job is dispatched to a compute worker, THE Credential_Broker SHALL issue a short-lived credential scoped exclusively to: the specific job_id, the org_id that owns the job, and only the storage paths required for that job's inputs and outputs
2. THE Credential_Broker SHALL set credential expiration to no longer than the job's maximum timeout plus a 5-minute grace period
3. THE Credential_Broker SHALL never transmit durable secrets (B2 master keys, Supabase service role key, API keys) to any compute worker
4. WHEN a job completes, fails, or is cancelled, THE Credential_Broker SHALL revoke the issued credential within 60 seconds
5. IF a credential is used to access a storage path outside its authorized scope, THEN THE StorageProvider SHALL reject the access and THE Credential_Broker SHALL log the violation with worker_id, job_id, attempted_path, and timestamp
6. THE Credential_Broker SHALL maintain an audit log of all credential issuances and revocations, queryable by org_id and job_id
7. THE Credential_Broker SHALL support credential issuance for multiple storage providers (B2 pre-signed URLs, S3 pre-signed URLs, R2 pre-signed URLs) using the same interface
8. IF the Credential_Broker is unreachable, THEN THE Worker_Orchestrator SHALL not dispatch jobs and SHALL return HTTP 503 with code "CREDENTIAL_SERVICE_UNAVAILABLE"
9. THE Platform SHALL maintain separate encryption authorities for production and development environments — development credentials SHALL NOT be valid in production, and production key material SHALL NOT be accessible from development environments
10. THE Platform SHALL document the final production key/secrets authority (which system holds master keys, rotation policy, break-glass procedures) as an explicit Founder decision before production launch

---

### Requirement 9: Configuration and Environment Safety

**Status:** PRESERVED from Rev 2 R9

**User Story:** As a platform operator, I want the application to refuse to start with unsafe configuration in production, so that secrets are never placeholder values and critical services are never misconfigured.

#### Acceptance Criteria

1. WHEN the ENVIRONMENT variable is set to "production" or "staging", THE Platform SHALL validate at startup that SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET, SECRET_KEY, and at least one storage provider credential set are all present, non-empty, and do not match placeholder patterns
2. WHEN the ENVIRONMENT variable is set to "production", THE Platform SHALL refuse to start if: DEBUG is "true", AUTH_REQUIRED is "false", ALLOWED_ORIGINS contains "*", or any critical provider is set to "simulation"
3. WHEN the ENVIRONMENT variable is set to "production", THE Platform SHALL refuse to start if SUPABASE_URL, DATABASE_URL, or REDIS_URL contain "localhost", "127.0.0.1", or "0.0.0.0"
4. THE Platform SHALL load all configuration exclusively via the Settings Pydantic model — application code SHALL NOT call os.environ or os.getenv directly
5. THE Platform SHALL expose a GET /ready endpoint that returns HTTP 200 with a JSON body listing each configured service and its status ("available", "unavailable", or "not_configured"), without including any secret values
6. IF a non-critical service is unavailable at startup, THEN THE Platform SHALL start in degraded mode, log a warning, and return HTTP 503 for endpoints that depend on that service
7. THE Platform SHALL validate that the Credential_Broker configuration is present and reachable before accepting job submissions


---

## PRIORITY TIER P1: Core Production Experience

---

### Requirement 10: Talent Graph, Identity Classification, and Consent

**Status:** PRESERVED from Rev 2 R10

**User Story:** As a content creator, I want to manage AI talent with typed relationships, identity classifications, and explicit consent records, so that my creative entities are richly connected and legally compliant.

#### Acceptance Criteria

1. WHEN a POST /api/v1/talent request is received with valid data including a name (1-100 characters), type (enum: model, character, voice, influencer, wardrobe, product, background, object), and identity_classification (enum: FICTIONAL, REAL_PERSON_SELF, REAL_PERSON_AUTHORIZED), THE Platform SHALL create a talent record scoped to the authenticated org_id and return HTTP 201
2. THE Platform SHALL enforce that talent with identity_classification REAL_PERSON_AUTHORIZED must have at least one consent record before being used in generation, training, or publishing operations
3. THE Platform SHALL support independent consent scopes stored per-talent: likeness, voice, model_training, adult_content, commercial_use, publishing, client_work — each with granted_at timestamp, grantor identity, and optional expiry_at
4. WHEN a GET /api/v1/talent request is received, THE Platform SHALL return a paginated list scoped to the authenticated org_id with format `{"items": [...], "total": N, "limit": 20, "offset": 0}`
5. IF a GET, PUT, or DELETE /api/v1/talent/{id} request targets a talent_id not belonging to the authenticated org, THEN THE Platform SHALL return HTTP 404
6. WHEN a DELETE /api/v1/talent/{id} request is received, THE Platform SHALL soft-delete and return HTTP 204
7. THE Platform SHALL support typed relationships between talents via POST /api/v1/talent/{id}/relationships with types: associated, friends, couple, wears, uses, lives_in, holds, appears_with, pairs_with, variant_of — enforcing uniqueness on (source_talent_id, target_talent_id, relationship_type)
8. THE Platform SHALL support talent-to-LoRA associations via a talent_loras junction table with: talent_id, lora_model_id, type (identity, style), strength (0.0-1.0), always_on (boolean), limited to 5 LoRAs per talent
9. WHEN a talent has an identity LoRA assigned with always_on=true, THE Generation_Engine SHALL automatically inject it into workflows at the configured strength when generating for that talent
10. THE Platform SHALL support batch media upload (1-50 files per request, each max 20 MB, MIME: image/jpeg, image/png, image/webp) to a talent's profile via POST /api/v1/talent/{id}/media
11. THE Platform SHALL enforce adult_status classification: VERIFIED_18_PLUS required on any talent used in adult content workflows — talent without this classification SHALL be blocked from adult content generation regardless of consent scopes
12. IF a generation, training, or publishing request references a talent lacking required consent for that operation type, THEN THE Platform SHALL reject with HTTP 403 and a message identifying the missing consent scope

---

### Requirement 11: Storage Provider Abstraction

**Status:** PRESERVED from Rev 2 R11

**User Story:** As a content creator, I want my assets stored securely with my choice of storage provider, and as a platform operator I want storage to be abstracted so the system works regardless of where files live.

#### Acceptance Criteria

1. THE Platform SHALL define a StorageProvider interface supporting: upload(key, data, metadata), download(key), delete(key), get_signed_url(key, expiry), list(prefix), and exists(key)
2. THE Platform SHALL support the following StorageProvider implementations: AI Studio managed B2 (default), customer-provided B2, S3-compatible (any), Cloudflare R2, and Google Drive — with local connector and NAS as future extensions
3. THE Platform SHALL store asset metadata (id, org_id, storage_provider, storage_key, content_type, file_size_bytes, talent_id, job_id, created_at) in Supabase regardless of which StorageProvider holds the binary data
4. THE Platform SHALL never return raw storage URLs in API responses; all URLs SHALL be signed with expiration (default 3600 seconds) or served via CDN
5. WHEN an asset is deleted, THE Platform SHALL soft-delete the database record and schedule the storage object deletion asynchronously
6. THE Platform SHALL store org_id, job_id, and content_type as object metadata on every upload (where the storage provider supports metadata)
7. WHEN a file larger than 100 MB is uploaded, THE StorageProvider SHALL use multipart upload
8. IF the configured StorageProvider is unreachable during upload, THEN THE Platform SHALL return HTTP 503 with code "STORAGE_UNAVAILABLE"
9. THE Platform SHALL validate uploaded file MIME types against the allowlist using magic byte inspection
10. IF a user requests an asset belonging to a different org_id, THEN THE Platform SHALL return HTTP 404
11. THE Platform SHALL support workspace-level storage configuration allowing tenants to select their preferred StorageProvider (subject to their plan entitlements)
12. THE Platform SHALL use the storage key structure: /{org_id}/{asset_type}/{talent_id}/{job_id}/{filename} for platform-managed storage

---

### Requirement 12: Provider-Agnostic Image Generation Pipeline

**Status:** PRESERVED from Rev 2 R12

**User Story:** As a content creator, I want to generate images using AI models on any available compute provider, so that I'm not locked into a single GPU vendor.

#### Acceptance Criteria

1. WHEN a POST /api/v1/generate/image request is received with a non-empty prompt (max 2000 characters), a supported model identifier, output dimensions (256-2048px per side), and an optional talent_id, THE Generation_Engine SHALL create a job record with status "queued" and return HTTP 202 within 2 seconds
2. THE Generation_Engine SHALL dispatch jobs to any available ComputeProvider that meets the job's requirements (VRAM, model availability, cost limit) without being tied to a specific vendor
3. WHILE a compute worker is reachable, WHEN a queued job is dispatched, THE Generation_Engine SHALL select the ComfyUI workflow matching the requested model, inject parameters, submit to the worker, and poll for completion at intervals no greater than 5 seconds
4. WHEN the generation_provider is "simulation", THE Generation_Engine SHALL return a simulated result within 3 seconds with simulation=true in response metadata
5. IF no compute worker is available AND auto_provision is enabled AND budget allows, THEN THE Worker_Orchestrator SHALL provision a new instance from the preferred ComputeProvider
6. IF the job exceeds the configured timeout (default 30 minutes), THEN THE Generation_Engine SHALL mark it as "failed" with reason "timeout" and terminate the instance
7. WHEN generation completes, THE Generation_Engine SHALL upload output to the configured StorageProvider, create an asset record, and update job status to "completed"
8. IF a workflow error occurs (bad JSON, missing model), THEN THE Generation_Engine SHALL fail immediately without retry
9. IF a transient infrastructure error occurs, THEN THE Generation_Engine SHALL retry up to 3 times with exponential backoff (10s, 20s, 40s)
10. WHEN a job reaches terminal status, THE Generation_Engine SHALL record cost_usd, gpu_type, runtime_seconds, and provider on the job record
11. IF a talent_id is provided that does not belong to the authenticated org, THEN THE Generation_Engine SHALL reject with HTTP 403
12. THE Generation_Engine SHALL support cost estimation before dispatch: WHEN a GET /api/v1/generate/estimate request is received with model and dimensions, THE Platform SHALL return estimated_cost_usd and estimated_duration_seconds


---

### Requirement 13: Compute Provider Abstraction

**Status:** AMENDED in Rev 4 — added availability states, customer-managed multi-GPU, and load balancing

**User Story:** As a platform operator, I want GPU compute abstracted behind a provider interface supporting multiple vendors and ownership modes, with customer-managed compute as the preferred model and platform-managed compute as a Founder-controlled option, so that the platform is not locked to any single GPU provider and expensive workloads default to customer infrastructure.

#### Acceptance Criteria

1. THE Platform SHALL define a ComputeProvider interface supporting: provision(requirements), terminate(instance_id), health_check(instance_id), get_status(instance_id), list_available(), and estimate_cost(requirements)
2. THE Platform SHALL support three compute modes configurable per workspace: PLATFORM_MANAGED (AI Studio provisions and manages), CUSTOMER_MANAGED (customer provides their own workers), and HYBRID (both) — with CUSTOMER_MANAGED as the architecturally preferred model for expensive ongoing creative workloads
3. THE Platform SHALL support ComputeProvider implementations for: RunPod (primary, persistent volumes), FluidStack, Lambda Labs, TensorDock — with Vast.ai as legacy/deprecated
4. THE Platform SHALL favor ComputeProviders that support persistent storage/cache (RunPod Network Volumes) to avoid repeated model downloads
5. THE Worker_Orchestrator SHALL terminate compute instances after job completion or failure, ensuring cleanup executes in a finally block regardless of exception type
6. WHILE a compute worker has received no job for longer than fleet_idle_timeout minutes (default 15), THE Worker_Orchestrator SHALL terminate it and record the session cost
7. THE Worker_Orchestrator SHALL track daily GPU spend per organization and reject new launches when the daily budget is exceeded with HTTP 402
8. THE Worker_Orchestrator SHALL maintain worker state in Supabase (not in-memory) that persists across server restarts
9. WHEN a compute instance fails to boot within 5 minutes, THE Worker_Orchestrator SHALL mark it as failed, blacklist the host for 24 hours in provider reputation, and retry on a different host (max 3 attempts)
10. THE Worker_Orchestrator SHALL perform health checks every 60 seconds for active workers
11. IF a worker fails 3 consecutive health checks, THEN THE Worker_Orchestrator SHALL mark it as unresponsive, terminate it, and re-queue any in-progress job
12. THE Worker_Orchestrator SHALL never provision more than fleet_max_instances concurrent workers per organization
13. WHEN a customer connects their own compute (CUSTOMER_MANAGED mode), THE Platform SHALL validate connectivity, ComfyUI availability, and model presence before accepting jobs for that worker
14. THE Platform SHALL enforce a Founder-controlled platform-managed compute availability state with three modes: DISABLED (platform-managed compute entirely unavailable — UI does not show it, Brain/Hermes does not recommend it, APIs reject requests for it, capability remains in registry as disabled), SELECTIVE (Founder can enable by workspace, plan, beta cohort, workload type, provider, temporary promotion, or manual override), and ENABLED (eligible workspaces may use according to plan, budget, workload, and capacity)
15. WHEN platform-managed compute is in DISABLED state, THE Platform SHALL reject any API request for platform-managed compute with HTTP 403 and code "PLATFORM_COMPUTE_DISABLED" — including forged requests that bypass UI
16. Changing platform-managed compute availability state SHALL NOT require architectural changes, code deployment, or service restart — the state change SHALL take effect through configuration alone
17. WHEN a workspace operates in CUSTOMER_MANAGED mode, THE Platform SHALL support multiple workers/GPUs from one or multiple providers connected simultaneously
18. THE Platform SHALL provide workload scheduling across a customer's eligible compute pool considering: workload type requirements, VRAM availability, model cache readiness, current utilization, worker health, queue depth, estimated execution time, job priority, concurrency entitlement, and workspace routing preferences
19. THE Platform SHALL support independent concurrent job execution across multiple eligible workers in a customer's compute pool
20. THE Platform SHALL NOT exceed customer-configured concurrency limits or plan-authorized concurrency limits when scheduling across a customer's compute pool

---

### Requirement 14: Cost Tracking, Budget Enforcement, and Reconciliation

**Status:** AMENDED in Rev 4 — added platform compute cost protections, cost classification

**User Story:** As a platform operator, I want all GPU, LLM, and API costs tracked per-organization with enforced budgets and atomic cost reservations across any compute or AI provider, so that no tenant generates runaway costs and cost accounting is always accurate.

#### Acceptance Criteria

1. WHEN a GPU job completes or fails after consuming resources, THE Platform SHALL record a cost entry to Supabase containing: cost_usd (4 decimal places), org_id, job_id, provider_name, provider_type (compute, llm, voice, storage), gpu_type (if applicable), runtime_seconds, and created_at timestamp
2. THE Platform SHALL persist all cost records to Supabase so they survive server restarts; cost records SHALL be immutable once written
3. WHEN an organization's cumulative spend for the current UTC day reaches or exceeds daily_budget, THE Platform SHALL reject new GPU job submissions with HTTP 402 and code "DAILY_BUDGET_EXCEEDED"
4. WHEN an organization's cumulative spend for the current UTC month reaches or exceeds monthly_budget, THE Platform SHALL reject new GPU job submissions with HTTP 402 and code "MONTHLY_BUDGET_EXCEEDED"
5. THE Platform SHALL provide a GET /api/v1/costs/summary endpoint returning: today_spend, month_spend, daily_budget, monthly_budget, projected_monthly_cost, and a breakdown by provider_type
6. WHEN a cloud LLM API is used, THE Platform SHALL calculate token cost using the provider's per-token pricing and record it in the cost ledger
7. WHEN a user submits an operation with estimated cost exceeding the workspace's auto_approve_threshold (default $0.05), THE Platform SHALL return the cost estimate and require confirmation before execution
8. THE Platform SHALL attribute costs to the correct ComputeProvider regardless of vendor, using the provider's API billing data or calculated from hourly rate × runtime
9. BEFORE dispatching a platform-managed expensive operation (GPU job, training, batch generation), THE Platform SHALL create an atomic Cost_Reservation against the tenant's budget/entitlement — if the reservation would exceed budget, THE Platform SHALL reject the operation before any resource is provisioned
10. AFTER execution completes, THE Platform SHALL reconcile estimated cost against actual cost: release unused reservation, record actual cost_usd, and log any variance exceeding 20% as a cost anomaly for investigation
11. THE Platform SHALL record cost for failed operations (including partial GPU time consumed before failure) and retry attempts — each attempt that consumes resources SHALL have its own cost entry
12. THE Platform SHALL distinguish between three cost classifications: customer infrastructure cost (informational — tracking customer-owned compute usage for visibility), platform infrastructure expense (AI Studio's own operational costs), and customer-billed managed-compute usage (platform-managed compute charged to tenant)
13. THE Platform SHALL never treat missing cost evidence as $0 — if cost data is unavailable after job completion, THE Platform SHALL flag the job for manual cost reconciliation and log a warning
14. Platform-managed operations SHALL NOT begin if any of: cost cannot be estimated within policy tolerance, budget reservation cannot be created, provider pricing is unavailable and policy requires known cost, platform-wide compute budget has been reached, or workspace entitlement has been reached
15. Customer-owned compute cost SHALL be tracked as informational cost from AI Studio's perspective — not reserved against tenant budget unless a future billing arrangement explicitly states otherwise


---

### Requirement 15: Project Management

**Status:** PRESERVED from Rev 2 R15

**User Story:** As a content creator, I want to organize my work into projects, so that I can group related talent, assets, and jobs under a single creative context.

#### Acceptance Criteria

1. WHEN a POST /api/v1/projects request is received with a valid name (1-200 characters) and optional description (max 2000 characters), THE Platform SHALL create a project scoped to the authenticated org_id with status "active" and return HTTP 201
2. THE Platform SHALL support associating talent, assets, and jobs to a project via project_id; a resource SHALL belong to at most one project at a time
3. WHEN a GET /api/v1/projects/{id} request is received, THE Platform SHALL return the project including talent_count, asset_count, and job_count
4. THE Platform SHALL enforce project status transitions: active → archived, active → completed, archived → active, completed → active; all others rejected with HTTP 422
5. WHILE a project has status "archived", THE Platform SHALL exclude it from list responses unless include_archived=true is provided
6. IF a DELETE /api/v1/projects/{id} request is received, THEN THE Platform SHALL soft-delete, remove project_id from linked resources, and return HTTP 204
7. IF creating a project would exceed 500 projects per org (excluding soft-deleted), THEN THE Platform SHALL reject with HTTP 422

---

### Requirement 16: API Error Handling and Response Format

**Status:** PRESERVED from Rev 2 R16

**User Story:** As a frontend developer, I want all API errors to follow a consistent structure with typed error codes, so that the UI can render appropriate error states.

#### Acceptance Criteria

1. THE Platform SHALL return all error responses with Content-Type application/json in the format: `{"detail": "<message>", "code": "<SNAKE_CASE_ERROR_CODE>"}`
2. THE Platform SHALL never include stack traces, internal paths, environment variable values, or third-party service URLs in error responses
3. WHEN a 500 error occurs, THE Platform SHALL log the full exception but return only `{"detail": "Internal server error", "code": "INTERNAL_ERROR"}`
4. THE Platform SHALL include a unique X-Request-ID header (UUID v4) on every response, propagated into all log entries
5. THE Platform SHALL never use bare `except:` without re-raising
6. WHEN a dependent service is unreachable after 5 seconds, THE Platform SHALL return HTTP 503 with a service-specific error code and Retry-After header
7. THE Platform SHALL apply consistent HTTP status codes: 201 for creation, 204 for deletion, 202 for async jobs, 404 for not found, 422 for validation, 403 for permission, 401 for auth

---

### Requirement 17: Frontend State Management and Data Fetching

**Status:** PRESERVED from Rev 2 R17

**User Story:** As a content creator, I want pages to load instantly with cached data and handle errors gracefully.

#### Acceptance Criteria

1. THE Platform frontend SHALL use SWR or React Query for all API calls with stale-while-revalidate caching (30s stale time), background revalidation on focus, request deduplication, and retry with backoff (max 3)
2. WHEN navigating between pages, THE Platform frontend SHALL render cached data within 100ms and revalidate in background
3. WHILE data is loading for the first time, THE Platform frontend SHALL display animated skeleton placeholders matching final layout
4. WHEN an API call fails after all retries, THE Platform frontend SHALL display an inline error with "Retry" button
5. WHEN offline, THE Platform frontend SHALL display a persistent banner and disable mutation buttons
6. THE Platform frontend SHALL persist user preferences to the backend, falling back to localStorage only when API fails
7. WHEN a list returns zero items, THE Platform frontend SHALL display an empty-state with description and creation CTA

---

### Requirement 18: Frontend Authentication Flow

**Status:** PRESERVED from Rev 2 R18

**User Story:** As a user, I want secure sign-in with persistent sessions and automatic redirect on expiry.

#### Acceptance Criteria

1. THE Platform frontend SHALL use Supabase Auth for authentication supporting email/password and Google OAuth
2. WHEN a user without a session visits any route other than /login, THE Platform frontend SHALL redirect to /login within 100ms
3. WHEN any API call returns HTTP 401, THE Platform frontend SHALL clear session, clear cache, and redirect to /login
4. THE Platform frontend SHALL include the Supabase access token in Authorization: Bearer on every API request
5. WHEN sign-out is triggered, THE Platform frontend SHALL call signOut(), clear caches, and redirect to /login within 500ms
6. THE Platform frontend SHALL register onAuthStateChange to auto-refresh tokens before expiration

---

### Requirement 19: Capability Registry

**Status:** AMENDED in Rev 4 — added disabled state handling, feature rollout controls

**User Story:** As a platform operator, I want a single source of truth for what features are production-ready, simulated, or missing, with support for feature rollout controls, so that UI, readiness probes, Platform Operators, and Hermes all report consistent capability status.

#### Acceptance Criteria

1. THE Platform SHALL maintain a Capability_Registry that classifies every feature as one of: PRODUCTION, PARTIAL, SIMULATED, MISSING, DEPRECATED, DISABLED, or UNVERIFIED
2. THE Capability_Registry SHALL be queryable via GET /api/v1/capabilities returning all capabilities with their current classification, required provider, and health status
3. WHEN the GET /ready endpoint is called, THE Platform SHALL derive service readiness from the Capability_Registry rather than independent checks
4. THE Platform frontend SHALL use the Capability_Registry to determine which UI features to show, disable, or badge with simulation indicators
5. THE Platform Operator control plane SHALL display the full Capability_Registry with the ability to override classifications (e.g., force a capability to SIMULATED for maintenance)
6. WHEN a capability transitions from one classification to another (e.g., SIMULATED → PRODUCTION), THE Platform SHALL log the transition with timestamp, actor, and reason
7. THE Capability_Registry SHALL be the authoritative source for Hermes when answering questions about what the platform can currently do
8. WHEN a user attempts to use a capability classified as MISSING, THE Platform SHALL return HTTP 501 with code "CAPABILITY_NOT_IMPLEMENTED" and a human-readable message
9. Capabilities classified as DISABLED SHALL remain in the registry but be marked as unavailable — DISABLED capabilities SHALL be inaccessible through ALL surfaces: UI (not shown), API (rejected), Brain/Hermes (not recommended or invokable), MCP (not available), and direct execution paths
10. THE Platform SHALL support feature rollout controls allowing Founder/Platform Operators to enable capabilities: globally, by plan tier, by specific workspace, by beta cohort, by individual user, by workload type, or by provider — without requiring code deployment or architectural changes


---

### Requirement 20: Onboarding and First-Run Experience

**Status:** PRESERVED from Rev 2 R20

**User Story:** As a new user, I want a guided introduction that helps me create my first talent within 60 seconds.

#### Acceptance Criteria

1. WHEN a user logs in and their organization has zero talent and zero projects, THE Platform frontend SHALL display a welcome onboarding flow
2. THE onboarding SHALL consist of no more than 3 steps collecting: primary use case (content creator, brand, developer) and first talent creation (name + type required, photo optional)
3. THE onboarding SHALL be completable within 60 seconds with required fields only
4. WHEN onboarding completes, THE Platform frontend SHALL redirect to Brain with a contextual welcome message referencing the created talent
5. A "Skip" action SHALL be visible on every step; skipping persists a flag and navigates to Home
6. IF onboarding was previously completed or skipped, THE Platform frontend SHALL NOT display it again

---

### Requirement 21: Job Leasing and Durable Execution

**Status:** AMENDED in Rev 3 — replaced Celery/Redis prescription with implementation-agnostic behavioral contract

**User Story:** As a platform operator, I want long-running operations to execute reliably via a durable job system with leasing, heartbeat, and recovery semantics, so that jobs survive infrastructure failures and the web server is never blocked.

#### Acceptance Criteria

1. THE Platform SHALL dispatch all operations exceeding 5 seconds to a durable job system, never executing them synchronously in the web server process
2. WHEN a job is submitted, THE Platform SHALL create a durable record with status "queued", org_id from JWT, and return HTTP 202 within 2 seconds — the record SHALL persist across server restarts
3. WHEN a worker claims a job, THE Platform SHALL issue an atomic lease with: lease_token (unique per claim), worker_identity, lease_expiration (configurable per job type, default 30 minutes), and attempt_count
4. WHILE holding a lease, the worker SHALL send heartbeat signals at intervals no greater than lease_duration / 3 — each heartbeat extends the lease expiration
5. IF a lease expires without heartbeat renewal, THEN THE Platform SHALL mark the job as "lease_expired", increment attempt_count, and make it available for re-claim by another worker
6. THE Platform SHALL support job cancellation via explicit request — cancellation of a leased job SHALL revoke the lease and signal the worker to stop
7. WHEN polling GET /api/v1/jobs/{id}, THE Platform SHALL return: status, progress_percent, started_at, completed_at, error_message, output_asset_ids, attempt_count, and current_worker_identity
8. IF a job has no heartbeat for longer than its lease expiration, THEN THE Platform SHALL treat the worker as lost and the job as eligible for retry
9. IF a transient error causes failure, THEN THE Platform SHALL retry up to 3 times with exponential backoff — retry delay and max attempts configurable per job type
10. IF a content error causes failure (invalid workflow, missing model), THEN THE Platform SHALL fail immediately without retry
11. WHEN a submission includes an idempotency_key matching a non-terminal job for the same org, THE Platform SHALL return the existing job rather than creating a duplicate
12. THE Platform SHALL reject stale workers attempting to write results for a job whose lease they no longer hold — only the current lease holder may update job state
13. THE Platform SHALL support progress reporting from workers: progress_percent (0-100), progress_message, and optional structured progress_metadata
14. THE design.md SHALL select the implementation technology (Celery+Redis, Supabase polling, SQS, or other) — this requirement defines behavioral contract only

---

### Requirement 22: Pagination and List Endpoints

**Status:** PRESERVED from Rev 2 R22

**User Story:** As a frontend developer, I want all list endpoints to support consistent pagination.

#### Acceptance Criteria

1. THE Platform SHALL accept limit (1-100, default 20) and offset (>=0, default 0) on all list endpoints
2. THE Platform SHALL return `{"items": [...], "total": N, "limit": <applied>, "offset": <applied>}`
3. WHEN limit exceeds 100, THE Platform SHALL clamp to 100 without error
4. IF limit or offset is invalid, THEN THE Platform SHALL return HTTP 422
5. WHEN offset >= total, THE Platform SHALL return empty items with correct total
6. THE Platform SHALL order by created_at DESC by default unless sort parameter is provided
7. IF sort value is not an allowed field, THEN THE Platform SHALL return HTTP 422
8. THE Platform SHALL maintain indexes on org_id and created_at on all paginated tables

---

### Requirement 23: Frontend Global Error Boundary

**Status:** PRESERVED from Rev 2 R23

**User Story:** As a user, I want the application to recover gracefully from errors without showing a blank screen.

#### Acceptance Criteria

1. THE Platform frontend SHALL wrap all page-level components in a React Error Boundary
2. WHEN an error is caught, THE Platform frontend SHALL display: heading, truncated error message (200 chars max), "Try Again" button, and "Go Home" link
3. THE error page SHALL render within 500ms without full page reload
4. IF in development, THE Platform frontend SHALL log error + component stack to console
5. IF in production, THE Platform frontend SHALL send error to the error reporting service within 5 seconds
6. THE error boundary SHALL isolate to page-content region — sidebar and topbar SHALL remain navigable

---

### Requirement 24: Simulation Mode Transparency

**Status:** PRESERVED from Rev 2 R24

**User Story:** As a user, I want to clearly know when a feature returns simulated data instead of real results.

#### Acceptance Criteria

1. WHEN a response is produced by a simulation provider, THE Platform SHALL include `{"simulation": true, "provider": "simulation"}` in response metadata
2. THE Platform frontend SHALL display a "Simulation Mode" badge on every UI component rendering simulated data
3. IF simulation handles a request in non-local environment, THEN THE Platform SHALL emit a warning log
4. WHEN GET /ready is called, THE Platform SHALL enumerate every provider in simulation mode from the Capability_Registry
5. WHEN environment is "production", THE Platform SHALL refuse to start if any critical provider (generation or training) is set to simulation


---

## PRIORITY TIER P2: AI-Native Platform

---

### Requirement 25: Brain + AIOS + Hermes Runtime Hierarchy

**Status:** AMENDED in Rev 4 — added user-specific sessions, per-user learning, memory isolation

**User Story:** As a content creator, I want to converse with an intelligent assistant (Brain) that orchestrates production tasks through natural language, backed by a canonical runtime (AIOS) with a planning layer (Hermes) that manages reasoning, tools, and orchestration — with my sessions and preferences kept separate from other users.

#### Acceptance Criteria

1. WHEN a POST /aios/v1/chat request is received with a message (1-10000 characters), THE Brain_Service SHALL stream the LLM response using SSE with token-by-token delivery, keepalive every 15 seconds, and close within 120 seconds of inactivity
2. THE Brain_Service SHALL be the customer-facing conversational interface providing user-visible modes, personality, and chat UX; AIOS SHALL be the canonical runtime and control plane handling authorization, policy, routing, approvals, memory, cost, and execution records; Hermes SHALL be the planning and orchestration layer inside AIOS handling reasoning, task decomposition, context retrieval, and tool selection
3. Execution_Adapters SHALL connect AIOS to external systems: LLMs, MCP servers, REST APIs, GPU compute providers, storage providers, and media systems — each adapter is independently replaceable
4. Hermes SHALL propose and coordinate actions; AIOS SHALL authorize, budget, execute, record, and govern those actions — Hermes has no direct execution authority
5. THE Platform SHALL select the LLM provider dynamically from a configured priority chain, attempting providers in order and selecting the first that responds to a health check within 5 seconds
6. IF the active provider fails mid-response, THEN THE Brain_Service SHALL failover to the next provider without user intervention
7. THE Brain_Service SHALL persist all conversations to Supabase scoped by org_id and user_id, storing max 200 messages per conversation and injecting the 20 most recent as context
8. WHEN a conversation includes a talent_id, THE Brain_Service SHALL retrieve the talent's Creative DNA and inject it into the system prompt; returning 404 if talent_id not in user's org
9. THE Brain_Service SHALL support modes: creative, prompt_engineer, story_assistant, production_advisor, research, image_analyzer, business_strategy — defaulting to "creative", with future modes addable without architectural change
10. IF all LLM providers are unavailable, THEN THE Brain_Service SHALL return HTTP 503 with code "LLM_UNAVAILABLE" within 15 seconds
11. THE Brain_Service SHALL enforce a per-request output token budget of 4096 tokens
12. IF the SSE connection is interrupted, THEN THE Brain_Service SHALL stop generation within 5 seconds to avoid unnecessary cost
13. Hermes SHALL maintain workspace knowledge (Talent graph, Creative DNA, project state, capability status) and inject relevant context automatically without user needing to reference it explicitly
14. Hermes SHALL never silently promote LLM output to canonical truth — all memory writes SHALL be explicit and auditable
15. Each user SHALL have separate Brain sessions scoped by org_id, user_id, conversation_id, and trust_domain — one user's session state SHALL NOT be visible to or influence another user's session
16. Users MAY maintain multiple resumable conversations within a workspace — conversations SHALL be independently addressable and switchable
17. THE Brain_Service MAY learn per-user preferences over time including: communication style preferences, workflow habits, response style, accepted/rejected recommendation patterns, quality/speed/cost trade-off preferences, tool preferences, and mode preferences
18. User-private Brain memory SHALL NOT be injected into another user's Brain session under any circumstance
19. Private conversation content SHALL NOT automatically become workspace-shared knowledge — promotion from private to workspace-shared SHALL require explicit user action or an approved promotion workflow
20. Users SHALL be able to inspect, correct, delete, or disable any durable user-level personalization that the Brain_Service has learned about them

---

### Requirement 26: Provider-Agnostic LLM Routing

**Status:** AMENDED in Rev 4 — added fallback preferences, privacy/data-location policies

**User Story:** As a platform operator, I want LLM requests routed to the best available provider based on task complexity, privacy, cost, and latency, with workspace-configurable fallback behavior and privacy restrictions, so that the system uses the optimal model for each request while respecting data sovereignty.

#### Acceptance Criteria

1. THE Platform SHALL support LLM providers: Ollama (local), LM Studio (local), OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter, and any OpenAI-compatible endpoint — configurable per workspace
2. THE Platform SHALL route LLM requests based on: provider health, task complexity (estimated from prompt length and tool requirements), privacy sensitivity (tenant config), cost budget, latency requirement (interactive vs batch), and model capabilities (tool use, vision, code)
3. WHEN the preferred provider is unavailable, THE Platform SHALL apply the workspace's configured fallback preference: AUTO (automatically route to next available alternate), ASK (present alternatives and request user confirmation before switching), or STRICT (fail or queue the request rather than using an alternate provider)
4. THE Platform SHALL support per-workspace provider preferences allowing users to set their preferred provider order and disable providers they don't want
5. THE Platform SHALL log every provider routing decision with: selected_provider, model, routing_reason, estimated_cost, and fallback_chain
6. THE Platform SHALL expose a GET /api/v1/llm/providers endpoint returning all configured providers with their current health status and capabilities
7. WHEN a workspace configures a custom OpenAI-compatible endpoint, THE Platform SHALL validate connectivity and model availability before accepting it as a provider option
8. THE Platform SHALL support workspace-level privacy and data-location policies that override fallback preferences: local models only, customer-managed compute only, approved LLM providers only, no external LLM for designated projects, approved storage only, Talent-specific provider restrictions, and project-specific privacy constraints
9. Privacy and data-location policies SHALL take precedence over fallback preference — if AUTO fallback would route to a provider disallowed by privacy policy, THE Platform SHALL treat the request as STRICT (fail/queue) rather than violating the policy

---

### Requirement 27: MCP and API Integration Fabric (Connections Hub)

**Status:** AMENDED in Rev 4 — added unified Connections Hub concept, OAuth-preferred flows

**User Story:** As a power user, I want to connect external tools, services, and AI assistants to my AI Studio workspace via a unified Connections Hub with OAuth-preferred flows, so that my workflow extends beyond the built-in capabilities without requiring technical configuration knowledge.

#### Acceptance Criteria

1. THE Platform SHALL expose an MCP server at /aios/v1/mcp providing tool definitions for: talent management, image generation, video generation, project management, asset search, scheduling, cost estimation, and Brain chat
2. THE Platform SHALL provide a unified Connections Hub as one surface for all connection types: AI/model providers, storage providers, publishing/social platforms, compute providers, developer tools, business applications, and MCP servers
3. THE Platform SHALL enforce that any LLM (regardless of provider) can invoke approved MCP tools through the same interface — tool use SHALL NOT be provider-specific
4. THE Platform SHALL require authentication for all connections using the appropriate mechanism for the integration type — OAuth SHALL be the preferred connection flow where supported by the target service
5. Ordinary users SHALL NOT need to configure: OAuth client IDs, client secrets, redirect URIs, bearer tokens, raw permission scopes, or MCP transport internals — these SHALL be managed by the Platform or Platform Operators
6. WHEN an API key connection is established, THE Platform SHALL: accept the key once, validate it against the target service, discover available capabilities, securely store it, and never redisplay the complete secret value
7. WHEN an MCP connection is established, THE Platform SHALL: discover available tools, display them in plain language, request explicit user permissions per tool, and ensure all invocations remain governed by the AIOS Governance_Boundary
8. THE Platform SHALL maintain a tool allowlist per workspace specifying which MCP tools are permitted, with deny-by-default for tools not explicitly allowed
9. THE Platform SHALL log all MCP tool invocations with: tool_name, invoking_provider, org_id, parameters (sanitized of secrets), result_status, and duration_ms
10. WHEN an MCP client attempts to invoke a tool not in the workspace allowlist, THE Platform SHALL reject with an error indicating the tool is not permitted
11. THE Platform SHALL support environment restrictions on MCP tools (e.g., "only in development", "requires approval in production")

---

### Requirement 28: MCP/Agent Tool Governance

**Status:** PRESERVED from Rev 2 R28 (strengthened by R59 single governance boundary)

**User Story:** As a security engineer, I want all agent and MCP tool operations governed by least-privilege credentials, approval gates, and full audit trails, so that automated actions cannot exceed their authority.

#### Acceptance Criteria

1. THE Platform SHALL issue tool-scoped credentials with explicit capability boundaries — a credential authorized for "read talent" SHALL NOT be usable for "delete talent"
2. THE Platform SHALL classify tools as: read-only (no approval needed), mutating (workspace policy determines approval), or destructive (always requires human approval)
3. WHEN a destructive tool is invoked (delete, publish, launch fleet, spend > threshold), THE Platform SHALL create a pending approval record and halt execution until human confirmation
4. THE Platform SHALL support credential expiration (max 24 hours for long-lived, max job duration + 5 minutes for job-scoped) and automatic rotation
5. THE Platform SHALL support immediate credential revocation via POST /api/v1/credentials/{id}/revoke, taking effect within 60 seconds
6. THE Platform SHALL maintain an audit log of all tool invocations, credential issuances, approvals, and rejections — queryable by org_id, tool_name, actor, and time range
7. THE Platform SHALL enforce per-workspace tool allowlists that limit which tools agents can invoke, updatable by workspace admin or owner only
8. IF a tool invocation fails permission checks, THEN THE Platform SHALL log the attempt and return a structured error indicating which permission was missing


---

### Requirement 29: Knowledge and Memory Architecture

**Status:** AMENDED in Rev 4 — added Brain memory layers, private-to-workspace promotion boundaries

**User Story:** As a content creator, I want the system to learn my preferences over time while clearly separating what the AI infers from what I've explicitly confirmed, with distinct memory layers ensuring private context stays private unless I promote it.

#### Acceptance Criteria

1. THE Platform SHALL distinguish and separately store the following memory layers: conversation/session context (ephemeral, max 200 per conversation), user-private memory (durable user preferences and learned patterns, scoped to individual user), workspace-shared knowledge (org-level settings, rules, shared Creative DNA, promoted knowledge), and platform-level learning (aggregated/de-identified signals for improving platform UX and routing — never proprietary creative content)
2. THE Platform SHALL persist Creative DNA per talent in Supabase with versioning — each update creates a new version preserving full history
3. WHEN a user provides positive feedback (rating 4-5) on a generation, THE Platform SHALL extract generation parameters and append them to the talent's Creative DNA within 5 seconds
4. THE Platform SHALL never overwrite prior Creative DNA versions; the latest version is authoritative
5. WHEN generating content for a talent, THE Platform SHALL inject that talent's Creative DNA into the system prompt as context
6. THE Platform SHALL explicitly mark all memory writes with their provenance classification: USER_CONFIRMED (user typed/confirmed it), OBSERVED (derived from explicit user actions such as feedback ratings or settings changes), IMPORTED (brought in from external source with user consent), INFERRED (suggested by LLM or derived from patterns, not confirmed), SUGGESTED (proposed to user but not yet accepted)
7. LLM-inferred knowledge SHALL NOT be promoted to durable memory without explicit user confirmation or a feedback signal — THE Platform SHALL never silently treat LLM output as canonical truth
8. THE Brain_Service SHALL NOT present INFERRED or SUGGESTED memory items to the user as though the user told the system — when surfacing inferred knowledge, THE Brain_Service SHALL explicitly indicate the source and confidence level
9. THE Platform SHALL scope all knowledge and memory records to org_id and reject cross-tenant access with HTTP 404
10. Supabase SHALL be the authoritative store for all durable memory — browser localStorage SHALL be used only as a temporary cache for session UX and SHALL NOT be treated as a source of truth for memory state
11. WHEN memory provenance conflicts exist (e.g., user-confirmed preference contradicts an inferred preference), THE Platform SHALL always prefer USER_CONFIRMED over OBSERVED over IMPORTED over INFERRED over SUGGESTED
12. Private conversation content SHALL NOT automatically become workspace-shared knowledge — Brain/Hermes SHALL require explicit user action or an approved promotion workflow before private information becomes workspace-shared
13. Users SHALL be able to inspect, correct, delete, or disable any durable user-level personalization through a dedicated memory management interface
14. User-private memory SHALL be scoped to the individual user and SHALL NOT be accessible to other workspace members, workspace admins, or Platform Operators (except under elevated support access per R97)

---

### Requirement 30: AIOS Governance, Approval Workflow, and Agent Autonomy

**Status:** AMENDED in Rev 4 — added autonomy profiles, delegated permissions, user-facing activity history

**User Story:** As a platform operator, I want ALL AI-initiated side effects — regardless of originating system — to pass through one canonical governance boundary with configurable autonomy levels, so that users can delegate appropriate authority to agents while maintaining safety.

#### Acceptance Criteria

1. THE Platform SHALL require user approval before: deleting data permanently, spending > $5 in a single action, launching 3+ workers, publishing to social media, cloning a voice, or any operation classified as "destructive" in the tool governance
2. WHEN approval is required, THE Platform SHALL create a pending_approval record in Supabase with action_type, estimated_cost_usd, parameters, requesting_user_id, and present it in Brain chat or UI notification within 2 seconds
3. WHEN approved via POST /aios/v1/approvals/{id}/approve, THE Platform SHALL execute within 10 seconds and record approval with timestamp and approver
4. WHEN rejected via POST /aios/v1/approvals/{id}/reject, THE Platform SHALL discard the action and record rejection with optional reason
5. IF an approval is not acted upon within 24 hours, THEN THE Platform SHALL expire it without executing
6. THE Platform SHALL allow configurable thresholds per-organization: auto_approve_generation, auto_approve_training, auto_approve_gpu_launch, require_publish_approval, require_delete_approval, max_auto_spend_usd (0.01-10000.00)
7. IF a user attempts to approve/reject a non-pending approval, THEN THE Platform SHALL return an error indicating it's already decided or expired
8. THE Governance_Boundary SHALL evaluate ALL of the following before permitting any AI-initiated side effect: identity, trust domain, tenant context, role, entitlement, consent (where applicable), safety policy, budget availability, resource ownership, action risk classification, required approvals, provider capability, and environment restrictions
9. THE Governance_Boundary SHALL be the ONE canonical enforcement point — Brain, Hermes, AIOS, MCP tool invocations, scheduled workflows, user-triggered agents, internal automation, and any future agent systems SHALL all pass through this same boundary
10. High-impact actions SHALL fail closed when policy, consent, authorization, or budget cannot be established — THE Platform SHALL NOT execute when governance evaluation is indeterminate
11. Read-only experiences MAY degrade safely (return partial data, indicate unavailability) rather than failing closed when governance evaluation encounters transient issues
12. THE Platform SHALL support agent autonomy profiles configurable per workspace: ADVISORY (recommend only, no mutations without explicit user instruction), ASSISTED (low-risk actions auto-execute, high-risk actions require user confirmation), and AUTONOMOUS_WITHIN_LIMITS (delegated actions execute within configured limits without per-action confirmation)
13. Mandatory safety, security, consent, budget, destructive-action, and legal controls SHALL be enforced regardless of the active autonomy profile — autonomy profiles control convenience delegation, not security bypass
14. Users and workspace admins MAY delegate specific action classes to Hermes — delegated permissions SHALL be: capability-specific (not blanket), connection-specific (scoped to named integrations), revocable (immediately), auditable (full trail), scoped by role (cannot exceed delegator's own permissions), and subject to the Governance_Boundary
15. THE Platform SHALL provide a user-facing agent activity history answering "What did Brain/Hermes do?" — including: recommendations made, tool calls executed, jobs dispatched, approvals requested/resolved, connections used, changes made, failures encountered, costs incurred, and outputs produced — presented as a human-readable activity feed separate from engineering/debug logs

---

### Requirement 31: Creative Recipes System

**Status:** PRESERVED from Rev 2 R31

**User Story:** As a content creator, I want proven generation configurations that I can select with one click.

#### Acceptance Criteria

1. THE Platform SHALL maintain a creative_recipes table with: id, org_id, name (1-100 chars), model, sampler, scheduler, cfg (1.0-30.0), steps (1-150), width, height, negative_prompt (max 2000 chars), loras (JSON array max 5), quality_score (0.0-5.0), success_rate (0.0-1.0), content_type, is_public
2. THE Platform SHALL seed 20 system recipes covering: portrait, product, landscape, editorial, video, social — at least 2 per type
3. WHEN generating with a recipe, THE Platform SHALL apply all recipe parameters to the workflow
4. WHEN a user rates a generation (1-5 stars), THE Platform SHALL update the recipe's quality_score as weighted moving average
5. THE Platform SHALL allow custom recipe creation (max 100 per org) via POST /api/v1/recipes
6. WHEN requesting recommendations, THE Platform SHALL return up to 10 recipes sorted by quality_score
7. IF a duplicate recipe name exists within the org, THEN THE Platform SHALL return an error


---

### Requirement 32: Repository Intelligence

**Status:** PRESERVED from Rev 2 R32

**User Story:** As a developer and as Hermes, I want automated understanding of the codebase including capability-to-code mapping, endpoint discovery, dead code, and architecture drift, so that the platform's self-awareness is always current.

#### Acceptance Criteria

1. THE Platform SHALL maintain a machine-readable capability-to-code mapping linking each Capability_Registry entry to: backend module(s), router file(s), frontend page(s), database table(s), and test file(s)
2. THE Platform SHALL support automated endpoint discovery by scanning router registrations and reporting: route path, HTTP method, auth requirement, and whether integration tests exist
3. THE Platform SHALL detect TODO/FIXME annotations in code and surface them as tracked technical debt items with file location and severity classification
4. THE Platform SHALL detect frontend pages that call API endpoints which either don't exist or always return mock data, flagging them as "UI without backend"
5. THE Platform SHALL detect duplicate functionality (same resource managed in multiple places) and flag for consolidation
6. THE Platform SHALL detect architecture drift: router files importing database models directly (layer violation), services with direct os.environ calls, or blocking I/O in async handlers
7. THE Platform SHALL make repository intelligence queryable by Hermes for answering developer questions about system state

---

### Requirement 33: Platform Operator Control Plane

**Status:** AMENDED in Rev 4 — replaced undifferentiated Super Admin with capability-based Platform Operator model

**User Story:** As a platform operator, I want a capability-based administration model with granular permission groups, so that operational authority is distributed appropriately without every operator having god-level access to all tenant data.

#### Acceptance Criteria

1. THE Platform Operator control plane SHALL display: platform health (all services), capability health (from Capability_Registry), compute provider health, storage provider health, LLM provider health, and deployment health
2. THE Platform Operator SHALL be able to view (read-only) any tenant's: capability usage, cost summary, job history, and configuration — subject to having the Tenant Support or Tenant Access Escalation capability
3. THE Platform Operator SHALL be able to configure platform-wide: compute modes available, storage modes available, adult content policy, safety policy overrides, maximum cost limits, feature flags, and simulation state overrides — subject to having the Platform Configuration capability
4. THE Platform Operator SHALL have access to: queue health (pending/stuck jobs), credential health (expired/leaked), deployment status, and takedown case management — subject to appropriate capability grants
5. THE Platform SHALL implement a capability-based Platform Operator model with the following capability groups: Platform Observe (read-only system health and metrics), Tenant Support (view tenant state for support purposes), Tenant Access Escalation (time-limited elevated access to tenant workspace with audit), Platform Configuration (system settings, feature flags, provider config), Financial Controls (billing, cost limits, plan overrides), Safety & Rights (content policy, takedowns, safety kernel config), Security Administration (credential management, RLS audit, threat response), Deployment/Operations (deploy, restart, infrastructure management), Release Management (release gates, version control, rollback authority), Destructive Platform Actions (purge, wipe, force-delete requiring dual approval), and Founder Authority (broadest capability set, compute availability state changes, platform-level architectural decisions)
6. A Platform Operator MAY receive any permitted subset of capability groups — THE Platform SHALL NOT require all operators to have equal access
7. THE Founder retains the broadest capability set without requiring every operator to have equivalent access
8. Platform Operators SHALL NOT receive unrestricted permanent access to private workspace creative content — elevated tenant access SHALL require: documented reason, identified operator, target workspace, permitted surfaces, configurable maximum duration (policy-determined), approval (for escalation), automatic expiration, and full audit trail
9. ALL Platform Operator actions SHALL be logged with full audit trail including actor, capability used, target tenant (if applicable), action, and timestamp
10. THE Platform Operator interface SHALL be accessible only via a dedicated route (/platform-admin) that returns 404 for users without any Platform Operator capability grants


---

## PRIORITY TIER P3: Advanced Creative Stack

---

### Requirement 34: Model and LoRA Import with Provenance and Promotion Gates

**Status:** AMENDED in Rev 3 — added promotion gates lifecycle

**User Story:** As a content creator, I want to import models and LoRAs from HuggingFace, CivitAI, or direct upload with tracked provenance, license terms, and a governed promotion lifecycle so that only verified, evaluated models reach production use.

#### Acceptance Criteria

1. THE Platform SHALL support model import from: HuggingFace (repo/model URL), CivitAI (model page URL), CivitAI.red (model page URL), direct URL (any HTTP-accessible safetensors/ckpt), and local file upload
2. WHEN a model is imported, THE Platform SHALL record provenance: source_url, source_platform, author, download_date, original_filename, file_hash (SHA-256), and file_size_bytes
3. THE Platform SHALL track license information per model: license_type (enum: permissive, non-commercial, commercial, custom, unknown), commercial_allowed (boolean), credit_required (boolean), modification_allowed (boolean), and license_url
4. THE Platform SHALL track model compatibility: base_model (flux, sdxl, sd15, wan), model_type (checkpoint, lora, vae, controlnet, upscaler, embedding), trigger_words (array of strings), and recommended_strength (for LoRAs)
5. WHEN a model with license commercial_allowed=false is used in a job tagged as commercial, THE Platform SHALL warn the user (not block) with a notice about license terms
6. THE Platform SHALL distinguish system models (readable by all) from user models (org-scoped only)
7. WHEN a model is imported, THE Platform SHALL verify it can be downloaded and validate the file format before recording it as "stored"
8. THE Platform SHALL enforce a model/LoRA promotion lifecycle: imported/trained → integrity_verified → evaluated → approved → active → deprecated → quarantined — models SHALL NOT automatically become approved production assets upon import or training completion
9. Promotion from one lifecycle state to the next MAY require (configurable per risk class): file integrity verification (SHA-256 match, format validation), compatibility verification (base model match, node compatibility), license compliance check, safety policy evaluation, quality evaluation (test generation with rating), and human approval for high-risk classes
10. THE Platform SHALL support quarantining a model at any lifecycle stage — quarantined models SHALL be immediately unavailable for generation, training, or publishing regardless of prior approval state
11. IF a DELETE request is received for a model, THE Platform SHALL verify admin/owner role, soft-delete, schedule storage deletion, and return HTTP 204
12. THE Platform SHALL log all promotion gate transitions with: model_id, from_state, to_state, actor, evidence (what checks passed), and timestamp

---

### Requirement 35: LoRA Training Pipeline

**Status:** PRESERVED from Rev 2 R35

**User Story:** As a content creator, I want to train custom LoRA models from my talent's photos on any available compute provider, with cost estimates and automatic talent association.

#### Acceptance Criteria

1. WHEN a POST /api/v1/training/jobs request is received with a talent_id (owned by requesting org) and 10-200 training images, THE Training_Pipeline SHALL create a job with status "queued" and return HTTP 202
2. THE Platform SHALL provide cost estimation via GET /api/v1/training/estimate before submission
3. WHEN the training provider is a real ComputeProvider, THE Training_Pipeline SHALL provision a GPU instance, upload the dataset, execute SimpleTuner, download results, and upload to StorageProvider
4. WHEN training completes successfully, THE Training_Pipeline SHALL create a model record with provenance (source: "user_trained", base_model, training parameters), link it to the talent, and update job status to "completed"
5. THE Platform SHALL support training cancellation via POST /api/v1/training/jobs/{id}/cancel for queued or running jobs
6. IF cancellation targets a completed/failed/cancelled job, THEN THE Platform SHALL return HTTP 409
7. THE Training_Pipeline SHALL enforce a 4-hour timeout; exceeding it terminates the instance and marks job as "failed"
8. THE Training_Pipeline SHALL terminate the compute instance in a finally block regardless of outcome
9. WHEN training_provider is "simulation", THE Training_Pipeline SHALL return progress with simulation=true without provisioning GPU
10. IF fewer than 10 or more than 200 images provided, THEN THE Platform SHALL reject with HTTP 422
11. WHEN training completes, THE Training_Pipeline SHALL automatically create a talent_loras association with type "identity", strength 0.7, always_on true

---

### Requirement 36: Video Generation Pipeline

**Status:** PRESERVED from Rev 2 R36

**User Story:** As a content creator, I want to generate short video clips from text or images using available compute.

#### Acceptance Criteria

1. WHEN a POST /api/v1/generate/video request is received with prompt (1-2000 chars) and optional reference_image, THE Platform SHALL create a video job and return HTTP 202
2. THE Platform SHALL support WAN 2.1 T2V and I2V workflows on ComfyUI workers with minimum 12 GB VRAM
3. WHEN complete, THE Platform SHALL upload to StorageProvider, create asset record, and update job to "completed"
4. THE Platform SHALL enforce max 10 seconds per generation request
5. IF the required model is not loaded on any worker, THEN THE Platform SHALL return HTTP 503 listing available models
6. THE Platform SHALL record video generation cost as a separate line item with job_type "video_generation"
7. IF worker fails to respond within 600 seconds, THEN THE Platform SHALL mark failed, terminate instance, do not retry

---

### Requirement 37: Voice and Audio Pipeline

**Status:** PRESERVED from Rev 2 R37

**User Story:** As a content creator, I want to assign voices to talent and generate speech from text.

#### Acceptance Criteria

1. WHEN a voice profile is created with a valid talent_id and provider (elevenlabs, moss-tts, simulation), THE Platform SHALL create the profile and return HTTP 201
2. THE Platform SHALL support providers in priority: ElevenLabs, MOSS-TTS, simulation
3. WHEN TTS is requested with text (1-5000 chars) and voice_profile_id, THE Platform SHALL generate and return audio as base64 or signed URL
4. IF the voice provider returns quota/key/availability error, THEN THE Platform SHALL return HTTP 502 with provider name and reason
5. IF text exceeds 5000 chars or is empty, THEN THE Platform SHALL return HTTP 422
6. WHEN complete, THE Platform SHALL persist as an asset linked to talent and project
7. WHILE provider is "simulation", THE Platform SHALL return 1-second silent audio with simulation metadata

---

### Requirement 38: Publishing Pipeline

**Status:** PRESERVED from Rev 2 R38

**User Story:** As a content creator, I want to schedule and publish content to social media platforms.

#### Acceptance Criteria

1. WHEN a post is scheduled with valid platform (tiktok, instagram, youtube), asset_id, and scheduled_at (min 5 minutes future), THE Platform SHALL create a scheduled post and return HTTP 201
2. IF scheduled_at is past or < 5 minutes from now, THEN THE Platform SHALL reject with HTTP 422
3. WHEN scheduled time arrives (±60 seconds), THE Publishing_Service SHALL dispatch and update status within 120 seconds
4. THE Platform SHALL support OAuth-based platform connections stored per org with status tracking
5. IF OAuth token expired on publish attempt, THEN THE Platform SHALL attempt refresh; if refresh fails, mark connection "disconnected" and post "failed"
6. WHEN DELETE targets a "scheduled" post, THE Platform SHALL cancel and return HTTP 204; targeting "published"/"failed" returns HTTP 409
7. WHEN publishing, THE Platform SHALL resize to platform specs (9:16 TikTok, 4:5 IG, 16:9 YouTube)
8. WHILE publishing_provider is "simulation", THE Platform SHALL record intent without API calls and set status "simulated"

---

### Requirement 39: Adult Content Policy and Safety Kernel

**Status:** PRESERVED from Rev 2 R39

**User Story:** As a platform operator, I want a three-layer content policy (mandatory safety, platform policy, workspace policy) that enables adult creative workflows for authorized fictional/consented characters while absolutely preventing illegal content.

#### Acceptance Criteria

1. THE Platform SHALL enforce a mandatory Safety_Kernel that cannot be disabled by any user, admin, or Platform Operator — covering exclusively: (a) sexual exploitation or sexual depiction involving minors (CSAM), (b) real-person nonconsensual intimate imagery where required authorization is absent, (c) content facilitating imminent physical harm, and (d) mandatory legal/takedown compliance obligations. Hosting provider Terms of Service compliance SHALL be enforced at the Platform Operator Creative Policy layer (Layer 2, configurable) rather than the non-disableable Safety Kernel, because hosting provider restrictions vary by infrastructure choice.
2. THE Safety_Kernel SHALL block generation, storage, and publishing of content matching Safety_Kernel rules regardless of all other policy settings — this is the one absolute constraint
3. THE Platform SHALL explicitly distinguish between: (a) fictional adult content involving fictional adult characters (including CNC themes, kink, and explicit content) — which is governed by Platform Operator Creative Policy (Layer 2) and Workspace Policy (Layer 3), NOT the Safety Kernel, and (b) real-person nonconsensual intimate imagery — which IS blocked by the Safety Kernel regardless of all other policy settings. Fictional adult characters cannot be victimized; real persons can be. The Safety Kernel protects real persons from non-consensual harm. Platform Operator Creative Policy governs creative fiction involving adult fictional characters.
4. THE Platform SHALL support a Platform Operator Creative Policy layer (platform-wide) that sets default content boundaries for all workspaces: allowed_content_ratings (enum: SFW_ONLY, MATURE, ADULT), prohibited_content_categories (configurable list), and required_warnings
5. THE Platform SHALL support a Workspace Policy layer that can be EQUAL TO or STRICTER THAN the platform policy, but never more permissive — attempting to set a workspace policy more permissive than platform policy SHALL fail with HTTP 422
6. WHEN adult content generation is attempted for a talent, THE Platform SHALL evaluate based on identity_classification:
  - IF FICTIONAL: verify (a) workspace policy allows adult content AND (b) talent has adult_status=VERIFIED_18_PLUS (creator attestation that the character is an adult). No consent record required for fictional characters.
  - IF REAL_PERSON_SELF: verify (a) workspace policy allows adult content AND (b) talent has adult_status=VERIFIED_18_PLUS AND (c) talent has consent scope 'adult_content' granted by the real person themselves.
  - IF REAL_PERSON_AUTHORIZED: verify (a) workspace policy allows adult content AND (b) talent has adult_status=VERIFIED_18_PLUS AND (c) talent has consent scope 'adult_content' granted by an authorized representative AND (d) the consent record includes explicit adult-content authorization with grantor identity and evidence.
7. IF any applicable condition in criterion 6 is not met for the talent's identity_classification, THEN THE Platform SHALL reject with HTTP 403 and a message identifying specifically which condition failed
8. THE Platform SHALL tag all generated content with a content_rating derived from the generation parameters and prompt analysis, stored as asset metadata
9. THE Safety_Kernel SHALL operate at generation time (before ComfyUI dispatch), storage time (before B2 upload), and publishing time (before social API call) — never only at one stage

---

### Requirement 40: Rights and Takedown Center

**Status:** PRESERVED from Rev 2 R40

**User Story:** As a platform operator, I want to receive, investigate, and act on content rights complaints and takedown requests, so that the platform respects intellectual property and legal obligations.

#### Acceptance Criteria

1. THE Platform SHALL provide a report intake endpoint (POST /api/v1/takedowns) accepting: reporter_email, content_url_or_id, complaint_type (enum: copyright, trademark, likeness, privacy, illegal, other), description (max 5000 chars), and optional evidence_urls
2. WHEN a takedown report is received, THE Platform SHALL create a case record with status "received" and assign a unique case_id, returning HTTP 201
3. THE Platform SHALL support case status transitions: received → investigating → action_taken → resolved, and received → rejected → resolved (with reason)
4. WHEN a takedown action is approved (by Platform Operator with Safety & Rights capability or designated rights manager), THE Platform SHALL: soft-delete the content from the database, remove it from storage provider, add a perceptual hash to the block list, and block the asset from republishing
5. THE Platform SHALL support legal holds that prevent permanent deletion of content even when deletion lifecycle rules would otherwise purge it
6. THE Platform SHALL maintain a perceptual hash blocklist; WHEN new content is generated or uploaded, THE Platform SHALL compare against the blocklist and reject matches with HTTP 403 and code "CONTENT_BLOCKED"
7. THE Platform SHALL support appeals: a user whose content was removed can submit an appeal (POST /api/v1/takedowns/{case_id}/appeal) which reopens the case for review
8. THE Platform SHALL log all takedown actions with: case_id, actor, action, affected_asset_ids, timestamp for legal compliance and auditability
9. THE Platform SHALL maintain rights-case action history as an append-oriented event log rather than a single mutable record — each action SHALL preserve: actor, action_type, timestamp, reason, evidence references, and prior/new status. This enables tamper-evident audit reconstruction.


---

## PRIORITY TIER P4: Scale and Advanced Operations

---

### Requirement 41: Entitlements and Plans

**Status:** AMENDED in Rev 4 — added workload privacy restrictions, plan isolation guarantee

**User Story:** As a platform operator, I want subscription plans that gate features, compute quotas, storage, and capabilities, so that the business model is enforceable without compromising security invariants.

#### Acceptance Criteria

1. THE Platform SHALL maintain a plans table defining: plan_id, name, tier (free, starter, pro, enterprise), and a JSON entitlements object specifying limits for each gated resource
2. THE Platform SHALL enforce entitlements for: max_talent (per org), max_projects (per org), max_storage_gb, monthly_compute_budget_usd, gpu_quota_hours_monthly, max_team_members, allowed_compute_modes (PLATFORM_MANAGED, CUSTOMER_MANAGED, HYBRID), allowed_storage_providers, api_access (boolean), mcp_access (boolean), adult_content_eligible (boolean), max_concurrent_jobs
3. WHEN an operation would exceed a plan entitlement, THE Platform SHALL reject with HTTP 402 and code "ENTITLEMENT_EXCEEDED" with a message indicating the limit and the user's current usage
4. THE Platform SHALL provide a GET /api/v1/billing/usage endpoint returning current usage vs entitlement limits for the authenticated org
5. THE Platform SHALL support plan changes (upgrades/downgrades) with immediate effect for upgrades and end-of-billing-period effect for downgrades
6. THE Platform SHALL support a "custom" plan type for enterprise customers with individually negotiated limits
7. THE Platform Operator (with Financial Controls capability) SHALL be able to override entitlements for specific organizations (for trials, partnerships, or debugging)
8. Plan tier MAY affect: generation quality tiers, model class availability, queue priority, concurrency limits, and cost limits — but SHALL NEVER weaken tenant isolation, consent enforcement, safety kernel behavior, or truthfulness of system responses regardless of plan
9. THE Platform SHALL support per-workspace workload privacy and provider restrictions as part of the entitlement model: local models only, customer-managed compute only, approved LLM providers only, no external LLM for designated projects, approved storage only, Talent-specific restrictions, and project-specific privacy — these restrictions SHALL be respected by Brain/Hermes, LLM routing, and all execution paths

---

### Requirement 42: Data Lifecycle and Disaster Recovery

**Status:** PRESERVED from Rev 2 R42

**User Story:** As a platform operator, I want defined retention periods, soft-delete with restore windows, permanent purge schedules, and verified backups, so that data management is predictable and recoverable.

#### Acceptance Criteria

1. THE Platform SHALL define retention periods for each data type: generated assets (indefinite unless deleted by user), job records (365 days after completion), cost records (indefinite for billing), conversation messages (365 days), audit logs (730 days minimum), training datasets (until talent deleted + 30 day grace)

NOTE: Specific retention durations stated above are INITIAL defaults subject to Legal/Security/Privacy specialist review. The architecture SHALL support configurable retention policies. Exact periods for safety events, consent records, and audit logs may be adjusted upon specialist approval without architectural change.

2. THE Platform SHALL implement soft-delete for all user-facing resources (talent, assets, projects, models, recipes) with a 30-day restore window
3. AFTER the 30-day restore window, THE Platform SHALL permanently purge the database record and schedule storage object deletion — unless a legal hold is active on the resource
4. THE Platform SHALL support legal holds (per asset, per talent, or per org) that prevent permanent deletion regardless of retention policy
5. THE Platform SHALL maintain database backups with RPO (Recovery Point Objective) of 24 hours and RTO (Recovery Time Objective) of 4 hours
6. THE Platform SHALL include a backup verification process that restores from backup to a test environment and runs schema validation at least monthly
7. WHEN a user requests data export (GDPR Article 15), THE Platform SHALL provide all their org's data in a machine-readable format within 30 days
8. WHEN a user requests account deletion (GDPR Article 17), THE Platform SHALL purge all personal data within 30 days while preserving anonymized aggregate records needed for platform operation

---

### Requirement 43: Product Analytics and Social Performance Intelligence

**Status:** AMENDED in Rev 4 — expanded to include Social Performance Analytics and Market Intelligence

**User Story:** As a product owner, I want analytics on user activation, feature usage, success rates, and social performance, so that I can make data-driven product and content decisions.

#### Acceptance Criteria

1. THE Platform SHALL track and report: onboarding_completion_rate, time_to_first_talent, time_to_first_generation, generation_success_rate, generation_failure_rate_by_reason, average_queue_wait_seconds, average_generation_duration_seconds, cost_per_output_by_type, weekly_active_users, monthly_active_users
2. THE Platform SHALL track feature usage: which pages are visited (page_view events), which actions are taken (generation, training, publishing), and which features are never used
3. THE Platform SHALL NOT track or store personally identifiable information in analytics — all metrics SHALL be aggregated at the org level minimum
4. THE Platform SHALL expose analytics to workspace owners via GET /api/v1/analytics/workspace showing their org's usage patterns
5. THE Platform Operator (with Platform Observe capability) SHALL have access to platform-wide analytics showing aggregate metrics across all tenants
6. THE Platform SHALL store analytics events in a dedicated analytics schema, separate from operational data, to avoid performance impact on production queries
7. THE Platform SHALL retrieve social performance analytics from connected platforms (Instagram, TikTok, YouTube, future platforms) where workspace has authorized connections, storing normalized metrics associated with: workspace, account, post, asset, Talent, project, and timestamp
8. THE Platform SHALL normalize metrics across platforms while preserving original platform-specific definitions — cross-platform comparison views SHALL be available (TikTok vs IG performance, posts, campaigns, Talent, formats, time periods)
9. THE Platform SHALL support audience growth trend analysis: follower growth, engagement trend, reach trend, and content velocity — with historical metric snapshots for time-series analysis
10. Brain/Hermes SHALL be able to answer "what performed best?" and similar growth questions using the workspace's authorized analytics data
11. THE Platform SHALL distinguish data provenance classifications: FIRST_PARTY_CONNECTED (from authorized platform connections), PUBLIC_PLATFORM_DATA (publicly available metrics), THIRD_PARTY_DATA (from approved intelligence providers), USER_IMPORTED (manually provided by user), and DERIVED_ANALYSIS (calculated from other sources)
12. Missing metrics SHALL be represented as UNAVAILABLE — THE Platform SHALL NOT fabricate or estimate values where data is absent
13. Recommendations from analytics SHALL explicitly distinguish: observed fact, statistical pattern, AI interpretation, and suggested experiment — never presenting interpretations as facts
14. THE Platform SHALL support creative experiments and performance comparison against baseline for content strategy optimization

---

### Requirement 44: Local Connector (Future Architecture)

**Status:** PRESERVED from Rev 2 R44 — architecture definition only, not implementation

**User Story:** As a power user, I want to connect my local GPU, ComfyUI, LM Studio, Ollama, and local files to AI Studio, so that I can use my own hardware for generation and inference.

#### Acceptance Criteria

1. THE Platform SHALL define the Local_Connector protocol as an outbound-only authenticated connection from the user's machine to AI Studio — the Platform SHALL NOT require inbound network access to the user's machine
2. THE Local_Connector SHALL support registering local resources: GPU (with VRAM, CUDA version), ComfyUI instance (with loaded models), LM Studio/Ollama (with available models), local file paths, and NAS mounts
3. THE Platform SHALL require explicit user permission for each resource type the Local_Connector can access — no implicit access to local files or hardware
4. THE Local_Connector SHALL authenticate to AI Studio using a workspace-scoped API key with limited permissions (job execution, result upload only)
5. THE Platform SHALL treat Local_Connector compute as CUSTOMER_MANAGED mode, subject to the same job dispatch and result handling as cloud compute
6. THE Local_Connector architecture SHALL support future implementation without changes to the core Platform API — it is an additional ComputeProvider and StorageProvider implementation
7. THE Platform SHALL NOT implement the Local_Connector in this production revamp phase — this requirement defines the interface contract only


---

## CROSS-CUTTING REQUIREMENTS (All Tiers)

---

### Requirement 45: Structured Logging and Observability

**Status:** PRESERVED from Rev 2 R45

**User Story:** As a platform operator, I want structured JSON logs with request correlation IDs for full traceability.

#### Acceptance Criteria

1. THE Platform SHALL emit structured JSON logs with: timestamp, level, logger, message, request_id; and WHERE authenticated: org_id, user_id
2. THE Platform SHALL generate a unique request_id (UUIDv4) per request, return it in X-Request-ID header, and propagate through all downstream operations
3. THE Platform SHALL never log: API keys, tokens, passwords, service role keys, or raw credential request bodies
4. WHEN a job transitions state, THE Platform SHALL emit info-level log with: job_id, org_id, previous_status, new_status, provider, and for terminal states: duration_seconds, cost_usd
5. WHEN an external service call fails, THE Platform SHALL emit warning-level log with: service_name, endpoint_path, http_status, latency_ms, retry_attempt, request_id
6. THE Platform SHALL expose GET /api/v1/health requiring no auth, returning 200 with `{"status": "ok"}` within 200ms normally, or 503 with `{"status": "degraded"}` if critical deps unreachable

---

### Requirement 46: CORS and Security Headers

**Status:** PRESERVED from Rev 2 R46

**User Story:** As a security engineer, I want CORS and security headers properly configured.

#### Acceptance Criteria

1. THE Platform SHALL set CORS allow_origins from ALLOWED_ORIGINS env var (comma-separated); if it contains "*", refuse to start
2. THE Platform SHALL set allow_methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
3. THE Platform SHALL set allow_headers: Authorization, Content-Type, Accept, X-Requested-With, X-Request-ID
4. THE Platform SHALL include on all responses: X-Content-Type-Options: nosniff, X-Frame-Options: DENY; in production also: Strict-Transport-Security: max-age=31536000; includeSubDomains
5. THE Platform SHALL never expose internal service hostnames or IPs in any response
6. WHEN a request from an unlisted origin arrives, THE Platform SHALL omit Access-Control-Allow-* headers

---

### Requirement 47: Rate Limiting

**Status:** PRESERVED from Rev 2 R47

**User Story:** As a platform operator, I want per-tenant rate limiting so no org overwhelms the system.

#### Acceptance Criteria

1. THE Platform SHALL enforce per-tenant sliding-window (60s) limits: 100 req/window standard, 10 req/window GPU jobs, 20 req/window uploads
2. WHEN exceeded, THE Platform SHALL return HTTP 429 with Retry-After header (1-60 seconds)
3. THE Platform SHALL use Redis as primary; if unavailable, fall back to in-memory with degraded-mode warning
4. THE Platform SHALL exempt: GET /health, GET /ready, OPTIONS preflight
5. WHEN violated, THE Platform SHALL log: org_id, endpoint, request_count, configured_limit

---

### Requirement 48: Webhook Security

**Status:** PRESERVED from Rev 2 R48

**User Story:** As a platform operator, I want all incoming webhooks verified via HMAC.

#### Acceptance Criteria

1. WHEN a webhook arrives, THE Platform SHALL compute HMAC-SHA256 of raw body using webhook_secret and compare to X-Signature-256 header
2. IF signature missing or mismatch, THEN return HTTP 401 and log the attempt
3. THE Platform SHALL use constant-time comparison (secrets.compare_digest)
4. IF payload timestamp > 300 seconds old, THEN reject with HTTP 401
5. THE Platform SHALL process body only after signature and timestamp validation both pass

---

### Requirement 49: Frontend Accessibility

**Status:** PRESERVED from Rev 2 R49

**User Story:** As a user with assistive technology, I want the app navigable via keyboard and screen reader.

#### Acceptance Criteria

1. THE Platform frontend SHALL include aria-label on every interactive element without visible text
2. THE Platform frontend SHALL support keyboard navigation: Tab/Shift+Tab, Enter/Space to activate, Escape to close modals
3. THE Platform frontend SHALL display visible focus indicators (min 2px, 3:1 contrast)
4. THE Platform frontend SHALL use semantic HTML (nav, main, header, section, article)
5. THE Platform frontend SHALL meet WCAG 2.1 AA contrast ratios: 4.5:1 for normal text, 3:1 for large text
6. WHEN dynamic content changes, THE Platform frontend SHALL announce via aria-live regions (polite for updates, assertive for errors)

---

### Requirement 50: Dead Code and Simulation Cleanup

**Status:** PRESERVED from Rev 2 R50

**User Story:** As a developer, I want dead code identified and simulation inventory maintained.

#### Acceptance Criteria

1. THE Platform SHALL annotate every endpoint returning only mock data with @deprecated and target removal date
2. THE Platform SHALL remove all window global assignments for cross-component state
3. THE Platform frontend build SHALL strip console.log/debug/info from production bundles
4. IF duplicate functionality exists across pages/modules, THEN THE Platform SHALL consolidate
5. THE Platform SHALL maintain SIMULATION_INVENTORY.md listing every simulated feature with: name, behavior, target provider, activation variable, target milestone
6. IF a page calls a non-existent or mock-only endpoint, THEN THE Platform SHALL implement it or hide the UI behind a feature flag

---

### Requirement 51: Testing Infrastructure (Risk-Ordered)

**Status:** PRESERVED from Rev 2 R51

**User Story:** As a developer, I want automated tests covering critical paths in risk order, so that the most dangerous regressions are caught first.

#### Acceptance Criteria

1. THE Platform SHALL prioritize test creation in this risk order: (1) tenant isolation, (2) authentication, (3) authorization, (4) safety kernel, (5) consent enforcement, (6) destructive actions, (7) cost controls, (8) credential isolation, (9) job idempotency, (10) provider failure handling, (11) migrations, (12) deployment, (13) user journeys
2. THE Platform SHALL maintain unit tests (tests/unit/) for every service method, mocking all I/O
3. THE Platform SHALL maintain integration tests (tests/integration/) for every endpoint testing: happy path, unauthenticated (401), cross-tenant (404), invalid input (422)
4. THE Platform SHALL achieve minimum 80% line coverage on new/modified code
5. THE Platform SHALL include at least one test per mutation endpoint verifying unauthenticated returns 401
6. THE Platform SHALL include at least one test per tenant-scoped endpoint verifying cross-tenant returns 404 with no data leakage
7. THE Platform SHALL include round-trip serialization tests for every Pydantic response schema
8. THE Platform SHALL include RLS tests (one per Category A table) proving cross-tenant access is denied at the database level
9. THE Platform frontend SHALL include Playwright E2E tests for: login, create talent, submit generation, view asset — each completing within 60 seconds

---

### Requirement 52: Layered Architecture Compliance

**Status:** PRESERVED from Rev 2 R52

**User Story:** As a developer, I want all code following Router → Service → Repository layers.

#### Acceptance Criteria

1. THE Platform SHALL organize into: routers (HTTP concerns), services (business logic), repositories (data access)
2. Router modules SHALL never import SQLAlchemy models or execute queries directly
3. Service classes SHALL receive dependencies via constructor injection
4. THE Platform SHALL not define business logic inline within router endpoint bodies
5. WHEN a file exceeds 300 lines, THE Platform SHALL split it into focused modules
6. THE Platform SHALL use absolute imports exclusively — no relative imports

---

### Requirement 53: Design System and Visual Standards

**Status:** PRESERVED from Rev 2 R53

**User Story:** As a frontend developer, I want a consistent design system with semantic tokens, risk-tier confirmations, and responsive behavior, so that the UI is cohesive and accessible.

#### Acceptance Criteria

1. THE Platform frontend SHALL use the existing semantic design token system for all colors, spacing, typography, and component styling — no raw hex/rgb values outside of token definitions
2. THE Platform frontend SHALL implement risk-tier confirmation dialogs: low-risk actions (no confirmation), medium-risk (single confirmation), high-risk (explicit confirmation with action description and cost), destructive (type-to-confirm pattern)
3. THE Platform frontend SHALL be responsive: full functionality at 1440px+, usable at 1024px, mobile-navigable at 375px (sidebar collapses, content reflows)
4. THE Platform frontend SHALL support visual regression testing using screenshot comparison on key pages to detect unintended style changes
5. THE Platform frontend SHALL maintain a component library (shadcn/ui based) with consistent patterns for: cards, modals, forms, tables, empty states, loading skeletons, badges, and notifications
6. THE Platform frontend SHALL use the established dark navy (#0a0a1a) + purple (#7c3aed) theme consistently without introducing competing color systems

---

### Requirement 54: Kiro/Code Execution Workflow

**Status:** PRESERVED from Rev 2 R54

**User Story:** As a developer, I want clear boundaries for automated code changes: Hermes may inspect, draft, and prepare changes, but execution through Kiro requires independent review.

#### Acceptance Criteria

1. THE Platform SHALL define the Hermes→Kiro workflow as: Hermes identifies issue → Hermes drafts fix/feature → Hermes submits to Kiro for execution → Kiro executes → Hermes inspects results → Human reviews
2. Kiro SHALL NOT approve its own completion — all Kiro-executed changes require either human review or Hermes verification that the change meets acceptance criteria
3. Hermes SHALL have read access to: all source code, test results, build logs, deployment status, and capability registry — enabling it to identify issues and draft solutions
4. Hermes SHALL NOT have direct write access to production databases, deployed infrastructure, or live service configuration without going through the defined change workflow
5. THE Platform SHALL log all Hermes-initiated code change requests with: proposed_change, reasoning, affected_files, and outcome (accepted/rejected/modified)
6. IF Hermes proposes a change that affects security-critical code (auth, RLS, credentials, tenant isolation), THEN THE Platform SHALL require explicit human approval before Kiro execution

---

### Requirement 55: Production Readiness Gate

**Status:** PRESERVED from Rev 2 R55 (extended by R82 Independent Verification and R83 Final Production Gate)

**User Story:** As a platform operator, I want a clear definition of what makes any feature production-ready, so that we never ship incomplete capabilities as if they were complete.

#### Acceptance Criteria

1. THE Platform SHALL classify a feature as production-ready ONLY when ALL of the following are true: (a) CI passes (lint + type check + tests), (b) integration tests cover happy path + error cases, (c) tenant isolation verified by test, (d) auth required on all endpoints, (e) Pydantic validation on all inputs, (f) structured error responses, (g) capability registry shows PRODUCTION, (h) no simulation provider in the critical path
2. THE Platform SHALL classify a feature as PARTIAL when it functions correctly but one or more non-critical production criteria are not yet met (e.g., limited error handling, missing edge case tests)
3. THE Platform SHALL classify a feature as SIMULATED when the UI exists and the backend responds, but real provider integration is not connected
4. THE Platform SHALL NOT expose features classified below PARTIAL to end users without a visible indicator of their status
5. THE Capability_Registry SHALL be the authoritative source for feature classification, updated as features progress through implementation
6. WHEN a feature transitions to PRODUCTION classification, THE Platform SHALL record the date, verifying actor, and evidence (passing CI run ID, test coverage report)


---

## NEW REQUIREMENTS — REVISION 3 AMENDMENTS

---

## PRIORITY TIER P0-A: Runtime Architecture and Trust (New)

---

### Requirement 56: Canonical AI Runtime Hierarchy

**Status:** NEW in Rev 3

**User Story:** As a platform architect, I want a clearly defined runtime hierarchy separating user-facing experience, runtime control, planning/orchestration, and execution, so that each layer has explicit responsibilities and no layer overreaches its authority.

#### Acceptance Criteria

1. THE Platform SHALL define Brain_Service as the customer-facing conversational experience responsible for: user-visible modes, personality, chat UX, streaming responses, and conversation state — Brain SHALL NOT directly execute side effects or make authorization decisions
2. THE Platform SHALL define AIOS as the canonical runtime and control plane responsible for: authorization enforcement, policy evaluation, routing decisions, approval workflows, memory persistence, cost accounting, execution record-keeping, and governance boundary enforcement
3. THE Platform SHALL define Hermes as the planning and orchestration layer inside AIOS responsible for: reasoning over context, task decomposition, context retrieval from knowledge/memory, tool selection, and action proposal — Hermes proposes and coordinates but does NOT authorize or execute
4. THE Platform SHALL define Execution_Adapters as the connectors between AIOS and external systems: LLM providers, MCP servers, REST APIs, GPU compute providers, storage providers, and media systems — each adapter is independently replaceable without affecting the layers above
5. THE runtime hierarchy SHALL enforce: Hermes proposes → AIOS authorizes/budgets/executes/records/governs → Execution_Adapters perform the actual work → results flow back through AIOS for recording
6. THE Brain_Service SHALL retain and support user-facing modes (Creative, Prompt Engineer, Story Assistant, Production Advisor, Research, Image Analyzer, Business/Strategy) with future modes addable without architectural change to AIOS or Hermes
7. THE Platform SHALL NOT allow any component to bypass the AIOS layer for side-effecting operations — Brain cannot directly invoke tools, Hermes cannot directly execute, and Execution_Adapters cannot self-authorize

---

### Requirement 57: Trust-Domain Separation

**Status:** AMENDED in Rev 4 — added authorized relationship model for Brain/Hermes

**User Story:** As a security architect, I want explicit trust domains that prevent internal platform knowledge, founder strategy, and infrastructure secrets from leaking into customer-facing AI sessions, with Brain/Hermes understanding the authorized relationships between workspace entities.

#### Acceptance Criteria

1. THE Platform SHALL define and enforce the following trust domains: FOUNDER_PRIVATE (executive strategy, internal runbooks, infrastructure secrets), PLATFORM_ADMIN (system configuration, cross-tenant views, operational tooling), WORKSPACE_ADMIN (workspace settings, team management, billing), CUSTOMER_USER (creative work, generation, training, publishing), SERVICE_WORKER (job execution, result upload, health reporting), SYSTEM_AUTOMATION (scheduled tasks, maintenance, monitoring)
2. Each trust domain SHALL resolve to separately authorized: knowledge sources (what information is accessible), memory scopes (what memory can be read/written), system instructions (what prompts/context are injected), tools (what actions can be invoked), credentials (what secrets are available), and approval capabilities (what can be approved/rejected)
3. THE Platform SHALL enforce that FOUNDER_PRIVATE domain content (founder strategy documents, executive communications, infrastructure secrets, internal runbooks, platform financial data) SHALL NEVER become visible in customer-facing Brain sessions or be injectable into customer-facing LLM context
4. THE Platform SHALL enforce that PLATFORM_ADMIN domain content (cross-tenant data, system configuration, operational secrets) SHALL NOT be accessible to CUSTOMER_USER or SERVICE_WORKER domains
5. WHEN Hermes retrieves context for a Brain session, THE Platform SHALL filter retrieved knowledge and memory through the requesting user's trust domain — only content authorized for that domain SHALL be injected into the LLM context
6. THE Platform SHALL log trust domain boundary crossings (e.g., Platform Operator viewing tenant data) with full audit trail
7. IF a trust domain boundary is violated (content from a higher-privilege domain appears in a lower-privilege context), THE Platform SHALL treat this as a P0 security incident
8. Brain/Hermes SHALL understand authorized relationships between workspace entities: user, workspace, project, Talent, assets, connections, models, workflows, decisions, preferences, and approvals — enabling contextually relevant responses without leaking cross-entity data the requesting user is not authorized to see
9. This requirement SHALL NOT prescribe the database implementation for the relationship model — design.md SHALL determine the appropriate storage and query patterns

NOTE: Trust domains are security compartments, not a simple visibility hierarchy. Being a Platform Operator does NOT automatically inject arbitrary tenant creative content into Brain/Hermes context. Data access requires explicit authorization (role + capability + support session + resource scope + governance decision).

---

### Requirement 58: Brain/Hermes Application Context

**Status:** NEW in Rev 3

**User Story:** As a content creator, I want the Brain to understand what I'm currently working on (page, project, talent, active job) without me having to explain it every time, so that AI responses are contextually relevant.

#### Acceptance Criteria

1. THE Platform SHALL define an Application_Context envelope containing: current workspace (org_id, workspace settings), current page/route, active project (if any), selected Talent (if any), selected assets (if any), active job (if any), active Brain mode, available capabilities (from Capability_Registry), current workflow state, and relevant UI state
2. THE Platform frontend SHALL transmit Application_Context to the Brain_Service with each chat request — the context SHALL be structured, typed, and version-identified
3. THE Platform SHALL ensure that authorization fields (org_id, user_id, role, trust_domain) and tenant identity within the Application_Context are ALWAYS server-derived from the validated JWT and org_members lookup — these fields SHALL NEVER be trusted from browser-supplied context
4. THE Platform SHALL validate all Application_Context references (project_id, talent_id, asset_ids) against the authenticated user's org_id before injecting into Hermes context — invalid or cross-tenant references SHALL be silently dropped with a warning log
5. WHEN Brain receives a message with Application_Context, Hermes SHALL use the context to: retrieve relevant Creative DNA, scope knowledge queries, pre-load relevant tools, and tailor response personality to the active mode
6. THE Application_Context SHALL be treated as ephemeral session state — it does NOT constitute durable memory and SHALL NOT be persisted as user preferences without explicit confirmation


---

### Requirement 59: Mandatory Agent Governance Boundary

**Status:** NEW in Rev 3

**User Story:** As a security engineer, I want ONE canonical governance enforcement point that ALL AI-initiated side effects must pass through, regardless of their origin, so that no automated action can bypass policy evaluation.

#### Acceptance Criteria

1. EVERY AI-initiated side effect — from Brain, Hermes, AIOS, MCP tool invocations, scheduled workflows, user-triggered agents, internal automation, and any future agent systems — SHALL pass through ONE canonical Governance_Boundary before execution
2. THE Governance_Boundary SHALL evaluate ALL of the following before permitting execution: identity (who/what is requesting), trust domain (what privilege level), tenant context (which org), role (what workspace permissions), entitlement (what plan allows), consent (where applicable for talent/content), safety policy (content restrictions), budget availability (can the org afford it), resource ownership (does the actor own the target), action risk classification (read/mutate/destructive), required approvals (does policy require human confirmation), provider capability (can the target system perform it), and environment restrictions (prod/staging/dev constraints)
3. High-impact actions SHALL fail closed when policy, consent, authorization, or budget cannot be established — THE Platform SHALL NOT execute when governance evaluation is indeterminate or when required evidence is missing
4. Read-only experiences MAY degrade safely (return partial data, indicate unavailability, show cached results) rather than failing closed when governance evaluation encounters transient issues
5. THE Governance_Boundary SHALL be implemented as a single, auditable code path — not distributed across multiple middleware layers that could be independently bypassed or inconsistently configured
6. THE Platform SHALL log every Governance_Boundary evaluation with: request_id, identity, trust_domain, action_type, risk_classification, evaluation_result (permitted/denied/approval_required), and denial_reason (if applicable)
7. IF a new agent system, automation, or tool integration is added to the platform, it SHALL be required to route through the existing Governance_Boundary — the boundary is not optional for new subsystems

---

### Requirement 60: Immutable Generation Context Packages

**Status:** NEW in Rev 3

**User Story:** As a content creator, I want every generation job to reference an exact, versioned snapshot of all inputs used, so that I can reproduce results and understand what produced any given output.

#### Acceptance Criteria

1. BEFORE dispatching a generation job to a compute worker, AIOS SHALL resolve the approved generation context into a versioned, immutable Generation_Context_Package containing: Talent record (with identity classification and consent state), Creative DNA version, Object DNA (if applicable), source assets (references with checksums), wardrobe/product/location context, model/LoRA selections (with versions and strengths), prompt instructions (positive and negative), consent verification result, safety policy evaluation result, workflow template (with version), and project constraints
2. THE Generation_Context_Package SHALL be assigned a unique version identifier and stored in Supabase — it SHALL NOT be modified after creation
3. THE job record SHALL reference the exact Generation_Context_Package version used — enabling full reproducibility and audit of what inputs produced what output
4. ALL generation surfaces (Brain-initiated, API-initiated, MCP-initiated, scheduled, batch) SHALL use the same canonical Generation_Context_Package boundary — no generation path may bypass context resolution
5. IF any referenced resource in the context package is unavailable, deleted, or has changed consent/policy status since resolution, THEN THE Platform SHALL reject the job with an error identifying the stale reference rather than proceeding with potentially invalid context
6. THE Platform SHALL support context package comparison: given two package versions, show what changed (model version, DNA version, prompt, etc.)

---

### Requirement 61: Training Dataset Manifests

**Status:** NEW in Rev 3

**User Story:** As a content creator, I want training jobs to reference an immutable manifest of exactly which files were used, so that training is reproducible and consent/provenance is traceable per-file.

#### Acceptance Criteria

1. BEFORE dispatching a training job to a compute worker, THE Training_Pipeline SHALL create an immutable Dataset_Manifest containing: exact file references (storage keys), file checksums (SHA-256), asset role per file (training_image, regularization_image, caption_file), accepted/rejected state per file, provenance per file (upload source, upload date), consent references (which consent record authorizes this file's use), and Talent relationship (which talent this dataset trains)
2. THE Dataset_Manifest SHALL be assigned a unique version identifier and stored in Supabase — it SHALL NOT be modified after creation
3. THE training job record SHALL reference the exact Dataset_Manifest version used
4. WHEN a compute worker receives a training job, it SHALL verify that the files it downloads match the manifest checksums — if any file fails verification, THE worker SHALL reject the job before starting paid GPU training
5. IF a file referenced in the manifest has been deleted or its consent has been revoked since manifest creation, THEN THE Platform SHALL reject the training job with an error identifying the invalid file
6. THE Platform SHALL support manifest comparison: given two versions, show what files were added/removed/changed

---

### Requirement 62: Asset Upload Classification

**Status:** NEW in Rev 3

**User Story:** As a content creator, I want my uploads classified by purpose so that assets don't silently become training data or get used in ways I didn't intend.

#### Acceptance Criteria

1. WHEN an asset is uploaded, THE Platform SHALL require an explicit purpose/role classification: avatar, generation_reference, training_reference, wardrobe, product, voice_sample, continuity_reference, publishing_asset, or general
2. THE Platform SHALL NOT allow an asset to be silently reclassified to a more sensitive purpose (e.g., general → training_reference) without explicit user action — reclassification SHALL require a separate API call with the new role
3. WHEN a training job includes files, THE Platform SHALL verify that each referenced asset has a role of training_reference — assets with other roles SHALL NOT be included in training datasets without explicit reclassification
4. THE Platform SHALL display the asset's classified role in all UI contexts where the asset appears
5. IF an asset's role is changed, THE Platform SHALL record the change in an audit log with: asset_id, previous_role, new_role, actor, and timestamp
6. THE Platform SHALL support role-based filtering on asset list endpoints: GET /api/v1/assets?role=training_reference


---

## PRIORITY TIER P1-A: Infrastructure Contracts (New)

---

### Requirement 63: Realtime/Event Delivery Architecture

**Status:** NEW in Rev 3

**User Story:** As a frontend developer, I want a provider-neutral event delivery system with well-defined connection states, so that the UI stays synchronized with server state regardless of the underlying transport.

#### Acceptance Criteria

1. THE Platform SHALL define a provider-neutral event delivery layer with adapter support for: Supabase Realtime (primary), WebSocket (direct), Server-Sent Events (SSE), and future transports (AWS AppSync, etc.) — the frontend SHALL consume events through a unified interface regardless of transport
2. THE Platform SHALL enforce tenant authorization on all event subscriptions — a client SHALL only receive events for resources belonging to their authenticated org_id
3. THE Platform SHALL define a canonical event envelope containing: event_type, event_id (unique), version, correlation_id (linking to originating request), causation_id (linking to parent event), sequence/cursor (for ordering), timestamp, org_id, and payload
4. THE Platform SHALL support client reconnection with cursor-based resumption — after reconnect, the client SHALL receive events from the last acknowledged cursor without duplication
5. THE Platform SHALL handle deduplication (same event_id received twice is idempotent), out-of-order delivery (events applied by sequence number), gap detection (missing sequence numbers trigger reconciliation), and snapshot reconciliation (client can request full state after prolonged disconnection)
6. THE Platform frontend SHALL track and display explicit connection states: CONNECTED (receiving events normally), RECONNECTING (transport lost, attempting recovery), DEGRADED (connected but events may be delayed), STALE (data may be outdated, manual refresh recommended), OFFLINE (no connectivity)
7. THE Platform SHALL support at least the following event types for MVP: job_status_changed, asset_created, generation_completed, approval_requested, approval_resolved, cost_threshold_reached

---

### Requirement 64: Job Leasing and Durable Execution (Behavioral Contract)

**Status:** NEW in Rev 3 (supplements R21 with explicit behavioral semantics)

**User Story:** As a platform architect, I want the job system's behavioral contract defined independently of implementation technology, so that design.md can select the best implementation without being constrained by premature technology choices.

#### Acceptance Criteria

1. THE Platform SHALL NOT prematurely require Celery, Redis, or any specific queue technology in requirements — the behavioral contract SHALL be implementation-agnostic
2. THE job system SHALL provide: durable job state (survives server restart), atomic tenant-aware claims (no two workers can claim the same job), lease token (unique per claim attempt), worker identity tracking, heartbeat-based liveness, lease expiration (automatic release on worker death), attempt count tracking, configurable retry policies, cancellation support, idempotency key deduplication, stale-worker rejection (expired lease holder cannot write results), progress reporting, and crash recovery (orphaned jobs re-queued)
3. THE design.md SHALL select the implementation technology (Celery+Redis, Supabase job table with polling, SQS/SNS, Temporal, or custom) based on: current infrastructure, operational complexity, cost, observability, and scaling requirements
4. THE Platform SHALL define job type configurations specifying per-type: max_duration, retry_policy (max_attempts, backoff_strategy, retry_on_errors), heartbeat_interval, lease_duration, and cancellation_behavior
5. THE Platform SHALL support job priority levels to ensure time-sensitive operations (interactive generation) are processed before batch operations (scheduled publishing, analytics)
6. THE implementation SHALL be replaceable without changing the API contract or client behavior — switching from polling to queue-based SHALL be transparent to job submitters and consumers

---

### Requirement 65: Provider Capability, Reputation, and Workload Scheduling

**Status:** AMENDED in Rev 4 — added workload classes and capacity isolation

**User Story:** As a platform operator, I want provider selection to be dynamic and evidence-based with workload-aware scheduling, so that heavy workloads cannot exhaust interactive capacity and each workload class is independently manageable.

#### Acceptance Criteria

1. THE Platform SHALL capture per-provider performance metrics: startup_latency_seconds, queue_latency_seconds, generation_duration_seconds, failure_rate (rolling 24h), cost_estimate_vs_actual_variance, availability_percent (rolling 7d), gpu_type, vram_gb, model_cache_readiness (which models are pre-loaded), region, and quality_acceptance_rate (from user feedback on outputs)
2. THE Platform SHALL capture per-provider negative signals: cleanup_failures (instance not terminated), cost_overruns, timeout_rate, connection_failures, and data integrity issues
3. THE Worker_Orchestrator SHALL use accumulated reputation data to dynamically rank providers for each job type — provider preference SHALL be a learned ranking, not a permanent hardcoded list
4. THE Platform SHALL support provider quarantine: WHEN a provider's failure rate exceeds a configurable threshold (default 30% over 24h), THE Worker_Orchestrator SHALL automatically exclude it from job dispatch until manually reviewed or metrics recover
5. THE Platform SHALL persist all reputation data to Supabase (not in-memory) so that provider intelligence survives server restarts
6. THE Platform SHALL expose provider reputation data to Platform Operators (with Platform Observe capability) for review and manual override
7. THE Platform SHALL support manual provider preference overrides per-workspace for advanced users who want to target specific providers
8. THE Platform SHALL define workload classes as independently schedulable capacity categories: interactive language (Brain/Hermes responses), image generation, video generation, training, voice/audio, batch generation, production pipeline stages, and publishing/background operations
9. Heavy workloads (training, video generation, batch processing) SHALL NOT exhaust capacity available for interactive operations (Brain, quick image generation) — THE Platform SHALL maintain capacity isolation between workload classes
10. Interactive workloads MAY receive higher scheduling priority than batch/background workloads where policy permits — priority SHALL be configurable per workspace and per workload class

---

### Requirement 66: Cost Reservation and Reconciliation

**Status:** NEW in Rev 3 (extends R14 with atomic reservation mechanics)

**User Story:** As a platform operator, I want costs reserved atomically before expensive operations begin, so that concurrent job submissions cannot collectively exceed budget and cost accounting is always accurate.

#### Acceptance Criteria

1. BEFORE dispatching any platform-managed expensive operation (GPU job, training, batch generation, LLM call exceeding threshold), THE Platform SHALL create an atomic Cost_Reservation against the tenant's budget/entitlement — the reservation SHALL be created in a single database transaction that checks budget availability and creates the hold simultaneously
2. IF creating the reservation would cause total reservations + actual spend to exceed the tenant's budget (daily or monthly), THE Platform SHALL reject the operation with HTTP 402 before any resource is provisioned
3. AFTER execution completes (success or failure), THE Platform SHALL reconcile: release the reservation, record the actual cost_usd, log variance between estimated and actual, and flag anomalies exceeding 20% variance for investigation
4. THE Platform SHALL record cost for partial execution (e.g., GPU time consumed before a failure) — failed jobs that consumed resources SHALL NOT have their cost silently dropped
5. THE Platform SHALL record retry costs independently — each attempt that provisions resources or calls paid APIs SHALL have its own cost entry linked to the parent job
6. THE Platform SHALL distinguish between platform-managed costs (reserved against tenant budget) and customer-managed costs (informational only, tracked but not reserved)
7. THE Platform SHALL never treat missing cost evidence as $0 — if cost data cannot be determined after job completion (provider API failure, missing billing data), THE Platform SHALL flag the job for manual reconciliation and maintain the reservation until resolved
8. Cost_Reservations SHALL expire after max_job_duration + grace_period if not reconciled — expired reservations SHALL be released with a warning log


---

### Requirement 67: Model/LoRA Promotion Gates

**Status:** NEW in Rev 3 (extends R34 with explicit lifecycle contract)

**User Story:** As a platform operator, I want imported and trained models to go through a governed promotion lifecycle before becoming available for production use, so that untested or unsafe models cannot be used in customer-facing generation.

#### Acceptance Criteria

1. THE Platform SHALL enforce the following model/LoRA lifecycle states: IMPORTED (or TRAINED) → INTEGRITY_VERIFIED → EVALUATED → APPROVED → ACTIVE → DEPRECATED → QUARANTINED
2. Models SHALL NOT automatically become APPROVED or ACTIVE upon import or training completion — they SHALL enter the IMPORTED/TRAINED state and require progression through gates
3. Promotion from one state to the next MAY require (configurable per model risk class): file integrity verification (SHA-256 match, format validation, file not corrupted), compatibility verification (base model match, required nodes available), license compliance check (commercial use allowed if workspace uses commercially), safety policy evaluation (content safety scan if applicable), quality evaluation (test generation with minimum quality threshold), and human approval (for high-risk classes)
4. THE Platform SHALL support at minimum two risk classes: STANDARD (auto-promote through integrity and compatibility checks, human approval optional) and HIGH_RISK (human approval required before APPROVED state)
5. THE Platform SHALL support quarantining a model from any lifecycle state — quarantined models SHALL be immediately unavailable for all operations (generation, training, publishing) regardless of their prior state
6. THE Platform SHALL log all promotion gate transitions with: model_id, from_state, to_state, gate_checks_performed, gate_checks_passed, actor (human or system), evidence, and timestamp
7. THE Platform SHALL support model rollback: reverting an ACTIVE model to DEPRECATED SHALL remove it from future job dispatch while preserving it for reproducibility of historical jobs
8. WHEN a model is QUARANTINED, THE Platform SHALL identify all active/queued jobs using that model and either cancel them or flag them for review, depending on quarantine reason

---

### Requirement 68: Canonical Identity and Authority Model

**Status:** AMENDED in Rev 4 — aligned to Platform Operator capability model (R33/R97)

**User Story:** As a platform architect, I want ONE canonical identity and authority model that covers all actor types including the capability-based Platform Operator model, so that authorization logic is consistent and no subsystem silently invents its own authority semantics.

#### Acceptance Criteria

1. THE Platform SHALL define ONE canonical authority model covering: organizations (tenant boundary), memberships (user-to-org relationship with role), project/resource ownership (org_id on all Category A tables), workspace roles (owner > admin > editor > viewer), service identities (backend system operations), worker identities (GPU job execution), MCP identities (external tool connections), Platform Operators (capability-based, per R33/R97), support access (time-limited, audited tenant access with escalation), cross-workspace users (single user, multiple orgs), and future delegated authorities (API keys with subset permissions)
2. THE Platform SHALL NOT allow subsystems to independently define authority semantics — all permission checks SHALL reference the canonical authority model
3. THE Platform SHALL maintain a single resolution path for "what can this identity do?" — given any identity (user, service, worker, MCP client, Platform Operator), THE Platform SHALL produce a consistent capability set without consulting subsystem-specific permission tables
4. THE Platform SHALL support identity composition: a single human user MAY have different roles in different organizations, and each role resolves independently per-request based on the active org_id
5. IF a new identity type is needed (e.g., partner access, read-only audit bot), THE Platform SHALL extend the canonical model rather than creating a parallel permission system
6. THE Platform SHALL document the complete authority model as a single reference that all developers consult when implementing permission checks
7. Platform Operator capabilities (per R33/R97) SHALL be expressed within the canonical authority model as capability grants — not as a separate parallel permission system


---

## PRIORITY TIER P1-B: Data Integrity and Domain Model (New)

---

### Requirement 69: Ambiguous/Orphaned Data Quarantine

**Status:** NEW in Rev 3

**User Story:** As a platform operator, I want schema remediation to handle orphaned data safely without guessing ownership, so that data integrity is maintained and no records are silently misattributed.

#### Acceptance Criteria

1. THE Platform SHALL classify all existing records during schema remediation into: VALID_TENANT_OWNED (org_id is non-null and references a real, active organization), EXPLICITLY_SYSTEM_OWNED (org_id matches the system org UUID and the record is a legitimate shared resource), QUARANTINED_FOR_REVIEW (org_id is null, references a non-existent org, or ownership is ambiguous), ELIGIBLE_FOR_APPROVED_PURGE (quarantined records that have been reviewed and approved for deletion)
2. THE Platform SHALL NEVER guess tenant ownership for ambiguous records — records with NULL org_id or references to non-existent organizations SHALL be quarantined, not assigned to a placeholder org merely to satisfy a NOT NULL constraint
3. QUARANTINED records SHALL be: invisible to all tenant-scoped API queries, accessible only via Platform Operator or service-role queries, tagged with quarantine_reason and quarantine_date, and subject to a defined review process
4. THE Platform SHALL provide Platform Operator tooling to review quarantined records and either: assign them to the correct org (with evidence), classify them as system-owned, or approve them for permanent deletion
5. THE Platform SHALL NOT apply the org_id NOT NULL constraint on a table until all existing NULL rows have been explicitly classified (not bulk-assigned to founder without individual review for tables with non-trivial record counts)
6. THE Platform SHALL log all quarantine resolutions with: record_id, table, resolution (assigned/system/purged), actor, evidence, and timestamp

---

### Requirement 70: Domain Consolidation Classification

**Status:** NEW in Rev 3

**User Story:** As a developer, I want overlapping domain models explicitly classified so that I know which is canonical, which exists only for backward compatibility, and which should be migrated or retired.

#### Acceptance Criteria

1. THE Platform SHALL classify every domain model/schema/table into one of: CANONICAL (authoritative source of truth for this concept), COMPATIBILITY_ONLY (exists to support old code paths, reads redirect to canonical), MIGRATE (scheduled for data migration to canonical model), DEPRECATED (no new writes, existing reads still work), RETIRE (scheduled for removal after migration complete)
2. THE Platform SHALL specifically classify overlapping models in these areas: Brain persistence vs AIOS persistence (brain_sessions, brain_conversations, aios_sessions, aios_messages), worker concepts (workers table vs worker_sessions vs worker_connection_attempts), voice structures (voice_profiles vs voice_samples vs audio_clips vs voice_versions), timeline/cinematic (cinematic_timelines vs timeline_tracks vs video_projects), collections (brain_collections vs asset_collections vs collection_items)
3. THE Platform SHALL NOT merge domain models merely because names resemble each other — classification SHALL be based on actual data overlap, consumer analysis, and semantic equivalence
4. WHEN two models are classified as overlapping, THE Platform SHALL document: which is CANONICAL, what data lives in each, which code paths consume each, and the migration path (if applicable)
5. THE Platform SHALL maintain this classification as a living document, updated when new models are created or existing models evolve
6. THE design.md SHALL reference domain classifications when making schema decisions — new features SHALL use CANONICAL models and SHALL NOT create new overlapping concepts

---

### Requirement 71: Environment Map

**Status:** NEW in Rev 3

**User Story:** As a platform operator, I want ONE authoritative map of all environments so that I know exactly what infrastructure exists, what state it's in, and what data classification applies to each.

#### Acceptance Criteria

1. THE Platform SHALL maintain ONE authoritative environment map documenting all environments: development (local), test (CI), staging (if exists), and production — with explicit acknowledgment of environments that do NOT yet exist
2. THE environment map SHALL document per environment: GitHub repository and branch, frontend deployment (Vercel project/URL), backend deployment (host/URL), Supabase project (URL, region), storage provider (bucket, endpoint), compute provider connections, secrets authority (where secrets are stored/managed), MCP/API connections, domains and endpoints, data classification (real/synthetic/mixed), and deployment ownership (who deploys, how)
3. THE Platform SHALL explicitly identify unknown or abandoned environments (orphaned Vercel deployments, old Supabase branches, leftover GPU instances) and document their disposition
4. THE environment map SHALL identify gaps: if staging does not exist, it SHALL be documented as "NOT PROVISIONED" with the decision status (planned, deferred, or not needed)
5. THE environment map SHALL document data flow restrictions: which environments may contain real user data, which use synthetic data only, and what data may flow between environments
6. THE environment map SHALL be version-controlled and updated as part of any infrastructure change


---

## PRIORITY TIER P2-A: Security, Release, and Supply Chain (New)

---

### Requirement 72: Reproducible Release Identity

**Status:** NEW in Rev 3

**User Story:** As a platform operator, I want every production release to have ONE immutable identity that links all artifacts, so that I can trace any runtime behavior back to the exact code, config, and models that produced it.

#### Acceptance Criteria

1. THE Platform SHALL assign every production release ONE immutable Release_Identity linking: Git commit SHA, frontend build artifact (Vercel deployment ID or build hash), backend artifact (Docker image digest or deployment ID), worker images (if applicable), migration set (list of applied migration IDs with checksums), configuration version (env/secrets version identifier), AI/model manifest (which model versions are active), and deployment IDs (Vercel, Railway, or equivalent)
2. THE Platform SHALL surface Release_Identity in: health check responses (GET /ready), structured log entries, job records, error reports, and asset metadata — enabling reconstruction of what code/config produced any given result
3. THE Platform SHALL store Release_Identity as an immutable record in Supabase, created during deployment and never modified
4. WHEN investigating a failed job, disputed output, or bug report, an operator SHALL be able to retrieve the exact Release_Identity active at the time of the event using timestamps or correlation IDs
5. THE Platform SHALL reject deployments that cannot produce a complete Release_Identity — missing commit SHA, unsigned artifacts, or untracked migrations SHALL block production deployment
6. THE Platform SHALL support Release_Identity comparison: given two releases, show what changed (commits, migrations, config, models)

---

### Requirement 73: Release Security (GA-001)

**Status:** NEW in Rev 3

**User Story:** As a security engineer, I want production releases to fail closed on missing security evidence and critical trust failures, so that compromised or untraceable code never reaches production.

#### Acceptance Criteria

1. THE Platform SHALL enforce fail-closed behavior for mandatory evidence: production deployment SHALL NOT proceed if required security evidence is missing or incomplete — missing evidence SHALL NOT be treated as passing
2. THE Platform SHALL require immutable artifact identity for all production components: application code, worker images, AI orchestration, containers, migrations, CI/CD pipeline outputs, and third-party extensions
3. THE Platform SHALL generate or require Software Bills of Materials (SBOMs) for: backend dependencies (Python packages), frontend dependencies (npm packages), worker Docker images, and ComfyUI custom nodes
4. THE Platform SHALL enforce consistent security controls across: application code, GPU workers, AI orchestration layer, container images, database migrations, CI/CD pipeline, and third-party extensions — no component category SHALL be exempt from security review
5. Production deployment SHALL NOT proceed with any of: exposed secrets in artifacts, authentication bypass enabled, cross-tenant data access possible, unauthorized privilege escalation paths, known malicious artifacts, compromised CI/CD pipeline evidence, or untraceable releases (missing Release_Identity)
6. THE Platform SHALL support explicit, time-limited security exceptions — exceptions SHALL have: owner (person responsible), expiration date, approval record, scope limitation, and audit trail
7. AI-generated code SHALL receive the same security controls as human-written code — code origin (AI vs human) SHALL NOT affect the rigor of security review or testing requirements

---

### Requirement 74: Worker/AI Supply-Chain Security

**Status:** NEW in Rev 3

**User Story:** As a security engineer, I want all external components used by workers and AI systems (Docker images, models, LoRAs, custom nodes, MCP servers) to have verified provenance and integrity, so that compromised supply-chain components cannot execute on our infrastructure.

#### Acceptance Criteria

1. THE Platform SHALL identify and track all supply-chain components: Docker base images, model files (.safetensors, .ckpt), LoRA files, ComfyUI custom nodes, workflow definitions (JSON), MCP server packages, CI/CD actions, plugins, external binaries, and referenced external repositories
2. THE Platform SHALL require for each supply-chain component: immutable version reference (tag + digest, not just "latest"), checksum or signature verification, provenance record (where it came from, when it was fetched), license metadata, and security scanning results (where tooling exists)
3. THE Platform SHALL generate SBOMs for worker Docker images listing all installed packages, Python dependencies, and ComfyUI nodes
4. THE Platform SHALL enforce that GPU workers run as non-root with minimal capabilities, controlled volume mounts, and no default SSH/root exposure to the public internet
5. THE Platform SHALL ensure that runtime secrets on workers are scoped to the active job only (per R8 Credential Broker) — no long-lived secrets stored on worker filesystems
6. THE Platform SHALL maintain a known-good component registry for: approved Docker base images, approved ComfyUI nodes, and approved model sources — components not in the registry SHALL require explicit approval before use
7. WHEN a supply-chain component is updated (new Docker image version, ComfyUI node update), THE Platform SHALL verify integrity before deploying to production workers


---

## PRIORITY TIER P2-B: Observability and Performance (New)

---

### Requirement 75: Full Correlation and Observability

**Status:** NEW in Rev 3

**User Story:** As a platform operator, I want correlation IDs that span the entire request lifecycle from browser to asset, so that I can reconstruct any operation for debugging or dispute resolution without exposing protected content.

#### Acceptance Criteria

1. THE Platform SHALL propagate correlation IDs across the full span: Browser request → API endpoint → Brain/Hermes processing → AIOS policy/approval evaluation → tool/provider invocation → job dispatch → worker execution → asset creation → cost recording → release identity
2. THE Platform SHALL use the X-Request-ID as the root correlation ID, with child span IDs for sub-operations (LLM call, storage upload, GPU dispatch) linked to the parent
3. THE Platform SHALL enable reconstruction of a failed or disputed operation using only the correlation ID — an operator SHALL be able to trace: what was requested, who requested it, what policy was evaluated, what was approved/denied, what was dispatched, what the worker did, what was produced, and what it cost
4. THE Platform SHALL NOT expose protected content (generated images, PII, secrets, raw prompts) in observability data — correlation enables tracing to the relevant records without inlining sensitive content
5. THE Platform SHALL include correlation IDs in: structured logs, job records, cost entries, asset metadata, approval records, and error reports
6. THE Platform SHALL support time-bounded trace queries: given a time range and org_id, return all correlation chains for that period

---

### Requirement 76: Product-Level Performance Requirements

**Status:** AMENDED in Rev 4 — added scalability verification and load testing targets

**User Story:** As a content creator, I want the platform to feel responsive and fast for common operations, so that the creative flow is never interrupted by slow infrastructure.

#### Acceptance Criteria

1. THE Platform SHALL meet the following navigation and data loading targets: page navigation with cached data renders within 100ms, fresh data load completes within 500ms for lists under 100 items, image thumbnails load within 200ms from CDN
2. THE Platform SHALL meet the following Talent and project query targets: single talent detail loads within 300ms, talent list (20 items) loads within 500ms, project detail with counts loads within 500ms
3. THE Platform SHALL meet the following Brain/chat targets: first token appears within 2 seconds of submission, streaming maintains consistent token delivery without gaps > 500ms, mode switching takes effect within 100ms
4. THE Platform SHALL meet the following generation targets: job submission returns HTTP 202 within 2 seconds, job status polling returns within 200ms, realtime event delivery latency under 1 second from state change to client receipt
5. THE Platform SHALL meet the following admin dashboard targets: fleet status loads within 1 second, cost summary loads within 1 second, capability registry loads within 500ms
6. THE Platform SHALL use representative workloads and query execution plans to optimize database performance — optimization SHALL be evidence-based (EXPLAIN ANALYZE), not speculative
7. THE Platform SHALL identify and document operations that cannot meet interactive latency targets (training, video generation, batch operations) and ensure they use async patterns with progress feedback
8. THE Platform SHALL be designed so that scaling registered users does not require proportional GPU scaling — user growth and compute capacity SHALL scale independently
9. THE Platform SHALL support load testing verification targets before broad availability: 6000 registered users, hundreds simultaneously active users, 1000+ concurrent sessions, generation request bursts, concurrent video/training jobs, and concurrent Brain streams — exact numeric targets SHALL be finalized during design/performance testing phase
10. THE Platform architecture SHALL allow job transport technology replacement without changing the public API contract — the job submission/polling interface SHALL remain stable regardless of backend queue implementation

---

### Requirement 77: Beginner vs Advanced UX

**Status:** AMENDED in Rev 4 — added Connections Hub, OAuth-preferred flows

**User Story:** As a content creator, I want infrastructure complexity hidden by default so I can focus on creating, while having access to advanced controls when I need them — with connections managed through a familiar OAuth-style experience.

#### Acceptance Criteria

1. THE Platform frontend SHALL hide infrastructure complexity from ordinary creators by default — users SHALL NOT need to understand: GPU providers, model file formats, storage providers, MCP protocols, inference infrastructure, or compute pricing to accomplish basic creative tasks
2. THE Platform frontend SHALL support basic flows without infrastructure knowledge: create talent, generate image (with recipe or simple prompt), edit/rate output, publish content, chat with Brain, import/train model (with guided wizard)
3. THE Platform frontend SHALL provide progressive disclosure of advanced controls for users who want them: provider selection, compute ownership mode, model/LoRA routing preferences, storage destination, MCP/API connection management, cost control settings, and diagnostic views
4. THE Platform frontend SHALL separate basic and advanced experiences via UI patterns: expandable "Advanced" sections, separate settings pages, and capability-gated UI elements — never by requiring users to navigate complex menus for basic operations
5. THE Platform SHALL use the Capability_Registry and user's plan tier to determine which advanced features are visible — features the user cannot access SHALL not be shown (not shown as disabled)
6. THE Platform SHALL support a "what will this cost?" preview for any operation with non-trivial cost, presented in plain language (not raw GPU pricing)
7. THE Connections Hub SHALL present all integrations through one familiar surface with OAuth-preferred flows — ordinary users SHALL NOT need to manually configure OAuth client IDs, secrets, redirect URIs, bearer tokens, raw scopes, or MCP transport internals
8. Advanced users MAY access: direct provider selection, compute ownership configuration, MCP transport details, and raw API/credential management — but these SHALL NOT be required for standard creative workflows

---

### Requirement 78: Capability-Driven Provider Selection

**Status:** NEW in Rev 3

**User Story:** As a content creator, I want to request what I need (resolution, style, speed, budget) and have the platform select the best provider, rather than choosing infrastructure myself.

#### Acceptance Criteria

1. THE Platform SHALL support capability-driven generation requests where the user specifies desired outcomes (resolution, quality level, style, speed preference, budget limit) rather than infrastructure details (GPU type, provider, model file)
2. THE Platform SHALL filter and recommend eligible providers/models using verified capabilities from the reputation system (R65) — recommendations SHALL be based on actual measured performance, not marketing claims
3. THE Platform SHALL present generation options as: "Quick draft" (fastest, cheapest), "Standard quality" (balanced), "High quality" (best available, higher cost) — abstracting the underlying provider and model selection
4. THE Platform SHALL support manual provider/model override for advanced users who want direct control — this SHALL be available as an advanced option, not the default flow
5. WHEN the user's requested capability cannot be met by any available provider (e.g., budget too low for requested quality), THE Platform SHALL explain the constraint and suggest alternatives rather than silently degrading quality
6. THE Platform SHALL log capability-driven selection decisions (what was requested, what was selected, why) for learning and transparency


---

## PRIORITY TIER P3-A: Publishing and Production Integrity (New)

---

### Requirement 79: Publishing Approval Integrity

**Status:** NEW in Rev 3

**User Story:** As a content creator, I want publishing approvals to bind to the exact content reviewed, so that changes after approval require re-evaluation and nothing gets published that wasn't explicitly approved.

#### Acceptance Criteria

1. WHEN a publishing action is approved (via governance approval workflow), THE Platform SHALL bind the approval to the exact package reviewed: specific asset version (by checksum or immutable ID), caption text, destination platform, scheduled time, targeting parameters, consent state at time of approval, disclosure settings, and applicable policy state
2. IF any bound element changes after approval (content re-generated, caption edited, destination changed, schedule moved, targeting modified, consent revoked, disclosures updated, or policy changed), THEN THE Platform SHALL invalidate the approval and require re-evaluation before publishing
3. THE Platform SHALL store the approved package snapshot as an immutable record — enabling audit of exactly what was approved vs what was published
4. WHEN publishing executes, THE Platform SHALL verify the current state matches the approved package — if any drift is detected, THE Platform SHALL halt publishing and create a new approval request
5. THE Platform SHALL support approval delegation for scheduled posts: an approval granted for a specific future time SHALL remain valid only if the bound package has not changed
6. THE Platform SHALL log all approval invalidations with: original_approval_id, invalidation_reason, changed_element, and timestamp

---

### Requirement 80: Synthetic/AI Media Disclosure Hooks

**Status:** NEW in Rev 3

**User Story:** As a platform operator, I want publishing to support policy hooks for AI disclosure, provenance metadata, and platform-specific requirements, so that the platform can comply with evolving regulations without hardcoding specific rules.

#### Acceptance Criteria

1. THE Publishing_Service SHALL retain configurable policy hooks for: AI/synthetic-media disclosure (labeling content as AI-generated), sponsorship/commercial disclosure (FTC/ASA compliance indicators), provenance metadata (C2PA/Content Credentials attachment points), destination-specific policy (platform ToS compliance), and future watermark/content credential requirements
2. THE Platform SHALL NOT hardcode a universal disclosure rule — disclosure policy SHALL be configurable at platform level (by Platform Operator) and workspace level (stricter-only), with the final policy determined at publish time based on: destination platform requirements, workspace policy, and platform policy
3. THE Platform SHALL store disclosure configuration per-workspace: which disclosures are enabled, what text/tags to include, and which platforms require specific disclosures
4. WHEN a publishing action is dispatched, THE Platform SHALL evaluate applicable disclosure hooks and include required disclosures in the published content (tags, captions, metadata) as configured
5. THE Platform SHALL support a "disclosure preview" showing the user exactly what disclosures will be attached before publishing
6. THE Platform SHALL log all disclosure decisions (what was applied, what policy triggered it) for audit and compliance purposes
7. THE Platform SHALL document the disclosure policy decision (what is required at launch) as an unresolved Founder decision until explicitly approved

---

### Requirement 81: Full Production Stage Graph

**Status:** NEW in Rev 3

**User Story:** As a content creator working on complex productions, I want multi-stage workflows (story → storyboard → image → video → voice → music → assembly → publish) with tracked dependencies and recoverable stages, so that I can manage long-form creative projects.

#### Acceptance Criteria

1. THE Platform SHALL support a production stage model where a parent production contains ordered stages: Story → Storyboard → Image Generation → Video Generation → Voice/Audio → Music → Assembly/Export → Publish — not all stages are required for every production
2. Each stage SHALL track: status (pending, in_progress, completed, failed, skipped), dependencies (which prior stages must complete first), input lineage (what assets/outputs from prior stages feed this stage), output assets (what this stage produces), cost (accumulated per-stage), approval state (if stage requires approval), retry state (attempt count, last failure reason), and failure handling (retry, skip, or block)
3. THE Platform SHALL enforce stage dependencies: a stage SHALL NOT begin execution until all required predecessor stages have completed successfully (or been explicitly skipped)
4. THE Platform SHALL support stage-level recovery: if a stage fails, the user can retry that specific stage without re-executing successful predecessor stages
5. THE Platform SHALL track input/output lineage across stages: the output assets of one stage become input assets for subsequent stages, forming a traceable production graph
6. THE Platform SHALL NOT require all stages for MVP — the stage model SHALL be designed for future composition, with Image Generation as the minimum viable single-stage production
7. THE Platform SHALL support cost aggregation across all stages of a production, with per-stage cost breakdown visible to the user


---

## PRIORITY TIER P0-B: Verification and Release (New)

---

### Requirement 82: Independent Verification

**Status:** AMENDED in Rev 4 — updated deployment reality

**User Story:** As a platform operator, I want implementation and verification to be separate concerns, so that the entity that built something is not the sole entity certifying it works correctly.

#### Acceptance Criteria

1. THE Platform SHALL treat implementation and verification as separate concerns — Kiro's completion statement alone SHALL NOT constitute acceptance evidence for any production-readiness claim
2. Production verification SHALL independently validate: requirements coverage (do tests map to acceptance criteria?), code correctness (do tests pass?), schema integrity (do migrations produce expected schema?), deployment success (does the app start and serve traffic?), log integrity (are structured logs emitted correctly?), security posture (are auth/RLS/tenant isolation working?), tenant isolation (adversarial cross-tenant tests pass?), runtime capability (do real operations work end-to-end?), and completion evidence (is there traceable proof for each claim?)
3. THE Platform SHALL support verification by at minimum two independent mechanisms: automated test suites AND either human review, Hermes inspection, or adversarial testing (Red Team)
4. THE Platform SHALL maintain a verification evidence record per feature/requirement linking: requirement ID, verification method, evidence location (test file, CI run, manual sign-off), verification date, and verifier identity
5. IF verification reveals a discrepancy between claimed state and actual state, THE Platform SHALL update the Capability_Registry to reflect actual state and create a defect record
6. THE Platform SHALL NOT allow a feature to be classified as PRODUCTION in the Capability_Registry based solely on developer assertion — independent evidence is required
7. Deployment verification SHALL acknowledge the current Vercel reality: at least one successful READY deployment has been demonstrated from main, but deployment is classified as "demonstrated but unstable" until repeatability is proven — a single successful deployment SHALL NOT constitute production readiness evidence
8. Deployment with ignored or disabled required build errors SHALL NOT constitute clean production evidence

---

### Requirement 83: Final Production Gate

**Status:** AMENDED in Rev 4 — updated deployment evidence requirements

**User Story:** As a platform operator, I want a final production gate that requires specific evidence before any release goes live, so that incomplete or broken releases cannot reach customers.

#### Acceptance Criteria

1. THE Platform SHALL bind every release candidate to an immutable Release_Identity (per R72) — no release without traceable identity
2. THE Platform SHALL require the following evidence before production deployment: clean frontend build (zero errors), clean backend build (zero errors), CI pipeline passes (all checks green), frontend deploys successfully to Vercel, backend deploys successfully to hosting, database schema matches migration expectations, tenant isolation passes adversarial verification (not just unit tests), all PRODUCTION-classified capabilities pass health checks, required security evidence present (per R73), rollback procedure documented and tested, database restore rehearsed within last 30 days, and monitoring/alerting active for critical paths
3. THE Platform SHALL NOT allow new feature work during final production verification except remediation of failed gate checks — scope creep during verification SHALL be blocked
4. THE Platform SHALL support partial release gates for PARTIAL features: features classified below PRODUCTION may be released with appropriate UI indicators, but SHALL NOT be presented to users as complete
5. THE Platform SHALL document gate failures with: which check failed, what evidence was expected vs actual, and remediation path
6. WHEN all gate checks pass, THE Platform SHALL record the gate passage with: Release_Identity, evidence links for each check, gate passage timestamp, and approving actor (human or automated)
7. THE Platform SHALL support emergency releases (hotfixes) with a reduced gate that still requires: clean build, critical security checks, and tenant isolation verification — with post-release full verification within 24 hours
8. Deployment repeatability from the canonical branch SHALL be required for production gate passage — a deployment that succeeded once but cannot be repeated on demand SHALL NOT pass the gate
9. Frontend deployment SHALL require zero TypeScript errors, zero ESLint errors, and zero Next.js build errors from the canonical branch without manual intervention or suppressed checks


---

## NEW REQUIREMENTS — REVISION 4 AMENDMENTS (Founder Decisions)

---

## PRIORITY TIER P1-C: Authentication and Identity (New)

---

### Requirement 84: Unified Signup and Login Experience

**Status:** NEW in Rev 4

**User Story:** As a new or returning user, I want one authentication entry surface that handles both signup and login seamlessly, including OAuth, so that I never face confusion about which flow to use.

#### Acceptance Criteria

1. THE Platform SHALL provide one unified authentication entry surface supporting: Sign Up (new user), Log In (returning user), Continue with Google (OAuth), email/password, and future OAuth providers — without requiring users to choose between separate signup and login pages
2. WHEN an OAuth flow completes for an existing identity, THE Platform SHALL log the user in; WHEN an OAuth flow completes for a new identity, THE Platform SHALL create the user and initiate workspace provisioning
3. WHEN a user authenticates via OAuth, THE Platform SHALL NOT require them to create a separate AI Studio password — the OAuth identity SHALL be sufficient for full platform access
4. WHEN workspace provisioning is triggered (new user or first login), THE Platform SHALL create or resume: user identity record, workspace/organization, org_members membership, and onboarding state
5. THE Platform SHALL ensure workspace provisioning is idempotent — retrying the signup or OAuth flow (due to network failure, browser back, accidental resubmit) SHALL NOT create duplicate workspaces, duplicate users, or duplicate memberships
6. WHEN a newly authenticated user has no org_members record and is eligible for provisioning, THE Platform SHALL enter the provisioning flow rather than returning NO_MEMBERSHIP — the provisioning eligibility criteria SHALL be defined in design.md

---

### Requirement 85: Unified Connections Hub

**Status:** NEW in Rev 4

**User Story:** As a content creator, I want one surface for managing all my integrations (AI providers, storage, social, compute, developer tools, MCP) with familiar OAuth flows, so that I don't need to manually configure credentials.

#### Acceptance Criteria

1. THE Platform SHALL provide a unified Connections Hub as one surface for all connection types: AI/model providers, storage providers, publishing/social platforms, compute providers, developer tools, business applications, and MCP servers
2. OAuth SHALL be the preferred connection flow where supported by the target service — THE Platform SHALL manage OAuth client configuration centrally so ordinary users never configure client IDs, secrets, or redirect URIs
3. THE Platform SHALL classify connection ownership as either USER_CONNECTION (belongs to individual user, follows them across workspaces they have access to) or WORKSPACE_CONNECTION (belongs to the organization, stays with workspace when members leave)
4. THE Platform SHALL track connection lifecycle states: CONNECTING (flow in progress), CONNECTED (healthy and usable), DEGRADED (partially functional), REAUTH_REQUIRED (credentials expired, user action needed), DISCONNECTED (intentionally disconnected), REVOKED (access revoked by target service or admin)
5. WHEN a connection enters REAUTH_REQUIRED or DEGRADED state, THE Platform SHALL provide plain-language recovery actions and Brain/Hermes SHALL detect the condition and provide contextual guidance
6. Workspace-wide connections SHALL require admin or owner permission to create — viewer and editor roles SHALL NOT be able to create workspace connections
7. Connection access (which workspace members can USE a connection) SHALL be governed independently from connection existence — a connection may exist but be restricted to certain roles or specific tool policies

---

## PRIORITY TIER P1-D: Compute and Capacity (New)

---

### Requirement 86: Compute Availability Modes (Founder-Controlled)

**Status:** NEW in Rev 4

**User Story:** As a Founder, I want platform-managed compute to be globally controllable with three states (DISABLED/SELECTIVE/ENABLED), so that I can manage cost exposure and feature rollout without code changes.

#### Acceptance Criteria

1. THE Platform SHALL support three Founder-controlled global states for platform-managed compute availability: DISABLED (entirely unavailable), SELECTIVE (available to Founder-selected workspaces/cohorts), and ENABLED (available to all eligible workspaces)
2. WHEN platform-managed compute is DISABLED, THE Platform SHALL ensure complete feature unavailability — not just UI hiding — including: UI does not show platform compute options, Brain/Hermes does not recommend it, APIs reject requests with HTTP 403, Capability_Registry marks it as disabled, and no forged or direct requests can bypass the restriction
3. WHEN platform-managed compute is SELECTIVE, THE Founder SHALL be able to enable access by: specific workspace, plan tier, beta cohort, workload type, provider, temporary promotion (time-limited), or manual per-workspace override
4. WHEN platform-managed compute is ENABLED, eligible workspaces MAY use it according to their plan entitlements, budget limits, workload requirements, and available capacity
5. Changing platform-managed compute availability state SHALL NOT require code deployment, architectural changes, or service restart — the state change SHALL propagate through configuration alone within 60 seconds

---

### Requirement 87: Customer Multi-GPU Capacity and Load Balancing

**Status:** NEW in Rev 4

**User Story:** As a content creator with my own GPU infrastructure, I want AI Studio to intelligently schedule work across all my connected GPUs without manual assignment.

#### Acceptance Criteria

1. THE Platform SHALL support workspaces connecting: a single GPU, multiple GPUs from one provider, GPUs from multiple providers simultaneously, and future local GPU connections
2. THE Platform SHALL provide workload scheduling across a workspace's eligible compute pool considering: workload type requirements (VRAM, model type), model cache readiness (which models are pre-loaded on which worker), current utilization (jobs in progress), worker health (responsive, not degraded), queue depth (pending jobs per worker), estimated execution time, job priority level, concurrency entitlement, and workspace routing preferences
3. WHEN multiple eligible workers are available, THE Platform SHALL support independent concurrent job execution — each eligible worker MAY process jobs independently
4. THE Platform SHALL NOT exceed customer-configured concurrency limits or plan-authorized concurrency limits when scheduling work
5. Workers SHALL be load-balanced automatically without requiring manual GPU assignment by the user for each job

---

### Requirement 88: Capacity Pools and Workload Isolation

**Status:** NEW in Rev 4

**User Story:** As a platform operator, I want workloads classified into independently schedulable capacity pools, so that heavy operations cannot starve interactive experiences.

#### Acceptance Criteria

1. THE Platform SHALL define workload classes as independently schedulable capacity categories: interactive language (Brain/Hermes responses), image generation, video generation, training, voice/audio synthesis, batch generation, production pipeline stages, and publishing/background operations
2. Heavy workloads (training, video generation, batch processing) SHALL NOT exhaust capacity available for interactive operations — THE Platform SHALL maintain capacity isolation between workload classes
3. Interactive workloads MAY receive higher scheduling priority than batch/background workloads where policy permits — priority SHALL be configurable per workspace and per workload class
4. WHEN capacity for a workload class is exhausted, THE Platform SHALL queue work rather than rejecting it (unless budget limits are also exceeded) and provide queue position and estimated wait time where reliable estimates are available

---

### Requirement 89: Platform Compute Cost Protection

**Status:** NEW in Rev 4

**User Story:** As a Founder, I want platform-managed compute to have absolute cost guardrails that prevent runaway liability regardless of user behavior.

#### Acceptance Criteria

1. Platform-managed compute operations SHALL use Cost Reservations (per R14/R66) before provisioning any GPU resources
2. Platform-managed operations SHALL NOT begin if any of: cost cannot be estimated within policy tolerance, budget reservation cannot be created, provider pricing is unavailable and policy requires known cost, platform-wide compute budget has been reached, or workspace entitlement has been reached
3. THE Platform SHALL distinguish cost classifications: customer infrastructure cost (informational — customer pays their provider directly), platform infrastructure expense (AI Studio's own costs), and customer-billed managed-compute usage (platform-managed compute billed to tenant)
4. Customer-owned compute usage SHALL be tracked as informational cost from AI Studio's perspective — THE Platform SHALL NOT reserve against tenant budget for customer-owned compute unless a future explicit billing arrangement states otherwise
5. THE Platform SHALL enforce platform-wide compute budget limits that cap total platform-managed GPU liability independent of individual workspace budgets

---

### Requirement 90: Capacity Management and Graceful Load Shedding

**Status:** NEW in Rev 4

**User Story:** As a platform operator, I want the system to degrade gracefully under load rather than failing catastrophically, with visibility into capacity pressure.

#### Acceptance Criteria

1. WHEN demand exceeds available capacity for a workload class, THE Platform SHALL queue work rather than exceeding configured limits — providing queue status and estimated wait time where reliable estimates are available
2. THE Platform SHALL support graceful degradation of non-critical functionality during capacity pressure — read-only navigation, page rendering, and data viewing SHALL remain usable when generation capacity is exhausted
3. THE Platform SHALL maintain capacity telemetry including: active users, API request rate, Brain streams active, realtime connections, database utilization, queue depth per workload class, average wait time, active jobs per provider, available workers, GPU utilization, provider available capacity, failure rate, and platform compute liability
4. THE Platform SHALL use capacity telemetry to inform scheduling decisions and provide Platform Operators with visibility into system load

---

### Requirement 91: Scalability Verification

**Status:** NEW in Rev 4

**User Story:** As a platform architect, I want verified evidence that the system scales appropriately before broad user availability.

#### Acceptance Criteria

1. THE Platform SHALL be designed so that scaling registered users does not require proportional GPU scaling — user growth and compute capacity SHALL scale independently
2. THE Platform SHALL support load testing verification targets before broad availability: 6000 registered users, hundreds simultaneously active users, 1000+ concurrent sessions, generation request bursts, concurrent video/training jobs, and concurrent Brain streams — exact numeric targets SHALL be finalized during design/performance testing phase
3. THE Platform architecture SHALL allow job transport technology replacement without changing the public API contract — switching backend queue implementation SHALL be transparent to API consumers
4. THE Platform SHALL document which components are expected to scale horizontally vs vertically and what their current capacity constraints are

---

## PRIORITY TIER P2-C: Data Ownership and Lifecycle (New)

---

### Requirement 92: Connection Ownership and Lifecycle

**Status:** NEW in Rev 4

**User Story:** As a workspace admin, I want clear rules about who owns connections and what happens when team members leave.

#### Acceptance Criteria

1. USER_CONNECTIONs SHALL belong to the individual user — usable while the user has workspace access, with personal auth credentials that never become shared workspace credentials
2. WORKSPACE_CONNECTIONs SHALL belong to the organization — usable by authorized workspace members per role/tool policy, remaining functional when individual members leave
3. THE Platform SHALL require explicit ownership classification at connection creation time — connections SHALL NOT have ambiguous ownership
4. Workspace-wide connections SHALL require admin or owner role to create
5. Connection access (who can USE a connection) SHALL be governed independently from connection existence — a WORKSPACE_CONNECTION may exist but be restricted to specific roles or specific tool policies
6. THE Platform SHALL define connection lifecycle states: CONNECTING, CONNECTED, DEGRADED, REAUTH_REQUIRED, DISCONNECTED, REVOKED — with each state having defined user-facing meaning and recovery path
7. A USER_CONNECTION SHALL NOT automatically become usable by every workspace the user joins — explicit authorization of a personal connection for a workspace/context SHALL be required where appropriate. Personal credentials SHALL remain personal; workspace use of those credentials SHALL be explicit, revocable, capability-scoped, and auditable.

---

### Requirement 93: Brain User-Specific Experience

**Status:** NEW in Rev 4

**User Story:** As a team member, I want my Brain conversations and preferences to be private to me within the workspace.

#### Acceptance Criteria

1. Each user SHALL have separate Brain sessions scoped by: org_id, user_id, conversation_id, and trust_domain
2. Users MAY maintain multiple resumable conversations — each conversation SHALL be independently addressable and resumable across sessions
3. THE Brain_Service MAY learn per-user preferences: communication style, workflow habits, response preferences, accepted/rejected recommendation patterns, quality/speed/cost trade-offs, tool preferences, and mode preferences
4. User-private Brain memory SHALL NOT be injected into another user's Brain session under any circumstance
5. Private conversation content SHALL NOT automatically become workspace knowledge without explicit promotion action by the user

---

### Requirement 94: Brain Memory Layers

**Status:** NEW in Rev 4

**User Story:** As a content creator, I want clear separation between my private memory, workspace shared knowledge, and platform learning.

#### Acceptance Criteria

1. THE Platform SHALL maintain distinct Brain memory layers: conversation/session context (ephemeral, per-conversation), user-private memory (durable per-user preferences and learned patterns), workspace-shared knowledge (org-level knowledge accessible to all workspace members), and platform-level learning (aggregated/de-identified signals for platform improvement)
2. Private memory SHALL NOT become workspace-shared without explicit user-initiated promotion or an approved promotion workflow
3. Users SHALL be able to inspect, correct, delete, or disable any durable user-level personalization
4. THE Platform SHALL clearly indicate in Brain responses when workspace-shared knowledge vs user-private memory vs fresh inference is being used

---

### Requirement 95: Cross-Tenant Learning Isolation

**Status:** NEW in Rev 4

**User Story:** As a content creator, I want confidence that my creative work, prompts, strategies, and content are never used to benefit another customer.

#### Acceptance Criteria

1. THE Platform MAY improve its general capabilities but SHALL NOT reuse one customer's proprietary creative content as cross-tenant knowledge, training data, or retrieval context for another customer
2. THE following SHALL be forbidden for cross-tenant retrieval or learning: prompts, campaign concepts, stories, Talent data, Creative DNA, assets, conversations, workflows, generated media, strategy documents, workspace knowledge, and Brain memory
3. Platform-level learning MAY use aggregated and de-identified signals for: UX improvement, routing optimization, success rate analysis, assistance pattern improvement, performance optimization, recommendation quality, and general capability improvement
4. THE Platform SHALL distinguish "learning how to help users generally" from "learning a specific customer's creative ideas" — the former is permitted, the latter is forbidden
5. Cross-tenant retrieval of protected creative content SHALL be treated as a P0 security incident equivalent to a tenant isolation breach

---

### Requirement 96: Workspace Content Ownership

**Status:** NEW in Rev 4

**User Story:** As a workspace owner, I want workspace-created content to remain workspace property when team members leave.

#### Acceptance Criteria

1. Content created within a workspace SHALL belong to the workspace (organization), including: Talent, projects, assets, LoRA models, Creative DNA, recipes, workflows, workspace-shared knowledge, metadata, and recorded decisions
2. WHEN a member leaves or is removed from a workspace: workspace material SHALL remain accessible to remaining members, the departing user's personal connections SHALL be revoked from workspace use, personal credentials SHALL become inaccessible to the workspace, workspace connections SHALL remain functional, unfinished jobs owned by the departing user SHALL be reassigned or paused, and scheduled operations requiring the departing user's personal credentials SHALL pause and request reauthorization
3. Account deletion by a user SHALL NOT delete the organization's workspace — ownership transfer to another admin/owner SHALL be required before the final owner can delete their account
4. THE Platform SHALL NOT allow a user to export or take workspace-owned content with them when leaving unless the workspace admin explicitly grants export permission

---

### Requirement 97: Platform Operator Capability Model

**Status:** NEW in Rev 4

**User Story:** As a Founder, I want platform administration to use a granular capability model rather than an undifferentiated god role, so that operational access is proportional to responsibility.

#### Acceptance Criteria

1. THE Platform SHALL replace the concept of undifferentiated "Super Admin" with a capability-based Platform Operator model throughout all requirements, API endpoints, and UI
2. THE Platform SHALL define capability groups: Platform Observe, Tenant Support, Tenant Access Escalation, Platform Configuration, Financial Controls, Safety & Rights, Security Administration, Deployment/Operations, Release Management, Destructive Platform Actions, and Founder Authority
3. A Platform Operator MAY receive any permitted subset of capability groups — not all operators need the same access
4. THE Founder retains the broadest capability set without requiring every operator to have equivalent access
5. Platform Operators SHALL NOT receive unrestricted permanent access to private workspace creative content — elevated access SHALL require documented reason, identified operator, target workspace, permitted surfaces, configurable maximum duration (policy-determined), approval record, automatic expiration, and full audit trail
6. ALL Platform Operator actions SHALL be logged with capability used, actor, target, and timestamp

---

### Requirement 98: Agent Autonomy Profiles

**Status:** NEW in Rev 4

**User Story:** As a workspace admin, I want to configure how much autonomous authority Brain/Hermes has, so that teams can choose their comfort level.

#### Acceptance Criteria

1. THE Platform SHALL support configurable agent autonomy profiles per workspace: ADVISORY (recommend only — no mutations without explicit user instruction), ASSISTED (low-risk actions auto-execute, high-risk actions require user confirmation), and AUTONOMOUS_WITHIN_LIMITS (delegated actions execute within configured limits without per-action confirmation)
2. Mandatory safety, security, consent, budget, destructive-action, and legal controls SHALL be enforced regardless of the active autonomy profile — autonomy profiles control convenience delegation, not security bypass
3. Users and workspace admins MAY delegate specific action classes to Hermes — delegated permissions SHALL be: capability-specific (scoped to named actions), connection-specific (scoped to named integrations), revocable (effective immediately), auditable (full trail), role-scoped (cannot exceed delegator's own permissions), and subject to the Governance_Boundary (R59)
4. THE Platform SHALL log all autonomous agent actions with the same detail as human-initiated actions

---

### Requirement 99: User-Facing Agent Activity History

**Status:** NEW in Rev 4

**User Story:** As a user, I want to see what Brain/Hermes did on my behalf in plain language.

#### Acceptance Criteria

1. THE Platform SHALL provide a human-readable agent activity history answering "What did Brain/Hermes do?" — including: recommendations made, tool calls executed, jobs dispatched, approvals requested and resolved, connections used, changes made, failures encountered, costs incurred, and outputs produced
2. THE agent activity history SHALL be presented as a user-friendly activity feed — separate from engineering/debug logs and system observability data
3. THE agent activity history SHALL be scoped to the requesting user's sessions and workspace — users SHALL NOT see other users' agent activity unless workspace policy explicitly shares it
4. Each activity entry SHALL include: timestamp, action type, outcome (success/failure/pending), and cost (if applicable)

---

### Requirement 100: Undo and Recovery for AI-Assisted Operations

**Status:** NEW in Rev 4

**User Story:** As a content creator, I want to undo AI-assisted mutations where feasible, and be clearly warned when an operation is irreversible.

#### Acceptance Criteria

1. WHEN a mutating AI-assisted operation is performed, THE Platform SHALL preserve sufficient state for reversal where technically feasible (e.g., previous asset version, previous DNA version, previous workflow state)
2. Irreversible operations SHALL be: classified as such by the Governance_Boundary, subject to stronger confirmation requirements (per R53 risk-tier confirmations), and communicated to the user as irreversible BEFORE execution
3. THE Platform SHALL NOT guarantee undo for all operations — operations involving external side effects (published content, consumed GPU time, sent messages) MAY be irreversible by nature

---

### Requirement 101: Notification System

**Status:** NEW in Rev 4

**User Story:** As a user, I want to be notified about important events without needing to watch the screen constantly.

#### Acceptance Criteria

1. THE Platform SHALL define a canonical notification model with categories: job completed, job failed, approval requested, approval resolved, connection expired/degraded, provider unavailable, publishing complete/failed, budget threshold reached, safety/takedown action, and Hermes needs input
2. THE Platform SHALL deliver notifications in-app as the canonical channel — with future adapter support for: email, push notifications, SMS, and messaging platforms (Telegram, Slack)
3. Users SHALL be able to control notification preferences per category where safety and platform policy permits — mandatory notifications (safety, takedown, legal) SHALL NOT be disableable

---

### Requirement 102: Provider Fallback Preference

**Status:** NEW in Rev 4

**User Story:** As a workspace admin, I want to control what happens when my preferred provider is unavailable.

#### Acceptance Criteria

1. THE Platform SHALL support per-workspace provider fallback preference: AUTO (automatically route to next available alternate provider), ASK (present alternatives and request user confirmation before switching), or STRICT (fail or queue the request rather than using an alternate provider)
2. Privacy and data-location policies (per R103) SHALL override fallback preference — if AUTO fallback would route to a provider disallowed by privacy policy, THE Platform SHALL treat the request as STRICT
3. THE Platform SHALL apply fallback preference to all provider types: LLM, compute, storage, and voice/audio

---

### Requirement 103: Workload Privacy and Provider Restrictions

**Status:** NEW in Rev 4

**User Story:** As a workspace admin, I want to restrict which providers and infrastructure my workspace's data can flow through.

#### Acceptance Criteria

1. THE Platform SHALL support workspace-level privacy and provider restrictions: local models only (no external LLM calls), customer-managed compute only (no platform GPU), approved LLM providers only (whitelist), no external LLM for designated projects, approved storage providers only, Talent-specific provider restrictions, and project-specific privacy settings
2. Brain/Hermes, LLM routing, job dispatch, and all execution paths SHALL respect workspace privacy restrictions — a restricted workspace SHALL never have its data processed by a disallowed provider
3. IF a workspace's restrictions prevent fulfilling a request (e.g., all allowed providers are unavailable), THE Platform SHALL return an appropriate error indicating the restriction rather than silently violating it

---

### Requirement 104: Workspace Data Portability

**Status:** NEW in Rev 4

**User Story:** As a workspace owner, I want to export my workspace's creative data in a portable format.

#### Acceptance Criteria

1. THE Platform SHALL support workspace data export including: Talent metadata and relationships, Creative DNA, recipes, project metadata, prompts and generation parameters, provenance records, workflow definitions, model/LoRA metadata (not necessarily binaries), asset references (with optional binary export), consent records, and workspace knowledge
2. Data export SHALL NOT expose: provider secrets, another user's private Brain memory, internal platform configuration, or infrastructure credentials
3. THE export format SHALL be machine-readable and documented, enabling import into other systems or future re-import

---

### Requirement 105: External Deletion Propagation

**Status:** NEW in Rev 4

**User Story:** As a platform operator, I want deletion state to honestly reflect whether external objects have actually been removed.

#### Acceptance Criteria

1. THE Platform SHALL track deletion states for assets with external storage: removed from AI Studio (database soft-deleted), external deletion requested (storage API called), external deletion confirmed (storage confirms removal), external deletion failed (storage API failed, retry needed), retained by legal hold (deletion blocked by hold), and retained by backup lifecycle (may exist in backups per retention policy)
2. THE Platform SHALL NOT claim an external object is deleted unless deletion has been confirmed where confirmation is technically possible
3. WHEN external deletion fails, THE Platform SHALL retry with backoff and surface the failure to Platform Operators for investigation

---

### Requirement 106: Feature Rollout Controls

**Status:** NEW in Rev 4

**User Story:** As a Founder/Operator, I want granular control over which users and workspaces can access new or sensitive features.

#### Acceptance Criteria

1. THE Founder or Platform Operator (with Platform Configuration capability) SHALL be able to roll capabilities out: globally, by plan tier, by specific workspace, by beta cohort, by individual user, by workload type, or by provider
2. Feature rollout controls SHALL apply to: platform-managed GPU, hybrid compute mode, adult content eligibility, new AI models, agent autonomy levels, publishing platforms, and experimental features
3. WHEN a capability is disabled for a user/workspace through rollout controls, it SHALL be unavailable through ALL surfaces: UI (not shown), API (rejected), Brain/Hermes (not recommended or invokable), MCP (not available), and direct execution paths

---

## PRIORITY TIER P2-D: Analytics and Intelligence (New)

---

### Requirement 107: Social Performance Analytics and Audience Growth Intelligence

**Status:** NEW in Rev 4

**User Story:** As a content creator, I want to understand how my published content performs across platforms with growth trends and creative performance analysis.

#### Acceptance Criteria

1. THE Platform SHALL retrieve social performance analytics from connected platforms (Instagram, TikTok, YouTube, future platforms) where workspace has authorized connections
2. THE Platform SHALL store normalized metrics associated with: workspace, connected account, post, asset, Talent, project, and timestamp — metrics include where available: views, reach, likes, comments, shares, saves, watch time, completion rate, CTR, profile visits, follower changes, engagement rate, audience demographics, and traffic sources
3. THE Platform SHALL normalize metrics across platforms while preserving original platform-specific values — cross-platform comparison views SHALL be available
4. THE Platform SHALL support audience growth trend analysis: follower growth, engagement trend, reach trend, and content velocity — with historical metric snapshots for time-series analysis
5. Brain/Hermes SHALL be able to answer growth and performance questions using the workspace's authorized analytics data
6. THE Platform SHALL support performance analysis by creative attributes: Talent, model used, content type, duration, aspect ratio, recipe, style, campaign, and platform
7. THE Platform SHALL support pattern identification: above-baseline engagement, unusual growth spikes, better-performing formats, and poor performance patterns
8. Recommendations SHALL be advisory unless autonomous publishing is explicitly delegated via R98 autonomy profiles
9. Analytics SHALL be tenant-isolated — no workspace can see another workspace's analytics
10. Missing metrics SHALL be represented as UNAVAILABLE — THE Platform SHALL NOT fabricate values
11. Manual refresh and scheduled sync SHALL be subject to platform API rate limits — failed sync SHALL NOT affect publishing capability
12. Recommendations SHALL explicitly distinguish: observed fact, statistical pattern, AI interpretation, and suggested experiment

---

### Requirement 108: Market, Competitor, and Public Content Intelligence

**Status:** NEW in Rev 4

**User Story:** As a content strategist, I want to understand the competitive landscape using publicly available data and approved intelligence sources.

#### Acceptance Criteria

1. THE Platform SHALL support analysis from multiple data sources: first-party analytics (from connected accounts), publicly available content/metrics, approved third-party intelligence providers, user-supplied data, and future platform APIs
2. THE Platform SHALL classify all data with provenance: FIRST_PARTY_CONNECTED, PUBLIC_PLATFORM_DATA, THIRD_PARTY_DATA, USER_IMPORTED, and DERIVED_ANALYSIS
3. THE Platform SHALL NOT assume unrestricted access to another user's private analytics — public metrics and private analytics SHALL be explicitly distinguished
4. THE Platform SHALL support competitive comparison where publicly available data permits: followers, growth rate, posting frequency, public engagement, format preferences, hashtag usage, posting cadence, and creative patterns
5. THE Platform SHALL support watchlists: creators, brands, competitors, topics, and hashtags that the workspace wants to track
6. Brain/Hermes SHALL be able to answer competitive questions, identifying the source of each insight (private analytics, public data, third-party, historical observation, or inference)
7. THE Platform SHALL never represent estimates or inferences as private analytics data — observed growth calculations SHALL be identified as estimates
8. THE Platform SHALL respect platform terms of service, API permissions, rate limits, and privacy restrictions when gathering intelligence
9. THE Platform architecture SHALL permit approved third-party SocialIntelligenceProvider implementations — with the specific providers determined separately
10. Missing data SHALL be represented as UNAVAILABLE — THE Platform SHALL NOT fabricate competitive intelligence

---

## PRIORITY TIER P0-C: Deployment Reality (New)

---

### Requirement 109: Deployment Reality Update

**Status:** NEW in Rev 4

**User Story:** As a platform operator, I want honest assessment of deployment state reflected in requirements and verification criteria.

#### Acceptance Criteria

1. THE Platform SHALL acknowledge that Vercel has demonstrated at least one successful READY deployment from the main branch — this establishes architectural feasibility but not production readiness
2. Deployment architecture SHALL be classified as "demonstrated but unstable" until repeatability is independently proven — THE Platform SHALL NOT claim production deployment capability based on a single successful deployment
3. A single successful deployment SHALL NOT constitute production readiness evidence — repeatable deployment from the canonical branch on demand SHALL be required
4. Deployment with ignored, disabled, or suppressed required build errors SHALL NOT constitute clean production evidence — all TypeScript errors, ESLint errors, and Next.js build errors SHALL be zero for a clean deployment
5. THE Platform SHALL track deployment success rate over time as evidence toward stability classification

---

## Unresolved Decisions

The following require product, specialist, or operational decisions before implementation can proceed.

### Founder/Product Decisions

| # | Decision Needed | Impact | Current Assumption |
|---|---|---|---|
| 1 | Pricing/plan structure and tier limits | Entitlements, billing | Deferred until first paying customer |
| 2 | Default adult content policy | Safety configuration, platform reputation | SFW_ONLY default assumed |
| 3 | AI/synthetic media disclosure policy at launch | R80 publishing hooks | Undecided — no universal rule hardcoded until policy approved |

### Specialist Review Required

| # | Decision Needed | Specialist | Current Assumption |
|---|---|---|---|
| 4 | Production key/secrets authority | Security | Which system holds master keys, rotation policy, break-glass procedures |
| 5 | Exact retention periods for safety/consent/audit data | Legal + Privacy | Initial defaults in R42; specialist review may adjust |
| 6 | Jurisdiction-specific consent requirements | Legal | Generic consent model — jurisdiction-specific rules TBD |
| 7 | Adult content jurisdiction restrictions | Legal + Safety | No jurisdiction-specific restrictions beyond Safety Kernel |
| 8 | Provider data-collection permissions per platform | Legal | Platform ToS compliance assumed sufficient |
| 9 | Model risk classification criteria | Security + ML Ops | Two classes (STANDARD auto-promote, HIGH_RISK requires human) |

### Operational/Implementation Decisions (safe for design/implementation phase)

| # | Decision Needed | Impact | Current Assumption |
|---|---|---|---|
| 10 | Orphaned data disposition (per-table reconciliation) | R69 quarantine | Per-table review during schema remediation |
| 11 | Connection ownership defaults | R85/R92 | WORKSPACE for social/compute, USER for AI keys |
| 12 | Load testing numeric targets | R91 scalability | Finalized during performance testing phase |
| 13 | Third-party SocialIntelligenceProvider selection | R108 Market Intelligence | None at launch — architecture supports future addition |
| 14 | Capacity alerting thresholds | R90 capacity management | Need operational baseline before setting |
| 15 | Support session maximum duration policy | R97 Platform Operators | Configurable; policy-determined default TBD |


---

## Test Priority Matrix

Per Requirement 51, tests SHALL be created in this risk-priority order:

| Priority | Category | Risk if Untested | Example Test |
|---|---|---|---|
| 1 | Tenant isolation | Data leak between orgs | Insert as org A, read as org B → 404 |
| 2 | Authentication | Unauthorized access to all data | No JWT → 401 on every endpoint |
| 3 | Authorization | Privilege escalation | Viewer attempts DELETE → 403 |
| 4 | Safety kernel | Illegal content generated | CSAM-adjacent prompt → blocked |
| 5 | Consent enforcement | Unauthorized use of real person | No consent → generation blocked |
| 6 | Destructive actions | Accidental data loss | Delete without approval → blocked |
| 7 | Cost controls | Runaway spend | Over-budget job → 402; reservation prevents overdraft |
| 8 | Credential isolation | Worker accesses other org's data | Job credential scoped to single org |
| 9 | Cross-tenant learning | Customer ideas leaked to other tenant | Private creative content not in another user's context |
| 10 | Platform learning isolation | De-identified boundary violated | Raw creative content in platform learning layer → blocked |
| 11 | Job idempotency | Duplicate billing | Same idempotency_key → existing job returned |
| 12 | Governance boundary | Bypass of approval | AI-initiated side effect without governance check → blocked |
| 13 | Trust domain separation | Internal knowledge leaked to customer | FOUNDER_PRIVATE content in Brain session → blocked |
| 14 | Brain memory isolation | User A's memory in User B's session | Private memory not injected cross-user |
| 15 | Provider failure | Silent failure, stuck jobs | Provider timeout → retry → fail gracefully |
| 16 | Compute availability | Forged platform-compute request when DISABLED | API rejects with 403 when state is DISABLED |
| 17 | Workspace content ownership | Content lost when member leaves | Member removal preserves workspace assets |
| 18 | Migrations | Schema drift, broken deploy | Clean DB + all migrations → all queries pass |
| 19 | Release identity | Untraceable production behavior | Deploy without Release_Identity → blocked |
| 20 | Deployment | App won't start | Build succeeds, /ready returns 200 |
| 21 | User journeys | Broken core flows | Login → create talent → generate → view asset |
