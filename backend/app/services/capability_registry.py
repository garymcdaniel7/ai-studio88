"""Capability Registry Service — single source of truth for feature classifications.

Maintains the canonical Capability_Registry that classifies every feature as one of:
PRODUCTION, PARTIAL, SIMULATED, MISSING, DEPRECATED, DISABLED, or UNVERIFIED.

Key responsibilities:
- Queryable via GET /api/v1/capabilities
- DISABLED capabilities are inaccessible through ALL surfaces
- MISSING capabilities return 501 CAPABILITY_NOT_IMPLEMENTED
- Transitions are logged with timestamp, actor, and reason
- Integrates with FeatureRolloutService for DISABLED enforcement

Validates: Requirements R19.1, R19.2, R19.3, R19.6, R19.7, R19.8, R19.9
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID


# =============================================================================
# Enums
# =============================================================================


class CapabilityClassification(str, Enum):
    """Classification states for platform capabilities.

    R19.1: Every feature must be classified as one of these values.
    """

    PRODUCTION = "production"
    PARTIAL = "partial"
    SIMULATED = "simulated"
    MISSING = "missing"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    UNVERIFIED = "unverified"


class HealthStatus(str, Enum):
    """Health status for a capability's required providers."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class Capability:
    """A single platform capability with its current state.

    Attributes:
        name: Unique identifier for the capability.
        classification: Current classification state.
        required_providers: List of provider names required for this capability.
        health_status: Current health of the capability's dependencies.
        description: Human-readable description of the capability.
    """

    name: str
    classification: CapabilityClassification
    required_providers: list[str] = field(default_factory=list)
    health_status: HealthStatus = HealthStatus.NOT_APPLICABLE
    description: str = ""


@dataclass
class ClassificationTransition:
    """Audit record of a capability classification change.

    R19.6: Transitions are logged with timestamp, actor, and reason.
    """

    capability_name: str
    previous_classification: CapabilityClassification
    new_classification: CapabilityClassification
    actor: str
    reason: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# =============================================================================
# Errors
# =============================================================================


class CapabilityNotFoundError(Exception):
    """Raised when a capability name is not found in the registry."""

    def __init__(self, capability_name: str) -> None:
        super().__init__(f"Capability '{capability_name}' not found in registry")
        self.capability_name = capability_name


class CapabilityNotImplementedError(Exception):
    """Raised when a MISSING capability is invoked.

    R19.8: MISSING capabilities return 501 CAPABILITY_NOT_IMPLEMENTED.
    """

    def __init__(self, capability_name: str) -> None:
        super().__init__(
            f"Capability '{capability_name}' is not implemented"
        )
        self.status_code = 501
        self.code = "CAPABILITY_NOT_IMPLEMENTED"
        self.capability_name = capability_name


class CapabilityDisabledRegistryError(Exception):
    """Raised when a DISABLED capability is accessed.

    R19.9: DISABLED capabilities are inaccessible through ALL surfaces.
    """

    def __init__(self, capability_name: str) -> None:
        super().__init__(
            f"Capability '{capability_name}' is disabled"
        )
        self.status_code = 403
        self.code = "CAPABILITY_DISABLED"
        self.capability_name = capability_name


# =============================================================================
# Default Capabilities (sourced from CAPABILITY_MAP.md)
# =============================================================================

