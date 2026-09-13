"""Unit tests for the Thunder H3 adapter (workflow wiring + length grid).

Network is fully mocked — these tests never touch the box. They verify:
- 17k+5 length grid snapping / validation
- The EXACT proven H3 I2V node wiring (UNETLoader -> 3 LoRAs -> SigmaShift
  -> KSamplerAdvanced + CLIP/VAE/I2V/CreateVideo/SaveVideo)
- The official five-part prompt format
- The submit() flow end-to-end with a fake ComfyUI client
"""

from __future__ import annotations

import pytest

from backend.video.adapters.thunder_h3_adapter import (
    H3_DEFAULT_LORAS,
    H3_DEFAULT_NEGATIVE,
    H3_FPS,
    H3_LENGTH_GRID,
    H3_LORA_MALE_ANATOMY,
    H3_LORA_MOTION_FIX,
    H3_LORA_TURBO_8STEP,
    ThunderH3VideoAdapter,
    build_h3_prompt,
    build_h3_workflow,
    snap_h3_length,
    validate_h3_length,
)
from backend.video.contract import (
    VideoGenerationRequest,
    VideoJobStatus,
    VideoMode,
)


# =============================================================================
# Length grid
# =============================================================================


def test_length_grid_is_17k_plus_5() -> None:
    # 17k + 5: 17*13+5=226, 17*14+5=243, 17*15+5=260, 17*16+5=277
    assert H3_LENGTH_GRID == [226, 243, 260, 277]
    for v in H3_LENGTH_GRID:
        assert (v - 5) % 17 == 0


def test_snap_h3_length_exact_values_pass_through() -> None:
    for v in H3_LENGTH_GRID:
        assert snap_h3_length(v) == v


def test_snap_h3_length_snaps_to_nearest() -> None:
    assert snap_h3_length(230) == 226   # |230-226|=4 < |230-243|=13
    assert snap_h3_length(251) == 243   # |251-243|=8 < |251-260|=9
    assert snap_h3_length(268) == 260   # |268-260|=8 < |268-277|=9
    assert snap_h3_length(999) == 277


def test_validate_h3_length_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        validate_h3_length(100)
    with pytest.raises(ValueError):
        validate_h3_length(300)
    with pytest.raises(ValueError):
        validate_h3_length("abc")


# =============================================================================
# Prompt format
# =============================================================================


def test_build_h3_prompt_five_part_format() -> None:
    prompt = build_h3_prompt("A man walks forward.", overall_soundscape="city ambience")
    assert "For the target video, at 0.00 seconds into the target video" in prompt
    assert "<Picture 1> (from [Shot 1]) is fully referenced" in prompt
    assert "integrated_multimodal_description: A man walks forward." in prompt
    assert "overall_soundscape: city ambience" in prompt
    assert "non_diegetic_music" in prompt
    assert "AVOID:" in prompt


# =============================================================================
# Workflow wiring (the proven recipe)
# =============================================================================


