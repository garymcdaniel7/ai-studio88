"""SQLAlchemy ORM models for AI Studio.

All models inherit from Base and use standard mixins:
    - UUIDMixin: UUID primary key
    - TimestampMixin: created_at, updated_at
    - TenantMixin: org_id NOT NULL (multi-tenant isolation)
    - SoftDeleteMixin: deleted_at (optional)
"""

from app.models.brain_memory import (
    BrainConversation,
    BrainMessage,
    BrainUserMemory,
    BrainWorkspaceKnowledge,
)
from app.models.connection import Connection
from app.models.external_deletion import DeletionState, ExternalDeletionTracking
from app.models.model_lifecycle import ModelRegistryEntry, ModelTransition
from app.models.consent import ConsentRecord
from app.models.feature_rollout import FeatureRollout
from app.models.rights_case import RightsCase
from app.models.generation_context_package import GenerationContextPackage
from app.models.social_analytics import (
    SocialAccount,
    SocialContent,
    SocialDerivedInsight,
    SocialExperiment,
    SocialMetricSnapshot,
    SocialWatchlist,
    SocialWatchlistMember,
)
from app.models.talent import AiTalent
from app.models.talent_lora import TalentLora
from app.models.talent_relationship import TalentRelationship
from app.models.asset import Asset
from app.models.compute_availability import (
    ComputeAvailabilityConfig,
    ComputeSelectiveGrant,
)
from app.models.cost import CostEntry, CostReservation
from app.models.job import Job
from app.models.job_lease import JobLease

__all__ = [
    "AiTalent",
    "Asset",
    "BrainConversation",
    "BrainMessage",
    "BrainUserMemory",
    "BrainWorkspaceKnowledge",
    "ComputeAvailabilityConfig",
    "ComputeSelectiveGrant",
    "Connection",
    "ConsentRecord",
    "DeletionState",
    "ExternalDeletionTracking",
    "CostEntry",
    "CostReservation",
    "FeatureRollout",
    "GenerationContextPackage",
    "Job",
    "JobLease",
    "ModelRegistryEntry",
    "ModelTransition",
    "RightsCase",
    "SocialAccount",
    "SocialContent",
    "SocialDerivedInsight",
    "SocialExperiment",
    "SocialMetricSnapshot",
    "SocialWatchlist",
    "SocialWatchlistMember",
    "TalentLora",
    "TalentRelationship",
]
