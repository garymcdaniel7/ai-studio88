# AI Studio — Production Studio

> Phase F. Complete production environment for professional content creation.

---

## Overview

The Production Studio transforms stories into finished productions through
automated media pipelines. It sits between the Story Engine (what to create)
and the Execution Platform (where to execute), managing HOW content is assembled.

```
Story Engine → Production Studio → Execution Platform → Finished Content
```

---

## Production Types (20+)

Portrait, Fashion Campaign, Commercial Photo, Instagram Post, Carousel,
Story, Reel, TikTok, YouTube Short, YouTube Long, Commercial, Music Video,
Short Film, Feature Film, Animation, Podcast, Voiceover, Audiobook,
Livestream Asset, Advertisement, Talking Head.

---

## Media Pipelines (15)

| Pipeline | Description |
|---|---|
| text_to_image | Prompt → Generated image |
| image_to_video | Still image → Animated video |
| text_to_video | Prompt → Generated video |
| storyboard_to_video | Shot list → Assembled video |
| photo_to_reel | Portrait → Motion reel |
| photo_to_talking | Portrait + script → Talking head |
| video_to_clips | Long video → Social clips |
| film_to_trailer | Full film → Trailer |
| podcast_to_shorts | Audio → Video clips |

---

## Production Graph

Every production is a directed graph of nodes. Each node becomes a job:

```
Generate Image → Animate to Video → Add Voiceover → Add Music → Mix → Export
       ↓                  ↓                ↓              ↓         ↓
    [image]           [video]          [audio]        [music]    [final]
```

Nodes are: generation, voice, music, editing, export.
Dependencies are explicit. Every node is retryable and resumable.

---

## Pipeline Templates

| Template | Steps |
|---|---|
| instagram_reel | Generate → Animate → Voice → Music → Mix → Captions → Export |
| tiktok | Generate → Animate → Trim → Music → Export |
| fashion_campaign | Hero → Detail 1 → Detail 2 → BTS → Color Grade → Package |
| talking_head | Portrait → Speech → Lip Sync → Final Mix |
| commercial | Product → Lifestyle → Animate → VO → Music → Assemble → CTA → Export |
| short_film | Shots → Animate → Dialogue → Narration → Score → Assemble → Sound → Grade → Export |

---

## Timeline System

Multi-track timeline for assembling media:

| Track | Content |
|---|---|
| Video | Generated clips, animations |
| Voice | Dialogue, narration, voiceover |
| Music | Background music, jingles |
| Effects | Sound effects, ambient |
| Subtitles | Captions, text overlays |

---

## Camera System

Structured camera metadata attached to every shot:

**Moves:** static, pan, tilt, dolly, truck, crane, orbit, tracking, steadicam, handheld, drone, zoom, rack_focus

**Sizes:** extreme_wide, wide, medium_wide, medium, medium_close, close_up, extreme_close, overhead, dutch_angle

---

## Voice Studio

Voice profiles per character:
- Provider (ElevenLabs, XTTS, OpenVoice, simulation)
- Emotion, accent, language
- Speed, pitch, speaking style
- Character assignment

---

## Music Studio

Music library with:
- Mood, genre, tempo, energy
- Duration, licensing info
- Auto-recommendation by content type

---

## Editing Operations

Graph nodes for post-processing:
trim, merge, split, transition, fade, crop, resize, rotate,
subtitle, watermark, intro, outro, logo, background_music,
voice_mix, audio_normalize, color_grade, export

---

## API Endpoints (13 new)

| Method | Path | Description |
|---|---|---|
| GET | `/production/types` | List production types |
| GET | `/production/pipelines` | List pipeline types |
| GET | `/production/templates` | Pipeline templates with steps |
| POST | `/production/plan` | Build production graph |
| POST | `/production/timeline` | Build timeline from shots |
| GET | `/production/camera/moves` | Camera movements |
| GET | `/production/camera/sizes` | Shot sizes |
| GET | `/production/editing/operations` | Edit operations |
| GET | `/production/voices` | Voice library |
| POST | `/production/voices` | Add voice profile |
| GET | `/production/music` | Music library |
| GET | `/production/music/recommend` | Music recommendation |

---

## Files

| File | Purpose |
|---|---|
| `backend/production/__init__.py` | Package |
| `backend/production/models.py` | All data models (production, timeline, camera, voice, music) |
| `backend/production/pipeline_engine.py` | Graph builder + templates + timeline assembly |
| `backend/production/voice_studio.py` | Voice profile library |
| `backend/production/music_studio.py` | Music library + recommendations |
| `dashboard/pages/13_Production.py` | Production Studio dashboard |
