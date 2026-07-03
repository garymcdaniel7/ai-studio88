# Skill: Create a Video Project

## Purpose

Create a video project from concept to rendered output.

## Steps

```bash
# 1. Create video project
curl -X POST http://localhost:8000/api/v1/videos \
  -H "Content-Type: application/json" \
  -d '{"name":"Dubai Reel","video_type":"reel","platform":"instagram","aspect_ratio":"9:16","duration_seconds":5}'

# 2. Add shots
curl -X POST http://localhost:8000/api/v1/videos/{project_id}/shots \
  -d '{"prompt":"luxury rooftop golden hour","motion_prompt":"slow dolly in","shot_number":1,"duration_seconds":3,"camera_motion":"dolly_in"}'

curl -X POST http://localhost:8000/api/v1/videos/{project_id}/shots \
  -d '{"prompt":"Melissa close-up portrait","motion_prompt":"subtle hair movement","shot_number":2,"duration_seconds":2,"camera_motion":"static"}'

# 3. Generate all shots
curl -X POST http://localhost:8000/api/v1/videos/{project_id}/generate

# 4. View timeline
curl http://localhost:8000/api/v1/videos/{project_id}/timeline

# 5. Render
curl -X POST http://localhost:8000/api/v1/videos/{project_id}/render

# 6. Export
curl -X POST http://localhost:8000/api/v1/videos/{project_id}/export \
  -d '{"format":"mp4","resolution":"1080x1920","fps":24}'
```

## Video types

reel, tiktok, youtube_short, trailer, commercial, music_video,
talking_head, character_overlay, text_to_video, image_to_video

## Camera motions

static, pan_left, pan_right, dolly_in, dolly_out, orbit,
tracking, steadicam, handheld, drone, crane_up, zoom_in
