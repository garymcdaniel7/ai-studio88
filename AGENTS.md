# AI Studio Agent Rules

## Multi-Session Protocol

Before starting work, every executor MUST read the current repository state:

```bash
git status
git log --oneline -5
```

### Lane sovereignty

Each executor MUST edit only files covered by its lane's `owned_paths` in `LANES.json`. Do not modify another lane's files, and do not stage unrelated pre-existing changes. Lane branches are isolated workspaces; integration merges them serially after their scoped checks pass.

### Frozen shared components

`frontend/src/components/**` is frozen for all lane agents. Lane-local components belong beside the page that owns them. Moving a component into the shared directory is an integration-only change, handled one PR at a time.

### `backend/api_v1.py` single-file mutex

`backend/api_v1.py` is a single-file mutex across all executors. Only the backend lane may modify it, and only one backend session may edit it at a time. Other lanes MUST queue endpoint requests through the orchestrator rather than editing this file.

### Single migration runner

Only one executor may run database migrations at a time. Use the repository's designated migration runner and run migrations serially. Never run Alembic and the legacy SQL migration runner concurrently or apply the same migration from multiple sessions.

### Small, frequent commits

Make small, focused commits after each completed checkpoint. A commit MUST contain only the files owned by the active lane and the work required for that checkpoint. Do not bundle unrelated work or pre-existing dirty files.
