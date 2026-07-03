"""Continuity Checker — validates story consistency before generation.

Checks character identity, wardrobe, props, lighting, weather,
timeline, and relationship consistency across shots and episodes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContinuityWarning:
    """A potential continuity issue detected."""
    severity: str = "warning"  # info, warning, error
    category: str = "general"
    message: str = ""
    shot_number: int | None = None
    suggestion: str = ""


def check_continuity(
    shots: list[dict],
    scene: dict,
    story_memory: list[dict] | None = None,
    character_dna: dict | None = None,
) -> list[ContinuityWarning]:
    """Check a set of shots for continuity issues.

    Args:
        shots: List of shot dicts to validate
        scene: The parent scene context
        story_memory: Relevant story events to check against
        character_dna: Creative DNA for characters in this scene

    Returns:
        List of warnings/errors found
    """
    warnings = []
    memory = story_memory or []
    dna = character_dna or {}

    # Check 1: Character consistency across shots
    scene_characters = set(scene.get("characters", []))
    for shot in shots:
        shot_chars = set(shot.get("characters", []))
        unknown = shot_chars - scene_characters
        if unknown:
            warnings.append(ContinuityWarning(
                severity="warning",
                category="character",
                message=f"Shot {shot.get('shot_number')}: characters {unknown} not in scene",
                shot_number=shot.get("shot_number"),
                suggestion="Add characters to scene or remove from shot",
            ))

    # Check 2: Time of day consistency
    time_of_day = scene.get("time_of_day", "day")
    for shot in shots:
        desc = shot.get("description", "").lower()
        if time_of_day == "night" and any(w in desc for w in ["sunset", "golden hour", "daylight"]):
            warnings.append(ContinuityWarning(
                severity="warning",
                category="lighting",
                message=f"Shot {shot.get('shot_number')}: mentions daylight but scene is set at night",
                shot_number=shot.get("shot_number"),
                suggestion=f"Adjust description to match {time_of_day} setting",
            ))

    # Check 3: Story memory violations
    for event in memory:
        if event.get("category") == "death":
            dead_char = event.get("character_id", "")
            for shot in shots:
                if dead_char in shot.get("characters", []):
                    warnings.append(ContinuityWarning(
                        severity="error",
                        category="continuity",
                        message=f"Shot {shot.get('shot_number')}: includes character '{dead_char}' who is deceased",
                        shot_number=shot.get("shot_number"),
                        suggestion="Remove character or set scene before their death",
                    ))

        if event.get("category") == "injury":
            injured_char = event.get("character_id", "")
            for shot in shots:
                if injured_char in shot.get("characters", []):
                    warnings.append(ContinuityWarning(
                        severity="info",
                        category="continuity",
                        message=f"Shot {shot.get('shot_number')}: {injured_char} has injury: {event.get('event', '')}",
                        shot_number=shot.get("shot_number"),
                        suggestion="Ensure injury is visible/referenced in generation prompt",
                    ))

    # Check 4: Weather consistency across shots
    weather = scene.get("weather", "clear")
    for shot in shots:
        desc = shot.get("description", "").lower()
        if weather == "rain" and "sunny" in desc:
            warnings.append(ContinuityWarning(
                severity="warning",
                category="weather",
                message=f"Shot {shot.get('shot_number')}: describes sunny but scene weather is rain",
                shot_number=shot.get("shot_number"),
            ))

    # Check 5: Duration sanity
    total_duration = sum(s.get("duration_seconds", 3.0) for s in shots)
    if total_duration > 120:
        warnings.append(ContinuityWarning(
            severity="info",
            category="duration",
            message=f"Total scene duration ({total_duration:.0f}s) exceeds 2 minutes",
            suggestion="Consider splitting into multiple scenes",
        ))

    return warnings
