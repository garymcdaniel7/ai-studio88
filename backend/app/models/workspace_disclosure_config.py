"""WorkspaceDisclosureConfig ORM model.

Per-workspace configuration for disclosure hooks applied at publish time.
Supports AI/synthetic disclosure, sponsorship/commercial disclosure,
provenance metadata (C2PA), and platform-specific policy hooks.

Disclosure policy is configurable per workspace. The platform does NOT
hardcode universal disclosure rules — they are evaluated at publish time
based on workspace config + destination platform requirements.

Requirements: R80.1, R80.2, R80.3, R80.4, R80.5, R80.6
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class WorkspaceDisclosureConfig(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Per-workspace disclosure configuration.

    Controls which disclosure hooks are enabled, what text/tags to include,
    platform-specific requirements, and C2PA provenance attachment.

    Only one active config record per org_id (upsert pattern).

    Requirements: R80.1, R80.2, R80.3
    """

    __tablename__ = "workspace_disclosure_configs"

    # AI/synthetic media disclosure
    ai_disclosure_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    ai_disclosure_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    # Sponsorship/commercial disclosure (FTC/ASA compliance)
    sponsorship_disclosure_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    sponsorship_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    # Disclosure tags (e.g., #AIGenerated, #Sponsored)
    disclosure_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True, default=None
    )

    # Platform-specific requirements (JSONB for schema flexibility)
    # Example: {"instagram": {"label": "AI-generated"}, "tiktok": {"tag": "#AIContent"}}
    platform_requirements: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # C2PA / Content Credentials provenance metadata
    c2pa_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
