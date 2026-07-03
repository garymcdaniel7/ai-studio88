# Changelog

All notable changes to AI Studio are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- `.kiro/steering/` — 12 engineering standards files for AI-assisted development
- `.kiro/skills/` — 9 reusable workflow recipes for recurring engineering tasks
- `ARCHITECTURE.md` — full system architecture documentation
- `SETUP.md` — developer environment setup guide
- `CONTRIBUTING.md` — contribution workflow and code standards
- `ROADMAP.md` — phased feature roadmap (8 phases)
- `SECURITY.md` — security policy and vulnerability reporting
- `CODEOWNERS` — GitHub code review ownership rules
- `bootstrap.sh` / `bootstrap.ps1` — one-command developer environment setup
- `verify_environment.sh` / `verify_environment.ps1` — environment health checks
- `.env.example` — comprehensive environment variable template
- `.gitignore` — expanded to cover Python, Node, Docker, AI/ML artefacts
- `.pre-commit-config.yaml` — Ruff, Black, secrets detection, Bandit
- `.github/workflows/ci.yml` — CI pipeline (lint, security, test, Docker build)
- `docker-compose.yml` — full local stack (API, worker, Redis, Nginx, Flower)
- `infrastructure/docker/Dockerfile.api` — multi-stage production Docker build
- `infrastructure/nginx/nginx.dev.conf` — local reverse proxy configuration

---

## [0.0.1] — 2026-07-03

### Added
- Initial FastAPI application (`backend/main.py`)
- Supabase client integration (`backend/database.py`)
- Stub files for GPU, jobs, and storage modules
- Basic `requirements.txt` with core dependencies
- Repository initialised on GitHub at `garymcdaniel7/ai-studio88`
