# AI Studio — Creative DNA & Feedback Loop

> Sprint 7. Rule-based learning system that improves recommendations from user feedback.

---

## Overview

Creative DNA stores learned preferences per talent. When users rate outputs and
tag problems, the system adjusts future prompt recommendations automatically.

This is **rule-based learning** — no ML models. Patterns are simple:
- If user tags "face_drift" → add "face deformation, inconsistent face" to negative prompt
- If user prefers "warm cinematic lighting" → add it to positive prompt
- If user avoids "harsh flash" → add to negative prompt

---

## How It Works

```
User generates content
         │
         ▼
User submits feedback (stars + problem tags)
         │
         ▼
Feedback stored in generation_feedback table
         │
         ▼
Next Creative Session:
  1. Load Creative DNA for talent
  2. Load recent problems from feedback
  3. Prompt Engineer reads both
  4. Prompt adjusted automatically:
     - DNA preferred_styles → added to positive prompt
     - DNA prompt_rules → added to positive prompt
     - DNA avoided_styles → added to negative prompt
     - DNA negative_prompt_rules → added to negative prompt
     - Frequent problems → mapped to negative prompt additions
  5. Feedback warning card shown to user
```

---

## Database Tables

### `creative_dna`

Per-talent learned preferences:

| Column | Type | Purpose |
|---|---|---|
| talent_id | UUID | FK → talent |
| preferred_styles | JSONB[] | Styles to always include |
| avoided_styles | JSONB[] | Styles to always avoid |
| color_palette | JSONB[] | Preferred colours |
| camera_preferences | JSONB | Angles, lenses, etc. |
| wardrobe_preferences | JSONB | Clothing style notes |
| setting_preferences | JSONB | Environment preferences |
| prompt_rules | JSONB[] | Phrases always added to prompt |
| negative_prompt_rules | JSONB[] | Phrases always added to negative |
| lora_preferences | JSONB | LoRA strength settings |
| model_preferences | JSONB | Model selection preferences |
| notes | TEXT | Freeform creative notes |

### `generation_feedback`

User ratings on outputs:

| Column | Type | Purpose |
|---|---|---|
| job_id | UUID | Which job produced this output |
| asset_id | UUID | Which asset was rated |
| talent_id | UUID | Which talent was in the output |
| rating | INTEGER | 1-5 stars |
| problems | TEXT[] | Problem tags (see below) |
| notes | TEXT | Freeform comments |
| context | JSONB | Snapshot of settings used |

### Problem Tags

| Tag | Mapped Negative Prompt |
|---|---|
| `face_drift` | face deformation, inconsistent face |
| `bad_hands` | malformed hands, extra fingers |
| `bad_lighting` | harsh lighting, overexposed |
| `too_artificial` | plastic skin, uncanny valley, CGI look |
| `poor_composition` | cluttered background, bad framing |
| `identity_mismatch` | wrong person, different face |
| `poor_motion` | (video: jerky movement) |
| `wrong_outfit` | (wardrobe note) |
| `prompt_mismatch` | (creative brief note) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/creative-dna` | List all DNA records |
| GET | `/api/v1/creative-dna/{talent_id}` | Get DNA for a talent |
| POST | `/api/v1/creative-dna` | Create DNA record |
| PUT | `/api/v1/creative-dna/{id}` | Update DNA record |
| GET | `/api/v1/feedback` | List feedback (filter by talent_id) |
| POST | `/api/v1/feedback` | Submit feedback |

---

## Curl Examples

```bash
# Create Creative DNA
curl -X POST http://localhost:8000/api/v1/creative-dna \
  -H "Content-Type: application/json" \
  -d '{
    "talent_id": "d2349ed1-afb5-4b6b-858f-4b91c1de25cb",
    "preferred_styles": ["warm cinematic lighting", "golden hour"],
    "avoided_styles": ["harsh flash", "flat lighting"],
    "prompt_rules": ["soft rim lighting"],
    "negative_prompt_rules": ["cold blue tones"]
  }'

# Submit feedback
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "talent_id": "d2349ed1-afb5-4b6b-858f-4b91c1de25cb",
    "rating": 3,
    "problems": ["face_drift", "bad_lighting"],
    "notes": "Face drifted slightly, lighting too harsh"
  }'

# Get feedback for a talent
curl http://localhost:8000/api/v1/feedback?talent_id=d2349ed1-afb5-4b6b-858f-4b91c1de25cb
```

---

## Dashboard Pages

| Page | Features |
|---|---|
| 🧬 Creative DNA | View/edit DNA per talent, see recent feedback |
| ✨ Creative Session | Automatically loads DNA + feedback to adjust recommendations |

---

## Tested Behaviour

| Input | Expected Effect | Status |
|---|---|---|
| DNA `preferred_styles: ["warm cinematic lighting"]` | Added to positive prompt | ✅ |
| DNA `prompt_rules: ["soft rim lighting"]` | Added to positive prompt | ✅ |
| DNA `avoided_styles: ["harsh flash"]` | Added to negative prompt | ✅ |
| DNA `negative_prompt_rules: ["cold blue tones"]` | Added to negative prompt | ✅ |
| Feedback `problems: ["face_drift"]` | "face deformation" in negative | ✅ |
| Multiple feedback entries with same problem | Feedback warning card shown | ✅ |

---

## Future: ML-Powered Learning

When real ML is added:
- Aggregate ratings per (model, LoRA strength, prompt pattern) → recommend optimal combos
- Cluster high-rated outputs to extract latent style signatures
- Auto-update Creative DNA confidence scores based on sample count
- Provide "why this recommendation" explanations

Current implementation is purely rule-based — explicit mappings only.
