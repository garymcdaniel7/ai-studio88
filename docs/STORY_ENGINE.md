# AI Studio — Story Engine

> Phase E. Narrative-driven content production.

---

## Overview

The Story Engine enables AI Studio to think in narratives, not just single prompts.
It manages universes, characters, episodes, scenes, and shots — turning AI content
production into filmmaking.

```
Universe → Characters → Episodes → Scenes → Shots → Generation Jobs → Assets
```

---

## Hierarchy

```
Universe (Luxury Lives)
  ├── Characters (Melissa, Latifah, Zara)
  ├── Story Memory (persistent events)
  └── Episodes
      └── Scenes
          └── Shots → Generation Jobs → Assets
```

---

## Key Concepts

| Entity | Purpose |
|---|---|
| Universe | Creative world with rules, tone, genre |
| Character | Recurring persona with DNA, memory, relationships |
| Episode | A complete content piece (reel, ad, short film) |
| Scene | A segment with location, mood, characters |
| Shot | A single generation unit (becomes a job) |
| Story Memory | Persistent events that affect continuity |

---

## Scene Builder

Automatically breaks a scene into shots:

1. Establishing wide shot (location, mood)
2. Character introduction (medium shots)
3. Dialogue/interaction (close-ups)
4. Action/reveal (tracking/dolly)
5. Hero beauty shot
6. Closing shot (pull back)

API: `POST /api/v1/scenes/{scene_id}/plan-shots`

---

## Continuity Checker

Validates shots before generation:

- Character presence matches scene
- Time of day consistency
- Weather consistency
- Story memory violations (dead characters, injuries)
- Duration sanity

API: `POST /api/v1/scenes/{scene_id}/check-continuity`

---

## Shot → Generation Pipeline

Each shot becomes a generation job:

```
Shot (description + camera + mood)
  → Generation Engine
  → Provider (simulation or ComfyUI)
  → Output Asset
  → Linked back to shot record
```

API: `POST /api/v1/shots/{shot_id}/generate`

---

## Story Memory

Persistent facts about the universe:

```
"Melissa met Zara in Dubai"                    (relationship)
"Melissa bought a black Rolls Royce"           (possession)
"The penthouse burned down"                    (event)
"Latifah broke her arm in Episode 3"           (injury)
```

Memory persists across episodes and is checked by the Continuity Director.

---

## Database Tables (7 new)

| Table | Purpose |
|---|---|
| universes | Creative worlds |
| characters | Recurring personas |
| episodes | Content pieces |
| scenes | Scene segments |
| shots | Individual generation units |
| story_memory | Persistent events |

---

## API Endpoints (18 new)

| Method | Path | Description |
|---|---|---|
| GET | `/universes` | List universes |
| GET | `/universes/{id}` | Get universe |
| POST | `/universes` | Create universe |
| PUT | `/universes/{id}` | Update universe |
| DELETE | `/universes/{id}` | Delete universe |
| GET | `/universes/{id}/characters` | List characters |
| POST | `/characters` | Create character |
| GET | `/characters/{id}` | Get character |
| PUT | `/characters/{id}` | Update character |
| GET | `/universes/{id}/episodes` | List episodes |
| POST | `/episodes` | Create episode |
| GET | `/episodes/{id}` | Get episode |
| PUT | `/episodes/{id}` | Update episode |
| GET | `/episodes/{id}/scenes` | List scenes |
| POST | `/scenes` | Create scene |
| GET | `/scenes/{id}/shots` | List shots |
| POST | `/scenes/{id}/plan-shots` | Auto-generate shot plan |
| POST | `/shots/{id}/generate` | Generate content for shot |
| POST | `/scenes/{id}/check-continuity` | Validate continuity |
| GET | `/universes/{id}/memory` | List story memory |
| POST | `/memory` | Record story event |

---

## Files

| File | Purpose |
|---|---|
| `backend/story_engine/__init__.py` | Package |
| `backend/story_engine/models.py` | Data models + shot presets |
| `backend/story_engine/scene_builder.py` | Auto shot planning |
| `backend/story_engine/continuity_checker.py` | Continuity validation |
| `dashboard/pages/12_Story.py` | Dashboard page |
| `docs/sql/005_story_engine.sql` | Database migration |
