"""AI Studio Service Boundaries — Story 051.

Defines the deployable service map for AI Studio. Each service has a
distinct responsibility, lifecycle, scaling rule, and entrypoint.

Service Map:
    ┌─────────────┐     ┌──────────────┐     ┌───────────────┐
    │  Frontend   │     │  API Server  │     │  Orchestrator │
    │  (Next.js)  │────▶│  (FastAPI)   │────▶│  (singleton)  │
    │  port 3000  │     │  port 8000   │     │  GPU lifecycle│
    └─────────────┘     └──────────────┘     └───────────────┘
                              │                      │
                              ▼                      ▼
                        ┌──────────────┐     ┌───────────────┐
                        │   Worker     │     │   Scheduler   │
                        │  (N replicas)│     │  (singleton)  │
                        │  long jobs   │     │  cron/health  │
                        └──────────────┘     └───────────────┘

Rules:
    - API Server: stateless, horizontally scalable, NO daemon threads
    - Orchestrator: singleton leader, owns GPU lifecycle state
    - Worker: N replicas consuming from job queue, long-running OK
    - Scheduler: singleton, periodic tasks (health checks, UAT, publishing)
    - Frontend: stateless Next.js, horizontally scalable
"""
