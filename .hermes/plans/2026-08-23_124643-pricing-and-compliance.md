# AI Studio — Pricing Architecture + Compliance Pipeline (Phased)

> **For Hermes/Kiro:** Execute workstream-by-workstream; each task is independently shippable. Triage bucket: KIRO EXECUTABLE unless marked GARY ACTION / DECISION REQUIRED.

**Goal:** Turn AI Studio's existing metering bones into a five-tier consumer subscription product with a compliance pipeline that keeps Gary legally protected while users create adult content with synthetic and (later) selfie-verified personal talents.

**Architecture:** Credits remain the metering spine (GPU-seconds, TTS chars, storage GB all reduce to credits). Subscriptions are prepaid credit bundles at a discount — no unlimited tiers, ever. Compliance is built as pipeline stages around the existing `aios` gateway + consent-enforcement tests, not as a bolt-on moderation queue.

**Tech Stack:** FastAPI backend (`backend/`), Supabase Postgres, RunPod serverless (pooled workers), B2 weights storage, ElevenLabs voice APIs, Stripe-or-adult-processor (see DECISION REQUIRED).

---

## Verified foundations (already in repo — do NOT rebuild)

| Exists | Where |
|---|---|
| Billing surface | `backend/billing_router.py` |
| Model/preset catalog | `backend/engine/preset_packs.py` (16 presets incl. WAN t2v/i2v) |
| Voice providers | `backend/audio/elevenlabs_provider.py`, `backend/providers/elevenlabs/client.py` (`eleven_turbo_v2`, `eleven_multilingual_v2`) |
| Consent enforcement tests | `backend/tests/unit/test_properties/test_property_19_consent_enforcement.py` |
| Quarantine/audit logging | `backend/alembic/versions/20260809_001_quarantine_log_and_org_id_backfill.py` |
| Object/place intelligence | `backend/object_intelligence/router.py`, `backend/continuity_model.py`, `backend/object_dna_contract.py` |
| GPU orchestration | `backend/providers/runpod/client.py`, `backend/infrastructure/auto_provisioner.py`, `backend/training/vast_provider.py` |

---

## Unit economics (Aug 2026 RunPod rates — re-verify quarterly)

| Generation | Est. platform cost | Credits charged | Margin |
|---|---|---|---|
| SDXL/Flux image (RTX 4090 @ ~$0.74/hr, 6–10s active) | ~$0.002–0.006 | 1 credit (≈$0.30 value) | ~98% |
| WAN 5s t2v/i2v (H100 @ ~$2.89/hr, 3–6 min wall) | ~$0.15–0.30 | 12–20 credits | ~85% |
| Long video 10s+ (multi-clip + FFmpeg assembly) | ~$0.60–1.20 | 40–80 credits | ~80% |
| ElevenLabs voiceover (turbo, ~900 chars/min) | ~$0.02–0.20/mo-tier dependent | 1 credit/min | ~90% |
| Third-party API models (Veo/Imagen via keys) | provider price | passthrough × 1.5 | 33% |

**Rule:** blended margin floor ≥ 75% after warm-worker idle costs. Warm pool budget: 1× RTX 4090-class worker always-on during beta (~$18/day max) — kill switch if weekly revenue < weekly idle spend.

---

## Tier structure

| Tier | Price | Monthly credits | Extras |
|---|---|---|---|
| Screen Test | Free (one-time grant) | 250 | Watermarked, queue-last |
| Day Player | $29/mo | 2,000 | All base presets |
| Series Regular | $99/mo | 8,000 | No watermark, all models, faster queue |
| Showrunner | $249/mo | 25,000 | Storyboard/continuity suite, priority queue, provenance certs |
| The Hefner | By application, ~$999+/mo | Custom | Dedicated warm capacity, concierge, human review pass, private LoRA training (Phase 2) |

Founding-member promo: first 100 paid accounts lock lifetime rate parity. Annual = 2 months free.

---

## Workstream A — Credit metering spine (KIRO EXECUTABLE)

