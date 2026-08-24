"""Unit tests for ImageGenerationHandler."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.image_handler import ImageGenerationHandler


def _job(**overrides) -> dict:
    job = {
        "id": "job-1",
        "input": {"prompt": "a test image", "model": "sdxl-turbo", "width": 1024, "height": 1024},
    }
    job["input"].update(overrides)
    return job


@patch("backend.handlers.image_handler.httpx.post")
@patch("backend.handlers.image_handler.httpx.get")
@patch("backend.handlers.image_handler.upload_file", return_value="https://b2.example/img.png")
@patch("backend.handlers.image_handler.generate_storage_key", return_value="image/img.png")
def test_execute_generates_and_uploads(mock_key, mock_upload, mock_get, mock_post):
    # POST /prompt returns a prompt_id
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"prompt_id": "abc123"}
    mock_post.return_value.raise_for_status = MagicMock()

    # GET /history returns the output image ref
    history = MagicMock()
    history.status_code = 200
    history.json.return_value = {
        "abc123": {"outputs": {"9": {"images": [{"filename": "aistudio_00001_.png"}]}}}
    }
    # GET /view returns the image bytes
    view = MagicMock()
    view.status_code = 200
    view.content = b"\x89PNG fake-image-bytes"

    def _get_side_effect(url, *a, **kw):
        if "/history" in url:
            return history
        if "/view" in url:
            return view
        return MagicMock(status_code=404)

    mock_get.side_effect = _get_side_effect

    handler = ImageGenerationHandler()
    progress_calls = []
    result = handler.execute(_job(), lambda p: progress_calls.append(p))

    assert result["image_url"] == "https://b2.example/img.png"
    assert result["provider"] == "comfyui"
    assert result["storage_provider"] == "backblaze_b2"
    assert result["model"] == "sdxl-turbo"
    mock_upload.assert_called_once()
    assert progress_calls[-1] == 100


@patch("backend.handlers.image_handler.httpx.post")
def test_execute_requires_prompt(mock_post):
    handler = ImageGenerationHandler()
    with pytest.raises(ValueError, match="requires a prompt"):
        handler.execute(_job(prompt=""), MagicMock())


@patch("backend.handlers.image_handler.httpx.post")
def test_execute_rejects_unknown_model(mock_post):
    handler = ImageGenerationHandler()
    with pytest.raises(RuntimeError, match="No ComfyUI checkpoint"):
        handler.execute(_job(model="unknown-model"), MagicMock())


@patch("backend.handlers.image_handler.httpx.post")
def test_execute_fails_fast_when_comfyui_down(mock_post):
    mock_post.side_effect = __import__("httpx").ConnectError("conn refused")
    handler = ImageGenerationHandler()
    with pytest.raises(RuntimeError, match="ComfyUI unreachable"):
        handler.execute(_job(), MagicMock())
