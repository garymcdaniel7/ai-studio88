# Implementation Plan: Alembic Graph Repair + Durable Compliance Persistence

## Overview

Four checkpoints, strictly ordered: (R1) graph integrity, (R2) connectivity + reconciliation, (R3) credit-ledger apply, (R4) durable quarantine/takedown persistence. TDD throughout. One serial Alembic execution sequence total. Dry-run SQL for every hosted-DB mutation goes in the final report.

## Tasks

---

- [ ] 1. Graph validator test (fails first)
  - [ ] 1.1 Write `backend/tests/unit/test_protocol/test_migration_graph.py`: parse all `backend/alembic/versions/*.py` for revision/down_revision; assert no duplicate ids, all refs resolvable, heads == 1. Run: FAIL (documents current breakage)
  - [ ] 1.2 Commit nothing yet — proceed to fix
- [ ] 2. Repair the graph
  - [ ] 2.1 Reassign unique ids to the six duplicate-id files (new ids follow date-based convention, e.g. `20260811002`, `20260812002/3`, `20260816002`); update their self-declarations AND any child references to old ids
  - [ ] 2.2 Fix `20260810_002` down_revision to the real id of add_job_leases (`20260810001`)
  - [ ] 2.3 Link the orphan root `20260822_001` into the main chain (down_revision = previous chronological head)
  - [ ] 2.4 Graph validator PASSES; commit `fix(migrations): repair alembic graph integrity`
- [ ] 3. Connectivity + reconciliation (single serial sequence)
  - [ ] 3.1 Ensure backend deps installed via project pyproject (alembic, asyncpg); `alembic heads` succeeds
  - [ ] 3.2 Read-only probe: SELECT 1 against configured URL; dump current `alembic_version` rows + existence check for known tables
  - [ ] 3.3 Produce `--sql` dry-runs; decide stamp-vs-run per revision based on live schema; STAMP where DDL pre-exists
  - [ ] 3.4 Apply `20260825001` credit ledger incrementally; verify table + RLS; commit any env/config fixes as `chore(migrations): enable serial migration execution`
- [ ] 4. Durable compliance persistence
  - [ ] 4.1 Migration: `quarantined_assets` + `takedown_cases` tables (org_id FK, phash TEXT + index, sla_started_at/sla_deadline_at/sla_completed_at, status enum) with RLS; include in the same serial sequence or as one additional incremental apply with dry-run reported
  - [ ] 4.2 Repository layer behind existing signatures (`quarantine_asset`, `is_asset_quarantined`, `filter_visible_assets`, takedown service methods) — swap storage, keep callers untouched
  - [ ] 4.3 Update compliance tests to exercise the durable store; ALL prior compliance/billing/protocol tests green
  - [ ] 4.4 Commit `feat(compliance): durable quarantine and takedown persistence`
- [ ] 5. Final validation
  - [ ] 5.1 `pytest backend/tests` scoped to billing+compliance+protocol: green
  - [ ] 5.2 `git diff --name-only <base>..HEAD` shows backend/** only; report protected-path check
  - [ ] 5.3 Report: stamp decisions, dry-run SQL actually executed, remaining limitations

## Explicitly out of scope
Frontend anything; api_v1.py; new product features beyond persistence swap.
