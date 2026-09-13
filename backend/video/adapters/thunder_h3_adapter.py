"""Thunder H3 Video Adapter — Gary's Thunder Compute A6000 box (local ComfyUI H3).

Implements the canonical CanonicalVideoProvider contract for MiniMax H3
image-to-video generation running on Gary's Thunder Compute GPU box
(RTX A6000 48GB) via its local ComfyUI instance.

The workflow wiring here reproduces EXACTLY the proven recipe from
/home/ubuntu/h3_tsq_crawl.py on the box:

    UNETLoader(FL2VA pruned int8)
      -> LoraLoaderModelOnly(Male_Anatomy @0.9)
      -> LoraLoaderModelOnly(JOKER141 motion repair @0.9)
      -> LoraLoaderModelOnly(turbo 8-step / 4-step @1.0)
      -> MiniMaxH3SigmaShift(shift_video=1.0, shift_audio=1.0)
      -> KSamplerAdvanced (res_multistep / simple, cfg=1.0, 8 steps)
    CLIPLoader(qwen3vl_32b nvfp4_awq, type=minimax) -> text encode
    VAELoader(video_vae) + VAELoader(audio_vae)
    LoadImage(first frame) -> MiniMaxH3ImageToVideo
      -> KSamplerAdvanced -> VAEDecode + VAEDecodeAudio
      -> CreateVideo(fps=24) -> SaveVideo

Lengths must snap to the 17k+5 frame grid: 226 / 243 / 260 / 277.

Deployment mode: local (self-hosted, uncensored, zero per-generation cost).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import random
import time
import uuid
from typing import TYPE_CHECKING

import requests
from dotenv import load_dotenv

from backend.video.contract import (
    CanonicalVideoProvider,
    VideoErrorCode,
    VideoGenerationProgress,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoJobStatus,
    VideoMode,
    VideoModelInfo,
    VideoProviderCapabilities,
    VideoProviderConfig,
    VideoProviderError,
    VideoProviderHealth,
    VideoProviderStatus,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

load_dotenv()

# =============================================================================
# Constants — exact model filenames as present on the box
# =============================================================================

COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
COMFYUI_TIMEOUT = int(os.getenv("COMFYUI_API_TIMEOUT", os.getenv("COMFYUI_TIMEOUT_SECONDS", "1800")))

H3_FL2VA = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
H3_QWEN_CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
H3_VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
H3_AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"

H3_LORA_MALE_ANATOMY = "Male_Anatomy-v2.02-ep4.safetensors"
H3_LORA_MOTION_FIX = "JOKER141_MiniMax-H3-General-Motion-Continuity-Repair.safetensors"
H3_LORA_TURBO_8STEP = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
H3_LORA_TURBO_4STEP = "minimax_h3_fl2v_lightx2v_turbo_4step_v1.0_768p_resized_avg_rank_31_bf16.safetensors"

# The proven LoRA stack (filename, strength) applied in this order.
H3_DEFAULT_LORAS: list[tuple[str, float]] = [
    (H3_LORA_MALE_ANATOMY, 0.9),
    (H3_LORA_MOTION_FIX, 0.9),
    (H3_LORA_TURBO_8STEP, 1.0),
]

# H3 output is fixed at 24 fps with native 32 kHz audio.
H3_FPS = 24
H3_MAX_DURATION_SECONDS = 15.0
H3_DEFAULT_WIDTH = 768
H3_DEFAULT_HEIGHT = 1152

# 17k+5 frame grid — these are the ONLY valid H3 lengths.
H3_LENGTH_GRID = [226, 243, 260, 277]

# Proven default negative prompt (explicit anatomy negatives + ghosting /
# morphing / background-change negatives) from h3_tsq_crawl.py.
H3_DEFAULT_NEGATIVE = (
    "low quality, lowres, bad hands, extra limbs, missing fingers, poorly drawn face, "
    "bad anatomy, blurred, jpeg artifacts, deformed, ugly, bad proportions, disfigured, "
    "watermark, text, logo, signature, unrealistic eyes, lopsided, bad lighting, harsh "
    "shadows, flat shading, unshapely body, pixelated, duplicate limbs, bad perspective, "
    "morphed, distorted, glitch, malformed hands, distorted fingers, noisy background, "
    "overly saturated, unnatural colors, lens distortion, grainy, low detail, identity "
    "change, ghosting, doubled body, images appearing, clothes appearing, clothes "
    "teleporting, background changing, sudden camera movement, sliding across pavement, "
    "unnatural joint rotation, extra person"
)


# =============================================================================
# Helpers
# =============================================================================


def snap_h3_length(length: int) -> int:
    """Snap a requested length to the nearest valid H3 grid value (17k+5)."""
    if length in H3_LENGTH_GRID:
        return length
    return min(H3_LENGTH_GRID, key=lambda v: (abs(v - length), v))


def validate_h3_length(length: int) -> int:
    """Validate length and snap to grid; raises ValueError on absurd input."""
    try:
        length = int(length)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"H3 length must be an integer, got {length!r}") from exc
    if length < H3_LENGTH_GRID[0] or length > H3_LENGTH_GRID[-1]:
        raise ValueError(
            f"H3 length {length} out of range. Valid lengths: {H3_LENGTH_GRID}"
        )
    return snap_h3_length(length)


def build_h3_prompt(
    description: str,
    *,
    overall_soundscape: str = "",
    non_diegetic_music: str = "",
    avoid: str = "",
) -> str:
    """Build the official MiniMax H3 five-part prompt format.

    The first line anchors the target video to Picture 1 from Shot 1 —
    this is required for image-to-video to preserve the first frame.
    """
    parts = [
        "For the target video, at 0.00 seconds into the target video, "
        "<Picture 1> (from [Shot 1]) is fully referenced.",
        "",
        f"integrated_multimodal_description: {description.strip()}",
    ]
    if overall_soundscape:
        parts.append(f"\noverall_soundscape: {overall_soundscape.strip()}")
    parts.append(f"\nnon_diegetic_music: {non_diegetic_music.strip() if non_diegetic_music else 'N/A'}")
    parts.append(f"\nAVOID: {avoid.strip() if avoid else 'clothes appearing or disappearing, background objects appearing or vanishing, camera jumps, morphing, ghosting, extra limbs, changes to facial identity, sliding, unnatural joint rotation, sudden body-position changes, background distortion.'}")
    return "\n".join(parts)


def build_h3_workflow(
    prompt: str,
    image_filename: str,
    *,
    negative: str = H3_DEFAULT_NEGATIVE,
    width: int = H3_DEFAULT_WIDTH,
    height: int = H3_DEFAULT_HEIGHT,
    length: int = 243,
    seed: int = -1,
    steps: int = 8,
    model_loras: list[tuple[str, float]] | None = None,
    out_prefix: str = "video/tsq_crawl",
) -> dict:
    """Build the exact proven H3 I2V ComfyUI API workflow (nodes dict).

    Mirrors /home/ubuntu/h3_tsq_crawl.py build_h3() node-for-node.
    Returns the API-format nodes dict ready for POST /prompt.
    """
    length = validate_h3_length(length)
    seed = seed if seed and seed > 0 else random.randint(1, 999999999)
    loras = list(model_loras) if model_loras else list(H3_DEFAULT_LORAS)
    # Always 3 loader slots in the proven chain: Male_Anatomy, motion fix, turbo.
    if len(loras) < 3:
        loras = loras + H3_DEFAULT_LORAS[len(loras):]

    nodes: dict = {}
    nodes["1"] = {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": H3_FL2VA, "weight_dtype": "default"},
    }
    cur: list = ["1", 0]
    lora_ids = ["1a", "1b", "1c"]
    for i, (name, strength) in enumerate(loras[:3]):
        nid = lora_ids[i]
        nodes[nid] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": cur, "lora_name": name, "strength_model": strength},
        }
        cur = [nid, 0]

    nodes["2"] = {
        "class_type": "MiniMaxH3SigmaShift",
        "inputs": {"model": cur, "shift_video": 1.0, "shift_audio": 1.0},
    }
    nodes["3"] = {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": H3_QWEN_CLIP, "type": "minimax"},
    }
    nodes["4"] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": H3_VIDEO_VAE},
    }
    nodes["5"] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": H3_AUDIO_VAE},
    }
    nodes["6"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative, "clip": ["3", 0]},
    }
    nodes["7"] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_filename},
    }
    nodes["8"] = {
        "class_type": "MiniMaxH3ImageToVideo",
        "inputs": {
            "clip": ["3", 0],
            "vae": ["4", 0],
            "prompt": prompt,
            "width": width,
            "height": height,
            "length": length,
            "first_frame": ["7", 0],
        },
    }
    nodes["9"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": ["2", 0],
            "add_noise": "enable",
            "noise_seed": seed,
            "steps": steps,
            "cfg": 1.0,
            "sampler_name": "res_multistep",
            "scheduler": "simple",
            "positive": ["8", 0],
            "negative": ["6", 0],
            "latent_image": ["8", 1],
            "start_at_step": 0,
            "end_at_step": steps,
            "return_with_leftover_noise": "disable",
        },
    }
    nodes["10"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["9", 0], "vae": ["4", 0]},
    }
    nodes["11"] = {
        "class_type": "VAEDecodeAudio",
        "inputs": {"samples": ["9", 0], "vae": ["5", 0]},
    }
    nodes["12"] = {
        "class_type": "CreateVideo",
        "inputs": {"images": ["10", 0], "audio": ["11", 0], "fps": float(H3_FPS)},
    }
    nodes["13"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["12", 0],
            "filename_prefix": out_prefix,
            "format": "auto",
            "codec": "auto",
        },
    }
    return nodes


# =============================================================================
# Model Definition
# =============================================================================

THUNDER_H3_MODEL = VideoModelInfo(
    id="thunder-h3",
    name="MiniMax H3 (Thunder A6000 — local)",
    provider="thunder-h3",
    modes=[VideoMode.IMAGE_TO_VIDEO],
    max_duration_seconds=H3_MAX_DURATION_SECONDS,
    max_resolution=f"{H3_DEFAULT_WIDTH}x{H3_DEFAULT_HEIGHT}",
    default_resolution=f"{H3_DEFAULT_WIDTH}x{H3_DEFAULT_HEIGHT}",
    default_fps=H3_FPS,
    max_fps=H3_FPS,
    min_frames=H3_LENGTH_GRID[0],
    max_frames=H3_LENGTH_GRID[-1],
    vram_required_gb=48.0,
    supports_negative_prompt=True,
    supports_camera_motion=False,
    supports_seed=True,
    notes=(
        "Gary's Thunder A6000 box - uncensored local H3. "
        "768x1152 portrait, 24fps, native 32kHz audio, lengths 226/243/260/277 "
        "(17k+5 grid). Proven 8-step res_multistep recipe with Male_Anatomy + "
        "JOKER141 motion repair + turbo LoRAs."
    ),
)


# =============================================================================
# ComfyUI Client
# =============================================================================


class ThunderH3ComfyUIClient:
    """Minimal ComfyUI HTTP client for the H3 workflow on Gary's box."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self._base_url = (base_url or COMFYUI_BASE_URL).rstrip("/")
        self._timeout = timeout or COMFYUI_TIMEOUT

    @property
    def base_url(self) -> str:
        return self._base_url

    def system_stats(self) -> dict:
        resp = requests.get(f"{self._base_url}/system_stats", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def upload_image(self, image_bytes: bytes, filename: str = "first.png") -> str:
        """Upload an image via POST /upload/image. Returns the stored name."""
        files = {"image": (filename, image_bytes, "image/png")}
        resp = requests.post(
            f"{self._base_url}/upload/image",
            files=files,
            timeout=120,
        )
        resp.raise_for_status()
        name = resp.json().get("name")
        if not name:
            raise RuntimeError(f"ComfyUI upload returned no name: {resp.text[:200]}")
        return name

    def submit_prompt(self, workflow: dict, client_id: str | None = None) -> str:
        """POST /prompt with the API nodes dict. Returns prompt_id."""
        payload: dict = {"prompt": workflow}
        if client_id:
            payload["client_id"] = client_id
        resp = requests.post(
            f"{self._base_url}/prompt",
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise RuntimeError(f"ComfyUI rejected workflow (HTTP {resp.status_code}): {detail}")
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI /prompt returned no prompt_id: {resp.text[:200]}")
        return prompt_id

    def poll_history(self, prompt_id: str, interval: float = 4.0) -> dict:
        """Poll /history/{id} until terminal. Returns the history entry dict.

        Raises RuntimeError on error status or timeout.
        """
        start = time.time()
        while (time.time() - start) < self._timeout:
            time.sleep(interval)
            try:
                resp = requests.get(
                    f"{self._base_url}/history/{prompt_id}", timeout=10
                )
                if not resp.ok:
                    continue
                history = resp.json()
            except requests.RequestException:
                continue
            if prompt_id not in history:
                continue
            entry = history[prompt_id]
            status = entry.get("status", {})
            status_str = status.get("status_str", "")
            if status_str == "success" or status.get("completed"):
                return entry
            if status_str == "error":
                msgs = [str(m) for m in status.get("messages", [])]
                raise RuntimeError(f"H3 generation failed (prompt_id={prompt_id}): {msgs[-1] if msgs else 'unknown error'}")
        raise TimeoutError(
            f"Timeout after {self._timeout}s waiting for H3 prompt {prompt_id}"
        )

    def download_output(self, file_info: dict) -> bytes:
        """Download an output file via GET /view."""
        params = {
            "filename": file_info.get("filename", "output.mp4"),
            "type": file_info.get("type", "output"),
        }
        if file_info.get("subfolder"):
            params["subfolder"] = file_info["subfolder"]
        resp = requests.get(f"{self._base_url}/view", params=params, timeout=300)
        resp.raise_for_status()
        return resp.content

    def interrupt(self) -> bool:
        try:
            resp = requests.post(f"{self._base_url}/interrupt", timeout=5)
            return resp.ok
        except requests.RequestException:
            return False


# =============================================================================
# Canonical Adapter
# =============================================================================


class ThunderH3VideoAdapter(CanonicalVideoProvider):
    """Canonical adapter for H3 image-to-video on Gary's Thunder box.

    Configuration (via VideoProviderConfig.settings):
        base_url: ComfyUI HTTP URL (default: $COMFYUI_BASE_URL or localhost:8188)
        timeout_seconds: Max wait for generation (default: 1800)
        out_prefix: SaveVideo filename prefix (default: video/tsq_crawl)
    """

    def __init__(self) -> None:
        self._config: VideoProviderConfig | None = None
        self._client: ThunderH3ComfyUIClient | None = None

    @property
    def name(self) -> str:
        return "thunder-h3"

    @property
    def display_name(self) -> str:
        return "Thunder H3 (local ComfyUI)"

    # ─── Discovery ──────────────────────────────────────────────────────────

    def capabilities(self) -> VideoProviderCapabilities:
        return VideoProviderCapabilities(
            provider_name=self.name,
            modes=[VideoMode.IMAGE_TO_VIDEO],
            models=[THUNDER_H3_MODEL],
            max_concurrent_jobs=1,
            supports_cancellation=True,
            supports_progress=True,
            supports_cost_estimate=False,
            supports_priority=False,
            deployment_mode="local",
            notes=(
                "MiniMax H3 via Gary's Thunder Compute A6000 box (ComfyUI). "
                "Uncensored local generation, zero per-clip cost. "
                "Native 32kHz stereo audio. 768x1152 portrait."
            ),
        )

    def health(self) -> VideoProviderHealth:
        client = self._get_client()
        try:
            stats = client.system_stats()
            devices = stats.get("devices", [{}])
            gpu = devices[0] if devices else {}
            return VideoProviderHealth(
                provider_name=self.name,
                status=VideoProviderStatus.AVAILABLE,
                message="ComfyUI reachable",
                gpu_name=gpu.get("name", "Unknown"),
                vram_total_gb=round(gpu.get("vram_total", 0) / (1024**3), 1),
                vram_free_gb=round(gpu.get("vram_free", 0) / (1024**3), 1),
                queue_size=stats.get("exec_info", {}).get("queue_remaining", 0),
            )
        except requests.RequestException as exc:
            return VideoProviderHealth(
                provider_name=self.name,
                status=VideoProviderStatus.UNAVAILABLE,
                message=f"ComfyUI not reachable at {self._base_url_env()}: {exc}",
            )
        except Exception as exc:
            return VideoProviderHealth(
                provider_name=self.name,
                status=VideoProviderStatus.DEGRADED,
                message=f"Health check error: {type(exc).__name__}",
            )

    def list_models(self) -> list[VideoModelInfo]:
        return [THUNDER_H3_MODEL]

    # ─── Validation ─────────────────────────────────────────────────────────

    def validate_request(self, request: VideoGenerationRequest) -> VideoProviderError | None:
        if request.mode != VideoMode.IMAGE_TO_VIDEO:
            return VideoProviderError(
                code=VideoErrorCode.UNSUPPORTED_MODE,
                message=(
                    "thunder-h3 only supports image_to_video mode (H3 I2V on "
                    "the box). Provide a first-frame image."
                ),
                provider_name=self.name,
            )
        if request.duration_seconds > H3_MAX_DURATION_SECONDS:
            return VideoProviderError(
                code=VideoErrorCode.DURATION_EXCEEDED,
                message=f"Maximum duration is {H3_MAX_DURATION_SECONDS}s for H3 on the box.",
                provider_name=self.name,
            )
        if not request.prompt or not request.prompt.strip():
            return VideoProviderError(
                code=VideoErrorCode.INVALID_INPUT,
                message="A prompt is required for H3 image-to-video.",
                provider_name=self.name,
            )
        has_image = bool(
            request.input_image_url
            or request.input_image_bytes
            or request.provider_options.get("first_frame_path")
            or request.provider_options.get("first_frame_b64")
        )
        if not has_image:
            return VideoProviderError(
                code=VideoErrorCode.INVALID_INPUT,
                message=(
                    "Image-to-video requires a first frame: input_image_url, "
                    "input_image_bytes, or provider_options first_frame_path / first_frame_b64."
                ),
                provider_name=self.name,
            )
        return None

    # ─── Execution ──────────────────────────────────────────────────────────

    def submit(
        self,
        request: VideoGenerationRequest,
        on_progress: Callable[[VideoGenerationProgress], None] | None = None,
    ) -> VideoGenerationResult:
        start = time.time()
        client = self._get_client()

        error = self.validate_request(request)
        if error:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=error.code,
                error_message=error.message,
                retryable=False,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
            )

        provider_opts = request.provider_options or {}
        width = int(provider_opts.get("width", request.width) or H3_DEFAULT_WIDTH)
        height = int(provider_opts.get("height", request.height) or H3_DEFAULT_HEIGHT)
        length_raw = int(provider_opts.get("length", provider_opts.get("num_frames", 243)))
        try:
            length = validate_h3_length(length_raw)
        except ValueError as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.INVALID_INPUT,
                error_message=str(exc),
                retryable=False,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
            )
        steps = int(provider_opts.get("steps", request.steps) or 8)
        seed = int(provider_opts.get("seed", request.seed) or -1)
        model_loras_raw = provider_opts.get("model_loras")
        model_loras: list[tuple[str, float]] | None = None
        if model_loras_raw:
            parsed: list[tuple[str, float]] = []
            for item in model_loras_raw:
                if isinstance(item, dict):
                    name = item.get("filename") or item.get("name")
                    strength = item.get("strength", item.get("strength_model", 1.0))
                    parsed.append((str(name), float(strength)))
                else:
                    parsed.append((str(item[0]), float(item[1])))
            model_loras = parsed
        out_prefix = provider_opts.get("out_prefix", "video/tsq_crawl")
        # Allow explicit negative override, else the proven default.
        negative = provider_opts.get("negative") or request.negative_prompt or H3_DEFAULT_NEGATIVE

        # 1. Resolve first-frame image bytes
        try:
            image_bytes, image_name = self._resolve_first_frame(request)
        except Exception as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.INVALID_INPUT,
                error_message=f"Failed to resolve first frame: {exc}",
                retryable=False,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
            )

        # 2. Upload image
        try:
            uploaded_name = client.upload_image(image_bytes, filename=image_name)
        except Exception as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.GENERATION_FAILED,
                error_message=f"Image upload to ComfyUI failed: {exc}",
                retryable=True,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
            )
        logger.info("thunder_h3_image_uploaded image=%s prompt_id_step=upload", uploaded_name)

        # 3. Build workflow with the proven wiring
        workflow = build_h3_workflow(
            request.prompt,
            uploaded_name,
            negative=negative,
            width=width,
            height=height,
            length=length,
            seed=seed,
            steps=steps,
            model_loras=model_loras,
            out_prefix=out_prefix,
        )

        # 4. Submit
        try:
            prompt_id = client.submit_prompt(workflow, client_id=f"thunder_h3_{uuid.uuid4().hex[:8]}")
        except Exception as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.GENERATION_FAILED,
                error_message=str(exc),
                retryable=True,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
            )
        logger.info("thunder_h3_submitted prompt_id=%s length=%d steps=%d", prompt_id, length, steps)
        if on_progress:
            on_progress(VideoGenerationProgress(percent=2, message=f"H3 submitted (prompt_id={prompt_id})"))

        # 5. Poll
        try:
            entry = client.poll_history(prompt_id)
        except TimeoutError as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.TIMED_OUT,
                error_code=VideoErrorCode.PROVIDER_TIMEOUT,
                error_message=str(exc),
                retryable=True,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
                provider_job_id=prompt_id,
                generation_time_seconds=round(time.time() - start, 2),
            )
        except RuntimeError as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.GENERATION_FAILED,
                error_message=str(exc),
                retryable=False,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
                provider_job_id=prompt_id,
                generation_time_seconds=round(time.time() - start, 2),
            )

        # 6. Extract output file info from SaveVideo (node 13)
        outputs = entry.get("outputs", {})
        file_info = self._find_video_output(outputs)
        if not file_info:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.OUTPUT_MISSING,
                error_message="H3 completed but no output video found in history",
                retryable=True,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
                provider_job_id=prompt_id,
                generation_time_seconds=round(time.time() - start, 2),
            )

        # 7. Download the video
        try:
            video_bytes = client.download_output(file_info)
        except Exception as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.GENERATION_FAILED,
                error_message=f"Failed to download output: {exc}",
                retryable=True,
                provider_name=self.name,
                model_used=THUNDER_H3_MODEL.id,
                provider_job_id=prompt_id,
                generation_time_seconds=round(time.time() - start, 2),
            )

        elapsed = round(time.time() - start, 2)
        duration = round(length / H3_FPS, 3)
        if on_progress:
            on_progress(VideoGenerationProgress(percent=100, message="H3 complete — video downloaded"))

        return VideoGenerationResult(
            success=True,
            status=VideoJobStatus.COMPLETED,
            output_bytes=video_bytes,
            filename=file_info.get("filename", f"thunder_h3_{prompt_id[:8]}.mp4"),
            mime_type="video/mp4",
            duration_seconds=duration,
            fps=H3_FPS,
            width=width,
            height=height,
            generation_time_seconds=elapsed,
            provider_name=self.name,
            model_used=THUNDER_H3_MODEL.id,
            seed_used=seed,
            provider_job_id=prompt_id,
            metadata={
                "prompt_id": prompt_id,
                "length_frames": length,
                "steps": steps,
                "width": width,
                "height": height,
                "has_native_audio": True,
                "audio_sample_rate_hz": 32000,
                "audio_channels": "stereo",
                "storage_key": "",
                "public_url": "",
            },
        )

    def cancel(self, provider_job_id: str) -> bool:
        return self._get_client().interrupt()

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self, config: VideoProviderConfig) -> None:
        self._config = config
        settings = config.settings
        base_url = settings.get("base_url", COMFYUI_BASE_URL)
        if not base_url:
            raise ValueError("thunder-h3 adapter requires 'base_url' in settings")
        timeout = int(settings.get("timeout_seconds", COMFYUI_TIMEOUT))
        self._client = ThunderH3ComfyUIClient(base_url=base_url, timeout=timeout)
        logger.info("Thunder H3 adapter initialized (url=%s)", base_url)

    def shutdown(self) -> None:
        self._client = None
        self._config = None

    # ─── Internal ───────────────────────────────────────────────────────────

    def _get_client(self) -> ThunderH3ComfyUIClient:
        if self._client is None:
            self._client = ThunderH3ComfyUIClient(
                base_url=(self._config.settings.get("base_url") if self._config else None),
                timeout=int(self._config.settings.get("timeout_seconds")) if self._config else None,
            )
        return self._client

    def _base_url_env(self) -> str:
        return COMFYUI_BASE_URL

    @staticmethod
    def _resolve_first_frame(request: VideoGenerationRequest) -> tuple[bytes, str]:
        """Resolve first-frame bytes from any supported input shape."""
        provider_opts = request.provider_options or {}
        # Local path on the backend host (dev box / tunnel host)
        path = provider_opts.get("first_frame_path")
        if path:
            with open(path, "rb") as fh:
                return fh.read(), os.path.basename(path) or "first.png"
        # Base64-encoded bytes
        b64 = provider_opts.get("first_frame_b64")
        if b64:
            raw = base64.b64decode(b64)
            return raw, "first.png"
        # Direct bytes
        if request.input_image_bytes:
            return request.input_image_bytes, "first.png"
        # URL (http/https — e.g. B2 public URL)
        url = request.input_image_url
        if url:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content, url.rsplit("/", 1)[-1] or "first.png"
        raise ValueError("no first-frame image provided")

    @staticmethod
    def _find_video_output(outputs: dict) -> dict | None:
        """Find the SaveVideo output file in a ComfyUI history entry.

        SaveVideo reports its file under the 'images' key with
        subfolder 'video' and type 'output'.
        """
        for _node_id, node_output in outputs.items():
            for key in ("video", "gifs", "images"):
                items = node_output.get(key)
                if not items:
                    continue
                if isinstance(items, list) and items:
                    return items[0]
        return None


