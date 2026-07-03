# AI Studio — Voice, Audio, and Lip Sync Pipeline

> Priority 6. Character voices, narration, dialogue, music, SFX, and lip sync.

---

## Overview

Full audio production pipeline: voice profiles → TTS/dialogue/narration → 
music/SFX → lip sync → video integration. All heavy inference on external workers.

---

## Pipeline

```
Voice Profile → Text → TTS Provider → Audio Asset → Timeline
                                                    ↓
Video Asset + Audio Asset → Lip Sync Provider → Synced Video Asset
```

---

## Provider Interfaces (5)

| Interface | Purpose | Simulated | Future |
|---|---|---|---|
| VoiceProvider | TTS, dialogue, narration | ✅ | ElevenLabs, XTTS, OpenVoice, Fish Speech, RVC |
| MusicProvider | Music generation | ✅ | Suno, Udio, Stable Audio |
| SFXProvider | Sound effects | ✅ | ElevenLabs SFX, Stable Audio |
| LipSyncProvider | Video + audio sync | ✅ | Wav2Lip, SadTalker, MuseTalk, SyncLabs |
| AudioEditingProvider | Cleanup, mix | Planned | FFmpeg |

---

## API Endpoints (20+)

| Method | Path | Description |
|---|---|---|
| GET | `/voice-profiles` | List profiles |
| POST | `/voice-profiles` | Create profile |
| GET | `/voice-profiles/{id}` | Get profile |
| PUT | `/voice-profiles/{id}` | Update profile |
| DELETE | `/voice-profiles/{id}` | Delete profile |
| GET | `/voice-profiles/{id}/samples` | List samples |
| POST | `/voice-profiles/{id}/samples` | Add sample |
| POST | `/audio/tts` | Generate TTS → B2 → Asset |
| POST | `/audio/dialogue` | Generate dialogue |
| POST | `/audio/narration` | Generate narration |
| GET | `/audio/clips` | List audio clips |
| GET | `/audio/clips/{id}` | Get clip |
| POST | `/lip-sync` | Create lip sync job |
| GET | `/lip-sync/jobs` | List lip sync jobs |
| GET | `/lip-sync/jobs/{id}` | Get job |
| GET | `/music` | List music tracks |
| POST | `/music` | Add music track |
| GET | `/sfx` | List sound effects |
| POST | `/sfx` | Add sound effect |
| GET | `/audio/providers/health` | All audio provider health |

---

## Voice Profile Fields

name, provider, voice_type, language, accent, gender, age_range,
tone, speaking_style, speed, pitch, stability, similarity

---

## Database Tables (7 new)

`voice_profiles`, `voice_samples`, `audio_clips`, `lip_sync_jobs`,
`music_tracks_db`, `sound_effects`

See `docs/sql/010_voice_audio_pipeline.sql`.

---

## Full Pipeline Example

```bash
# 1. Create voice profile
curl -X POST .../voice-profiles -d '{"name":"Melissa Voice","tone":"warm","speaking_style":"confident"}'

# 2. Generate dialogue
curl -X POST .../audio/tts -d '{"text":"Welcome to Dubai","voice_profile_id":"...","emotion":"warm"}'

# 3. Lip sync with existing video
curl -X POST .../lip-sync -d '{"video_asset_id":"...","audio_asset_id":"..."}'
```

---

## Files

| File | Purpose |
|---|---|
| `backend/audio/__init__.py` | Package |
| `backend/audio/provider.py` | All provider interfaces + simulated |
| `backend/audio/router.py` | API endpoints |
| `docs/sql/010_voice_audio_pipeline.sql` | Database migration |
