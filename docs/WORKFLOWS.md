# AI Studio — Workflow Engine

> Sprint 3. Orchestrates multi-step jobs with dependency tracking.

---

## Overview

A workflow is a reusable template that chains multiple job steps together.
When executed, the engine spawns child jobs in dependency order, passes
outputs between steps, and tracks the run to completion or failure.

---

## Concepts

| Concept | Description |
|---|---|
| **Workflow** | A saved template with name, steps, and config |
| **Step** | One unit of work (maps to a job handler) |
| **Workflow Run** | A single execution instance |
| **Dependency** | A step can require other steps to finish first |
| **Handler** | The job type that processes the step |

---

## Workflow Lifecycle

```
          ┌────────┐
  POST    │ draft  │  (created but not runnable)
          └───┬────┘
              │ activate
          ┌───▼────┐
          │ active │  (can be run)
          └───┬────┘
              │ archive
          ┌───▼─────┐
          │archived │
          └─────────┘
```

A workflow run lifecycle:

```
POST /workflows/{id}/run
         │
    ┌────▼─────┐
    │ running  │ ← steps executing in dependency order
    └────┬─────┘
    ╱    │     ╲
   ▼     │      ▼
┌──────┐ │  ┌──────┐
│ done │ │  │failed│
└──────┘ │  └──────┘
         ▼
    ┌──────────┐
    │cancelled │  (user cancels mid-run)
    └──────────┘
```

---

## Workflow Schema (`workflows` table)

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| project_id | UUID | FK → projects, nullable |
| name | TEXT | Required |
| description | TEXT | |
| version | INTEGER | Default 1 |
| status | TEXT | draft / active / archived |
| trigger_type | TEXT | manual / schedule / event / api |
| steps | JSONB | Array of step definitions (see below) |
| definition | JSONB | Additional config (future) |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

---

## Workflow Runs Schema (`workflow_runs` table)

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| workflow_id | UUID | FK → workflows |
| status | TEXT | running / completed / failed / cancelled |
| input | JSONB | Input passed at run time |
| output | JSONB | Aggregated step outputs |
| current_step | INTEGER | Steps completed so far |
| total_steps | INTEGER | Total step count |
| error | TEXT | Error if failed |
| created_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

---

## Step Definition

Each entry in `steps` JSONB:

```json
{
  "name": "Generate Image",
  "handler": "image_generation",
  "config": {"width": 1024, "height": 1024, "steps": 20},
  "depends_on": [0]
}
```

| Field | Type | Description |
|---|---|---|
| name | string | Human-readable step name |
| handler | string | Job type from JOB_HANDLERS registry |
| config | object | Input params for the handler |
| depends_on | int[] | Indices of steps that must complete first |

---

## Step Dependencies

- Steps with `depends_on: []` run first (no prerequisites)
- A step only executes when ALL dependencies have `completed` status
- Outputs from completed dependencies are injected into the step's input as `step_{index}_output`
- If any step fails, the entire run fails immediately
- Circular dependencies are detected and cause immediate failure

Example: three-step chain

```
Step 0: Prompt Enhancement  (depends_on: [])
Step 1: Generate Image      (depends_on: [0])  ← waits for step 0
Step 2: Upscale             (depends_on: [1])  ← waits for step 1
```

---

## How Workflows Create Jobs

Each workflow step spawns a real job in the `jobs` table:

```
workflow_run (a7e363...)
  ├── job (step 0: asset_processing)   workflow_id=76a4bbc8...
  ├── job (step 1: image_generation)   workflow_id=76a4bbc8...
  └── job (step 2: image_upscale)      workflow_id=76a4bbc8...
```

- Jobs have `workflow_id` set → links them to the parent workflow
- Jobs are standard entries visible in `GET /api/v1/jobs`
- Worker processes workflow jobs identically to standalone jobs
- Progress is tracked at both the job level and the run level

---

## Handler Pattern

The workflow engine uses the same `JOB_HANDLERS` registry as the standalone worker:

