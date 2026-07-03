# AI Studio — Performance Engine

> Priority 7. Unified system for voice training, song creation, performance memory, and series continuity.

---

## Overview

The Performance Engine makes AI characters not just look consistent — they **perform** consistently. It unifies voice, music, acting, and continuity into one connected system.

```
Performance Engine
  ├── Voice Training (datasets → training → voice versions)
  ├── Song Studio (lyrics → composition → generation)
  ├── Performance Memory (how characters were performing at each moment)
  ├── Performance DNA (how characters perform generally)
  ├── Voice DNA (how characters speak/sing)
  ├── Series Structure (universe → series → season → episode)
  └── Soundtrack Cues (music attached to story moments)
```

---

## Key Innovation: Performance Memory

Most AI tools regenerate from scratch. AI Studio remembers:

- What emotion the character was in
- Where they were standing
- What direction they were facing
- What they were wearing/holding
- What happened in the previous scene
- What energy level they had

If Melissa storms out angry in Scene 4, Scene 5 **automatically** begins with her still angry, same outfit, same direction, same energy.

---

## Voice Training Pipeline

```
Upload samples → Build dataset → Validate → Train → Store model → Attach to character → Use in dialogue/songs
```

**Consent:** Every voice dataset stores `consent_confirmed`, `usage_rights`, and `license_notes`.

Future providers: ElevenLabs, XTTS, OpenVoice, Fish Speech, RVC, Coqui

---

## Song Studio Pipeline

```
Concept → Lyrics → Hook → Chorus → Instruments → Vocals → Master → Publish
```

Songs link to: story_id, episode_id, scene_id, character_id

Future providers: Suno, Udio, Stable Audio, MusicGen, ACE-Step

---

## Performance DNA

How a character performs (body language, mannerisms):

- smile_frequency, eyebrow_movement, eye_contact
- head_tilts, walking_style, hand_gestures
- laugh_style, breathing_pattern, idle_animations
- camera_awareness, signature_moves

---

## Voice DNA

How a character speaks/sings:

- personality, vocabulary, cadence, energy
- warmth, confidence, humor, pacing
- filler_words, slang, avoid_words
- singing_range, singing_style, singing_genre

---

## Series Structure

```
Universe → Series → Season → Episode → Scene → Shot
```

Series support:
- opening/ending theme songs
- episode count, season count
- platform targeting (YouTube, TikTok, etc.)

---

## Soundtrack Cues

Music attached to specific story moments:

- cue_type: background, theme, transition, sting, underscore
- Linked to episode/scene/shot
- Volume, fade in/out

Musical storytelling: Opening Theme → Character Theme → Love Theme → Battle → Credits

---

## API Endpoints (25+)

| Category | Endpoints |
|---|---|
| Voice Training | datasets, jobs, versions |
| Voice DNA | CRUD |
| Songs | CRUD + generate |
| Performance Memory | record, list, get latest |
| Performance DNA | CRUD |
| Series | CRUD |
| Soundtrack Cues | CRUD |

---

## Database Tables (10 new)

`voice_datasets`, `voice_training_jobs`, `voice_versions`, `voice_dna`,
`songs`, `performance_memory`, `performance_dna`, `series`, `soundtrack_cues`

See `docs/sql/011_performance_engine.sql`.

---

## AI Agents (designed for future implementation)

| Agent | Role |
|---|---|
| AI Songwriter | Writes lyrics, hooks, chooses genre, recommends BPM/key |
| AI Vocal Producer | Emotional delivery, breathing, pauses, harmonies |
| AI Director | Tells characters how to perform (body language, motion) |

---

## Definition of Done

AI Studio can plan voice training and song creation as part of story/series production.
Performance Memory maintains character continuity across shots.
All using simulated providers, ready for real providers later.
