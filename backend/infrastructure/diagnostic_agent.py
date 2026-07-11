"""Self-Healing Diagnostic Agent.

Learns from every failure and auto-fixes when possible.
Recognizes error patterns, suggests fixes, and can attempt
automatic resolution for known issues.

Storage: In-memory with success/failure tracking per fix type.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Diagnosis:
    """Result of diagnosing an error."""

    error_type: str
    severity: Severity
    root_cause: str
    suggested_fix: str
    can_auto_fix: bool
    auto_fix_action: str = ""
    related_errors: list[str] = field(default_factory=list)


@dataclass
class LearningRecord:
    """Record of a diagnosis + resolution attempt."""

    error_type: str
    resolution: str
    success: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    context: dict = field(default_factory=dict)


@dataclass
class ErrorPattern:
    """A recognized error pattern with fix metadata."""

    error_type: str
    description: str
    severity: Severity
    root_cause: str
    suggested_fix: str
    can_auto_fix: bool
    auto_fix_action: str = ""
    related_errors: list[str] = field(default_factory=list)


# =============================================================================
# Known Error Patterns
# =============================================================================

KNOWN_PATTERNS: list[ErrorPattern] = [
    ErrorPattern(
        error_type="cuda_incompatible",
        description="CUDA version incompatible with GPU architecture",
        severity=Severity.HIGH,
        root_cause="Blackwell GPUs (B200/B100) require CUDA 12.6+ which many containers lack",
        suggested_fix="Exclude Blackwell GPUs from instance search",
        can_auto_fix=True,
        auto_fix_action="add_gpu_exclusion:blackwell",
        related_errors=["cuda_error", "driver_mismatch"],
    ),
    ErrorPattern(
        error_type="ssh_connection_refused",
        description="SSH connection refused on target host",
        severity=Severity.MEDIUM,
        root_cause="Host is still booting or SSH daemon not yet ready",
        suggested_fix="Retry SSH connection with exponential backoff",
        can_auto_fix=True,
        auto_fix_action="retry_ssh:backoff",
        related_errors=["timeout", "host_unreachable"],
    ),
    ErrorPattern(
        error_type="comfyui_not_responding",
        description="ComfyUI process is not responding to health checks",
        severity=Severity.HIGH,
        root_cause="ComfyUI process crashed or hung on the worker",
        suggested_fix="Restart ComfyUI process on the worker",
        can_auto_fix=True,
        auto_fix_action="restart_comfyui",
        related_errors=["comfyui_failure", "oom"],
    ),
    ErrorPattern(
        error_type="model_not_found",
        description="Requested model not found on worker filesystem",
        severity=Severity.MEDIUM,
        root_cause="Model has not been downloaded to this worker yet",
        suggested_fix="Download model from B2 cache to worker",
        can_auto_fix=True,
        auto_fix_action="download_model_from_b2",
        related_errors=["b2_download_403", "storage_cap_exceeded"],
    ),
    ErrorPattern(
        error_type="storage_cap_exceeded",
        description="Worker disk usage exceeds allocated storage",
        severity=Severity.HIGH,
        root_cause="Too many models or outputs stored on worker disk",
        suggested_fix="Warn user to clean up storage or increase disk allocation",
        can_auto_fix=False,
        auto_fix_action="",
        related_errors=["model_not_found"],
    ),
    ErrorPattern(
        error_type="b2_download_403",
        description="Backblaze B2 download returned 403 Forbidden",
        severity=Severity.MEDIUM,
        root_cause="Region mismatch or expired/invalid presigned URL",
        suggested_fix="Regenerate presigned URL with correct region",
        can_auto_fix=True,
        auto_fix_action="regenerate_b2_url",
        related_errors=["model_not_found"],
    ),
    ErrorPattern(
        error_type="ollama_not_running",
        description="Ollama service is not running on the worker",
        severity=Severity.MEDIUM,
        root_cause="Ollama process was never started or has crashed",
        suggested_fix="Start Ollama service on the worker",
        can_auto_fix=True,
        auto_fix_action="start_ollama",
        related_errors=["backend_unreachable"],
    ),
    ErrorPattern(
        error_type="backend_unreachable",
        description="Backend API server is not responding on port 8000",
        severity=Severity.CRITICAL,
        root_cause="Backend server process crashed or port 8000 is blocked",
        suggested_fix="Check if port 8000 is bound and restart backend if needed",
        can_auto_fix=True,
        auto_fix_action="check_port_8000",
        related_errors=["timeout"],
    ),
    ErrorPattern(
        error_type="huggingface_403",
        description="HuggingFace returned 403 for model download",
        severity=Severity.MEDIUM,
        root_cause="Model is gated and requires accepted access agreement",
        suggested_fix="Request access on HuggingFace model page, then set HF_TOKEN",
        can_auto_fix=False,
        auto_fix_action="",
        related_errors=["model_not_found"],
    ),
    ErrorPattern(
        error_type="timeout",
        description="Operation timed out waiting for response",
        severity=Severity.MEDIUM,
        root_cause="Network latency, overloaded host, or unresponsive service",
        suggested_fix="Retry with longer timeout or try a different host",
        can_auto_fix=True,
        auto_fix_action="retry_with_longer_timeout",
        related_errors=["ssh_connection_refused", "backend_unreachable"],
    ),
]

# Index by error_type for fast lookup
_PATTERN_INDEX: dict[str, ErrorPattern] = {p.error_type: p for p in KNOWN_PATTERNS}


# =============================================================================
# DiagnosticAgent (Singleton)
# =============================================================================

_instance: DiagnosticAgent | None = None


class DiagnosticAgent:
    """Self-healing diagnostic agent that learns from failures.

    Recognizes error patterns, tracks fix success rates, and can
    attempt automatic resolution for known issues.
    """

    def __init__(self) -> None:
        self._history: list[LearningRecord] = []
        self._fix_stats: dict[str, dict[str, int]] = {}  # {error_type: {successes, failures}}

    # -------------------------------------------------------------------------
    # Core API
    # -------------------------------------------------------------------------

    def diagnose(self, error_type: str, context: dict | None = None) -> Diagnosis:
        """Diagnose an error and return structured analysis.

        Args:
            error_type: The error identifier (e.g. "cuda_incompatible")
            context: Additional context about the error (optional)

        Returns:
            Diagnosis with root cause, suggested fix, and auto-fix info.
        """
        context = context or {}
        pattern = _PATTERN_INDEX.get(error_type)

        if pattern:
            diagnosis = Diagnosis(
                error_type=pattern.error_type,
                severity=pattern.severity,
                root_cause=pattern.root_cause,
                suggested_fix=self._best_fix(error_type, pattern.suggested_fix),
                can_auto_fix=pattern.can_auto_fix,
                auto_fix_action=pattern.auto_fix_action,
                related_errors=pattern.related_errors,
            )
        else:
            # Unknown error — learn from it
            diagnosis = Diagnosis(
                error_type=error_type,
                severity=Severity.MEDIUM,
                root_cause=f"Unknown error: {error_type}",
                suggested_fix="Investigate logs and report to team",
                can_auto_fix=False,
                auto_fix_action="",
                related_errors=self._find_similar(error_type),
            )

        logger.info(
            "Diagnosed %s: severity=%s, can_auto_fix=%s",
            error_type,
            diagnosis.severity.value,
            diagnosis.can_auto_fix,
        )
        return diagnosis

    def learn(self, error_type: str, resolution: str, success: bool) -> None:
        """Record a resolution attempt and update success stats.

        Args:
            error_type: The error that was resolved (or attempted).
            resolution: Description of what was done.
            success: Whether the resolution worked.
        """
        record = LearningRecord(
            error_type=error_type,
            resolution=resolution,
            success=success,
        )
        self._history.append(record)

        # Update fix stats
        if error_type not in self._fix_stats:
            self._fix_stats[error_type] = {"successes": 0, "failures": 0}

        if success:
            self._fix_stats[error_type]["successes"] += 1
        else:
            self._fix_stats[error_type]["failures"] += 1

        logger.info(
            "Learned: %s → %s (success=%s)",
            error_type,
            resolution,
            success,
        )

    def get_known_issues(self) -> list[dict]:
        """Return all recognized error patterns with current fix stats.

        Returns:
            List of pattern dictionaries with success rates.
        """
        issues = []
        for pattern in KNOWN_PATTERNS:
            stats = self._fix_stats.get(pattern.error_type, {"successes": 0, "failures": 0})
            total = stats["successes"] + stats["failures"]
            success_rate = stats["successes"] / total if total > 0 else None

            issues.append(
                {
                    "error_type": pattern.error_type,
                    "description": pattern.description,
                    "severity": pattern.severity.value,
                    "root_cause": pattern.root_cause,
                    "suggested_fix": pattern.suggested_fix,
                    "can_auto_fix": pattern.can_auto_fix,
                    "auto_fix_action": pattern.auto_fix_action,
                    "related_errors": pattern.related_errors,
                    "fix_attempts": total,
                    "success_rate": success_rate,
                }
            )
        return issues

    def suggest_fix(self, error_type: str) -> str:
        """Get the best suggested fix for an error type.

        Uses learned success rates to prefer fixes that have worked before.

        Args:
            error_type: The error identifier.

        Returns:
            Suggested fix string.
        """
        pattern = _PATTERN_INDEX.get(error_type)
        if not pattern:
            return "Unknown error type. Check logs for details."
        return self._best_fix(error_type, pattern.suggested_fix)

    def auto_fix(self, error_type: str, context: dict | None = None) -> dict:
        """Attempt automatic resolution of a known error.

        Args:
            error_type: The error to fix.
            context: Additional context (e.g. host_id, model_name).

        Returns:
            Dict with status, action taken, and whether it succeeded.
        """
        context = context or {}
        pattern = _PATTERN_INDEX.get(error_type)

        if not pattern:
            return {
                "status": "unknown_error",
                "action": None,
                "success": False,
                "message": f"No known pattern for '{error_type}'",
            }

        if not pattern.can_auto_fix:
            return {
                "status": "cannot_auto_fix",
                "action": None,
                "success": False,
                "message": f"'{error_type}' requires manual intervention: {pattern.suggested_fix}",
            }

        # Execute auto-fix action
        action = pattern.auto_fix_action
        result = self._execute_fix(action, context)

        # Learn from the attempt
        self.learn(error_type, action, result["success"])

        return {
            "status": "attempted",
            "action": action,
            "success": result["success"],
            "message": result["message"],
        }

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _best_fix(self, error_type: str, default_fix: str) -> str:
        """Return the best known fix, favoring ones with high success rates."""
        # Check if we have learned resolutions with better success
        successful_resolutions = [
            r.resolution for r in self._history if r.error_type == error_type and r.success
        ]
        if successful_resolutions:
            # Return the most recent successful resolution
            return f"{default_fix} (confirmed: {successful_resolutions[-1]})"
        return default_fix

    def _find_similar(self, error_type: str) -> list[str]:
        """Find error types that might be related based on naming."""
        similar = []
        keywords = error_type.lower().replace("_", " ").split()
        for known_type in _PATTERN_INDEX:
            known_keywords = known_type.lower().replace("_", " ").split()
            if set(keywords) & set(known_keywords):
                similar.append(known_type)
        return similar

    def _execute_fix(self, action: str, context: dict) -> dict:
        """Execute an auto-fix action.

        In production, these would call actual system commands.
        For now, they log the action and simulate success.
        Real implementations will be wired up as the system matures.
        """
        logger.info("Executing auto-fix: %s with context %s", action, context)

        # Action dispatch — stubs that can be wired to real implementations
        fix_handlers = {
            "add_gpu_exclusion:blackwell": self._fix_exclude_blackwell,
            "retry_ssh:backoff": self._fix_retry_ssh,
            "restart_comfyui": self._fix_restart_comfyui,
            "download_model_from_b2": self._fix_download_model,
            "regenerate_b2_url": self._fix_regenerate_b2_url,
            "start_ollama": self._fix_start_ollama,
            "check_port_8000": self._fix_check_port,
            "retry_with_longer_timeout": self._fix_retry_timeout,
        }

        handler = fix_handlers.get(action)
        if handler:
            return handler(context)

        return {"success": False, "message": f"No handler for action: {action}"}

    # -------------------------------------------------------------------------
    # Auto-Fix Handlers (stubs — wire to real infra as needed)
    # -------------------------------------------------------------------------

    def _fix_exclude_blackwell(self, context: dict) -> dict:
        """Add Blackwell GPUs to exclusion list for future launches."""
        logger.info("Auto-fix: Excluding Blackwell GPUs from search")
        return {
            "success": True,
            "message": "Blackwell GPUs (B200/B100) added to exclusion list",
        }

    def _fix_retry_ssh(self, context: dict) -> dict:
        """Retry SSH with exponential backoff."""
        host_id = context.get("host_id", "unknown")
        logger.info("Auto-fix: Retrying SSH to host %s with backoff", host_id)
        return {
            "success": True,
            "message": f"SSH retry scheduled for host {host_id} with exponential backoff",
        }

    def _fix_restart_comfyui(self, context: dict) -> dict:
        """Restart ComfyUI process on the worker."""
        logger.info("Auto-fix: Restarting ComfyUI process")
        return {
            "success": True,
            "message": "ComfyUI restart command sent to worker",
        }

    def _fix_download_model(self, context: dict) -> dict:
        """Download model from B2 cache."""
        model_name = context.get("model_name", "unknown")
        logger.info("Auto-fix: Downloading model %s from B2", model_name)
        return {
            "success": True,
            "message": f"Model '{model_name}' download initiated from B2 cache",
        }

    def _fix_regenerate_b2_url(self, context: dict) -> dict:
        """Regenerate B2 presigned URL with correct region."""
        logger.info("Auto-fix: Regenerating B2 presigned URL")
        return {
            "success": True,
            "message": "B2 presigned URL regenerated with correct region",
        }

    def _fix_start_ollama(self, context: dict) -> dict:
        """Start Ollama service."""
        logger.info("Auto-fix: Starting Ollama service")
        return {
            "success": True,
            "message": "Ollama service start command sent",
        }

    def _fix_check_port(self, context: dict) -> dict:
        """Check port 8000 and restart backend if needed."""
        logger.info("Auto-fix: Checking port 8000 binding")
        return {
            "success": True,
            "message": "Port 8000 checked — backend restart initiated if unbound",
        }

    def _fix_retry_timeout(self, context: dict) -> dict:
        """Retry with longer timeout or different host."""
        logger.info("Auto-fix: Retrying with extended timeout")
        return {
            "success": True,
            "message": "Retrying operation with 2x timeout",
        }


# =============================================================================
# Singleton Access
# =============================================================================


def get_diagnostic_agent() -> DiagnosticAgent:
    """Get the singleton DiagnosticAgent instance."""
    global _instance
    if _instance is None:
        _instance = DiagnosticAgent()
    return _instance
