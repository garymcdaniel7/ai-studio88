# AI Studio — Video Studio

> Priority 5. Complete video production pipeline.

---

## Overview

Manages video projects from concept to final export:
Project → Shots → Generate → Timeline → Render → Export → Asset

All heavy video generation and editing runs on external GPU workers.

---

## Supported Video Modes

text_to_video, image_to_video, video_to_video, talking_head,
character_overlay, reel, tiktok, youtube_short, trailer,
commercial, music_video, storyboard_to_video, scene_to_video

---

## Pipeline

```
Create Video Project
  → Define shots (prompt, motion, camera)
  → Generate each shot via VideoProvider
  → Upload outputs to B2, register as Assets
  → Build timeline (tracks + clips)
  → Render timeline via EditingProvider
  → Export final video
  → Register final export as Asset
```

---

## API Endpoints (15+)

| Method | Path | Description |
|---|---|---|
| GET | `/videos` | List video projects |
| POST | `/videos` | Create video project |
| GET | `/videos/{id}` | Get project details |
| PUT | `/videos/{id}` | Update project |
| DELETE | `/videos/{id}` | Delete project |
| GET | `/videos/{id}/shots` | List shots |
| POST | `/videos/{id}/shots` | Add shot |
| POST | `/videos/{id}/generate` | Generate all planned shots |
| GET | `/videos/{id}/timeline` | Get full timeline |
| POST | `/videos/{id}/timeline/tracks` | Add timeline track |
| POST | `/videos/{id}/timeline/clips` | Add timeline clip |
| POST | `/videos/{id}/render` | Render video |
| POST | `/videos/{id}/export` | Export final |
| GET | `/video-renders` | List renders |
| GET | `/video-renders/{id}` | Get render details |

---

## Video Providers

| Provider | Status | Models |
|---|---|---|
| simulation | ✅ Active | any |
| wan | Planned | wan-2.1 |
| hunyuan | Planned | hunyuan-video |
| ltx | Planned | ltx-video |
| kling | Planned | kling |
| runway | Planned | gen-3 |
| pika | Planned | pika |
| comfyui_video | Planned | flux-animate, etc. |

---

## Editing Providers

| Provider | Status | Capabilities |
|---|---|---|
| simulation | ✅ Active | all (simulated) |
| ffmpeg | Planned | trim, merge, audio, export |
| moviepy | Planned | programmatic editing |
| cloud | Planned | remote rendering |

---

## Database Tables (6 new)

`video_projects`, `video_shots`, `video_renders`,
`timeline_tracks`, `timeline_clips`, `timeline_exports`

See `docs/sql/009_video_pipeline.sql`.

---

## Shot Metadata

Each shot stores: prompt, negative_prompt, motion_prompt, model,
duration, fps, resolution, camera_motion, provider, input/output asset refs.

---

## Timeline Structure

```
Video Project
  └── Timeline
      ├── Track: Video (clips from generated shots)
      ├── Track: Voice (dialogue, narration)
      ├── Track: Music (background)
      ├── Track: Effects (transitions, overlays)
      └── Track: Subtitles (captions)
```
