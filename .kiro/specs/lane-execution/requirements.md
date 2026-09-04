# Requirements Document

## Multi-Agent Lane Execution — AI Studio Parallel Development Protocol

## Introduction

This specification defines how AI Studio is developed by MULTIPLE agents working simultaneously (Kiro sessions, Hermes-spawned subagents, and future agent CLIs) without stepping on each other. It establishes the lane partition, git worktree isolation, collision rules, executor assignments, and the integration (merge) procedure.

This spec implements the Hybrid-C model agreed 2026-08-23: **Hermes orchestrates subagents for frontend page lanes in isolated worktrees; Kiro owns all backend/migration work and the protocol infrastructure.**

Companion document (pricing + compliance content): `.hermes/plans/2026-08-23_124643-pricing-and-compliance.md`

## Requirements

### Protocol Infrastructure

- **PLN-R1**: The repository SHALL contain a lane manifest (`LANES.json`) declaring every development lane: id, owned paths, owning executor (kiro|subagent), and worktree path.
- **PLN-R2**: The root `AGENTS.md` SHALL contain a "Multi-Session Protocol" section stating: read-before-write (check `git status` + recent commits), lane sovereignty (edit only owned paths), commit discipline (small frequent commits on the lane branch), single-migration-runner rule, and the frozen-shared-components rule.
- **PLN-R3**: A helper script (`scripts/new_lane_worktree.sh <lane>`) SHALL create `../ai-studio88-<lane>` as a git worktree on branch `agent/<lane>` from current HEAD, failing if the worktree or branch already exists.

### Lane Partition

- **PLN-R4**: Frontend work SHALL be partitioned into six lanes, each owning disjoint page directories:
  - `talent`: `src/app/talent/**`, `src/app/training/**`
  - `creation`: `src/app/create/**`, `src/app/story/**`, `src/app/production/**`
  - `post`: `src/app/editor/**`, `src/app/assets/**`, `src/app/projects/**`
  - `platform`: `src/app/admin/**`, `src/app/settings/**`, `src/app/models/**`, `src/app/workflows/**`
  - `growth`: `src/app/page.tsx`, `src/app/login/**`, `src/app/analytics/**`, `src/app/publish/**`, NEW `src/app/pricing/**`
  - `brain`: `src/app/brain/**`
- **PLN-R5**: `frontend/src/components/**` SHALL be FROZEN for all lane agents. Lane-local components SHALL be colocated inside the lane's page directories. Promotion of a component to shared status happens ONLY in an integration pass, one PR at a time.
- **PLN-R6**: `backend/api_v1.py` SHALL be treated as a single-file mutex across ALL executors: only the backend lane may modify it at any given time; other lanes queue endpoint additions through the orchestrator.

### Backend Execution (Kiro-owned)

- **PLN-R7**: Kiro SHALL implement Workstream A (credit metering spine: `backend/billing/credit_costs.py`, ledger migration, tier grants) per the companion plan, including the tripwire test that fails when any preset in `preset_packs.py` lacks a credit cost entry.
- **PLN-R8**: Kiro SHALL implement Workstream C Phase-1 compliance items (bright-line prompt filters feeding `quarantine_log`, takedown endpoint with 48h SLA clock + pHash copy sweep, provenance metadata stamping) per the companion plan.

### Frontend Execution (Subagent-owned, Hermes-orchestrated)

- **PLN-R9**: Each frontend lane SHALL be executed by a dedicated subagent inside its worktree, on branch `agent/<lane>`, committing only within its owned paths.
- **PLN-R10**: Every lane agent SHALL be briefed that this Next.js version has breaking changes and MUST consult `node_modules/next/dist/docs/` (per `frontend/AGENTS.md`) before writing code.

### Integration

- **PLN-R11**: Lane branches SHALL merge back to `main` SERIALLY, one at a time, only after: (a) `next build` passes in the worktree, (b) backend test suite green where touched, (c) no files outside owned paths modified (verified by `git diff --name-only main...agent/<lane>`).
- **PLN-R12**: Integration SHALL NOT commit unrelated dirty files present on `main` (e.g., another session's uncommitted edits); integration commits contain only merged lane content.
