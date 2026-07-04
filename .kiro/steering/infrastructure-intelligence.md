---
inclusion: auto
fileMatchPattern: "backend/infrastructure/*"
---

# Infrastructure Intelligence (Phase 13)

## Overview

The infrastructure layer provides intelligent GPU worker orchestration,
provider learning, cost management, and fleet coordination.

## Connection Race Mode

When launching a GPU worker:
1. Query Vast.ai for rentable offers (filter Blackwell GPUs)
2. Launch N candidates simultaneously (default 3)
3. Poll SSH every 15s — first to respond wins
4. Immediately destroy all losers
5. Record attempt in reputation engine

Key code: `backend/infrastructure/connection_race.py`

## Provider Reputation

Every connection attempt feeds the learning engine:
- Reliability score (successes / attempts)
- Performance score (boot time)
- Cost efficiency score
- Auto-blacklist at <30% reliability after 3+ attempts
- Preferred hosts tracked for future use

Key code: `backend/infrastructure/provider_reputation.py`

## Render Fleet Mode

Multiple workers running simultaneously:
- Workers have specialties: general, image, video, training, upscale
- Jobs auto-route to best available worker
- Fleet-wide cost aggregation
- Emergency stop-all capability

Key code: `backend/infrastructure/render_fleet.py`

## Cost Intelligence

- Track per-session, daily, monthly spend
- Budget limits (COST_DAILY_BUDGET, COST_MONTHLY_BUDGET)
- Cost breakdown by GPU type and provider
- 30-day history for charting
- Warning (not blocking) when budget exceeded

Key code: `backend/infrastructure/cost_intelligence.py`

## Direct Generation

POST /api/v1/generate/image — submits ComfyUI workflow directly:
- Builds correct workflow per model (Flux, SDXL, SD15)
- Polls for completion
- Returns base64 image
- Handles errors gracefully

Key code: `backend/infrastructure/generate.py`

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/v1/infrastructure/launch | Launch worker (connection race) |
| GET | /api/v1/infrastructure/status | Live dashboard data |
| POST | /api/v1/infrastructure/stop | Stop current worker |
| GET | /api/v1/infrastructure/history | Connection attempt log |
| GET | /api/v1/infrastructure/cost | Cost summary + budget |
| GET | /api/v1/infrastructure/cost/history | 30-day cost chart data |
| GET | /api/v1/infrastructure/reputation | Provider scores |
| GET/POST | /api/v1/infrastructure/blacklist | Manage blacklist |
| GET | /api/v1/infrastructure/fleet | Fleet status |
| POST | /api/v1/infrastructure/fleet/add | Add fleet worker |
| DELETE | /api/v1/infrastructure/fleet/{id} | Remove fleet worker |
| POST | /api/v1/infrastructure/fleet/stop-all | Emergency shutdown |
| GET | /api/v1/infrastructure/admin/services | All service connections |
| POST | /api/v1/generate/image | Direct ComfyUI generation |

## Important Notes

- Vast.ai API base: https://console.vast.ai/api/v0
- All requests need follow_redirects=True + trailing slashes
- get_instance() returns nested {"instances": {...}} — must unwrap
- SSH info: top-level fields ssh_host, ssh_port (NOT in ports dict)
- Exclude Blackwell GPUs: RTX 5090/5080/5070/5060/PRO 6000
- Use pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime image
- SSH key: ~/.ssh/id_ed25519
- Presigned URLs for B2 downloads (don't pass raw credentials)
- model_exists_in_cache uses list_objects_v2 (not head_object — B2 compat)
