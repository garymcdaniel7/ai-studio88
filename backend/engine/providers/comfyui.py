"""ComfyUI Provider — connects to a ComfyUI instance.

Configuration via environment variables:
    COMFYUI_BASE_URL=http://localhost:8188

This provider:
- Submits workflow JSON to ComfyUI /prompt endpoint
- Polls /history/{prompt_id} for completion
- Downloads output images via /view endpoint
- Reports progress during execution
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Callable

import requests
from dotenv import load_dotenv

from backend.engine.provider import (
    GenerationProvider,
    ProviderConnectionError,
    ProviderExecutionError,
)
from backend.engine.models import (
    GenerationRequest,
    GenerationOutput,
    GenerationProgress,
    ProviderCapabilities,
    ProviderHealth,
)

load_dotenv()

COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
COMFYUI_TIMEOUT = int(os.getenv("COMFYUI_TIMEOUT_SECONDS", "300"))


class ComfyUIProvider(GenerationProvider):
    """ComfyUI generation provider.

    Connects to a running ComfyUI instance and executes workflows.
    """

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self._base_url = (base_url or COMFYUI_BASE_URL).rstrip("/")
        self._timeout = timeout or COMFYUI_TIMEOUT

    @property
    def name(self) -> str:
        return "comfyui"

    def health(self) -> ProviderHealth:
        """Check if ComfyUI is reachable and get system stats."""
        try:
            resp = requests.get(f"{self._base_url}/system_stats", timeout=5)
            if resp.ok:
                stats = resp.json()
                devices = stats.get("devices", [{}])
                gpu = devices[0] if devices else {}
                return ProviderHealth(
                    healthy=True,
                    provider_name=self.name,
                    message="ComfyUI connected",
                    gpu_name=gpu.get("name", "Unknown"),
                    vram_total_gb=round(gpu.get("vram_total", 0) / (1024**3), 1),
                    vram_free_gb=round(gpu.get("vram_free", 0) / (1024**3), 1),
                    queue_size=stats.get("exec_info", {}).get("queue_remaining", 0),
                )
            return ProviderHealth(
                healthy=False,
                provider_name=self.name,
                message=f"ComfyUI returned HTTP {resp.status_code}",
            )
        except requests.ConnectionError:
            return ProviderHealth(
                healthy=False,
                provider_name=self.name,
                message=f"ComfyUI not reachable at {self._base_url}",
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                provider_name=self.name,
                message=f"ComfyUI health check failed: {e}",
            )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            supports_image=True,
            supports_video=True,
            supports_upscale=True,
            supports_training=False,
            supports_voice=False,
            max_resolution=4096,
            supported_models=["flux-dev", "sdxl", "sd1.5", "wan-2.1"],
            max_batch_size=1,
        )

    def submit(
        self,
        request: GenerationRequest,
        on_progress: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationOutput:
        """Submit a workflow to ComfyUI and wait for output."""
        client_id = uuid.uuid4().hex
        workflow = request.extra.get("comfyui_workflow")

        if not workflow:
            # Build a basic txt2img workflow from request params
            workflow = self._build_basic_workflow(request)

        # Submit prompt
        try:
            resp = requests.post(
                f"{self._base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=10,
            )
            resp.raise_for_status()
            prompt_id = resp.json().get("prompt_id")
        except requests.ConnectionError as e:
            raise ProviderConnectionError(self.name, f"Cannot reach ComfyUI: {e}")
        except Exception as e:
            raise ProviderExecutionError(self.name, f"Failed to submit prompt: {e}")

        # Poll for completion
        start_time = time.time()
        while (time.time() - start_time) < self._timeout:
            time.sleep(1)

            try:
                hist_resp = requests.get(
                    f"{self._base_url}/history/{prompt_id}", timeout=5
                )
                if hist_resp.ok and prompt_id in hist_resp.json():
                    history = hist_resp.json()[prompt_id]
                    outputs = history.get("outputs", {})
                    return self._extract_output(outputs, request, time.time() - start_time)
            except Exception:
                pass

            # Report progress (estimated from time elapsed)
            if on_progress:
                elapsed = time.time() - start_time
                estimated_pct = min(int((elapsed / max(request.steps * 0.5, 1)) * 100), 95)
                on_progress(GenerationProgress(
                    percent=estimated_pct,
                    message=f"ComfyUI executing... ({elapsed:.0f}s)",
                ))

        raise ProviderExecutionError(
            self.name, f"Timeout after {self._timeout}s waiting for prompt {prompt_id}"
        )

    def cancel(self, job_id: str) -> bool:
        """Cancel via ComfyUI /interrupt endpoint."""
        try:
            resp = requests.post(f"{self._base_url}/interrupt", timeout=5)
            return resp.ok
        except Exception:
            return False

    def validate_workflow(self, workflow: dict) -> tuple[bool, str]:
        """Basic workflow validation."""
        if not workflow:
            return False, "Empty workflow"
        if not isinstance(workflow, dict):
            return False, "Workflow must be a dict"
        # Check for at least one node
        if len(workflow) == 0:
            return False, "Workflow has no nodes"
        return True, ""

    def _build_basic_workflow(self, request: GenerationRequest) -> dict:
        """Build a minimal ComfyUI workflow from request params.

        This is a simplified txt2img workflow. Real production workflows
        should be stored as JSON templates in the workflows/ directory.
        """
        # This is a placeholder that would be replaced with actual
        # ComfyUI workflow JSON for the target model
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": request.model},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": request.prompt, "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": request.negative_prompt, "clip": ["1", 1]},
            },
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": request.seed if request.seed > 0 else 42,
                    "steps": request.steps,
                    "cfg": request.cfg_scale,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["5", 0],
                },
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": request.width,
                    "height": request.height,
                    "batch_size": 1,
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["4", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {"images": ["6", 0], "filename_prefix": "aistudio"},
            },
        }

    def _extract_output(
        self, outputs: dict, request: GenerationRequest, elapsed: float
    ) -> GenerationOutput:
        """Extract the output file from ComfyUI history response."""
        # Find the SaveImage node output
        for node_id, node_output in outputs.items():
            images = node_output.get("images", [])
            if images:
                img = images[0]
                filename = img.get("filename", "output.png")
                subfolder = img.get("subfolder", "")

                # Download the image
                params = {"filename": filename, "type": "output"}
                if subfolder:
                    params["subfolder"] = subfolder

                try:
                    dl_resp = requests.get(
                        f"{self._base_url}/view", params=params, timeout=30
                    )
                    dl_resp.raise_for_status()
                    file_bytes = dl_resp.content
                except Exception as e:
                    raise ProviderExecutionError(
                        self.name, f"Failed to download output: {e}"
                    )

                return GenerationOutput(
                    file_bytes=file_bytes,
                    filename=filename,
                    mime_type="image/png",
                    width=request.width,
                    height=request.height,
                    generation_time_seconds=round(elapsed, 2),
                    metadata={
                        "provider": self.name,
                        "model": request.model,
                        "prompt": request.prompt,
                        "steps": request.steps,
                        "cfg_scale": request.cfg_scale,
                    },
                )

        raise ProviderExecutionError(self.name, "No output images found in ComfyUI history")