### Task A1: Single source of truth for credit costs
- Create `backend/billing/credit_costs.py`: dict mapping `{preset_id, model_id} -> {gpu_class, est_active_seconds, credits}` sourced FROM `preset_packs.py` ids (16 presets listed above).
- Test: every id in `preset_packs.py` has an entry (fail loudly when a new preset ships unpriced).

### Task A2: Ledger + debit middleware
- Extend `billing_router.py` with `credit_ledger` table migration (grant/debit/refund/expire rows, org_id scoped per tenant model Option A).
- Debit happens **after** successful generation only; failed jobs auto-refund. Property test mirroring `test_property_19` style: ledger never goes negative without an overdraft row.

### Task A3: Tier definitions + grant scheduler
- `backend/billing/tiers.py` with the five tiers above; monthly cron grants credits; expiry on unused free-tier credits (90 days).

---

## Workstream B — Checkout & payments (DECISION REQUIRED first)

**DECISION REQUIRED (Gary):** payment processor posture.
- Recommendation: begin **CCBill application immediately** (weeks-long lead time, adult-approved, their audit becomes third-party validation). Stripe only if/when Phase-1 marketing stays fully SFW "AI creative studio" — any explicit imagery in public marketing kills this. Do not build Stripe integration until this decision lands.
- Tasks blocked on decision: checkout page, webhook handling, dunning. Everything else proceeds.

---

## Workstream C — Compliance pipeline Phase 1 (KIRO EXECUTABLE)

### Task C1: Bright-line prompt/output filters
- Blocked-terms classifier at prompt ingress (minors-related terms hard-blocked always — zero tolerance, instant ban path) + post-generation NSFW classifier scan routed to `quarantine_log`.
- Tests: adversarial prompt suite; quarantined outputs never returned to client.

### Task C2: NCII takedown endpoint with 48h SLA clock (TAKE IT DOWN Act)
- `POST /compliance/takedown` (valid-request schema), perceptual hash (pHash) index over generated assets, identical-copy sweep job, immutable audit trail in `aios` logs, SLA timer column + escalation alert at 24h.
- This is federal statutory territory — treat SLA breaches as P0 incidents.

### Task C3: Provenance stamps
- Embed C2PA-style metadata (model, timestamp, org, talent-id) into every exported asset. Supports NY Synthetic Performer Disclosure Law (ads must disclose AI performers; effective June 2026).

### Task C4: Age gate + paper (GARY ACTION + attorney)
- 18+ attestation now; ToS w/ prohibited-content list, indemnification, arbitration clause; DMCA agent registration; 2257-exemption statement drafted by adult-industry attorney before ANY real-person training ships. LLC separate from Delta life. Media-liability insurance quote.

---

## Workstream D — Phase 2: Selfie-verified "Bring Yourself" lane (BLOCKED until post-revenue)

### Task D1: Verification flow
- Upload → live liveness selfie → face-embedding match (ArcFace-class, e.g. InsightFace) threshold gate → ID document capture → signed release stored immutably. Fail = training refused at the LoRA gate (construction-level prevention, not moderation).
- Unlocks "✓ Verified Talent" badge; required for any LoRA trained on a real person's likeness; Hefner-tier private LoRA training sits behind this same gate.

### Task D2: Compute posture (DECISION REQUIRED, recommendation recorded)
- Default: platform pooled RunPod serverless fleet, weights B2-canonical, model templates baked, 1–2 warm workers per hot model class. BYO-key demoted to labeled best-effort "Advanced" mode later. Rationale: cold-start amortization + support burden + revenue protection.

---

## Validation / acceptance

1. `pytest backend/tests/billing/` green (ledger invariants, unpriced-preset tripwire).
2. Simulated takedown request → removal + copy-sweep completes < 48h SLA in staging clock test.
3. Quarantined output never reaches client (property test).
4. **Founder play gate (GARY ACTION):** Gary runs ONE full real generation end-to-end — storyboard → talent → image/video → voice → FFmpeg assembly — before pricing goes public. First customer is the founder; the builder finally watches the episode.

## Risks / tradeoffs
- Processor denial risk mitigated by early CCBill application + clean synthetic-first posture.
- Warm-pool idle burn capped by kill-switch rule above.
- Attorney sign-off is a dependency, not a formality — budget $2–5k for the paper pass.
