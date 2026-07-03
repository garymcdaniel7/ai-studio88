"""Production Studio data models.

Defines productions, timelines, tracks, clips, voice/music libraries,
camera plans, and the production graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Production Types
# =============================================================================

class ProductionType(str, Enum):
    PORTRAIT = "portrait"
    FASHION_CAMPAIGN = "fashion_campaign"
    COMMERCIAL_PHOTO = "commercial_photo"
    INSTAGRAM_POST = "instagram_post"
    CAROUSEL = "carousel"
    STORY = "story"
    REEL = "reel"
    TIKTOK = "tiktok"
    YOUTUBE_SHORT = "youtube_short"
    YOUTUBE_LONG = "youtube_long"
    COMMERCIAL = "commercial"
    MUSIC_VIDEO = "music_video"
    SHORT_FILM = "short_film"
    FEATURE_FILM = "feature_film"
    ANIMATION = "animation"
    PODCAST = "podcast"
    VOICEOVER = "voiceover"
    AUDIOBOOK = "audiobook"
    LIVESTREAM_ASSET = "livestream_asset"
    ADVERTISEMENT = "advertisement"
    TALKING_HEAD = "talking_head"


# =============================================================================
# Media Pipelines
# =============================================================================

class PipelineType(str, Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_TO_VIDEO = "image_to_video"
    TEXT_TO_VIDEO = "text_to_video"
    VIDEO_TO_VIDEO = "video_to_video"
    STORYBOARD_TO_VIDEO = "storyboard_to_video"
    EPISODE_TO_FILM = "episode_to_film"
    PHOTO_TO_REEL = "photo_to_reel"
    PHOTO_TO_TALKING = "photo_to_talking"
    AUDIO_TO_VIDEO = "audio_to_video"
    VIDEO_TO_CLIPS = "video_to_clips"
    FILM_TO_TRAILER = "film_to_trailer"
    FILM_TO_SHORTS = "film_to_shorts"
    FILM_TO_THUMBNAILS = "film_to_thumbnails"
    PODCAST_TO_SHORTS = "podcast_to_shorts"


# =============================================================================
# Production
# =============================================================================

@dataclass
class Production:
    """A complete production — from concept to published deliverable."""
    id: str = ""
    project_id: str | None = None
    universe_id: str | None = None
    episode_id: str | None = None
    title: str = ""
    type: str = "reel"
    pipeline: str = "text_to_image"
    status: str = "draft"  # draft, planning, producing, editing, reviewing, published
    graph: list[dict] = field(default_factory=list)  # Production graph nodes
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Timeline
# =============================================================================

@dataclass
class Timeline:
    """A multi-track timeline for assembling media."""
    id: str = ""
    production_id: str = ""
    duration_seconds: float = 0.0
    fps: int = 24
    resolution: str = "1080x1920"  # width x height
    tracks: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Track:
    """A single track in a timeline (video, audio, voice, subtitle, effects)."""
    id: str = ""
    timeline_id: str = ""
    name: str = ""
    type: str = "video"  # video, audio, voice, music, subtitle, effects
    order: int = 0
    clips: list[dict] = field(default_factory=list)
    muted: bool = False
    locked: bool = False


@dataclass
class Clip:
    """A clip on a track — references an asset or generation output."""
    id: str = ""
    track_id: str = ""
    asset_id: str | None = None
    shot_id: str | None = None
    start_time: float = 0.0  # Position on timeline (seconds)
    duration: float = 3.0
    in_point: float = 0.0  # Trim start within source
    out_point: float = 0.0  # Trim end within source
    transition_in: str = "cut"
    transition_out: str = "cut"
    effects: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Camera System
# =============================================================================

class CameraMove(str, Enum):
    STATIC = "static"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    TRUCK_LEFT = "truck_left"
    TRUCK_RIGHT = "truck_right"
    CRANE_UP = "crane_up"
    CRANE_DOWN = "crane_down"
    ORBIT = "orbit"
    TRACKING = "tracking"
    STEADICAM = "steadicam"
    HANDHELD = "handheld"
    DRONE = "drone"
    POV = "pov"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    RACK_FOCUS = "rack_focus"


class ShotSize(str, Enum):
    EXTREME_WIDE = "extreme_wide"
    WIDE = "wide"
    MEDIUM_WIDE = "medium_wide"
    MEDIUM = "medium"
    MEDIUM_CLOSE = "medium_close"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE = "extreme_close"
    OVERHEAD = "overhead"
    DUTCH_ANGLE = "dutch_angle"


@dataclass
class CameraPlan:
    """Structured camera metadata for a shot."""
    move: str = "static"
    size: str = "medium"
    lens: str = "50mm"
    fps: int = 24
    slow_motion: bool = False
    slow_motion_factor: float = 1.0
    duration_seconds: float = 3.0
    aspect_ratio: str = "9:16"
    resolution: str = "1080x1920"
    notes: str = ""


# =============================================================================
# Voice
# =============================================================================

@dataclass
class VoiceProfile:
    """Voice DNA for a character."""
    id: str = ""
    character_id: str | None = None
    talent_id: str | None = None
    name: str = ""
    provider: str = "simulation"  # elevenlabs, xtts, openvoice
    voice_id: str = ""  # Provider-specific voice ID
    emotion: str = "neutral"
    accent: str = ""
    language: str = "en"
    speed: float = 1.0
    pitch: float = 1.0
    style: str = ""  # narrative, conversational, dramatic
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Music
# =============================================================================

@dataclass
class MusicTrack:
    """A music track in the library."""
    id: str = ""
    title: str = ""
    provider: str = "library"  # library, ai_generated, licensed
    mood: str = ""
    genre: str = ""
    tempo_bpm: int = 120
    energy: str = "medium"  # low, medium, high
    duration_seconds: float = 0.0
    asset_id: str | None = None
    license_info: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Editing Operations
# =============================================================================

class EditOp(str, Enum):
    TRIM = "trim"
    MERGE = "merge"
    SPLIT = "split"
    TRANSITION = "transition"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    CROP = "crop"
    RESIZE = "resize"
    ROTATE = "rotate"
    SUBTITLE = "subtitle"
    WATERMARK = "watermark"
    INTRO = "intro"
    OUTRO = "outro"
    LOGO = "logo"
    BACKGROUND_MUSIC = "background_music"
    VOICE_MIX = "voice_mix"
    AUDIO_NORMALIZE = "audio_normalize"
    COLOR_GRADE = "color_grade"
    EXPORT = "export"


# =============================================================================
# Production Graph Node
# =============================================================================

@dataclass
class GraphNode:
    """A node in the production graph. Each becomes a job."""
    id: str = ""
    type: str = ""  # generation, voice, music, editing, export
    name: str = ""
    status: str = "pending"  # pending, running, completed, failed
    depends_on: list[str] = field(default_factory=list)  # Node IDs
    provider: str = ""
    parameters: dict = field(default_factory=dict)
    output_asset_id: str | None = None
    job_id: str | None = None
    metadata: dict = field(default_factory=dict)
