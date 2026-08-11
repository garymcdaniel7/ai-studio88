"""Pydantic schemas for request/response serialisation.

Validates: Requirements R4.1, R4.2, R4.3, R4.4, R4.5, R4.8, R4.9, R4.10
"""

from backend.app.schemas.base import (
    BaseSchema,
    PaginatedResponse,
    StrictBaseSchema,
    TenantResponseSchema,
    TimestampedSchema,
)
from backend.app.schemas.validation import (
    AssetType,
    CostUSD,
    DescriptionStr,
    DimensionPx,
    Duration,
    FreeTextStr,
    IdentityClassification,
    JobStatus,
    JobType,
    LoraAssociationType,
    NameStr,
    NonEmptyStr,
    PageLimit,
    PageOffset,
    Priority,
    ProgressPercent,
    PromptStr,
    RelationshipType,
    StrictUUID,
    TalentType,
    WorkloadClass,
)

__all__ = [
    # Base schemas
    "BaseSchema",
    "StrictBaseSchema",
    "TenantResponseSchema",
    "TimestampedSchema",
    "PaginatedResponse",
    # Custom types
    "NonEmptyStr",
    "NameStr",
    "DescriptionStr",
    "FreeTextStr",
    "PromptStr",
    "StrictUUID",
    "PageLimit",
    "PageOffset",
    "Priority",
    "ProgressPercent",
    "CostUSD",
    "DimensionPx",
    "Duration",
    # Enums
    "JobType",
    "JobStatus",
    "AssetType",
    "IdentityClassification",
    "LoraAssociationType",
    "RelationshipType",
    "TalentType",
    "WorkloadClass",
]
