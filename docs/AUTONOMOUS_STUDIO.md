# AI Studio — Autonomous Studio

> Phase H. The platform that feels like hiring an elite creative agency.

---

## Overview

The Autonomous Studio is the coordination layer that makes AI Studio think
before acting. 19 AI Departments collaborate through shared context, produce
explainable recommendations, and learn from user decisions.

The user always retains final approval. The AI recommends; humans decide.

---

## Architecture

```
User opens AI Studio
         │
    ┌────▼────────────────────────────────────────────┐
    │           Daily Briefing                          │
    │  Production Status │ Recommendations │ Alerts    │
    └────┬────────────────────────────────────────────┘
         │
    ┌────▼────────────────────────────────────────────┐
    │          19 AI Departments                        │
    │  Creative │ Prompt │ Photography │ Film │ ...    │
    │  Each: analyze() → recommend() → explain()       │
    └────┬────────────────────────────────────────────┘
         │
    ┌────▼────────────────────────────────────────────┐
    │          Approval Workflow                         │
    │  Approve │ Reject │ Modify │ Ask for revision    │
    └────┬────────────────────────────────────────────┘
         │
    ┌────▼────────────────────────────────────────────┐
    │          Studio Memory                            │
    │  Track decisions → improve future recommendations │
    └─────────────────────────────────────────────────┘
```

---

## 19 AI Departments

| Department | Responsibility |
|---|---|
| Creative Director | Overall creative vision, concept elevation |
| Prompt Director | Prompt optimization, model-specific syntax |
| Photography Director | Composition, lighting for stills |
| Film Director | Narrative pacing, scene structure for video |
| Production Director | Pipeline selection, timeline management |
| Video Director | Motion, camera movement, transitions |
| Art Director | Visual style, color palette consistency |
| Character Director | Identity continuity across content |
| Voice Director | Voice casting, emotion, delivery |
| Music Director | Music selection, mood matching |
| Publishing Director | Platform strategy, posting times |
| Growth Director | Engagement optimization, audience growth |
| Business Director | Revenue, licensing, ROI |
| Analytics Director | Data analysis, performance reporting |
| Learning Director | Preference learning, recommendation improvement |
| Operations Director | System health, worker management |
| Research Director | New models, techniques |
| Trend Director | Social trends, viral patterns |
| Brand Director | Brand identity, partnerships |

---

## Daily Briefing

Presented when user opens AI Studio:

- Production status (workers, GPU, queue)
- Publishing status (scheduled, drafts)
- Campaign health (active, performance)
- Analytics summary (engagement, revenue)
- Top recommendations (prioritized)
- Alerts (critical issues)
- Learning progress (recommendation accuracy)

---

## Recommendation System

Every recommendation includes:
- Confidence score (0-100%)
- Reasoning (why this is suggested)
- Evidence (supporting data)
- Expected benefit
- Estimated cost and runtime
- Potential risks
- Suggested action

---

## Approval Workflow

| Action | Effect |
|---|---|
| Approve | Execute the recommendation |
| Reject | Dismiss (learning: won't suggest similar) |
| Modify | User adjusts before executing |
| Ask AI to revise | Departments reconsider |

---

## Studio Memory

Tracks all user decisions:
- Accepted recommendations
- Rejected recommendations
- Accuracy over time
- Preference patterns

Future recommendations improve based on this history.

---

## Multi-Agent Discussion

Departments collaborate on a topic:

```
User: "luxury travel campaign for Melissa"

Creative Director: "Position as aspirational lifestyle content..."
Photography Director: "Golden hour, shallow depth of field..."
Film Director: "Hook within 2 seconds for social..."
Production Director: "3 scheduled items ready, workers available..."
Publishing Director: "Instagram + TikTok dual publish..."
Growth Director: "Travel content trending +24%..."
```

Each contribution includes confidence score.

---

## API Endpoints (8)

| Method | Path | Description |
|---|---|---|
| GET | `/studio/briefing` | Daily Briefing with full status |
| GET | `/studio/recommendations` | All pending recommendations |
| POST | `/studio/recommendations/{i}/decide` | Approve/reject/modify |
| GET | `/studio/departments` | List all departments |
| GET | `/studio/departments/{name}/analyze` | Run specific department |
| POST | `/studio/discuss` | Multi-agent discussion |
| GET | `/studio/memory` | Learning/memory stats |
| GET | `/studio/health` | Overall studio health |

---

## Integration

| System | How Autonomous Studio uses it |
|---|---|
| Creator OS | Reads campaigns, calendar, analytics, brands |
| Execution Platform | Reads worker health, GPU availability |
| Intelligence Engine | Extends agent reasoning with department structure |
| Story Engine | Film/Character Directors reference narratives |
| Production Studio | Production Director plans pipelines |
| Creative DNA | Art/Character Directors check identity |
| Generation Engine | Recommendations flow into generation jobs |
| Feedback Loop | Learning Director tracks outcome quality |

---

## Files

| File | Purpose |
|---|---|
| `backend/autonomous_studio/__init__.py` | Package |
| `backend/autonomous_studio/department.py` | Department interface (ABC) |
| `backend/autonomous_studio/departments.py` | 19 department implementations |
| `backend/autonomous_studio/orchestrator.py` | Context builder, briefing, discussion, memory |
| `backend/autonomous_studio/router.py` | API endpoints |
| `dashboard/pages/15_Autonomous_Studio.py` | Dashboard page |
