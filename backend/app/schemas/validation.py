"""Shared validation utilities for Pydantic v2 schemas.

Provides reusable custom types and validators for consistent input validation
across all API endpoints.

Key rules (R4.1-R4.10):
    - UUID type for all IDs — never raw strings in query parameters
    - min_length=1 for required strings
    - ge/le bounds for bounded integers
    - Whitespace-only strings rejected with 422
    - Enum types for fixed option sets
    - File upload: magic byte + MIME + size validation (see file_upload.py)

Validates: Requirements R4.1, R4.2, R4.3, R4.4, R4.5, R4.8, R4.9, R4.10
"""

from __future__ import annotations

import enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, BeforeValidator, Field, field_validator


def _reject_whitespace_only(value: str) -> str:
    """Reject strings that are only whitespace after stripping.

    Strips leading/trailing whitespace and rejects empty results.

    Raises:
        ValueError: If the string contains only whitespace characters.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("Field must not be empty or contain only whitespace")
    return stripped


def _validate_uuid_string(value: Any) -> UUID:
    """Validate and coerce a value to UUID.

    Accepts UUID objects or valid UUID strings. Rejects everything else
    with a clear error message.

    Raises:
        ValueError: If value is not a valid UUID.
    """
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value.strip())
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid UUID format: '{value}'")
    raise ValueError(f"Expected UUID, got {type(value).__name__}")


# =============================================================================
# Custom Annotated Types
# =============================================================================

NonEmptyStr = Annotated[
    str,
    AfterValidator(_reject_whitespace_only),
    Field(min_length=1),
]
"""A string that rejects whitespace-only input and enforces min_length=1 after stripping."""

NameStr = Annotated[
    str,
    AfterValidator(_reject_whitespace_only),
    Field(min_length=1, max_length=100),
]
"""A name field: max 100 characters, whitespace-only rejected."""

DescriptionStr = Annotated[
    str,
    AfterValidator(_reject_whitespace_only),
    Field(min_length=1, max_length=1000),
]
"""A description field: max 1000 characters, whitespace-only rejected (R4.1)."""

FreeTextStr = Annotated[
    str,
    AfterValidator(_reject_whitespace_only),
    Field(min_length=1, max_length=5000),
]
"""A free-text content field: max 5000 characters, whitespace-only rejected."""

PromptStr = Annotated[
    str,
    AfterValidator(_reject_whitespace_only),
    Field(min_length=1, max_length=2000),
]
"""A prompt field for generation: max 2000 characters, whitespace-only rejected (R12.1)."""

StrictUUID = Annotated[
    UUID,
    BeforeValidator(_validate_uuid_string),
]
"""A UUID that accepts both UUID objects and valid UUID strings, rejecting invalid formats."""

# Bounded integer types
PageLimit = Annotated[int, Field(ge=1, le=100, description="Items per page (1-100)")]
PageOffset = Annotated[int, Field(ge=0, description="Pagination offset")]
Priority = Annotated[int, Field(ge=1, le=10, description="Priority level (1=lowest, 10=highest)")]
ProgressPercent = Annotated[int, Field(ge=0, le=100, description="Progress percentage (0-100)")]
CostUSD = Annotated[float, Field(ge=0.0, description="Cost in USD (non-negative)")]
DimensionPx = Annotated[int, Field(ge=256, le=2048, description="Image dimension in pixels (256-2048)")]
Duration = Annotated[int, Field(ge=1, le=14400, description="Duration in seconds (1-14400)")]


# =============================================================================
# Enums for Fixed Option Sets (R4.3)
# =============================================================================


class JobType(str, enum.Enum):
    """Valid job types for the generation pipeline."""

    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    VOICE_GENERATION = "voice_generation"
    LORA_TRAINING = "lora_training"
    BRAIN_HEAVY_INFERENCE = "brain_heavy_inference"
    BATCH_GENERATION = "batch_generation"
    PUBLISHING_DISPATCH = "publishing_dispatch"


class JobStatus(str, enum.Enum):
    """Valid job statuses."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LEASE_EXPIRED = "lease_expired"


class AssetType(str, enum.Enum):
    """Valid asset types for storage."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MODEL = "model"


class IdentityClassification(str, enum.Enum):
    """Identity classification for AI Talent (R10.4)."""

    FICTIONAL = "FICTIONAL"
    REAL_PERSON_SELF = "REAL_PERSON_SELF"
    REAL_PERSON_AUTHORIZED = "REAL_PERSON_AUTHORIZED"


class TalentType(str, enum.Enum):
    """Type of AI Talent (R10.1)."""

    MODEL = "model"
    CHARACTER = "character"
    VOICE = "voice"
    INFLUENCER = "influencer"
    WARDROBE = "wardrobe"
    PRODUCT = "product"
    BACKGROUND = "background"
    OBJECT = "object"


class RelationshipType(str, enum.Enum):
    """Typed relationships between talents (R10.7)."""

    ASSOCIATED = "associated"
    FRIENDS = "friends"
    COUPLE = "couple"
    WEARS = "wears"
    USES = "uses"
    LIVES_IN = "lives_in"
    HOLDS = "holds"
    APPEARS_WITH = "appears_with"
    PAIRS_WITH = "pairs_with"
    VARIANT_OF = "variant_of"


class LoraAssociationType(str, enum.Enum):
    """Type of LoRA association with talent (R10.8)."""

    IDENTITY = "identity"
    STYLE = "style"


class WorkloadClass(str, enum.Enum):
    """Workload scheduling classes (R65.8)."""

    INTERACTIVE_LANGUAGE = "interactive_language"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    TRAINING = "training"
    VOICE_AUDIO = "voice_audio"
    BATCH = "batch"
    PRODUCTION_STAGES = "production_stages"
    PUBLISHING = "publishing"