```python
JOB_HANDLERS = {
    "image_generation": SimulationHandler,   # → FluxHandler
    "video_generation": SimulationHandler,   # → WanHandler
    "lora_training":    SimulationHandler,   # → LoraTrainer
    "image_upscale":    SimulationHandler,   # → UpscaleHandler
    "image_edit":       SimulationHandler,   # → EditHandler
    "voice_generation": SimulationHandler,   # → ElevenLabsHandler
    "workflow_execution": SimulationHandler, # → nested workflows
    "asset_processing": SimulationHandler,   # → CaptionHandler
    "publishing":       SimulationHandler,   # → PublishHandler
}
```

To add a real handler:
1. Create a class inheriting `BaseHandler`
2. Implement `execute(job, report_progress) → dict`
3. Register in `JOB_HANDLERS`

Both the standalone worker and the workflow engine dispatch through the same registry.

---

## Current: Simulation Mode

All handlers currently use `SimulationHandler`:
- Accepts a `steps` count and `step_delay` from input config
- Reports progress incrementally
- Produces fake but structured output (URLs, dimensions, etc.)
- Allows full end-to-end workflow testing without real GPUs

---

## Future: ComfyUI Integration

When real handlers are built:

```python
class FluxHandler(BaseHandler):
    def execute(self, job, report_progress):
        # 1. Provision GPU instance (Vast.ai)
        # 2. Upload ComfyUI workflow JSON to instance
        # 3. Inject parameters from job.input (prompt, dimensions, etc.)
        # 4. Poll ComfyUI /history endpoint for progress
        # 5. Download output images
        # 6. Upload to B2 storage
        # 7. Return asset URLs
        ...
```

Workflow steps will map to ComfyUI workflow fragments:
- Each step's `config` becomes the node parameters
- The workflow engine handles orchestration between fragments
- ComfyUI runs on ephemeral GPU instances provisioned per-job

---

## Future: UI Controls / Dials

The `config` field in each step is designed to map directly to UI controls:

```json
{
  "handler": "image_generation",
  "config": {
    "prompt": "luxury portrait",       // text input
    "negative_prompt": "blurry",       // text input
    "width": 1024,                     // slider (512-2048)
    "height": 1024,                    // slider (512-2048)
    "steps": 20,                       // slider (1-50)
    "cfg_scale": 7.0,                  // slider (1-20)
    "seed": -1,                        // number input (-1 = random)
    "model": "flux-dev",               // dropdown
    "lora_id": "uuid-of-lora"          // asset picker
  }
}
```

Frontend workflow builder will:
- Render config fields as appropriate UI controls (sliders, dropdowns, text)
- Show step dependency graph visually (DAG editor)
- Allow drag-and-drop step reordering
- Preview outputs between steps
- Show real-time progress during execution

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/workflows` | List (filter: `?status=active`) |
| POST | `/api/v1/workflows` | Create |
| GET | `/api/v1/workflows/{id}` | Get with full steps |
| PUT | `/api/v1/workflows/{id}` | Update |
| DELETE | `/api/v1/workflows/{id}` | Delete |
| POST | `/api/v1/workflows/{id}/run` | Execute |

---

## Curl Examples

```bash
# Create
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Luxury Portrait",
    "status": "active",
    "steps": [
      {"name": "Prompt", "handler": "asset_processing", "config": {"prompt": "luxury portrait"}, "depends_on": []},
      {"name": "Generate", "handler": "image_generation", "config": {"width": 1024, "steps": 3, "step_delay": 0.3}, "depends_on": [0]},
      {"name": "Upscale", "handler": "image_upscale", "config": {"scale_factor": 2, "steps": 2, "step_delay": 0.3}, "depends_on": [1]}
    ]
  }'

# Run
curl -X POST http://localhost:8000/api/v1/workflows/{id}/run \
  -H "Content-Type: application/json" -d '{}'

# List
curl http://localhost:8000/api/v1/workflows

# Delete
curl -X DELETE http://localhost:8000/api/v1/workflows/{id}
```
