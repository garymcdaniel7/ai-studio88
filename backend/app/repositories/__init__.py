"""Repository layer — all database queries go through here.

Repositories enforce tenant isolation via TenantScopedRepository base class.
Every query is scoped to the authenticated org_id. Cross-tenant access
returns 404 (not 403) to prevent information leakage.

Requirements: R2.2, R2.6, R2.7, R2.8, R2.9, R2.10
"""

from app.repositories.talent_repository import TalentRepository
from app.repositories.asset_repository import AssetRepository
from app.repositories.job_repository import JobRepository

__all__ = [
    "TalentRepository",
    "AssetRepository",
    "JobRepository",
]
