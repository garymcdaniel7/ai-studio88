"""Generation Provider Interface.

All generation providers (ComfyUI, Forge, InvokeAI, cloud GPU, etc.)
implement this abstract interface. The Generation Engine dispatches
through it without knowing provider-specific details.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from backend.engine.models import (
    GenerationRequest,
    GenerationOutput,
    GenerationProgress,
    ProviderCapabilities,
    ProviderHealth,
)


class GenerationProvider(ABC):
    """Abstract base class for all generation providers.

    Implement this to add a new provider (ComfyUI, Forge, InvokeAI, etc.).
    Register the provider in the PROVIDERS registry.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'comfyui', 'forge', 'simulation')."""
        ...

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Check provider connectivity and resource status."""
        ...

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Report what this provider can do."""
        ...

    @abstractmethod
    def submit(
        self,
        request: GenerationRequest,
        on_progress: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationOutput:
        """Submit a generation request and wait for completion.

        Args:
            request: The generation request with all parameters
            on_progress: Optional callback for progress updates

        Returns:
            GenerationOutput with file data and metadata

        Raises:
            ProviderError: If generation fails
        """
        ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool:
        """Cancel a running generation. Returns True if cancelled."""
        ...

    @abstractmethod
    def validate_workflow(self, workflow: dict) -> tuple[bool, str]:
        """Validate a workflow payload before submission.

        Returns:
            (is_valid, error_message)
        """
        ...


class ProviderError(Exception):
    """Base exception for provider failures."""
    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class ProviderConnectionError(ProviderError):
    """Provider is unreachable. Retry may help."""
    pass


class ProviderExecutionError(ProviderError):
    """Provider failed during execution. Check logs."""
    pass
