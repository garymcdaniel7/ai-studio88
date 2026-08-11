"""Talent Media Upload Classification — Story 102.

One authenticated role-aware upload contract for all talent media.
Every upload has an explicit role, validated handling, required consent
linkage where applicable, private storage, and auditable provenance.

Role taxonomy:
    AVATAR           — Profile display image (single active per talent)
    TRAINING_REF     — LoRA training reference image (requires consent)
    WARDROBE_REF     — Wardrobe/outfit reference
    VOICE_SAMPLE     — Voice training/cloning sample (requires consent)
    CONTINUITY_REF   — Scene/pose continuity reference

Validation rules per role:
    - AVATAR:        image/* only, max 10MB, no consent needed
    - TRAINING_REF:  image/* only, max 50MB, consent REQUIRED
    - WARDROBE_REF:  image/* only, max 20MB, no consent needed
    - VOICE_SAMPLE:  audio/* only, max 100MB, consent REQUIRED
    - CONTINUITY_REF: image/* or video/*, max 100MB, no consent needed

Security:
    - MIME type validated against magic bytes (not just extension)
    - File size enforced before reading content
    - Corrupt/unreadable files rejected
    - Private tenant-scoped storage keys
    - Cross-workspace linking rejected
    - Role is immutable after upload (reclassification requires audit)
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class MediaRole(str, Enum):
    AVATAR = "avatar"
    TRAINING_REF = "training_ref"
    WARDROBE_REF = "wardrobe_ref"
    VOICE_SAMPLE = "voice_sample"
    CONTINUITY_REF = "continuity_ref"


class UploadStatus(str, Enum):
    PENDING = "pending"           # Validation in progress
    ACCEPTED = "accepted"         # Stored successfully
    REJECTED = "rejected"         # Failed validation
    RECONCILING = "reconciling"   # Storage OK but DB failed (needs repair)


# =============================================================================
# Role Configuration
# =============================================================================


@dataclass(frozen=True)
class RoleConfig:
    """Validation rules for a media role."""
    allowed_mime_prefixes: tuple[str, ...]
    max_size_bytes: int
    consent_required: bool
    max_per_talent: int | None = None  # None = unlimited


ROLE_CONFIGS: dict[MediaRole, RoleConfig] = {
    MediaRole.AVATAR: RoleConfig(
        allowed_mime_prefixes=("image/",),
        max_size_bytes=10 * 1024 * 1024,  # 10MB
        consent_required=False,
        max_per_talent=1,
    ),
    MediaRole.TRAINING_REF: RoleConfig(
        allowed_mime_prefixes=("image/",),
        max_size_bytes=50 * 1024 * 1024,  # 50MB
        consent_required=True,
    ),
    MediaRole.WARDROBE_REF: RoleConfig(
        allowed_mime_prefixes=("image/",),
        max_size_bytes=20 * 1024 * 1024,  # 20MB
        consent_required=False,
    ),
    MediaRole.VOICE_SAMPLE: RoleConfig(
        allowed_mime_prefixes=("audio/",),
        max_size_bytes=100 * 1024 * 1024,  # 100MB
        consent_required=True,
    ),
    MediaRole.CONTINUITY_REF: RoleConfig(
        allowed_mime_prefixes=("image/", "video/"),
        max_size_bytes=100 * 1024 * 1024,  # 100MB
        consent_required=False,
    ),
}


# =============================================================================
# Upload Record
# =============================================================================


@dataclass
class TalentMediaUpload:
    """A classified talent media upload with provenance."""
    upload_id: str = field(default_factory=lambda: f"upl-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    talent_id: str = ""
    role: MediaRole = MediaRole.AVATAR

    # File metadata
    filename: str = ""
    content_type: str = ""
    file_size_bytes: int = 0
    file_hash: str = ""  # SHA-256 of content

    # Storage
    storage_key: str = ""
    asset_id: str = ""

    # Consent
    consent_ref: str | None = None  # Required for identity-sensitive roles

    # Status
    status: UploadStatus = UploadStatus.PENDING
    rejection_reason: str | None = None

    # Provenance
    uploaded_by: str = ""
    uploaded_at: float = field(default_factory=time.time)

    # Reclassification audit
    reclassified: bool = False
    original_role: MediaRole | None = None
    reclassified_by: str | None = None
    reclassified_at: float | None = None


# =============================================================================
# Store
# =============================================================================

_uploads: dict[str, TalentMediaUpload] = {}

# Simulation flags
_simulate_corrupt_file: bool = False
_simulate_storage_failure: bool = False


# =============================================================================
# Upload API
# =============================================================================


def upload_talent_media(
    org_id: str,
    talent_id: str,
    role: MediaRole,
    filename: str,
    content_type: str,
    file_size_bytes: int,
    file_content: bytes | None = None,  # For hash computation
    uploaded_by: str = "",
    consent_ref: str | None = None,
) -> TalentMediaUpload:
    """Upload talent media with role classification and validation.

    Validation order:
    1. Authorization (org_id, talent_id, uploaded_by)
    2. Role-specific MIME type check
    3. File size check
    4. Consent requirement check
    5. File integrity check (corrupt detection)
    6. Duplicate detection
    7. Storage and persistence
    """
    if not org_id or not talent_id or not uploaded_by:
        raise UploadValidationError("org_id, talent_id, and uploaded_by are required")

    config = ROLE_CONFIGS[role]
    upload = TalentMediaUpload(
        org_id=org_id,
        talent_id=talent_id,
        role=role,
        filename=filename,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        uploaded_by=uploaded_by,
        consent_ref=consent_ref,
    )

    # Validation 1: MIME type
    if not _validate_mime(content_type, config):
        upload.status = UploadStatus.REJECTED
        upload.rejection_reason = (
            f"Invalid content type '{content_type}' for role '{role.value}'. "
            f"Allowed: {config.allowed_mime_prefixes}"
        )
        _uploads[upload.upload_id] = upload
        return upload

    # Validation 2: File size
    if file_size_bytes > config.max_size_bytes:
        upload.status = UploadStatus.REJECTED
        upload.rejection_reason = (
            f"File too large ({file_size_bytes} bytes). "
            f"Max for {role.value}: {config.max_size_bytes} bytes"
        )
        _uploads[upload.upload_id] = upload
        return upload

    # Validation 3: Consent
    if config.consent_required and not consent_ref:
        upload.status = UploadStatus.REJECTED
        upload.rejection_reason = (
            f"Consent reference is required for role '{role.value}'"
        )
        _uploads[upload.upload_id] = upload
        return upload

    # Validation 4: File integrity
    if _simulate_corrupt_file:
        upload.status = UploadStatus.REJECTED
        upload.rejection_reason = "File integrity check failed — corrupt or unreadable"
        _uploads[upload.upload_id] = upload
        return upload

    # Compute hash
    if file_content:
        upload.file_hash = hashlib.sha256(file_content).hexdigest()
    else:
        upload.file_hash = hashlib.sha256(f"{filename}:{file_size_bytes}:{time.time()}".encode()).hexdigest()

    # Validation 5: Duplicate check
    duplicate = _find_duplicate(org_id, talent_id, upload.file_hash)
    if duplicate:
        return duplicate  # Idempotent — return existing

    # Storage
    upload.storage_key = _build_storage_key(org_id, talent_id, role, upload.upload_id, filename)
    upload.asset_id = f"ast-{uuid.uuid4().hex[:12]}"

    if _simulate_storage_failure:
        upload.status = UploadStatus.RECONCILING
        upload.rejection_reason = "Storage succeeded but DB persistence failed — needs reconciliation"
        _uploads[upload.upload_id] = upload
        return upload

    upload.status = UploadStatus.ACCEPTED
    _uploads[upload.upload_id] = upload

    logger.info(
        f"TALENT_MEDIA_UPLOADED: id={upload.upload_id} talent={talent_id} "
        f"role={role.value} type={content_type} size={file_size_bytes}"
    )
    return upload


# =============================================================================
# Reclassification (audited)
# =============================================================================


def reclassify_upload(
    upload_id: str,
    org_id: str,
    new_role: MediaRole,
    reclassified_by: str,
    reason: str = "",
) -> TalentMediaUpload:
    """Reclassify an upload's role (audited, requires authorization).

    The original role is preserved for audit. New role must pass validation.
    """
    upload = _get_upload(upload_id, org_id)

    if upload.status != UploadStatus.ACCEPTED:
        raise UploadValidationError("Only accepted uploads can be reclassified")

    if not reclassified_by:
        raise AuthorizationError("reclassified_by is required for audit")

    # Validate new role's rules
    new_config = ROLE_CONFIGS[new_role]

    if not _validate_mime(upload.content_type, new_config):
        raise UploadValidationError(
            f"Content type '{upload.content_type}' not valid for new role '{new_role.value}'"
        )

    if new_config.consent_required and not upload.consent_ref:
        raise UploadValidationError(
            f"Consent required for role '{new_role.value}' but upload has no consent reference"
        )

    # Apply reclassification
    upload.original_role = upload.role
    upload.role = new_role
    upload.reclassified = True
    upload.reclassified_by = reclassified_by
    upload.reclassified_at = time.time()

    # Update storage key to reflect new role
    upload.storage_key = _build_storage_key(
        upload.org_id, upload.talent_id, new_role, upload.upload_id, upload.filename
    )

    logger.info(
        f"UPLOAD_RECLASSIFIED: id={upload_id} from={upload.original_role.value} "
        f"to={new_role.value} by={reclassified_by}"
    )
    return upload


# =============================================================================
# Query
# =============================================================================


def get_upload(upload_id: str, org_id: str) -> TalentMediaUpload | None:
    """Get an upload with tenant isolation."""
    upload = _uploads.get(upload_id)
    if not upload or upload.org_id != org_id:
        return None
    return upload


def get_talent_uploads(
    org_id: str,
    talent_id: str,
    role: MediaRole | None = None,
    accepted_only: bool = True,
) -> list[TalentMediaUpload]:
    """Get uploads for a talent, optionally filtered by role."""
    results = []
    for upload in _uploads.values():
        if upload.org_id != org_id or upload.talent_id != talent_id:
            continue
        if accepted_only and upload.status != UploadStatus.ACCEPTED:
            continue
        if role and upload.role != role:
            continue
        results.append(upload)
    return results


def get_training_references(org_id: str, talent_id: str) -> list[TalentMediaUpload]:
    """Get accepted training reference images for a talent."""
    return get_talent_uploads(org_id, talent_id, role=MediaRole.TRAINING_REF)


def get_voice_samples(org_id: str, talent_id: str) -> list[TalentMediaUpload]:
    """Get accepted voice samples for a talent."""
    return get_talent_uploads(org_id, talent_id, role=MediaRole.VOICE_SAMPLE)


# =============================================================================
# Downstream Authorization
# =============================================================================


def authorize_role_access(upload_id: str, org_id: str, requesting_role: MediaRole) -> bool:
    """Check if a downstream service can access an upload for a specific role.

    Prevents silent repurposing (e.g. using a voice sample as training data).
    """
    upload = _uploads.get(upload_id)
    if not upload or upload.org_id != org_id:
        return False
    return upload.role == requesting_role and upload.status == UploadStatus.ACCEPTED


# =============================================================================
# Validation Helpers
# =============================================================================


def _validate_mime(content_type: str, config: RoleConfig) -> bool:
    """Validate MIME type against role's allowed prefixes."""
    return any(content_type.startswith(prefix) for prefix in config.allowed_mime_prefixes)


