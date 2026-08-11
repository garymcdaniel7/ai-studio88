"""Job type configurations — per-type execution parameters.

Defines deployment-level configuration for each job type, including
maximum duration, retry policy, heartbeat interval, lease duration,
cancellation behavior, and workload class for scheduling priority.

Configuration is a Python constant (not stored in DB). It is used by
JobService to auto-set defaults on job submission and claiming.

Requirements: R64.4, R64.5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry configuration for a job type.

    Attributes:
        max_attempts: Maximum number of execution attempts before permanent failure.
        retry_delay_seconds: Base delay between retry attempts in seconds.
        retry_backoff_factor: Multiplier applied to delay for each subsequent retry.
    """

    max_attempts: int
    retry_delay_seconds: int
    retry_backoff_factor: float


@dataclass(frozen=True, slots=True)
class JobTypeConfig:
    """Per-type execution configuration for a job type.

    Defines how a specific job type behaves during its lifecycle —
    from submission through execution to completion or failure.

    The heartbeat_interval MUST always be <= lease_duration / 3 to
    ensure workers can detect lease expiration before it happens.

    Attributes:
        max_duration: Maximum allowed execution time for this job type.
        retry_policy: Retry configuration (max_attempts, delay, backoff).
        heartbeat_interval: How often workers must send heartbeats.
        lease_duration: How long a lease is valid before expiration.
        cancellation_behavior: Strategy for cancellation — either
            "immediate_lease_expire" (expire lease immediately) or
            "graceful_with_timeout" (allow grace period before expiring).
        workload_class: Scheduling workload class for capacity isolation.
        description: Human-readable description of this job type.

    Validates: R64.4, R64.5
    """

    max_duration: timedelta
    retry_policy: RetryPolicy
    heartbeat_interval: timedelta
    lease_duration: timedelta
    cancellation_behavior: str
    workload_class: str
    description: str


# =============================================================================
# Per-type configurations
# =============================================================================

JOB_TYPE_CONFIGS: dict[str, JobTypeConfig] = {
    "image_generation": JobTypeConfig(
        max_duration=timedelta(minutes=30),
        retry_policy=RetryPolicy(
            max_attempts=3,
            retry_delay_seconds=30,
            retry_backoff_factor=2.0,
        ),
        heartbeat_interval=timedelta(minutes=2),
        lease_duration=timedelta(minutes=10),
        cancellation_behavior="immediate_lease_expire",
        workload_class="image_generation",
        description="Single image generation via ComfyUI (SDXL/Flux)",
    ),
    "video_generation": JobTypeConfig(
        max_duration=timedelta(minutes=10),
        retry_policy=RetryPolicy(
            max_attempts=3,
            retry_delay_seconds=30,
            retry_backoff_factor=2.0,
        ),
        heartbeat_interval=timedelta(minutes=1),
        lease_duration=timedelta(minutes=5),
        cancellation_behavior="immediate_lease_expire",
        workload_class="video_generation",
        description="Video generation via ComfyUI (WAN 2.1/LTX)",
    ),
    "lora_training": JobTypeConfig(
        max_duration=timedelta(hours=4),
        retry_policy=RetryPolicy(
            max_attempts=2,
            retry_delay_seconds=120,
            retry_backoff_factor=2.0,
        ),
        heartbeat_interval=timedelta(minutes=5),
        lease_duration=timedelta(minutes=15),
        cancellation_behavior="graceful_with_timeout",
        workload_class="training",
        description="LoRA fine-tuning on GPU worker",
    ),
    "brain_heavy_inference": JobTypeConfig(
        max_duration=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            max_attempts=3,
            retry_delay_seconds=10,
            retry_backoff_factor=1.5,
        ),
        heartbeat_interval=timedelta(seconds=30),
        lease_duration=timedelta(minutes=2),
        cancellation_behavior="immediate_lease_expire",
        workload_class="interactive_language",
        description="Heavy LLM inference on GPU worker (long-form content)",
    ),
    "batch_generation": JobTypeConfig(
        max_duration=timedelta(hours=2),
        retry_policy=RetryPolicy(
            max_attempts=2,
            retry_delay_seconds=60,
            retry_backoff_factor=2.0,
        ),
        heartbeat_interval=timedelta(minutes=5),
        lease_duration=timedelta(minutes=15),
        cancellation_behavior="graceful_with_timeout",
        workload_class="batch",
        description="Batch image/video generation (multiple outputs)",
    ),
    "publishing_dispatch": JobTypeConfig(
        max_duration=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            max_attempts=3,
            retry_delay_seconds=15,
            retry_backoff_factor=2.0,
        ),
        heartbeat_interval=timedelta(seconds=30),
        lease_duration=timedelta(minutes=2),
        cancellation_behavior="immediate_lease_expire",
        workload_class="publishing",
        description="Social media publishing dispatch",
    ),
}


# =============================================================================
# Helper functions
# =============================================================================


def get_job_type_config(job_type: str) -> JobTypeConfig:
    """Return the configuration for the given job type.

    Args:
        job_type: The job type string (e.g., "image_generation").

    Returns:
        The JobTypeConfig for the specified type.

    Raises:
        ValueError: If the job_type is not recognized.

    Validates: R64.4
    """
    config = JOB_TYPE_CONFIGS.get(job_type)
    if config is None:
        valid_types = ", ".join(sorted(JOB_TYPE_CONFIGS.keys()))
        raise ValueError(
            f"Unknown job type '{job_type}'. "
            f"Valid types: {valid_types}"
        )
    return config


def validate_job_duration(job_type: str, requested_seconds: int) -> int:
    """Validate and clamp a requested duration to the type's maximum.

    If the requested duration exceeds the type's max_duration, the value
    is clamped to the maximum. If it is within bounds, it is returned as-is.

    Args:
        job_type: The job type string.
        requested_seconds: The client-requested max duration in seconds.

    Returns:
        The validated (possibly clamped) duration in seconds.

    Raises:
        ValueError: If the job_type is not recognized.

    Validates: R64.4
    """
    config = get_job_type_config(job_type)
    max_seconds = int(config.max_duration.total_seconds())
    return min(requested_seconds, max_seconds)
