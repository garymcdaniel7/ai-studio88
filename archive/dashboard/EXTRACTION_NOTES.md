# Extraction Notes — Streamlit Dashboard Archive

Extracted 2026-10-06 before archiving. Two files targeted per plan.

## 10_Intelligence.py — Concepts for Reimplementation

**Endpoint contract:** `POST /api/v1/intelligence/plan`
- Input: `user_idea`, `talent_id`, `platform`, `content_type`, `campaign`
- Output: plan with `prompt`, `negative_prompt`, `model`, `settings`, `estimated_time`, `estimated_cost`, `workflow_steps`, `agents[]` (each with agent name, confidence, reasoning, recommendations), `publishing`

**Salvageable:** The "multi-agent creative brief" concept is a solid product idea. The AI Studio Brain conversation layer (`backend/aios/`) could implement it as a structured persona deliberation — gather opinions from multiple AIOS persona files (Director, Cinematographer, Script Supervisor) and synthesize one production plan. The actual Streamlit code is just `requests.post` boilerplate; the value is the schema.

## 15_Autonomous_Studio.py — Concepts for Reimplementation

**Endpoint contracts:**
- `GET /api/v1/studio/briefing` — Daily briefing with production status, publishing status, campaign health, alerts, learning stats
- `GET /api/v1/studio/recommendations` — Prioritized AI recommendations with approve/reject workflow
- `POST /api/v1/studio/discuss` — Multi-department topic discussion (19 departments)
- `GET /api/v1/studio/departments` — Department roster
- `GET /api/v1/studio/health` — Studio health status

**Salvageable:** The "studio as an org of specialized AI departments" mental model. The `discuss` endpoint is the most novel — distributed persona deliberation. The recommendation approve/reject workflow is a good feedback loop pattern.

## api_client.py — Pattern Reference

**Salvageable:** The `_request` method with auto-refresh-on-401 pattern is production-grade. The `_handle` JSON error extraction is clean. The `upload` multipart helper is reusable. However, the new backend uses Supabase auth (JWT from frontend), not Streamlit session-based auth, so this can't be dropped in — it's a pattern reference only.

## Conclusion: Nothing to salvage as code

All files are Streamlit UI wrappers around HTTP calls. The **real value** is the API contract concepts (schemas above) — these should inform new FastAPI endpoint designs in the main backend, not be copied as code. The `api_client.py` transport pattern is the best-engineered file but doesn't fit the new architecture.

**No code migration needed.** Archive as-is.