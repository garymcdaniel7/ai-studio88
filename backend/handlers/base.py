"""Base class for AI Studio job handlers.

Defined in its own module (rather than ``backend.worker``) so that handler
implementations can subclass it without creating a circular import with the
worker module — which itself imports concrete handlers into ``JOB_HANDLERS``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseHandler(ABC):
    """Base class for all job handlers.

    Implement this interface to add support for a new job type.
    Register the handler in ``worker.JOB_HANDLERS``.
    """

    @abstractmethod
    def execute(self, job: dict, report_progress: Any) -> dict:
        """Execute the job and return output data.

        Args:
            job: Full job record from Supabase (includes input, type, etc.)
            report_progress: Callable(progress: int) to report 0-100 progress

        Returns:
            dict: Output data to store in job.output

        Raises:
            Exception: Any exception will mark the job as failed
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable handler name."""
        ...
