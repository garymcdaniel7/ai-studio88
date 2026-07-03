# AI Studio — Production Intelligence

> Phase 9. Autonomous advisors that continuously improve every production.

---

## Overview

Production Intelligence transforms AI Studio from a toolkit into an AI Executive Producer.
7 specialized agents observe every production, remember outcomes, and proactively recommend improvements.

---

## Agents (7)

| Agent | Responsibility |
|---|---|
| Executive Producer | Workflow, model, LoRA, GPU, budget, runtime, bottlenecks |
| Director | Scene pacing, camera language, emotional flow, shot order |
| Editor | Cuts, transitions, B-roll, music timing, social cuts |
| Model Advisor | Best model for content type, budget, GPU, quality |
| GPU Advisor | Worker routing, VRAM, queue time, cost, parallelization |
| Quality Scorer | Multi-dimension quality scoring per asset |
| Self-Healing Advisor | Failed workflow recovery, provider switching, retries |

---

## Quality Dimensions

Every generated asset is scored on:
- Identity consistency
- Prompt adherence
- Anatomy / hands
- Lighting / composition
- Cinematic quality
- Overall production score

---

## Self-Healing Workflows

When a job fails, the advisor recommends:
1. Retry with same parameters
2. Change provider
3. Reduce resolution/steps
4. Skip failed step
5. Reassign to different worker

---

## API Endpoints (10)

| Method | Path | Description |
|---|---|---|
| GET | `/intelligence/production-insights` | All agent insights |
| GET | `/intelligence/production-insights/agents` | List agents |
| POST | `/intelligence/quality-score` | Score an asset |
| GET | `/intelligence/quality-scores` | Recent scores |
| GET | `/intelligence/quality-scores/summary` | Aggregate quality |
| POST | `/intelligence/learning/event` | Record learning event |
| GET | `/intelligence/learning/events` | Recent events |
| GET | `/intelligence/learning/summary` | Learning stats |
| GET | `/intelligence/reports/production` | Production report |
| GET | `/intelligence/reports/recommendations` | Top recommendations |

---

## Learning System

Tracks:
- Positive/negative outcomes
- Learning rate (improving over time)
- What worked, what didn't
- Feeds into future recommendations

---

## Integration

Connects to: Worker Manager (GPU status), Jobs (failures/pending),
Assets (quality), Brain (planning), Publishing (analytics), Creative DNA (preferences)

---

## Files

| File | Purpose |
|---|---|
| `backend/production_intelligence/__init__.py` | Package |
| `backend/production_intelligence/agents.py` | 7 agent implementations |
| `backend/production_intelligence/router.py` | API endpoints |
| `docs/sql/014_production_intelligence.sql` | Database tables |