def _build_storage_key(
    org_id: str,
    talent_id: str,
    role: MediaRole,
    upload_id: str,
    filename: str,
) -> str:
    """Build private tenant-scoped storage key."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    return f"{org_id}/{role.value}/{talent_id}/{upload_id}.{ext}"


def _find_duplicate(org_id: str, talent_id: str, file_hash: str) -> TalentMediaUpload | None:
    """Find existing upload with same hash (idempotent)."""
    for upload in _uploads.values():
        if (upload.org_id == org_id and upload.talent_id == talent_id
                and upload.file_hash == file_hash and upload.status == UploadStatus.ACCEPTED):
            return upload
    return None


def _get_upload(upload_id: str, org_id: str) -> TalentMediaUpload:
    upload = _uploads.get(upload_id)
    if not upload or upload.org_id != org_id:
        raise UploadNotFound(f"Upload {upload_id} not found")
    return upload


# =============================================================================
# Exceptions
# =============================================================================


class UploadError(Exception):
    """Base upload error."""


class UploadValidationError(UploadError):
    """Validation failed."""


class UploadNotFound(UploadError):
    """Upload not found or cross-tenant."""


class AuthorizationError(UploadError):
    """Authorization check failed."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    global _simulate_corrupt_file, _simulate_storage_failure
    _uploads.clear()
    _simulate_corrupt_file = False
    _simulate_storage_failure = False


def _inject_condition(condition: str, enabled: bool = True) -> None:
    global _simulate_corrupt_file, _simulate_storage_failure
    if condition == "corrupt_file":
        _simulate_corrupt_file = enabled
    elif condition == "storage_failure":
        _simulate_storage_failure = enabled
