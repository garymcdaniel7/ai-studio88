# AI Studio — Cinematic Studio & Timeline Engine

> Priority 11. Professional virtual film production environment.

---

## Overview

The Cinematic Studio turns AI Studio into a complete film production environment.
Every generation becomes editable. Nothing exists as isolated output.

```
Universe → Series → Season → Episode → Sequence → Scene → Shot → Asset
                                                                    ↓
                                                              Timeline → Edit → Render → Export
```

---

## Production Hierarchy

| Level | Contains |
|---|---|
| Universe | Series, characters, world rules |
| Series | Seasons, episodes |
| Season | Episodes |
| Episode | Sequences, scenes |
| Sequence | Scenes (narrative blocks) |
| Scene | Shots, dialogue, mood |
| Shot | Single generation → asset |

---

## Timeline Engine

Professional multi-track timeline:

| Track Type | Content |
|---|---|
| video | Generated clips, animations |
| voice | Dialogue, narration |
| music | Background music, themes |
| sfx | Sound effects, foley |
| titles | Text overlays, captions |
| effects | Motion graphics, transitions |
| camera | Camera movement metadata |
| color | Color grading track |

---

## Editing Operations (15)

trim, split, merge, duplicate, replace, extend, slow_motion,
speed_ramp, freeze_frame, reverse, stabilize, crop, zoom, pan, rotate

---

## Transitions (10)

cut, fade, cross_dissolve, whip_pan, zoom_transition,
match_cut, flash, film_burn, blur, slide

---

## Color Grades (10)

none, cinematic_warm, cinematic_cool, netflix, kodak,
fuji, luxury_gold, editorial, film_noir, vintage

---

## Export Formats (8)

mp4, mov, png_sequence, gif, webm, audio_only, storyboard_pdf, shot_list_pdf

---

## API Endpoints (25+)

| Category | Endpoints |
|---|---|
| Timelines | CRUD, get with tracks/items |
| Tracks | Create per timeline, list |
| Items | Add/update/delete clips on tracks |
| Storyboard | Create panels, list by episode/scene |
| Editing | List operations, apply edit |
| Transitions | List available |
| Color | List grades |
| Render | Create render job, list |
| Export | List formats |
| Sequences | CRUD |
| Continuity | Check scene/shot consistency |

---

## Continuity Engine

Checks across shots:
- Wardrobe consistency
- Lighting continuity
- Screen direction (180° rule)
- Props, hair, makeup
- Time of day, weather
- Emotion, energy

AI warns before generation if continuity would break.

---

## Storyboard

Each panel links to:
- Scene + shot
- Description + camera + dialogue + action + mood
- Generated asset (when rendered)
- Workflow used

---

## Database Tables (8 new)

`sequences`, `cinematic_timelines`, `cinematic_tracks`, `cinematic_items`,
`storyboard_panels`, `cinematic_renders`, `editing_operations`

See `docs/sql/016_cinematic_studio.sql`.

---

## Lightweight Design

Timeline stores metadata only. Heavy rendering dispatched to workers.
FastAPI never processes video frames — it orchestrates.

---

## Files

| File | Purpose |
|---|---|
| `backend/cinematic/__init__.py` | Package |
| `backend/cinematic/router.py` | 25+ API endpoints |
| `docs/sql/016_cinematic_studio.sql` | 8 database tables |
| `docs/CINEMATIC_STUDIO.md` | This documentation |
