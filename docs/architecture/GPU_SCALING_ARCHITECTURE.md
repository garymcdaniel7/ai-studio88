# GPU Worker Scaling Architecture — Cost Tiers & Provider Routing

**Status:** Recommended design for product/eng review  
**Scope:** Autoscaling triggers, provider selection (Thunder vs RunComfy), SFW/NSFW cost tiers, runaway-cost prevention  
**Existing code touched:** `backend/worker.py`, `backend/infrastructure/auto_provisioner.py`, `backend/app/services/job_type_config.py`, `backend/app/schemas/validation.py`, `backend/infrastructure/worker_registry.py`

---

## 1. Provider Landscape (As-Is)

| Provider | GPU (price/hr) | Autoscaling | NSFW | Notes |
|---|---|---|---|---|
| Thunder Compute | A6000 ($0.35), A100 ($1.29), H100 ($3.09) | Fixed (you rent N boxes) | ✅ Yes | Bill per minute; snapshots available; 20-min spinup |
| RunComfy (Serverless API) | A6000 ($2.50), A100 ($4.99) | ✅ Built-in (min/max instances, queue threshold, keep-warm) | ✅ Yes | Per-second billing; webhooks; no infra management |
| Vast.ai / RunPod (retired) | — | — | — | Replaced by Thunder; code still in `auto_provisioner.py` |

**Key asymmetry:** Thunder is cheap but fixed-capacity (~$0.35/hr A6000). RunComfy is 7× more expensive but autoscales. The right strategy: **Thunder is baseline capacity, RunComfy is overflow/elastic tier.**

---

## 2. Content Tier Model

Introduce a `content_tier` enum on the `jobs` table (alongside existing `workload_class`) to separate infrastructure paths:

```python
class ContentTier(str, enum.Enum):
    SFW = "sfw"        # General-purpose, Stripe-billed
    NSFW = "nsfw"      # Adult content, CCBill-billed (or separate merchant)
```

### Where it lives

- **New DB column:** `jobs.content_tier` (nullable, defaults to `"sfw"` for backwards compat)
- **New schema field:** `ContentTier` enum in `backend/app/schemas/validation.py`
- **New job input field:** `content_tier` on `JobCreate` (optional — inferred from workspace/plan settings)
- **Provider routing decision:** Uses workload_class + content_tier to pick GPU provider

### Why two tiers, not per-workload-class pricing

Cost differentiation should be at the **billing/merchant level**, not the GPU level. NSFW content is identical to SFW content in GPU requirements (both run ComfyUI workflows). What differs is:

1. **Payment processor:** Stripe forbids NSFW → CCBill needed
2. **GPU provider choice:** RunComfy doesn't care about content; Thunder doesn't care — both work for either tier
3. **Margin strategy:** SFW can absorb higher costs; NSFW pricing should account for CCBill's higher fees (~8-12% vs 2.9%)

---

## 3. Provider Selection Logic

### Decision flow (replacing `_select_provider` in `auto_provisioner.py`)

```
                         ┌──────────────────────┐
                         │  Job enters queue     │
                         │  (has content_tier,   │
                         │   workload_class)     │
                         └──────┬───────┬───────┘
                                │       │
                       ┌────────▼──┐ ┌──▼────────┐
                       │ Thunder   │ │ RunComfy  │
                       │ available?│ │ (always)  │
                       └──┬────┬───┘ └────┬──────┘
                          │YES │NO       YES
                          ▼    │          │
                   ┌──────────┐│    ┌─────▼──────────┐
                   │ Assign to ││    │ Submit to      │
                   │ Thunder   ││    │ RunComfy API   │
                   │ worker    ││    │ (autoscaling)  │
                   └──────────┘│    └────────┬───────┘
                              │              │
                   ┌──────────▼──┐           │
                   │ Queue depth │           │
                   │ > threshold?│           │
                   │ (default 3) │           │
                   └──┬──────┬──┘            │
                    YES      │NO             │
                     ▼       │               │
              ┌──────────┐   │               │
              │ Spawn     │   │               │
              │ RunComfy  │   │               │
              │ instance  │   │               │
              └─────┬─────┘   │               │
                    │         │               │
              ┌─────▼─────────▼───────────────▼──┐
              │  Worker picks up job             │
              │  (Thunder worker → ComfyUI at    │
              │   64.247.206.140:30209;           │
              │   RunComfy → POST /prod/v2/...)   │
              └──────────────────────────────────┘
```

### Concrete rules

```python
def select_provider(workload_class: str, content_tier: str, queue_depth: int) -> str:
    """
    Returns 'thunder' or 'runcomfy'.

    Thunder = cheap base capacity.
    RunComfy = elastic overflow.
    """

    # 1. Check if any Thunder worker is idle and can handle this workload class
    thunder_available = worker_registry.has_idle_worker(
        min_vram=_VRAM_REQUIREMENTS.get(workload_class, 24)
    )

    if thunder_available:
        # Thunder has capacity — use it
        return "thunder"

    # 2. Queue depth check — is it worth auto-spawning RunComfy?
    #    RunComfy minimum cost is ~$2.50/hr (= $0.042/min).
    #    A single image gen takes ~30s → $0.021 per job.
    #    If queue depth < 3, RunComfy costs more than waiting 10s for Thunder.
    if queue_depth < int(os.getenv("RUNCOMFY_QUEUE_THRESHOLD", "3")):
        return "wait"  # Don't spawn — let Thunder catch up

    # 3. Spill to RunComfy
    return "runcomfy"
```

