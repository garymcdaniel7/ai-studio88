"""Unit coverage for LoraTrainingHandler.

Covers: input parsing, live-pipeline invocation, B2 upload, lifecycle
registration, and the distinct "training pipeline not implemented" path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.lora_handler import (
    LoraTrainingHandler,
    TrainingPipelineNotImplementedError,
)
from backend.training.provider import TrainingConfig, TrainingProgress, TrainingResult

pytestmark = pytest.mark.unit


def _job(**input_overrides) -> dict:
    defaults = {
        "talent_id": "talent-123",
        "dataset_id": "dataset-abc",
        "model_name": "character_lora",
        "provider": "simpletuner",
    }
    defaults.update(input_overrides)
    return {
        "id": "job-1",
        "type": "lora_training",
        "org_id": "org-xyz",
        "input": defaults,
    }


class FakeLiveProvider:
    """Provider whose capabilities report a live training backend."""

    name = "simpletuner"
    submitted: list = []

    def capabilities(self) -> dict:
        return {"live_mode": True, "provider": self.name}

    def submit(self, dataset_path, config, on_progress=None):
        self.submitted.append((dataset_path, config))
        if on_progress:
            on_progress(TrainingProgress(step=500, total_steps=1000))
        return TrainingResult(
            success=True,
            output_file_bytes=b"REAL-LORA-DATA" * 8,
            output_filename="simpletuner_character_ab12.safetensors",
            total_steps=1000,
            final_loss=0.04,
            training_time_seconds=10.0,
            logs="done",
            metadata={"provider": "simpletuner", "simulated": False},
        )


class FakeSimOnlyProvider:
    """Provider with no live backend (would only fake output)."""

    name = "simpletuner"

    def capabilities(self) -> dict:
        return {"live_mode": False, "provider": self.name}


class FakeNamedSimulationProvider:
    """The built-in SimulatedTrainingProvider (name == 'simulation')."""

    name = "simulation"

    def capabilities(self) -> dict:
        return {"provider": self.name}


def _version_stub():
    return SimpleNamespace(version_id="lora-v-1", version_number=1)


# =============================================================================
# Input parsing
# =============================================================================


def test_parse_input_requires_talent_id() -> None:
    with pytest.raises(ValueError):
        LoraTrainingHandler.parse_input(_job(talent_id=None))


def test_parse_input_requires_dataset() -> None:
    with pytest.raises(ValueError):
        LoraTrainingHandler.parse_input(_job(dataset_id=None, dataset_path=None))


def test_parse_input_normalizes_fields() -> None:
    parsed = LoraTrainingHandler.parse_input(
        _job(
            training_steps=500,
            rank=32,
            trigger_word="hero",
            version_number=3,
            learning_rate=5e-5,
        )
    )
    assert parsed["talent_id"] == "talent-123"
    assert parsed["dataset"] == "dataset-abc"
    assert parsed["model_name"] == "character_lora"
    assert parsed["version_number"] == 3
    assert parsed["org_id"] == "org-xyz"
    assert parsed["params"]["steps"] == 500
    assert parsed["params"]["rank"] == 32
    assert parsed["params"]["trigger_word"] == "hero"
    assert parsed["params"]["learning_rate"] == 5e-5


def test_parse_input_defaults_model_name_from_trigger() -> None:
    parsed = LoraTrainingHandler.parse_input(_job(model_name=None))
    assert parsed["model_name"] == "aistudio_character_lora"


# =============================================================================
# Live pipeline invocation + upload + registration
# =============================================================================


def test_execute_invokes_pipeline_uploads_and_registers() -> None:
    provider = FakeLiveProvider()
    handler = LoraTrainingHandler()
    job = _job()
    progress_log: list[int] = []

    with (
        patch(
            "backend.handlers.lora_handler.get_training_provider",
            return_value=provider,
        ) as mock_get,
        patch(
            "backend.handlers.lora_handler.storage.upload_file",
            return_value="https://b2.example/model.safetensors",
        ) as mock_upload,
        patch(
            "backend.handlers.lora_handler.storage.generate_storage_key",
            return_value="models/lora_abc.safetensors",
        ) as mock_key,
        patch(
            "backend.handlers.lora_handler.storage.compute_checksum",
            return_value="sha256-abc",
        ) as mock_checksum,
        patch(
            "backend.handlers.lora_handler.register_trained",
            return_value=_version_stub(),
        ) as mock_register,
    ):
        output = handler.execute(job, progress_log.append)

    mock_get.assert_called_once_with("simpletuner")
    # Pipeline invoked with the dataset ref and a real TrainingConfig.
    assert provider.submitted
    dataset_arg, config_arg = provider.submitted[0]
    assert dataset_arg == "dataset-abc"
    assert isinstance(config_arg, TrainingConfig)
    assert config_arg.steps == 1000
    assert config_arg.trigger_words == ["aistudio_character"]

    mock_key.assert_called_once()
    mock_checksum.assert_called_once_with(b"REAL-LORA-DATA" * 8)
    mock_upload.assert_called_once_with(
        b"REAL-LORA-DATA" * 8, "models/lora_abc.safetensors", "application/octet-stream"
    )

    mock_register.assert_called_once_with(
        org_id="org-xyz",
        talent_id="talent-123",
        model_name="character_lora",
        version_number=1,
        artifact_hash="sha256-abc",
        storage_key="models/lora_abc.safetensors",
        file_size_bytes=len(b"REAL-LORA-DATA" * 8),
    )

    assert output["status"] == "trained"
    assert output["model_path"] == "https://b2.example/model.safetensors"
    assert output["version_id"] == "lora-v-1"
    assert output["provider"] == "simpletuner"
    assert progress_log == [10, 50, 100]


def test_execute_raises_on_pipeline_failure() -> None:
    provider = MagicMock(name="simpletuner")
    provider.name = "simpletuner"
    provider.capabilities.return_value = {"live_mode": True}
    provider.submit.return_value = TrainingResult(
        success=False, error="GPU worker unavailable", output_file_bytes=None
    )

    handler = LoraTrainingHandler()
    with (
        patch("backend.handlers.lora_handler.get_training_provider", return_value=provider),
        patch("backend.handlers.lora_handler.storage.upload_file") as mock_upload,
        patch("backend.handlers.lora_handler.register_trained") as mock_register,
    ):
        with pytest.raises(RuntimeError, match="LoRA training failed"):
            handler.execute(_job(), lambda p: None)

    mock_upload.assert_not_called()
    mock_register.assert_not_called()


# =============================================================================
# "Training pipeline not yet implemented" path
# =============================================================================


@pytest.mark.parametrize(
    "fake_provider",
    [FakeSimOnlyProvider(), FakeNamedSimulationProvider()],
    ids=["live_mode_false", "named_simulation"],
)
def test_execute_reports_not_implemented_for_sim_only_provider(fake_provider) -> None:
    handler = LoraTrainingHandler()
    with (
        patch(
            "backend.handlers.lora_handler.get_training_provider",
            return_value=fake_provider,
        ) as mock_get,
        patch("backend.handlers.lora_handler.storage.upload_file") as mock_upload,
        patch("backend.handlers.lora_handler.register_trained") as mock_register,
    ):
        with pytest.raises(TrainingPipelineNotImplementedError) as exc_info:
            handler.execute(_job(), lambda p: None)

    mock_get.assert_called_once()
    assert "training pipeline not yet implemented" in str(exc_info.value)
    mock_upload.assert_not_called()
    mock_register.assert_not_called()


# =============================================================================
# Worker registry wiring
# =============================================================================


def test_worker_registers_lora_training_handler() -> None:
    from backend.worker import JOB_HANDLERS

    assert JOB_HANDLERS["lora_training"] is LoraTrainingHandler
