"""Structured logging configuration using structlog.

All log output is JSON in production and human-readable in development.

Security rules (R45.1, R45.2, R45.3):
    - Never log PII (emails, names, phone numbers) — log IDs and event types only
    - Never log secrets (tokens, passwords, API keys)
    - Always include request_id, org_id, user_id where available
    - Use structured JSON format in production for log aggregation

Structured JSON log format:
    {
        "timestamp": "2026-08-10T12:34:56.789Z",
        "level": "INFO",
        "logger": "backend.app.services.job_service",
        "message": "job_submitted",
        "request_id": "a1b2c3d4-...",
        "org_id": "org-1234-...",
        "user_id": "usr-5678-...",
        "extra": {...}
    }

Requirements: R16.3, R16.4, R45.1, R45.2, R45.3
"""

from __future__ import annotations

import logging
import re
import sys

import structlog

from app.core.config import get_settings

# =============================================================================
# Secret Detection Patterns (R45.3)
# =============================================================================

# Patterns that indicate a secret value in log context KEY names
_SECRET_KEY_PATTERNS = re.compile(
    r"(password|secret|token|key|authorization|credential|cookie|session)",
    re.IGNORECASE,
)

# Patterns that detect secrets embedded in log VALUE strings
SECRET_VALUE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),              # OpenAI/Anthropic keys
    re.compile(r"key_[A-Za-z0-9]{16,}"),              # Generic API keys
    re.compile(r"xox[bsp]-[A-Za-z0-9\-]{10,}"),      # Slack tokens
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),              # GitHub tokens
    re.compile(                                        # JWTs (3 dot-separated b64 segments)
        r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"
    ),
    re.compile(                                        # Key-value secrets
        r"(?:password|secret|token)\s*[:=]\s*\S+"
    ),
]

# Mask to replace secret values with
_SECRET_MASK = "[REDACTED]"


def sanitize_secret_values(value: str) -> str:
    """Sanitize a string by replacing detected secret patterns with [REDACTED].

    Scans the input string for known secret patterns (API keys, JWTs,
    Slack tokens, GitHub tokens, key-value secrets) and replaces them.

    This is a defense-in-depth measure — code should never log secrets
    in the first place, but this catches accidental leakage.

    Args:
        value: The string to sanitize.

    Returns:
        The sanitized string with secrets replaced by [REDACTED].

    Requirements: R45.3
    """
    result = value
    for pattern in SECRET_VALUE_PATTERNS:
        result = pattern.sub(_SECRET_MASK, result)
    return result


def _scrub_secrets(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict,
) -> dict:
    """Structlog processor that scrubs secret values from log events.

    Two-layer scrubbing:
        1. Key-name scrubbing: if a key name matches secret patterns, redact the value.
        2. Value-content scrubbing: if any string value contains a secret pattern, redact it.

    This is a defense-in-depth measure — code should never log secrets
    in the first place.

    Requirements: R45.2, R45.3
    """
    for key in list(event_dict.keys()):
        # Layer 1: scrub by key name
        if _SECRET_KEY_PATTERNS.search(key):
            event_dict[key] = _SECRET_MASK
            continue

        # Layer 2: scrub by value content (only for string values)
        val = event_dict[key]
        if isinstance(val, str):
            sanitized = sanitize_secret_values(val)
            if sanitized != val:
                event_dict[key] = sanitized

    return event_dict


def configure_logging() -> None:
    """Configure structlog for the application.

    Call once at application startup in app/main.py.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        _scrub_secrets,  # Remove any accidentally-logged secrets
    ]

    if settings.is_production:
        # JSON output for log aggregation (Datadog, CloudWatch, etc.)
        processors: list[structlog.types.Processor] = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Human-readable console output for development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to go through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the given module name.

    Usage:
        logger = get_logger(__name__)
        logger.info("job_started", job_id=str(job.id), org_id=str(org.id))

    The request_id, org_id, user_id are automatically included from
    structlog context vars (set by RequestIdMiddleware and TenantContext).
    """
    return structlog.get_logger(name)
