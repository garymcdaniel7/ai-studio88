"""Asset ORM model.

Represents a stored media file (image, video, audio, model) within a workspace.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDMixin


class Asset(Base, UUIDMixin, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """Asset entity — a stored media file within a workspace.

    Always scoped to org_id. Cross-tenant access returns 404.
    Storage keys are immutable once assigned.
    """

    __tablename__ = "assets"

    storage_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Optional references
    talent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    job_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Media metadata
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Extensible metadata
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