---

## 4. Autoscaling Logic

### 4a. RunComfy Autoscaling Parameters (set per deployment in RunComfy dashboard)

RunComfy natively supports autoscaling via **min/max instances, queue threshold, keep-warm duration**. Configure one deployment per workload class:

| Workload Class | GPU | Min | Max | Queue Threshold | Keep-Warm |
|---|---|---|---|---|---|
| `image_generation` | A6000 ($2.50/hr) | 0 | 3 | 5 pending jobs | 60s |
| `video_generation` | A100 ($4.99/hr) | 0 | 2 | 3 pending jobs | 120s |
| `training` | A100 ($4.99/hr) | 0 | 1 | 1 pending job | 300s |
| `batch` | A6000 ($2.50/hr) | 0 | 3 | 10 pending jobs | 120s |

### 4b. Auto-Spawn Logic (when no RunComfy instance is running)

When `select_provider` returns `"runcomfy"`, the auto_provisioner must:

1. Check if a RunComfy request is already in-flight (cooldown: 60s — RunComfy instances take ~30-60s to boot)  
2. POST to RunComfy's `POST /prod/v2/deployments/{deployment_id}/inference` with the job payload  
3. Attach a `webhook` URL pointing to the backend (e.g. `POST /api/v1/infrastructure/runcomfy/webhook`)  
4. Set `webhook_intermediate_status: true` to get queue/start/completion events

**Critical:** Do NOT spawn multiple RunComfy instances for jobs that could be handled by one. RunComfy's own autoscaling handles multi-instance — we submit to the deployment endpoint and RunComfy queues/spawns internally.

### 4c. Keep-Warm Logic (Thunder workers)

Thunder workers cost $0.35/hr whether they're working or not. RunComfy scales to zero. Strategy:

- **Thunder workers:** Stay alive during business hours (9AM-11PM), destroyed at night via cron
- **RunComfy:** Auto-scales to zero instantly — no action needed
- **Night-time overflow:** If a batch job arrives at 2AM and Thunder is offline, RunComfy auto-spawns from 0 and bills only for actual GPU time

---

## 5. Scaling Triggers

### Primary trigger: Queue depth

| Threshold | Action | Rationale |
|---|---|---|
| Queue > 0 AND Thunder worker idle | Assign to Thunder | $0.35/hr is baseline |
| Queue > 3 | Spawn RunComfy deployment request | One RunComfy instance handles the batch |
| Queue > 10 | Increase RunComfy max_instances by 1 (capped at per-deployment max) | RunComfy's internal queue triggers multi-instance |
| Queue = 0 for > 5 min | Keep-warm timer expires → RunComfy scales to zero | No idle GPU cost |

### Secondary trigger: Job type / VRAM demand

Jobs requiring >24GB VRAM (video, training) **cannot** run on Thunder's A6000 (24GB). These:

1. When Thunder is available with A100/H100 → assign to Thunder
2. Otherwise → always route to RunComfy A100 deployment (no queue-depth gate for video/training)

### Pricing / time-of-day trigger (optional)

Add a `RUNCOMFY_ACTIVATE_HOURS` config (default: any hour). Could gate RunComfy use to business hours if overnight GPU cost is a concern, but per-second billing makes this unnecessary — RunComfy scales to zero instantly.

---

## 6. Runaway Cost Prevention

### Per-user caps (DB-level, enforced at job submission)

| Cap | Scope | Default | Enforcement |
|---|---|---|---|
| `max_concurrent_jobs` | Per user | 3 | Reject submission with 429 |
| `max_daily_jobs` | Per user | 100 | Reject submission with 429 |
| `max_daily_spend_usd` | Per user | $50 | Reject when cumulative cost estimate exceeds cap |
| `max_concurrent_jobs_per_workspace` | Per workspace | 20 | Queued jobs past cap wait in pending state |

### Cost-estimate gating

Every job submission computes a **cost estimate** (max_duration × provider_rate × gpu_count) before accepting. If the user's `max_daily_spend_usd` would be exceeded, reject immediately with `{ "error": "DAILY_SPEND_LIMIT", "limit": 50, "estimated_cost": 12.50 }`.

### Burst protection

- **Rate limit job submissions:** 10/min per user
- **Queue depth warning:** When user has > 5 jobs queued, respond with estimated wait time instead of silent queueing
- **Kill switch:** Admin endpoint `POST /api/v1/infrastructure/fleet/killswitch` → sets a Redis flag that prevents any new RunComfy spawns (respects in-flight jobs to completion)

### Anti-runaway for RunComfy

