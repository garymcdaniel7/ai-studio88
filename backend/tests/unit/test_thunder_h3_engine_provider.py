"""Unit tests for the ThunderH3Provider engine provider (/generation/run path).

Verifies GenerationRequest -> canonical VideoGenerationRequest translation
and GenerationOutput mapping with a stubbed adapter (no network).
"""

from __future__ import annotations

import pytest

from backend.engine.models import GenerationRequest, GenerationType
from backend.engine.providers.thunder_h3 import ThunderH3Provider

pytestmark = pytest.mark.unit


class _StubAdapter:
    def __init__(self) -> None:
        self.last_request = None

    def initialize(self, config) -> None:
        self.config = config

    def submit(self, request, on_progress=None):
        self.last_request = request
        from backend.video.contract import VideoGenerationResult, VideoJobStatus

        return VideoGenerationResult(
            success=True,
            status=VideoJobStatus.COMPLETED,
            output_bytes=b"REAL-H3-BYTES",
            filename="video_00001_.mp4",
            mime_type="video/mp4",
            duration_seconds=226 / 24,
            fps=24,
            width=768,
            height=1152,
            seed_used=7,
            provider_job_id="prompt-abc",
            metadata={"prompt_id": "prompt-abc", "length_frames": 226},
        )

    def cancel(self, job_id: str) -> bool:
        return True


@pytest.fixture()
def provider(monkeypatch) -> tuple[ThunderH3Provider, _StubAdapter]:
    stub = _StubAdapter()
    monkeypatch.setattr(ThunderH3Provider, "_get_adapter", lambda self: stub)
    return ThunderH3Provider(base_url="http://localhost:18188"), stub


def test_submit_translates_generation_request(provider) -> None:
    p, stub = provider
    req = GenerationRequest(
        type=GenerationType.VIDEO,
        prompt="A man walks forward.",
        negative_prompt="ghosting, morphed",
        width=768,
        height=1152,
        steps=8,
        seed=7,
        model="thunder-h3",
        extra={"first_frame": "/tmp/first.png", "length": 226},
    )
    out = p.submit(req)

    assert out.file_bytes == b"REAL-H3-BYTES"
    assert out.filename == "video_00001_.mp4"
    assert out.seed_used == 7
    assert out.metadata["provider"] == "thunder-h3"
    assert out.metadata["prompt_id"] == "prompt-abc"
    assert out.width == 768 and out.height == 1152

    # The canonical request must carry the exact requested length + first frame path
    c = stub.last_request
    assert c.mode.value == "image_to_video"
    assert c.provider_options["length"] == 226  # exact frame-grid value
    assert c.provider_options["first_frame_path"] == "/tmp/first.png"
    assert c.prompt == "A man walks forward."


def test_submit_requires_first_frame(provider) -> None:
    p, _ = provider
    req = GenerationRequest(
        type=GenerationType.VIDEO,
        prompt="no image here",
        extra={},
    )
    from backend.engine.provider import ProviderExecutionError

    with pytest.raises(ProviderExecutionError, match="first frame"):
        p.submit(req)


@pytest.mark.parametrize("invalid_length", [0, -1, 216, 280, 601, "226", 226.0])
def test_submit_rejects_unsupported_or_non_integer_length(provider, invalid_length) -> None:
    p, _ = provider
    req = GenerationRequest(
        type=GenerationType.VIDEO,
        prompt="x",
        extra={"first_frame": "/tmp/f.png", "length": invalid_length},
    )
    from backend.engine.provider import ProviderExecutionError

    with pytest.raises(ProviderExecutionError):
        p.submit(req)


def test_provider_name_and_capabilities() -> None:
    p = ThunderH3Provider()
    assert p.name == "thunder-h3"
    caps = p.capabilities()
    assert caps.supports_video is True
    assert "thunder-h3" in caps.supported_models