# =============================================================================
# Legacy provider-compatible helper (used by /generation/run via engine)
# =============================================================================


class ThunderH3ClientAdapter:
    """Thin wrapper exposing the client for the engine provider."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        self.client = ThunderH3ComfyUIClient(base_url=base_url, timeout=timeout)

    def upload_and_generate(
        self,
        prompt: str,
        image_bytes: bytes,
        *,
        negative: str = H3_DEFAULT_NEGATIVE,
        width: int = H3_DEFAULT_WIDTH,
        height: int = H3_DEFAULT_HEIGHT,
        length: int = 243,
        seed: int = -1,
        steps: int = 8,
        model_loras: list[tuple[str, float]] | None = None,
        out_prefix: str = "video/tsq_crawl",
        on_progress: Callable[[VideoGenerationProgress], None] | None = None,
    ) -> VideoGenerationResult:
        """Upload an image and run the proven H3 I2V workflow end-to-end."""
        request = VideoGenerationRequest(
            mode=VideoMode.IMAGE_TO_VIDEO,
            prompt=prompt,
            negative_prompt=negative,
            input_image_bytes=image_bytes,
            width=width,
            height=height,
            steps=steps,
            seed=seed,
            provider_options={
                "length": length,
                "model_loras": model_loras or H3_DEFAULT_LORAS,
                "out_prefix": out_prefix,
            },
        )
        adapter = ThunderH3VideoAdapter()
        adapter._client = self.client  # reuse the same client
        return adapter.submit(request, on_progress=on_progress)
