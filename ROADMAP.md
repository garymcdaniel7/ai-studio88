# AI Studio — Roadmap

> Last updated: 2026-07-03

---

## Phase 1 — Foundation (Current)

Core platform infrastructure. Goal: working API with auth, basic CRUD, and one end-to-end generation job.

- [ ] Project structure and tooling setup
- [ ] FastAPI application scaffold
- [ ] Supabase auth integration (JWT validation middleware)
- [ ] Core data models: Organisation, User, AiTalent, Campaign, Asset
- [ ] Database migrations with Alembic
- [ ] Backblaze B2 upload service
- [ ] Vast.ai GPU provisioning service
- [ ] First ComfyUI workflow integration (Flux image generation)
- [ ] Job queue (Celery + Redis)
- [ ] Basic API health check and readiness endpoints
- [ ] Docker Compose for local development
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Environment bootstrap scripts

---

## Phase 2 — Core Feature Set

Goal: full AI talent management, image generation pipeline, and basic content calendar.

- [ ] AI Talent CRUD with profile management
- [ ] Brand and Product management
- [ ] Campaign creation and management
- [ ] Content Calendar with scheduling
- [ ] Image generation pipeline (Flux SDXL via ComfyUI)
- [ ] Asset management and organisation
- [ ] Signed URL delivery for assets
- [ ] Webhook callbacks for job completion
- [ ] Basic admin dashboard (API explorer)
- [ ] Rate limiting per tenant
- [ ] Usage tracking and quotas

---

## Phase 3 — LoRA Training

Goal: end-to-end LoRA training for custom AI characters.

- [ ] Training job creation and management
- [ ] Dataset upload and validation
- [ ] Vast.ai training instance provisioning
- [ ] LoRA training pipeline (Kohya / SimpleTuner)
- [ ] Training progress tracking (real-time via Supabase Realtime)
- [ ] Model versioning and storage
- [ ] Training cost estimation
- [ ] Auto-cancel for stalled jobs

---

## Phase 4 — Video and Voice

Goal: multi-modal content generation.

- [ ] WAN video generation pipeline
- [ ] LTX Video integration
- [ ] Video job management and progress tracking
- [ ] Voice generation integration (ElevenLabs or open-source)
- [ ] Voice profile management per AI talent
- [ ] Audio-video synchronisation pipeline
- [ ] Video storage and CDN delivery

---

## Phase 5 — Multi-tenant SaaS

Goal: production-ready multi-tenant platform with billing.

- [ ] Organisation management
- [ ] Role-based access control (owner, admin, editor, viewer)
- [ ] Stripe billing integration
- [ ] Subscription plans (starter, pro, enterprise)
- [ ] Usage-based billing for GPU jobs
- [ ] Team invitations and user management
- [ ] Audit logging
- [ ] GDPR compliance (data export, deletion)
- [ ] SSO / OAuth (Google, GitHub)

---

## Phase 6 — Analytics and Intelligence

Goal: actionable insights for content performance and cost optimisation.

- [ ] Generation cost tracking per job
- [ ] GPU utilisation dashboard
- [ ] Content performance analytics (views, engagement via API)
- [ ] Campaign ROI tracking
- [ ] Cost forecasting
- [ ] Model performance comparison
- [ ] Automated content quality scoring

---

## Phase 7 — Scale and Resilience

Goal: production hardening for thousands of concurrent jobs.

- [ ] RunPod GPU provider integration
- [ ] Multi-provider GPU scheduling (cost arbitrage)
- [ ] Horizontal API scaling
- [ ] Multi-region deployment
- [ ] PgBouncer connection pooling
- [ ] Redis cluster
- [ ] Distributed tracing (OpenTelemetry)
- [ ] Automated failover
- [ ] Load testing baseline (Locust)

---

## Phase 8 — Frontend Dashboard

Goal: full web application for non-technical users.

- [ ] Next.js 14+ app with App Router
- [ ] Authentication flow (Supabase Auth UI)
- [ ] Talent management interface
- [ ] Campaign builder
- [ ] Content calendar view
- [ ] Generation queue monitor
- [ ] Asset browser
- [ ] Training dashboard
- [ ] Analytics visualisation
- [ ] Mobile-responsive design
- [ ] Dark mode

---

## Backlog (unscheduled)

- Marketplace for sharing ComfyUI workflows
- API SDK (Python, JavaScript)
- Zapier / Make integration
- White-label support
- On-premise deployment option
- Model hub integration (Civitai, HuggingFace)
- A/B testing for prompts
- Automated content posting (Instagram, TikTok APIs)
- AI prompt optimisation
