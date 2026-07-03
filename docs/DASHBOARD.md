# AI Studio — Dashboard UI

> Sprint 4. Streamlit-based web interface calling the FastAPI backend.

---

## Overview

The dashboard provides a browser-based UI for managing AI Studio. It is a thin
client — all logic lives in the FastAPI backend. The dashboard only calls API
endpoints and renders results.

---

## Starting the Dashboard

```bash
# Terminal 1: Start the FastAPI backend
cd ai-studio88
uv run uvicorn backend.main:app --reload

# Terminal 2: Start the Streamlit dashboard
cd ai-studio88
uv run streamlit run dashboard/app.py
```

The dashboard opens at **http://localhost:8501** by default.

---

## Pages

| Page | Features |
|---|---|
| **Dashboard** | Project/talent/asset/job/workflow counts, job status breakdown |
| **Talent** | List talent, create new talent, view details |
| **Assets** | Upload files to B2, list assets, view metadata, delete |
| **Jobs** | Create jobs, filter by status/type, cancel, retry, delete |
| **Workflows** | Create multi-step workflows, run them, view results |
| **Settings** | Connection status for Supabase/B2, feature flags (no secrets shown) |

---

## Architecture

```
┌─────────────────────────┐          ┌──────────────────────────┐
│   Streamlit Dashboard   │  HTTP    │    FastAPI Backend        │
│   (localhost:8501)      │────────► │    (localhost:8000)       │
│                         │          │                          │
│   dashboard/app.py      │          │    backend/main.py       │
│   dashboard/api_client  │          │    backend/api_v1.py     │
│   dashboard/pages/      │          │                          │
└─────────────────────────┘          └──────────────────────────┘
```

- `dashboard/api_client.py` — shared HTTP client for all pages
- All requests go to `API_BASE_URL` (from `.env`, default `http://localhost:8000`)
- Never duplicates backend logic — the API is the single source of truth
- Secrets are never displayed in the UI

---

## File Structure

```
dashboard/
├── app.py                ← Main entry point (home page)
├── api_client.py         ← Shared API client (all pages use this)
└── pages/
    ├── 1_Dashboard.py    ← Overview metrics
    ├── 2_Talent.py       ← Talent management
    ├── 3_Assets.py       ← Asset upload/management
    ├── 4_Jobs.py         ← Job creation/monitoring
    ├── 5_Workflows.py    ← Workflow creation/execution
    └── 6_Settings.py     ← Connection status
```

---

## Configuration

Add to `.env`:
```
API_BASE_URL=http://localhost:8000
```

---

## Requirements

- Streamlit (already in `requirements.txt`)
- FastAPI backend must be running before starting the dashboard
- All data operations go through the API

---

## Future Enhancements

- Real-time job progress via polling or WebSocket
- Image/video preview in Assets page
- Drag-and-drop workflow builder
- User authentication (Supabase Auth)
- Dark/light theme toggle
- Mobile-responsive layout
