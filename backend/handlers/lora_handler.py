"""LoRA training job handler.

Wires a ``lora_training`` worker job to the real LoRA training pipeline
(character consistency / "same face").

The real training entrypoint is ``backend.training.provider``: a
``TrainingProvider`` is resolved via :func:`get_training_provider`, then
``submit()`` runs the actual training pipeline (SimpleTuner / Vast.ai on a GPU
worker) and returns a :class:`TrainingResult` carrying the resulting
``.safetensors`` bytes.

This handler deliberately does NOT fabricate a model. Providers whose live
training backend is not configured (simulation-only) raise
:class:`TrainingPipelineNotImplementedError` — a distinct, honest failure —
instead of returning a fake success. When a live provider is available, the
handler uploads the produced model to Backblaze B2 via ``backend.storage`` and
registers the trained version through ``backend.lora_lifecycle.register_trained``
(status=``trained``, never auto-activated).
"""

from __future__ import annotations

import os
from typing import Any, Callable

from backend import storage
from backend.handlers.base import BaseHandler
from backend.lora_lifecycle import register_trained
from backend.training.provider import TrainingConfig, get_training_provider


class TrainingPipelineNotImplementedError(NotImplementedError):
    """Raised when no live LoRA training pipeline is configured.

    Distinct from a generic failure so callers can tell "the pipeline does not
    exist yet" apart from "the pipeline ran but failed".
    """


class LoraTrainingHandler(BaseHandler):
    """Executes a ``lora_training`` job against the real training pipeline."""

    @property
    def name(self) -> str:
        return "lora_training"

    # ------------------------------------------------------------------
    # Input parsing
    # ------------------------------------------------------------------

    @staticmethod
    def parse_input(job: dict) -> dict[str, Any]:
        """Validate and normalise a job's ``input`` dict.

        Returns a dict with keys: ``talent_id``, ``dataset``, ``model_name``,
        ``version_number``, ``org_id`` and a ``TrainingConfig``-compatible
        ``params`` dict.
        """
        input_data = job.get("input", {}) or {}

        talent_id = input_data.get("talent_id")
        if not talent_id:
            raise ValueError("'input.talent_id' is required for lora_training")

        # Dataset reference — either a storage path (local dir / B2 key) or a
        # training_datasets row id. At least one must be provided.
        dataset = input_data.get("dataset_path") or input_data.get("dataset_id")
        if not dataset:
            raise ValueError(
                "No dataset reference: provide 'input.dataset_path' or 'input.dataset_id'"
            )

        params = {
            "base_model": input_data.get("base_model", "flux-dev"),
            "resolution": int(input_data.get("resolution", 1024)),
            "rank": int(input_data.get("rank", 16)),
            "steps": int(input_data.get("training_steps", input_data.get("steps", 1000))),
            "learning_rate": float(input_data.get("learning_rate", 1e-4)),
            "optimizer": input_data.get("optimizer", "adamw"),
            "scheduler": input_data.get("scheduler", "cosine"),
            "batch_size": int(input_data.get("batch_size", 1)),
            "trigger_word": input_data.get("trigger_word", "aistudio_character"),
            "provider": input_data.get("provider"),
        }

        model_name = input_data.get("model_name") or f"{params['trigger_word']}_lora"
        version_number = int(input_data.get("version_number", 1))

        return {
            "talent_id": talent_id,
            "dataset": dataset,
            "model_name": model_name,
            "version_number": version_number,
            "org_id": job.get("org_id") or "",
            "params": params,
        }

    # ------------------------------------------------------------------
    # Provider selection / live detection
    # ------------------------------------------------------------------

    @staticmethod
    def _provider_is_live(provider: Any) -> bool:
        """Return True only if the provider has a real (non-simulated) backend."""
        if getattr(provider, "name", None) == "simulation":
            return False
        for method in ("capabilities", "health"):
            try:
                info = getattr(provider, method)()
            except Exception:
                continue
            if isinstance(info, dict) and "live_mode" in info:
                return bool(info["live_mode"])
        return False

    def _resolve_provider(self, params: dict[str, Any]):
        requested = params.get("provider") or os.getenv("TRAINING_PROVIDER") or "simpletuner"
        return get_training_provider(requested)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, job: dict, report_progress: Callable[[int], None]) -> dict:
        parsed = self.parse_input(job)
        params = parsed["params"]

        provider = self._resolve_provider(params)

        if not self._provider_is_live(provider):
            raise TrainingPipelineNotImplementedError(
                "training pipeline not yet implemented: "
                f"provider '{provider.name}' has no live training backend "
                "(simulation only). Configure a live provider (e.g. "
                "TRAINING_VAST_LIVE=true or SIMPLETUNER_LIVE=true) or supply a "
                "job 'input.provider' that supports live training."
            )

        def _on_training_progress(progress) -> None:
            total = progress.total_steps or params["steps"]
            if total and getattr(progress, "step", 0):
                report_progress(min(int(progress.step / total * 100), 100))
            else:
                report_progress(50)

        config = TrainingConfig(
            base_model=params["base_model"],
            resolution=params["resolution"],
            rank=params["rank"],
            steps=params["steps"],
            learning_rate=params["learning_rate"],
            optimizer=params["optimizer"],
            scheduler=params["scheduler"],
            batch_size=params["batch_size"],
            trigger_words=[params["trigger_word"]],
        )

        report_progress(10)
        result = provider.submit(parsed["dataset"], config, on_progress=_on_training_progress)

        if not result.success or not result.output_file_bytes:
            detail = result.error or "training provider returned no output"
            raise RuntimeError(f"LoRA training failed: {detail}")

        # Upload the produced model to B2.
        storage_key = storage.generate_storage_key(result.output_filename, "model")
        checksum = storage.compute_checksum(result.output_file_bytes)
        public_url = storage.upload_file(
            result.output_file_bytes, storage_key, "application/octet-stream"
        )

        # Register the trained version (status=trained — never auto-activated).
        version = register_trained(
            org_id=parsed["org_id"],
            talent_id=parsed["talent_id"],
            model_name=parsed["model_name"],
            version_number=parsed["version_number"],
            artifact_hash=checksum,
            storage_key=storage_key,
            file_size_bytes=len(result.output_file_bytes),
        )

        report_progress(100)

        return {
            "handler": self.name,
            "status": "trained",
            "model_path": public_url,
            "storage_key": storage_key,
            "artifact_hash": checksum,
            "file_size_bytes": len(result.output_file_bytes),
            "version_id": version.version_id,
            "version_number": version.version_number,
            "talent_id": parsed["talent_id"],
            "model_name": parsed["model_name"],
            "provider": provider.name,
            "training_steps": result.total_steps or params["steps"],
            "final_loss": result.final_loss,
            "training_time_seconds": result.training_time_seconds,
            "metadata": result.metadata,
        }
