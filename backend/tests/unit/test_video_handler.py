"""Unit tests for VideoGenerationHandler.

Covers:
    - Building the correct VideoRequest from job input (with defaults)
    - provider.submit being called with a VideoRequest + progress callback
    - Backblaze B2 upload invocation
    - The result dict shape ({video_url, duration_seconds, provider, storage_provider})
    - The simulation fallback path when ComfyUI is unreachable / not registered
    - Progress callback mapping to the worker's 0-100 report

All provider and storage interactions are mocked — these tests never hit a
real ComfyUI instance or Backblaze B2.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.handlers.video_handler import VideoGenerationHandler
from backend.video.provider import VideoProgress, VideoRequest, VideoResult


def _job(**input_overrides: object) -> dict:
    input_data = {
        "prompt": "A serene mountain lake at sunrise",
        "width": 1280,
        "height": 720,
        "duration_seconds": 6,
        "model": "wan-2.1",
    }
    input_data.update(input_overrides)
    return {"id": "job-1", "type": "video_generation", "input": input_data}


def _result(**overrides: object) -> VideoResult:
    data = {
        "success": True,
        "output_bytes": b"fake-video-bytes",
        "filename": "clip.mp4",
        "mime_type": "video/mp4",
        "duration_seconds": 6.0,
    }
    data.update(overrides)
    return VideoResult(**data)


def _providers(mock_gvp: MagicMock, comfy_healthy: bool = True) -> tuple[MagicMock, MagicMock]:
    """Build comfyui + simulation provider mocks and wire get_video_provider."""
    comfy = MagicMock(name="comfyui")
    comfy.name = "comfyui"
    comfy.health.return_value = (
        {"healthy": True, "provider": "comfyui"}
        if comfy_healthy
        else {"healthy": False, "error": "connection refused"}
    )
    sim = MagicMock(name="simulation")
    sim.name = "simulation"
    sim.submit.return_value = _result(filename="sim.mp4", duration_seconds=5.0)

    def _resolve(name: str):
        return comfy if name == "comfyui" else sim

    mock_gvp.side_effect = _resolve
    return comfy, sim


# =============================================================================
# VideoRequest construction
# =============================================================================


def test_builds_video_request_from_job_input() -> None:
    handler = VideoGenerationHandler()
    request = handler._build_request(_job()["input"])

    assert isinstance(request, VideoRequest)
    assert request.prompt == "A serene mountain lake at sunrise"
    assert request.resolution == "1280x720"
    assert request.duration_seconds == 6.0
    assert request.model == "wan-2.1"
    assert request.fps == 24


def test_build_request_applies_defaults() -> None:
    handler = VideoGenerationHandler()
    request = handler._build_request({"prompt": "hello"})

    assert request.resolution == "832x480"
    assert request.duration_seconds == 5.0
    assert request.model == "wan-2.1"
    assert request.fps == 24
    assert request.seed == -1


def test_build_request_supports_duration_alias() -> None:
    handler = VideoGenerationHandler()
    request = handler._build_request({"prompt": "x", "duration": 3})
    assert request.duration_seconds == 3.0


# =============================================================================
# Execution flow
# =============================================================================


@patch("backend.handlers.video_handler.get_video_provider_registry")
@patch("backend.handlers.video_handler.get_video_provider")
@patch("backend.handlers.video_handler.generate_storage_key", return_value="video/abc123.mp4")
@patch("backend.handlers.video_handler.upload_file", return_value="https://b2.example/abc123.mp4")
def test_execute_submits_and_uploads_to_b2(
    mock_upload: MagicMock,
    mock_gen_key: MagicMock,
    mock_gvp: MagicMock,
    mock_registry: MagicMock,
) -> None:
    registry = mock_registry.return_value
    registry.select_provider.return_value = MagicMock(name="comfyui-wan")

    comfy, _sim = _providers(mock_gvp, comfy_healthy=True)
    comfy.submit.return_value = _result()

    handler = VideoGenerationHandler()
    report_progress = MagicMock()
    output = handler.execute(_job(), report_progress)

    # provider.submit called with the right VideoRequest and a progress callback
    assert comfy.submit.called
    call = comfy.submit.call_args
    request = call.args[0]
    assert isinstance(request, VideoRequest)
    assert request.resolution == "1280x720"
    assert request.prompt == "A serene mountain lake at sunrise"
    assert call.kwargs.get("on_progress") is not None

    # B2 upload invoked with bytes / key / mime type
    mock_gen_key.assert_called_once_with("clip.mp4", "video")
    assert mock_upload.called
    upload_call = mock_upload.call_args
    assert upload_call.args[0] == b"fake-video-bytes"
    assert upload_call.args[1] == "video/abc123.mp4"
    assert upload_call.args[2] == "video/mp4"

    # Result dict shape
    assert output == {
        "video_url": "https://b2.example/abc123.mp4",
        "duration_seconds": 6.0,
        "provider": "comfyui",
        "storage_provider": "backblaze_b2",
    }
    # Progress reported at start and completion
    report_progress.assert_any_call(1)
    report_progress.assert_any_call(100)


@patch("backend.handlers.video_handler.get_video_provider_registry")
@patch("backend.handlers.video_handler.get_video_provider")
@patch("backend.handlers.video_handler.upload_file", return_value="https://b2.example/sim.mp4")
@patch("backend.handlers.video_handler.generate_storage_key", return_value="video/sim.mp4")
def test_execute_raises_when_provider_fails(
    mock_gen_key: MagicMock,
    mock_upload: MagicMock,
    mock_gvp: MagicMock,
    mock_registry: MagicMock,
) -> None:
    registry = mock_registry.return_value
    registry.select_provider.return_value = MagicMock(name="comfyui-wan")

    comfy, _sim = _providers(mock_gvp, comfy_healthy=True)
    comfy.submit.return_value = VideoResult(success=False, error="GPU OOM")

    handler = VideoGenerationHandler()
    try:
        handler.execute(_job(), MagicMock())
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "GPU OOM" in str(exc)

    # No upload should happen on failure
    assert not mock_upload.called


# =============================================================================
# Simulation fallback path
# =============================================================================


@patch("backend.handlers.video_handler.get_video_provider_registry")
@patch("backend.handlers.video_handler.get_video_provider")
@patch("backend.handlers.video_handler.upload_file", return_value="https://b2.example/sim.mp4")
@patch("backend.handlers.video_handler.generate_storage_key", return_value="video/sim.mp4")
def test_falls_back_to_simulation_when_comfyui_unreachable(
    mock_gen_key: MagicMock,
    mock_upload: MagicMock,
    mock_gvp: MagicMock,
    mock_registry: MagicMock,
) -> None:
    registry = mock_registry.return_value
    registry.select_provider.return_value = MagicMock(name="comfyui-wan")

    comfy, sim = _providers(mock_gvp, comfy_healthy=False)

    handler = VideoGenerationHandler()
    output = handler.execute(_job(), MagicMock())

    # ComfyUI was health-checked but never submitted to; simulation ran instead
    comfy.health.assert_called_once()
    assert comfy.submit.call_count == 0
    assert sim.submit.called
    assert output["provider"] == "simulation"
    assert output["storage_provider"] == "backblaze_b2"
    assert output["video_url"] == "https://b2.example/sim.mp4"


@patch("backend.handlers.video_handler.get_video_provider_registry")
@patch("backend.handlers.video_handler.get_video_provider")
@patch("backend.handlers.video_handler.upload_file", return_value="https://b2.example/sim.mp4")
@patch("backend.handlers.video_handler.generate_storage_key", return_value="video/sim.mp4")
def test_uses_simulation_when_registry_selects_nothing(
    mock_gen_key: MagicMock,
    mock_upload: MagicMock,
    mock_gvp: MagicMock,
    mock_registry: MagicMock,
) -> None:
    registry = mock_registry.return_value
    registry.select_provider.return_value = None

    _comfy, sim = _providers(mock_gvp)

    handler = VideoGenerationHandler()
    output = handler.execute(_job(), MagicMock())

    assert sim.submit.called
    assert output["provider"] == "simulation"


# =============================================================================
# Progress reporting
# =============================================================================


def test_progress_callback_maps_and_clamps_percent() -> None:
    handler = VideoGenerationHandler()
    report = MagicMock()
    cb = handler._progress_callback(report)

    cb(VideoProgress(percent=50, frame=12, total_frames=24, message="generating"))
    cb(VideoProgress(percent=150))
    cb(VideoProgress(percent=-5))

    assert report.call_count == 3
    assert report.call_args_list[0].args[0] == 50
    assert report.call_args_list[1].args[0] == 100
    assert report.call_args_list[2].args[0] == 0


# =============================================================================
# Worker wiring
# =============================================================================


def test_job_handlers_maps_video_generation_to_real_handler() -> None:
    from backend.worker import JOB_HANDLERS

    handler_class = JOB_HANDLERS["video_generation"]
    assert handler_class is VideoGenerationHandler
    assert handler_class is not None
    # Sanity: a real handler instance exposes the expected name
    assert handler_class().name == "video_generation"