RunComfy's own autoscaling has a **max_instances** hard cap (see table in §4a). Never set this above 3 for A6000 or 2 for A100. Combined with per-user caps, the maximum simultaneous spend is:

```
3 (max RunComfy instances) × $2.50/hr = $7.50/hr RunComfy
+ 1 Thunder worker × $0.35/hr = $0.35/hr
= $7.85/hr peak total GPU spend
```

Even with 100 jobs queued, you can't exceed ~$8/hr.

---

## 7. Pricing Model Recommendation

### Cost recovery per content tier

| Cost bucket | SFW | NSFW |
|---|---|---|
| GPU (Thunder A6000) | $0.35/hr | $0.35/hr |
| GPU (RunComfy A6000) | $2.50/hr | $2.50/hr |
| Payment processing | 2.9% + $0.30 (Stripe) | 8-12% (CCBill) |
| **Blended GPU cost per image** | ~$0.005 (10 images/min) | ~$0.005 (10 images/min) |

GPU cost is **identical** across tiers — both use the same ComfyUI workflows on the same GPU types. The differentiator is **payment processing margin**.

### Pricing recommendation

| User-facing price | SFW | NSFW |
|---|---|---|
| Per image generation | $0.049 | $0.099 |
| Per video generation (per clip) | $0.499 | $0.999 |
| LoRA training (per job) | $9.99 | $14.99 |

**Why not identical pricing?**
- NSFW carries higher payment processing fees (CCBill ~8-12% vs Stripe 2.9%+$0.30)
- NSFW has higher chargeback risk / regulatory overhead
- NSFW is price-inelastic — users willing to pay premium for uncensored access
- SFW price anchoring: $0.049/image is competitive with Replicate/Fal.ai ($0.002-0.013 per image for SDXL, but ours includes managed service, talent model, workspace features)

### Billing routing

| Payment processor | SFW | NSFW |
|---|---|---|
| Stripe (standard) | ✅ Primary | ❌ Prohibited by ToS |
| CCBill | ❌ Overkill | ✅ Primary |
| Crypto (optional) | ❌ | ✅ Alternative |

Implementation: `subscriptions` table gets a `payment_provider` column (`stripe` | `ccbill`). The billing system routes charges based on the **workspace's content_tier**, not per-job.

---

## 8. Migration Path

### Phase 1 — Add content_tier (no routing changes yet)

1. DB migration: `ALTER TABLE jobs ADD COLUMN content_tier VARCHAR(10) DEFAULT 'sfw';`
2. Add `ContentTier` enum + `content_tier` field to `JobCreate` schema
3. Backfill: all existing jobs → `sfw`
4. Deploy: no behavioral change yet

### Phase 2 — Thunder as primary, RunComfy as overflow

1. Register RunComfy as a compute provider in `get_provider_registry()` (like `thunder_provider.py`)
2. Add RunComfy client at `backend/providers/runcomfy/` with:
   - `client.py` — HTTP client for `POST /prod/v2/deployments/{id}/inference`
   - `webhook_handler.py` — validates RunComfy HMAC, updates `jobs.status`
3. Implement `_select_provider()` from §3 above
4. Wire queue-depth monitoring into the worker loop (worker already polls; add queue-depth check before `claim_next_job`)
5. Deploy with `RUNCOMFY_QUEUE_THRESHOLD=3` — RunComfy spawns only when Thunder is saturated

### Phase 3 — Content-tier billing

1. Add `payment_provider` to workspaces/subscriptions
2. Route Stripe charges → `content_tier=sfw`, CCBill → `content_tier=nsfw`
3. Differentiate pricing in the `generation_service.py` / `training_pipeline_service.py` cost estimators

### Phase 4 — Remove Vast/RunPod dead code

After verifying RunComfy + Thunder cover all workloads, delete:
- `backend/providers/vast/`
- `backend/providers/runpod/`
- `scripts/vast/`
- Vast/RunPod keys from `.env` template

---

## 9. Summary of Decisions

| Question | Decision |
|---|---|
| **Content tier as DB field?** | Yes — `jobs.content_tier` (becomes `sfw`/`nsfw`) |
| **Pricing per tier?** | Yes — NSFW ~2× SFW to cover CCBill fees + margin (GPU costs identical) |
| **CCBill for NSFW?** | Yes — Stripe prohibits adult content; CCBill is standard in the space |
| **Autoscaling engine?** | RunComfy's built-in (min/max instances, queue threshold, keep-warm). We submit + webhook; RunComfy handles multi-instance |
| **Autoscaling trigger?** | Queue depth > 3 AND no Thunder worker available. No time-of-day gate |
| **Provider selection?** | Thunder first (cheap, fixed cost) → spill to RunComfy (elastic, per-second billing) |
| **Runaway prevention?** | Per-user `max_concurrent_jobs=3`, `max_daily_spend=$50`, queue-depth warnings, admin kill switch. Peak GPU spend ~$8/hr capped |
| **Thunder keep-alive?** | Business hours only (9AM-11PM). Destroy at night; RunComfy handles off-hours overflow at near-zero base cost |