_DEFAULT_CAPABILITIES: list[Capability] = [
    # Core Platform
    Capability(
        name="talent_crud",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Talent CRUD operations with auth-gated Supabase queries",
    ),
    Capability(
        name="jobs_lifecycle",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Full CRUD job lifecycle with status tracking",
    ),
    Capability(
        name="assets_management",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase", "backblaze_b2"],
        health_status=HealthStatus.HEALTHY,
        description="Asset management with B2 upload/delete and metadata",
    ),
    Capability(
        name="projects",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Tenant-scoped project management",
    ),
    Capability(
        name="models_registry",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Model registry with seed data and capabilities",
    ),
    Capability(
        name="worker_orchestrator",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["vast_ai", "runpod"],
        health_status=HealthStatus.HEALTHY,
        description="Worker orchestration with connection race mode",
    ),
    Capability(
        name="provider_reputation",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Provider reputation learning engine with blacklist",
    ),
    Capability(
        name="cost_intelligence",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Budget tracking and per-org cost intelligence",
    ),
    Capability(
        name="brain_chat",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["ollama"],
        health_status=HealthStatus.HEALTHY,
        description="Brain chat with Ollama local LLM verified",
    ),
    Capability(
        name="aios_gateway",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["ollama"],
        health_status=HealthStatus.HEALTHY,
        description="AIOS gateway for chat routing and provider selection",
    ),
    Capability(
        name="governance_approvals",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Inline approve/reject governance in chat",
    ),
    Capability(
        name="generation_feedback",
        classification=CapabilityClassification.PRODUCTION,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Durable, idempotent generation feedback",
    ),
    # Generation & AI - PARTIAL
    Capability(
        name="image_generation",
        classification=CapabilityClassification.PARTIAL,
        required_providers=["comfyui", "gpu_worker"],
        health_status=HealthStatus.DEGRADED,
        description="Image generation via ComfyUI (works when GPU worker online)",
    ),
    Capability(
        name="lora_training",
        classification=CapabilityClassification.PARTIAL,
        required_providers=["vast_ai", "gpu_worker"],
        health_status=HealthStatus.DEGRADED,
        description="LoRA training lifecycle (SimulationProvider default)",
    ),
    Capability(
        name="workflows",
        classification=CapabilityClassification.PARTIAL,
        required_providers=["comfyui"],
        health_status=HealthStatus.DEGRADED,
        description="Workflow CRUD exists, execution via ComfyUI only when worker online",
    ),
    # Generation & AI - SIMULATED
    Capability(
        name="video_generation",
        classification=CapabilityClassification.SIMULATED,
        required_providers=["comfyui", "gpu_worker"],
        health_status=HealthStatus.UNAVAILABLE,
        description="Video generation (WAN 2.1) - provider simulated by default",
    ),
    Capability(
        name="voice_synthesis",
        classification=CapabilityClassification.PARTIAL,
        required_providers=["elevenlabs"],
        health_status=HealthStatus.DEGRADED,
        description="Voice synthesis via ElevenLabs (API key permission issue)",
    ),
    Capability(
        name="music_generation",
        classification=CapabilityClassification.SIMULATED,
        required_providers=["suno"],
        health_status=HealthStatus.UNAVAILABLE,
        description="Music generation via Suno (provider skeleton, no key)",
    ),
    Capability(
        name="social_publishing",
        classification=CapabilityClassification.SIMULATED,
        required_providers=["social_platform_api"],
        health_status=HealthStatus.UNAVAILABLE,
        description="Social publishing via webhooks (simulation default)",
    ),
    # Backend-only capabilities
    Capability(
        name="creative_dna",
        classification=CapabilityClassification.PARTIAL,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Creative DNA schema + CRUD, no UI surface",
    ),
    Capability(
        name="story_engine",
        classification=CapabilityClassification.PARTIAL,
        required_providers=["supabase"],
        health_status=HealthStatus.HEALTHY,
        description="Full story schema + CRUD, no dedicated UI page",
    ),
    # Deprecated
    Capability(
        name="generation_feedback_legacy",
        classification=CapabilityClassification.DEPRECATED,
        required_providers=[],
        health_status=HealthStatus.NOT_APPLICABLE,
        description="Legacy generation feedback (replaced by durable feedback)",
    ),
    # Missing capabilities (not yet implemented)
    Capability(
        name="batch_generation",
        classification=CapabilityClassification.MISSING,
        required_providers=["comfyui", "gpu_worker"],
        health_status=HealthStatus.NOT_APPLICABLE,
        description="Batch generation (schema exists, no router)",
    ),
    Capability(
        name="brain_embeddings",
        classification=CapabilityClassification.MISSING,
        required_providers=["supabase"],
        health_status=HealthStatus.NOT_APPLICABLE,
        description="Brain embeddings/RAG pipeline (schema exists, no implementation)",
    ),
    # Platform compute (Founder-controlled)
    Capability(
        name="platform_compute",
        classification=CapabilityClassification.DISABLED,
        required_providers=["runpod", "fluidstack"],
        health_status=HealthStatus.NOT_APPLICABLE,
        description="Platform-managed compute (Founder-controlled availability)",
    ),
]


# =============================================================================
# Service
# =============================================================================


