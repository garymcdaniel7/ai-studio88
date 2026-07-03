"""Story Engine data models.

Defines the hierarchy: Universe → Series → Episode → Scene → Shot
Plus supporting entities: Character, Location, Relationship, StoryMemory
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Universe:
    """A creative universe containing characters, stories, and continuity."""
    id: str = ""
    name: str = ""
    description: str = ""
    genre: str = ""
    tone: str = ""
    setting: str = ""
    rules: list[str] = field(default_factory=list)  # Universe rules (physics, magic, etc.)
    metadata: dict = field(default_factory=dict)


@dataclass
class Character:
    """A recurring character in the story universe."""
    id: str = ""
    universe_id: str = ""
    talent_id: str | None = None  # Links to AI talent for generation
    name: str = ""
    description: str = ""
    personality: str = ""
    goals: str = ""
    backstory: str = ""
    voice_style: str = ""
    wardrobe_default: str = ""
    relationships: list[dict] = field(default_factory=list)
    memory: list[dict] = field(default_factory=list)  # Story memory events
    visual_dna: dict = field(default_factory=dict)  # Creative DNA for this character
    metadata: dict = field(default_factory=dict)


@dataclass
class Episode:
    """A single episode/content piece in a series."""
    id: str = ""
    universe_id: str = ""
    title: str = ""
    description: str = ""
    episode_number: int = 1
    status: str = "draft"  # draft, planned, in_production, completed, published
    scenes: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Scene:
    """A scene within an episode."""
    id: str = ""
    episode_id: str = ""
    scene_number: int = 1
    title: str = ""
    purpose: str = ""
    location: str = ""
    time_of_day: str = "day"
    weather: str = "clear"
    mood: str = ""
    characters: list[str] = field(default_factory=list)  # Character IDs
    dialogue: list[dict] = field(default_factory=list)
    camera_style: str = ""
    music: str = ""
    desired_emotion: str = ""
    shots: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Shot:
    """A single shot within a scene — becomes a generation job."""
    id: str = ""
    scene_id: str = ""
    shot_number: int = 1
    shot_type: str = "medium"  # wide, medium, close_up, extreme_close, drone, tracking, pov
    description: str = ""
    characters: list[str] = field(default_factory=list)
    camera_movement: str = ""  # static, pan_left, dolly_in, orbit, crane_up
    duration_seconds: float = 3.0
    dialogue: str = ""
    action: str = ""
    mood: str = ""
    transition: str = "cut"  # cut, fade, dissolve, wipe
    generation_params: dict = field(default_factory=dict)  # prompt, model, etc.
    status: str = "planned"  # planned, generating, completed, approved, rejected
    asset_id: str | None = None  # Generated output
    job_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class StoryMemory:
    """A memorable event in the story universe that must persist."""
    id: str = ""
    universe_id: str = ""
    character_id: str | None = None
    event: str = ""
    episode_id: str | None = None
    scene_id: str | None = None
    category: str = "event"  # event, relationship, possession, location, injury, death
    active: bool = True
    metadata: dict = field(default_factory=dict)


# Shot type presets for auto-planning
SHOT_TYPE_PRESETS = {
    "establishing": {"shot_type": "wide", "camera_movement": "slow_pan", "duration_seconds": 4.0},
    "medium": {"shot_type": "medium", "camera_movement": "static", "duration_seconds": 3.0},
    "close_up": {"shot_type": "close_up", "camera_movement": "static", "duration_seconds": 2.5},
    "extreme_close": {"shot_type": "extreme_close", "camera_movement": "static", "duration_seconds": 2.0},
    "drone": {"shot_type": "drone", "camera_movement": "orbit", "duration_seconds": 5.0},
    "tracking": {"shot_type": "tracking", "camera_movement": "dolly_in", "duration_seconds": 4.0},
    "pov": {"shot_type": "pov", "camera_movement": "handheld", "duration_seconds": 3.0},
    "slow_motion": {"shot_type": "medium", "camera_movement": "static", "duration_seconds": 4.0},
    "overhead": {"shot_type": "drone", "camera_movement": "static", "duration_seconds": 3.0},
}
