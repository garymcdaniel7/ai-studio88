"""Video and Editing Provider Interfaces.

All video generation and editing backends implement these interfaces.
AI Studio dispatches through them without knowing provider details.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class VideoRequest:
    """Request for video generation."""
    prompt: str = ""
    negative_prompt: str = ""
    motion_prompt: str = ""
    input_image_bytes: bytes | None = None
    input_video_bytes: bytes | None = None
    duration_seconds: float = 5.0
    fps: int = 24
    resolution: str = "1080x1920"
    model: str = "wan-2.1"
    camera_motion: str = "static"
    seed: int = -1
    extra: dict = field(default_factory=dict)


@dataclass
class VideoResult:
    """Result from video generation."""
    success: bool = False
    output_bytes: bytes | None = None
    filename: str = ""
    mime_type: str = "video/mp4"
    duration_seconds: float = 0.0
    fps: int = 24
    resolution: str = ""
    generation_time_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class VideoProgress:
    percent: int = 0
    frame: int = 0
    total_frames: int = 0
    message: str = ""


class VideoProvider(ABC):
    """Abstract base for video generation providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def health(self) -> dict: ...

    @abstractmethod
    def capabilities(self) -> dict: ...

    @abstractmethod
    def submit(self, request: VideoRequest, on_progress: Callable | None = None) -> VideoResult: ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...


class EditingProvider(ABC):
    """Abstract base for video editing providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def trim(self, video_bytes: bytes, start: float, end: float) -> bytes: ...

    @abstractmethod
    def merge(self, clips: list[bytes]) -> bytes: ...

    @abstractmethod
    def add_audio(self, video_bytes: bytes, audio_bytes: bytes) -> bytes: ...

    @abstractmethod
    def add_subtitles(self, video_bytes: bytes, subtitles: list[dict]) -> bytes: ...

    @abstractmethod
    def export(self, video_bytes: bytes, format: str, resolution: str, fps: int) -> bytes: ...


# =============================================================================
# Simulated Providers
# =============================================================================

class SimulatedVideoProvider(VideoProvider):
    @property
    def name(self): return "simulation"

    def health(self): return {"healthy": True, "provider": self.name}

    def capabilities(self):
        return {
            "provider": self.name,
            "modes": ["text_to_video", "image_to_video", "video_to_video", "talking_head"],
            "models": ["wan-2.1", "hunyuan", "ltx", "any"],
            "max_duration": 30, "max_fps": 30, "max_resolution": "2160x3840",
        }

    def submit(self, request: VideoRequest, on_progress: Callable | None = None) -> VideoResult:
        start = time.time()
        total_frames = int(request.duration_seconds * request.fps)
        step_delay = 0.005  # Fast simulation

        for frame in range(1, min(total_frames, 50) + 1):  # Cap simulation frames
            time.sleep(step_delay)
            if on_progress and frame % 10 == 0:
                on_progress(VideoProgress(
                    percent=int((frame / min(total_frames, 50)) * 100),
                    frame=frame, total_frames=total_frames,
                    message=f"Generating frame {frame}/{total_frames}",
                ))

        fake_video = hashlib.sha256(f"video-{request.prompt}-{time.time()}".encode()).digest() * 64
        filename = f"video_{uuid.uuid4().hex[:8]}.mp4"

        return VideoResult(
            success=True,
            output_bytes=fake_video,
            filename=filename,
            mime_type="video/mp4",
            duration_seconds=request.duration_seconds,
            fps=request.fps,
            resolution=request.resolution,
            generation_time_seconds=round(time.time() - start, 2),
            metadata={
                "provider": self.name, "model": request.model,
                "prompt": request.prompt, "motion_prompt": request.motion_prompt,
                "camera_motion": request.camera_motion, "seed": request.seed,
            },
        )

    def cancel(self, job_id: str): return True


class SimulatedEditingProvider(EditingProvider):
    @property
    def name(self): return "simulation"

    def trim(self, video_bytes, start, end): return video_bytes
    def merge(self, clips): return clips[0] if clips else b""
    def add_audio(self, video_bytes, audio_bytes): return video_bytes
    def add_subtitles(self, video_bytes, subtitles): return video_bytes
    def export(self, video_bytes, format, resolution, fps): return video_bytes


# =============================================================================
# Provider Registry
# =============================================================================

from backend.video.comfyui_provider import ComfyUIVideoProvider

VIDEO_PROVIDERS: dict[str, type[VideoProvider]] = {
    "simulation": SimulatedVideoProvider,
    "comfyui": ComfyUIVideoProvider,
}

EDITING_PROVIDERS: dict[str, type[EditingProvider]] = {
    "simulation": SimulatedEditingProvider,
    # Future: "ffmpeg", "moviepy", "cloud_editing"
}

# Default provider is configurable via environment
_DEFAULT_VIDEO_PROVIDER = os.environ.get("VIDEO_GENERATION_PROVIDER", "simulation")


def get_video_provider(name: str | None = None) -> VideoProvider:
    provider_name = name or _DEFAULT_VIDEO_PROVIDER
    cls = VIDEO_PROVIDERS.get(provider_name)
    if not cls:
        raise ValueError(f"Unknown video provider: {provider_name}")
    return cls()


def get_editing_provider(name: str = "simulation") -> EditingProvider:
    cls = EDITING_PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"Unknown editing provider: {name}")
    return cls()