def test_build_h3_workflow_exact_proven_wiring() -> None:
    wf = build_h3_workflow("test prompt", "first.png", seed=42, steps=8, length=226)

    # UNETLoader -> 3 LoRA loaders -> SigmaShift
    assert wf["1"]["class_type"] == "UNETLoader"
    assert wf["1"]["inputs"]["unet_name"] == "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    assert wf["1a"]["class_type"] == "LoraLoaderModelOnly"
    assert wf["1a"]["inputs"]["model"] == ["1", 0]
    assert wf["1b"]["class_type"] == "LoraLoaderModelOnly"
    assert wf["1b"]["inputs"]["model"] == ["1a", 0]
    assert wf["1c"]["class_type"] == "LoraLoaderModelOnly"
    assert wf["1c"]["inputs"]["model"] == ["1b", 0]

    # Default LoRA stack: Male_Anatomy 0.9, motion repair 0.9, turbo 1.0
    assert wf["1a"]["inputs"]["lora_name"] == H3_LORA_MALE_ANATOMY
    assert wf["1a"]["inputs"]["strength_model"] == 0.9
    assert wf["1b"]["inputs"]["lora_name"] == H3_LORA_MOTION_FIX
    assert wf["1b"]["inputs"]["strength_model"] == 0.9
    assert wf["1c"]["inputs"]["lora_name"] == H3_LORA_TURBO_8STEP
    assert wf["1c"]["inputs"]["strength_model"] == 1.0
    assert len(H3_DEFAULT_LORAS) == 3

    # SigmaShift
    assert wf["2"]["class_type"] == "MiniMaxH3SigmaShift"
    assert wf["2"]["inputs"]["model"] == ["1c", 0]
    assert wf["2"]["inputs"]["shift_video"] == 1.0
    assert wf["2"]["inputs"]["shift_audio"] == 1.0

    # CLIP + VAEs
    assert wf["3"]["class_type"] == "CLIPLoader"
    assert wf["3"]["inputs"]["type"] == "minimax"
    assert wf["4"]["class_type"] == "VAELoader"
    assert wf["5"]["class_type"] == "VAELoader"

    # I2V node
    i2v = wf["8"]
    assert i2v["class_type"] == "MiniMaxH3ImageToVideo"
    assert i2v["inputs"]["width"] == 768
    assert i2v["inputs"]["height"] == 1152
    assert i2v["inputs"]["length"] == 226
    assert i2v["inputs"]["first_frame"] == ["7", 0]
    assert i2v["inputs"]["prompt"] == "test prompt"

    # KSamplerAdvanced — the proven 8-step fix
    ks = wf["9"]
    assert ks["class_type"] == "KSamplerAdvanced"
    assert ks["inputs"]["model"] == ["2", 0]
    assert ks["inputs"]["add_noise"] == "enable"
    assert ks["inputs"]["noise_seed"] == 42
    assert ks["inputs"]["steps"] == 8
    assert ks["inputs"]["cfg"] == 1.0
    assert ks["inputs"]["sampler_name"] == "res_multistep"
    assert ks["inputs"]["scheduler"] == "simple"
    assert ks["inputs"]["positive"] == ["8", 0]
    assert ks["inputs"]["negative"] == ["6", 0]
    assert ks["inputs"]["latent_image"] == ["8", 1]
    assert ks["inputs"]["start_at_step"] == 0
    assert ks["inputs"]["end_at_step"] == 8
    assert ks["inputs"]["return_with_leftover_noise"] == "disable"

    # Decode + audio + video assembly
    assert wf["10"]["class_type"] == "VAEDecode"
    assert wf["11"]["class_type"] == "VAEDecodeAudio"
    assert wf["12"]["class_type"] == "CreateVideo"
    assert wf["12"]["inputs"]["fps"] == float(H3_FPS)
    assert wf["13"]["class_type"] == "SaveVideo"
    assert wf["13"]["inputs"]["filename_prefix"] == "video/tsq_crawl"


def test_build_h3_workflow_default_negative_has_anatomy_and_ghost_negatives() -> None:
    assert "ghosting" in H3_DEFAULT_NEGATIVE
    assert "morphed" in H3_DEFAULT_NEGATIVE
    assert "extra limbs" in H3_DEFAULT_NEGATIVE
    wf = build_h3_workflow("p", "f.png")
    assert wf["6"]["inputs"]["text"] == H3_DEFAULT_NEGATIVE


def test_build_h3_workflow_custom_loras_override() -> None:
    custom = [("custom_lora.safetensors", 0.5)]
    wf = build_h3_workflow("p", "f.png", model_loras=custom)
    assert wf["1a"]["inputs"]["lora_name"] == "custom_lora.safetensors"
    assert wf["1a"]["inputs"]["strength_model"] == 0.5
    # Remaining slots fall back to the proven stack
    assert wf["1b"]["inputs"]["lora_name"] == H3_LORA_MOTION_FIX
    assert wf["1c"]["inputs"]["lora_name"] == H3_LORA_TURBO_8STEP


