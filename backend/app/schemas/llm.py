"""Pydantic schemas for LLM provider routing configuration.

Defines request/response schemas for the LLM routing API including:
- Provider configuration
- Routing requirements
- Health status reporting
- Routing decision audit records

Validates: Requirements R26.1, R26.2, R26.5, R26.6
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from backend.app.schemas.base import BaseSchema, StrictBaseSchema


# =============================================================================
# Enums (mirrored from domain for API serialization)
# =============================================================================


class PrivacyLevelSchema(str, Enum):
    """Privacy level for provider selection."""

    LOCAL = "local"
    CLOUD = "cloud"


class CostTierSchema(str, Enum):
    """Relative cost tier for a provider."""

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProviderHealthStatus(str, Enum):
    """Health status for a configured provider."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNCONFIGURED = "unconfigured"


class FallbackPreference(str, Enum):
    """Workspace fallback behavior when preferred provider is unavailable."""

    AUTO = "auto"
    ASK = "ask"
    STRICT = "strict"


# =============================================================================
# Request Schemas
# =============================================================================


class LLMCompletionRequest(StrictBaseSchema):
    """Request schema for LLM completion via the routing API."""

    prompt: str = Field(min_length=1, max_length=100_000, description="The prompt text")
    model: str | None = Field(default=None, max_length=200, description="Specific model override")
    max_tokens: int = Field(default=2048, ge=1, le=32_000, description="Max tokens to generate")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    privacy_level: PrivacyLevelSchema | None = Field(
        default=None, description="Required privacy level (local or cloud)"
    )
    max_cost_usd: float | None = Field(
        default=None, ge=0.0, description="Maximum acceptable cost in USD"
    )
    max_latency_ms: float | None = Field(
        default=None, ge=0.0, description="Maximum acceptable latency in ms"
    )
    require_streaming: bool = Field(default=False, description="Require streaming support")
    require_tool_use: bool = Field(default=False, description="Require tool/function calling")
    require_vision: bool = Field(default=False, description="Require vision/image support")


class LLMProviderConfigRequest(StrictBaseSchema):
    """Request schema for configuring an LLM provider in a workspace."""

    provider_name: str = Field(min_length=1, max_length=50)
    enabled: bool = Field(default=True)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)
    default_model: str | None = Field(default=None, max_length=200)
    priority: int = Field(default=0, ge=0, le=100, description="Lower number = higher priority")


class WorkspaceFallbackConfigRequest(StrictBaseSchema):
    """Request schema for workspace fallback preference."""

    fallback_preference: FallbackPreference = Field(default=FallbackPreference.AUTO)
    denied_providers: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Providers blocked by privacy policy",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class LLMCompletionResponse(BaseSchema):
    """Response schema for a completed LLM request."""

    content: str
    model: str
    provider: str
    tokens_used: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    cost_usd: float = Field(ge=0.0)


class ProviderCapabilitiesResponse(BaseSchema):
    """Provider capabilities for API responses."""

    name: str
    models: list[str]
    max_context_tokens: int = Field(ge=0)
    supports_streaming: bool
    supports_tool_use: bool
    supports_vision: bool
    privacy_level: PrivacyLevelSchema
    cost_tier: CostTierSchema


class LLMProviderStatusResponse(BaseSchema):
    """Health and capabilities of a single configured provider (R26.6)."""

    name: str
    health: ProviderHealthStatus
    capabilities: ProviderCapabilitiesResponse | None = None
    priority: int = Field(ge=0)
    enabled: bool


class LLMProvidersListResponse(BaseSchema):
    """Response for GET /api/v1/llm/providers — all configured providers."""

    providers: list[LLMProviderStatusResponse]
    fallback_preference: FallbackPreference
    denied_providers: list[str] = Field(default_factory=list)


class RoutingDecisionResponse(BaseSchema):
    """Audit record for a routing decision (R26.5)."""

    selected_provider: str
    model: str
    routing_reason: str
    estimated_cost: float
    fallback_chain: list[str]
    latency_ms: float = Field(ge=0.0)
    timestamp: datetime | None = None