class CapabilityRegistryService:
    """Canonical Capability Registry — single source of truth for feature state.

    Maintains all platform capabilities with their classification, required
    providers, health status, and description. Supports classification
    transitions with full audit logging.

    Key behaviors:
    - get_all_capabilities(): returns all capabilities with current state (R19.2)
    - get_capability(name): single capability lookup
    - is_available(name): check if usable (not DISABLED/MISSING) (R19.9)
    - update_classification(): transition with logging (R19.6)
    - get_transitions(name): audit log of state changes

    Validates: Requirements R19.1, R19.2, R19.3, R19.6, R19.7, R19.8, R19.9
    """

    def __init__(
        self,
        capabilities: list[Capability] | None = None,
    ) -> None:
        """Initialize the registry with known capabilities.

        Args:
            capabilities: Optional list of capabilities. If None, uses
                the default set sourced from CAPABILITY_MAP.md.
        """
        source = capabilities if capabilities is not None else _DEFAULT_CAPABILITIES
        self._capabilities: dict[str, Capability] = {
            cap.name: cap for cap in source
        }
        self._transitions: list[ClassificationTransition] = []

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    def get_all_capabilities(self) -> list[Capability]:
        """Return all capabilities with their current state.

        R19.2: GET /api/v1/capabilities returns all capabilities with
        classification, required provider, and health status.
        """
        return list(self._capabilities.values())

    def get_capability(self, name: str) -> Capability:
        """Look up a single capability by name.

        Args:
            name: The capability identifier.

        Returns:
            The Capability instance.

        Raises:
            CapabilityNotFoundError: If the name is not in the registry.
        """
        if name not in self._capabilities:
            raise CapabilityNotFoundError(name)
        return self._capabilities[name]

    def is_available(self, name: str) -> bool:
        """Check if a capability is usable (not DISABLED or MISSING).

        A capability is considered available if it can be invoked through
        some surface. DISABLED and MISSING capabilities are NOT available.
        DEPRECATED capabilities ARE still available (but discouraged).

        Args:
            name: The capability identifier.

        Returns:
            True if the capability exists and is not DISABLED or MISSING.

        Raises:
            CapabilityNotFoundError: If the name is not in the registry.
        """
        cap = self.get_capability(name)
        return cap.classification not in (
            CapabilityClassification.DISABLED,
            CapabilityClassification.MISSING,
        )

    # -------------------------------------------------------------------------
    # State Management
    # -------------------------------------------------------------------------

    def update_classification(
        self,
        name: str,
        new_classification: CapabilityClassification,
        actor: str,
        reason: str,
    ) -> ClassificationTransition:
        """Transition a capability to a new classification.

        R19.6: Transitions are logged with timestamp, actor, and reason.

        Args:
            name: The capability identifier.
            new_classification: The target classification state.
            actor: Identifier of the person/system making the change.
            reason: Human-readable reason for the transition.

        Returns:
            The ClassificationTransition audit record.

        Raises:
            CapabilityNotFoundError: If the name is not in the registry.
        """
        cap = self.get_capability(name)
        previous = cap.classification

        transition = ClassificationTransition(
            capability_name=name,
            previous_classification=previous,
            new_classification=new_classification,
            actor=actor,
            reason=reason,
        )
        self._transitions.append(transition)

        cap.classification = new_classification
        return transition

    # -------------------------------------------------------------------------
    # Audit
    # -------------------------------------------------------------------------

    def get_transitions(self, name: str | None = None) -> list[ClassificationTransition]:
        """Get the audit log of classification transitions.

        Args:
            name: Optional filter by capability name. If None, returns all.

        Returns:
            List of ClassificationTransition records.
        """
        if name is None:
            return list(self._transitions)
        return [t for t in self._transitions if t.capability_name == name]

    # -------------------------------------------------------------------------
    # Enforcement Helpers
    # -------------------------------------------------------------------------

    def check_available(self, name: str) -> None:
        """Check availability and raise appropriate error if not usable.

        R19.8: MISSING → 501 CAPABILITY_NOT_IMPLEMENTED
        R19.9: DISABLED → 403 CAPABILITY_DISABLED (inaccessible through ALL surfaces)

        Args:
            name: The capability identifier.

        Raises:
            CapabilityNotFoundError: If the name is not in the registry.
            CapabilityNotImplementedError: If classified as MISSING.
            CapabilityDisabledRegistryError: If classified as DISABLED.
        """
        cap = self.get_capability(name)
        if cap.classification == CapabilityClassification.MISSING:
            raise CapabilityNotImplementedError(name)
        if cap.classification == CapabilityClassification.DISABLED:
            raise CapabilityDisabledRegistryError(name)

    # -------------------------------------------------------------------------
    # Registry Management
    # -------------------------------------------------------------------------

    def register_capability(self, capability: Capability) -> None:
        """Register a new capability or replace an existing one.

        Args:
            capability: The Capability to add/update in the registry.
        """
        self._capabilities[capability.name] = capability
