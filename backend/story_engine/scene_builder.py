"""Scene Builder — breaks scenes into shots automatically.

Given a scene description, generates a shot plan with camera types,
movements, durations, and estimated generation parameters.
"""
from __future__ import annotations

from backend.story_engine.models import Shot, Scene, SHOT_TYPE_PRESETS


def plan_shots(scene: dict) -> list[dict]:
    """Auto-plan shots for a scene based on its properties.

    Args:
        scene: Scene dict with purpose, characters, location, mood, etc.

    Returns:
        List of shot dicts ready for storage/generation
    """
    shots = []
    purpose = scene.get("purpose", "").lower()
    characters = scene.get("characters", [])
    mood = scene.get("mood", "")
    location = scene.get("location", "")
    dialogue = scene.get("dialogue", [])

    shot_num = 1

    # 1. Always start with establishing shot
    shots.append({
        "shot_number": shot_num,
        "shot_type": "wide",
        "description": f"Establishing shot of {location or 'the scene'}. Set the mood: {mood}.",
        "camera_movement": "slow_pan",
        "duration_seconds": 4.0,
        "characters": [],
        "transition": "fade",
    })
    shot_num += 1

    # 2. Character introductions (medium shots)
    for char in characters[:3]:  # Max 3 character intros
        shots.append({
            "shot_number": shot_num,
            "shot_type": "medium",
            "description": f"Introduce {char}. Show their presence in the scene.",
            "camera_movement": "static",
            "duration_seconds": 3.0,
            "characters": [char],
            "transition": "cut",
        })
        shot_num += 1

    # 3. Dialogue/interaction shots
    if dialogue:
        for line in dialogue[:4]:
            char = line.get("character", characters[0] if characters else "character")
            text = line.get("text", "")
            shots.append({
                "shot_number": shot_num,
                "shot_type": "close_up" if len(text) < 50 else "medium",
                "description": f"{char} speaks: '{text[:60]}...'",
                "camera_movement": "static",
                "duration_seconds": max(2.0, len(text) * 0.05),
                "characters": [char],
                "dialogue": text,
                "transition": "cut",
            })
            shot_num += 1

    # 4. Action/purpose shots
    if "reveal" in purpose or "discover" in purpose:
        shots.append({
            "shot_number": shot_num,
            "shot_type": "close_up",
            "description": f"The reveal moment. {purpose}",
            "camera_movement": "dolly_in",
            "duration_seconds": 3.0,
            "characters": characters[:1],
            "transition": "cut",
        })
        shot_num += 1
    elif "chase" in purpose or "action" in purpose:
        shots.append({
            "shot_number": shot_num,
            "shot_type": "tracking",
            "description": f"Action sequence. {purpose}",
            "camera_movement": "tracking",
            "duration_seconds": 5.0,
            "characters": characters,
            "transition": "cut",
        })
        shot_num += 1

    # 5. Hero/beauty shot
    if characters:
        shots.append({
            "shot_number": shot_num,
            "shot_type": "medium",
            "description": f"Hero shot of {characters[0]}. Cinematic framing, best angle.",
            "camera_movement": "slow_dolly",
            "duration_seconds": 3.5,
            "characters": [characters[0]],
            "transition": "cut",
        })
        shot_num += 1

    # 6. Closing shot
    shots.append({
        "shot_number": shot_num,
        "shot_type": "wide",
        "description": f"Closing shot. Pull back from the scene. {mood} mood.",
        "camera_movement": "crane_up",
        "duration_seconds": 4.0,
        "characters": [],
        "transition": "fade",
    })

    return shots


def estimate_scene_duration(shots: list[dict]) -> float:
    """Calculate total estimated duration of a scene in seconds."""
    return sum(s.get("duration_seconds", 3.0) for s in shots)
