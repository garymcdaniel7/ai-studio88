# Scaling Strategy

## Overview

This document defines the horizontal vs vertical scaling strategy for each AI Studio system component. The architecture ensures that user growth does not require proportional GPU scaling, and that job transport technology is replaceable without changing the public API contract.

Validates: Requirements R91.1, R91.3, R91.4, R76.8, R76.10

## Design Principles

1. **User growth is independent of GPU capacity** — registering users, managing talent, chatting with Brain, and browsing assets requires zero GPU resources.
2. **Compute scales on demand** — GPU workers are provisioned per-job and terminated on completion; capacity is elastic and provider-agnostic.
3. **Job transport is an implementation detail** — the public API contract (POST job → 202, GET status → 200) is stable regardless of whether the backend uses Supabase polling, Celery+Redis, SQS, or any other queue.
4. **Backend is stateless** — all persistent state lives in Supabase or external storage. Multiple backend instances serve requests behind a load balancer without shared in-process state.

## Component Scaling Matrix

| Component | Scaling | Strategy | Current Constraint |
|-----------|---------|----------|--------------------|
| Backend (FastAPI) | Horizontal | Stateless behind load balancer; multiple instances | Single instance in dev; Railway/Render multi-instance ready |
| Database (Supabase PostgreSQL) | Vertical + Read Replicas | Connection pooling (PgBouncer); vertical via plan upgrade; read replicas for read scaling | Supabase Pro plan connection limits |
| Storage (Backblaze B2) | Managed (auto-scales) | Pay-per-use, no capacity planning | None — effectively unlimited |
| GPU Compute | Horizontal | Provider-abstracted; workers spin up/down per job; multiple providers | Provider availability + budget limits |
| Realtime (Supabase Realtime) | Managed (auto-scales) | WebSocket connections managed by Supabase | Plan-level connection limits |
| Brain/LLM | Horizontal | Provider routing adds capacity without code changes; local + cloud concurrent | Provider API rate limits |

## Backend: Stateless FastAPI

The FastAPI backend is designed to be fully stateless:

- **No in-memory singletons** storing request-scoped or user-scoped data
- **No local file state** — all uploads go to B2 via the StorageProvider interface
- **No session affinity required** — any backend instance can serve any request
- **Job state** persisted in Supabase `jobs` table, not in worker memory
- **Provider reputation** persisted in Supabase, not in-memory dicts
- **Brain conversations** persisted in Supabase, not process memory
- **Cost tracking** persisted in Supabase cost tables

This means:
- Multiple backend instances can run behind a load balancer (Railway, Render, Kubernetes)
- A backend restart loses zero state
- Horizontal scaling is adding instances; no code changes needed

## Database: Supabase PostgreSQL

Primary scaling strategy is vertical (larger Supabase plan), with horizontal read scaling via read replicas:

- **Connection pooling**: PgBouncer manages connection limits efficiently
- **Indexes**: org_id, created_at, status columns indexed for fast tenant-scoped queries
- **Read replicas**: Available for read-heavy analytics/reporting workloads
- **Write bottleneck**: Single writer; mitigated by efficient transactions and job leasing (FOR UPDATE SKIP LOCKED)

Capacity planning:
- 6000 registered users with hundreds simultaneously active is well within PostgreSQL capacity
- Supabase Pro supports thousands of concurrent connections via pooling
- Sharding is not needed at this scale

## Storage: Backblaze B2

No action needed for scaling:

- B2 is an object store with no capacity limits per account
- Pay-per-GB-stored and per-operation
- CDN (Cloudflare or B2 native) handles read traffic scaling
- Multipart upload for files > 100 MB ensures large file handling doesn't block

## GPU Compute: Provider-Abstracted

GPU compute scales independently of user growth:

- **Architecture**: ComputeProvider interface abstracts all GPU vendors
- **Scaling**: Adding more GPU providers or workers is a configuration change, not a code change
- **Independence**: A user base of 6000 vs 60000 requires zero additional GPU resources unless generation demand increases
- **Providers**: RunPod (primary), FluidStack, Lambda Labs, TensorDock — each independently available
- **Customer-managed**: Customers can bring their own GPUs, scaling their own capacity without platform changes

Key independence proof:
- User CRUD (talent, projects, assets) → hits Supabase only
- Brain chat → hits LLM provider only
- Image generation → hits GPU provider only when user explicitly requests
- No background GPU processes tied to user count

## Realtime: Supabase Realtime

Managed WebSocket service:

- Scales with connection count (Supabase manages infrastructure)
- Tenant authorization enforced on subscriptions
- Cursor-based resumption handles disconnects gracefully
- No backend state needed for realtime — backend publishes events, Supabase distributes

## Brain/LLM: Provider Routing

LLM capacity scales horizontally through provider routing:

- **Multiple providers**: Ollama (local), OpenAI, Anthropic, OpenRouter, custom endpoints
- **Dynamic routing**: Health-check-based selection; unhealthy providers skipped automatically
- **Adding capacity**: Register a new provider → immediately available for routing
- **No single point of failure**: If one provider is down, traffic routes to others
- **Local inference**: Ollama on user's machine scales with user's hardware at zero platform cost

## Job Transport Replaceability

The job system's public API contract is stable regardless of backend implementation:

```
POST /api/v1/jobs          → 202 {id, status: "queued"}
GET  /api/v1/jobs/{id}     → 200 {id, status, progress_percent, ...}
POST /api/v1/jobs/{id}/cancel → 200
```

Current implementation: Supabase job table with polling + lease (FOR UPDATE SKIP LOCKED).

This can be replaced with Celery+Redis, SQS, Temporal, or any other queue without:
- Changing the API endpoints
- Changing the frontend code
- Changing the job submission interface
- Changing the status polling interface

The `JobService` is the abstraction layer. Compute dispatch goes through `ComputeProvider`. Neither the API layer nor the frontend knows or cares about the queue technology.

## Load Testing Targets

Verification targets (to be proven through load testing before broad availability):

| Metric | Target |
|--------|--------|
| Registered users | 6000+ |
| Simultaneously active | Hundreds |
| Concurrent sessions | 1000+ |
| Generation request bursts | Handled via job queue |
| Concurrent video/training jobs | Limited by GPU budget, not architecture |
| Concurrent Brain streams | Limited by LLM provider capacity |

These are verification targets, not architecture guarantees. The architecture is designed to support them; load testing proves they are met.

## Summary

| Concern | Scales With | Independent Of |
|---------|-------------|----------------|
| User registrations | Database capacity | GPU count |
| Talent/Asset CRUD | Database + Storage | GPU count, LLM providers |
| Brain conversations | LLM provider capacity | GPU count, user count |
| Image generation | GPU provider pool | User count, database size |
| Video generation | GPU provider pool | User count |
| Training jobs | GPU provider pool | User count |
| Realtime events | Supabase plan | Everything else |
| Storage | B2 (unlimited) | Everything else |
