# AI Studio

**Commercial AI content production platform for creating, managing, training, and deploying AI influencers at scale.**

AI Studio gives brands and content creators a single platform to manage AI talent, run LoRA training jobs, generate images and video, schedule GPU workloads, and distribute content — all through a multi-tenant SaaS architecture.

---

## What it does

| Capability | Description |
|---|---|
| AI Talent Management | Create and manage AI personas (influencers) with associated brand identity |
| Brand & Campaign Management | Link AI talent to brands, products, and content campaigns |
| LoRA Training | Fine-tune diffusion models on custom character data using Vast.ai / RunPod GPUs |
| Image Generation | ComfyUI-powered image generation with Flux, SDXL, and future models |
| Video Generation | WAN and LTX Video integration for short-form AI video content |
| Voice Generation | AI voice cloning and synthesis for influencer audio content |
| Content Calendar | Schedule and queue content generation across campaigns |
| Asset Management | Organised storage on Backblaze B2 with CDN delivery |
| GPU Job Scheduling | Intelligent GPU provisioning and job queuing across cloud providers |
| Analytics | Content performance, generation cost, and GPU usage dashboards |
| Multi-user SaaS | Role-based access control, organisation management, billing |

---

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.12) |
| Database | Supabase (PostgreSQL) |
| Storage | Backblaze B2 |
| GPU Jobs | Vast.ai (+ RunPod roadmap) |
| Generation | ComfyUI, WAN, LTX Video, Flux, SDXL |
| Task Queue | Celery + Redis |
| Containerisation | Docker + Docker Compose |
| CI/CD | GitHub Actions |

---

## Quick start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/ai-studio.git
cd ai-studio

# 2. Run the bootstrap script (installs all dependencies)
chmod +x bootstrap.sh
./bootstrap.sh

# 3. Fill in your credentials
cp .env.example .env
# Edit .env with your Supabase, B2, Vast.ai keys

# 4. Start Supabase locally
supabase start

# 5. Activate the Python environment and start the API
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# 6. Visit the interactive API docs
open http://localhost:8000/docs
```

---

## Repository structure

```
ai-studio/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/v1/endpoints/ # Route handlers
│   │   ├── core/             # Config, security, dependencies
│   │   ├── db/               # Database session, base models
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic layer
│   │   └── workers/          # Celery tasks, GPU workers
│   ├── alembic/              # Database migrations
│   ├── tests/                # pytest test suite
│   └── pyproject.toml
├── frontend/                 # (future) Next.js dashboard
├── infrastructure/
│   ├── docker/               # Dockerfiles
│   ├── nginx/                # Reverse proxy config
│   └── scripts/              # Deploy scripts
├── supabase/                 # Supabase local config + migrations
├── .github/workflows/        # CI/CD pipelines
├── docs/                     # Architecture, ADRs, API docs
├── bootstrap.sh              # macOS/Linux setup
├── bootstrap.ps1             # Windows setup
├── verify_environment.sh     # Environment health check
└── .env.example              # Environment variable template
```

---

## Documentation

| Document | Description |
|---|---|
| [SETUP.md](SETUP.md) | Detailed setup instructions |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture overview |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [SECURITY.md](SECURITY.md) | Security policy |
| [ROADMAP.md](ROADMAP.md) | Feature roadmap |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Development verification

```bash
./verify_environment.sh    # Check all tools are installed and configured
```

---

## License

Proprietary — All rights reserved. See [LICENSE](LICENSE).