# =============================================================================
# Submit flow with a fake client (no network)
# =============================================================================


class _FakeClient:
    def __init__(self) -> None:
        self.uploaded: list[tuple[bytes, str]] = []
        self.submitted: list[dict] = []
        self.downloaded: list[dict] = []

    def system_stats(self) -> dict:
        return {"devices": [{"name": "RTX A6000", "vram_total": 48 * 1024**3, "vram_free": 40 * 1024**3}], "exec_info": {"queue_remaining": 0}}

    def upload_image(self, image_bytes: bytes, filename: str = "first.png") -> str:
        self.uploaded.append((image_bytes, filename))
        return "uploaded_first.png"

    def submit_prompt(self, workflow: dict, client_id: str | None = None) -> str:
        self.submitted.append(workflow)
        return "fake-prompt-id-123"

    def poll_history(self, prompt_id: str, interval: float = 4.0) -> dict:
        return {
            "prompt_id": prompt_id,
            "status": {"status_str": "success", "completed": True},
            "outputs": {
                "13": {
                    "images": [
                        {"filename": "tsq_crawl_00001_.mp4", "subfolder": "video", "type": "output"}
                    ],
                    "animated": [True],
                }
            },
        }

    def download_output(self, file_info: dict) -> bytes:
        self.downloaded.append(file_info)
        return b"FAKE-VIDEO-BYTES"

    def interrupt(self) -> bool:
        return True


def test_adapter_submit_end_to_end_with_fake_client() -> None:
    adapter = ThunderH3VideoAdapter()
    adapter._client = _FakeClient()

    request = VideoGenerationRequest(
        mode=VideoMode.IMAGE_TO_VIDEO,
        prompt="A man walks forward.",
        negative_prompt="bad anatomy, ghosting",
        input_image_bytes=b"PNG-DATA",
        width=768,
        height=1152,
        steps=8,
        seed=7,
        provider_options={"length": 230},  # should snap to 226
    )

    result = adapter.submit(request)

    assert result.success
    assert result.status == VideoJobStatus.COMPLETED
    assert result.output_bytes == b"FAKE-VIDEO-BYTES"
    assert result.provider_job_id == "fake-prompt-id-123"
    assert result.filename == "tsq_crawl_00001_.mp4"
    assert result.metadata["length_frames"] == 226  # snapped to grid
    assert result.metadata["steps"] == 8
    assert result.duration_seconds == pytest.approx(226 / 24, abs=0.01)
    assert adapter._client.downloaded[0]["subfolder"] == "video"


def test_adapter_submit_rejects_non_i2v() -> None:
    adapter = ThunderH3VideoAdapter()
    adapter._client = _FakeClient()
    request = VideoGenerationRequest(mode=VideoMode.TEXT_TO_VIDEO, prompt="hi")
    result = adapter.submit(request)
    assert not result.success
    assert result.error_code.value == "UNSUPPORTED_MODE"


def test_adapter_submit_requires_first_frame() -> None:
    adapter = ThunderH3VideoAdapter()
    adapter._client = _FakeClient()
    request = VideoGenerationRequest(
        mode=VideoMode.IMAGE_TO_VIDEO, prompt="hi", width=768, height=1152
    )
    result = adapter.submit(request)
    assert not result.success
    assert "first frame" in (result.error_message or "").lower()


def test_adapter_health_and_models() -> None:
    adapter = ThunderH3VideoAdapter()
    adapter._client = _FakeClient()
    health = adapter.health()
    assert health.status.value == "available"
    assert health.gpu_name == "RTX A6000"
    models = adapter.list_models()
    assert models[0].id == "thunder-h3"
    assert VideoMode.IMAGE_TO_VIDEO in models[0].modes
    assert models[0].max_resolution == "768x1152"
    assert models[0].default_fps == 24
    assert "uncensored local H3" in models[0].notes
