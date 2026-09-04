# Implementation Plan: Multi-Agent Lane Execution Protocol

## Overview

Sets up the lane partition infrastructure and implements the two backend workstreams (credit metering + compliance pipeline) that frontend lanes will build against. Frontend page lanes are NOT executed by Kiro — they are dispatched to Hermes subagents per PLN-R9; this spec gives Kiro everything it must own.

Tech stack: Python 3.12+ / FastAPI / SQLAlchemy 2.x async / Pydantic v2 / Supabase PostgreSQL 17. Follow backend-standards steering docs.

## Tasks

---

## Phase P0: Protocol Infrastructure — do first, blocks all lanes

- [ ] 1. Create lane manifest
  - [ ] 1.1 Write `LANES.json` at repo root with the six frontend lanes exactly as specified in PLN-R4 (id → owned paths → executor `subagent`), plus a `backend` lane (executor `kiro`) owning `backend/**`
  - [ ] 1.2 Validate: every path under `frontend/src/app/` appears in exactly one lane's owned paths (write a unit test for this invariant)
- [ ] 2. Add Multi-Session Protocol to root `AGENTS.md`
  - [ ] 2.1 Append section "Multi-Session Protocol" containing verbatim: read-before-write rule (`git status` + `git log --oneline -5` before starting), lane sovereignty, frozen components rule (`frontend/src/components/**`), api_v1.py single-file mutex, single-migration-runner rule, small-frequent-commits rule
- [ ] 3. Worktree helper script
  - [ ] 3.1 Write `scripts/new_lane_worktree.sh`: takes `<lane>`, creates `../ai-studio88-<lane>` worktree on branch `agent/<lane>` from HEAD; exits non-zero if either exists; prints the worktree path
  - [ ] 3.2 Test manually for one lane, then remove that test worktree
- [ ] 4. Commit P0 on `main` as a single commit: `feat(protocol): lane partition + multi-session rules`

## Phase P1: Workstream A — Credit Metering Spine

- [ ] 5. Credit cost registry
  - [ ] 5.1 Write failing test `backend/tests/billing/test_credit_costs.py::test_every_preset_has_cost` asserting every id in `engine/preset_packs.py` has an entry in `billing/credit_costs.py`
  - [ ] 5.2 Run test, verify FAIL
  - [ ] 5.3 Implement `backend/billing/credit_costs.py`: mapping `{preset_id -> {gpu_class, est_active_seconds, credits}}` covering all 16 presets (cinematic-portrait, product-shot, fast-draft, anime-illustration, landscape-environment, text-to-video-short, image-to-video-animate, upscale-4x, inpaint-edit, lora-portrait, controlnet-pose, ip-adapter-style, long-video, fashion-lookbook, film-grain-vintage, hdr-luxury). Use cost table from companion plan §unit-economics
  - [ ] 5.4 Run test, verify PASS; commit
- [ ] 6. Credit ledger migration
  - [ ] 6.1 Alembic migration creating `credit_ledger` (id, org_id FK, entry_type enum[grant|debit|refund|expire], amount int, balance_after int, reason, ref_id, created_at) — org_id per tenant Option A
  - [ ] 6.2 Property test: ledger balance never negative without explicit overdraft row; debits only after generation success event
  - [ ] 6.3 Run migrations ONCE (single runner); commit
- [ ] 7. Debit middleware + tier grants
  - [ ] 7.1 Extend `billing_router.py`: post-generation debit hook (async, after success), auto-refund on failure
  - [ ] 7.2 `backend/billing/tiers.py`: five tiers (screen_test/day_player/series_regular/showrunner/hefner) with monthly credit grants (250/2000/8000/25000/custom) per companion plan §tier-structure; grant scheduler job + 90-day free-tier expiry
  - [ ] 7.3 Tests green; commit

## Phase P2: Workstream C — Compliance Pipeline Phase 1

- [ ] 8. Bright-line filters
  - [ ] 8.1 Prompt-ingress blocked-terms classifier (minors-related terms = hard block + instant ban path, zero tolerance) writing violations to existing `quarantine_log`
  - [ ] 8.2 Post-generation NSFW classifier scan; quarantined outputs NEVER returned to client
  - [ ] 8.3 Adversarial prompt test suite; property test: no quarantined asset id is client-retrievable; commit
- [ ] 9. NCII takedown endpoint (48h SLA)
  - [ ] 9.1 `POST /compliance/takedown` implementing valid-request schema; pHash index over generated assets; identical-copy sweep background job
  - [ ] 9.2 SLA clock column + escalation alert at 24h; immutable audit trail via aios logging
  - [ ] 9.3 Staging clock test: simulated request completes removal + copy-sweep within SLA window; commit
- [ ] 10. Provenance stamps
  - [ ] 10.1 Embed C2PA-style metadata (model, timestamp, org, talent-id) into every exported asset at assembly time
  - [ ] 10.2 Test: exported assets carry provenance fields; commit

## Acceptance gates (all must pass before any frontend lane merges)

- [ ] 11. Full suite: `pytest backend/tests/billing backend/tests/compliance` green
- [ ] 12. `LANES.json` invariant test green
- [ ] 13. Founder-play gate remains OPEN (Gary action, outside Kiro scope): one real end-to-end generation before pricing goes public

## Explicitly out of scope for Kiro here

Frontend page work (six lanes) — dispatched by Hermes to subagents in worktrees per requirements PLN-R9/R10. Payment processor integration — BLOCKED on founder decision (CCBill vs Stripe posture).
