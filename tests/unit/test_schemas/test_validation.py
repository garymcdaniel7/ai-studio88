"""Unit tests for input validation schemas.

Tests cover:
- Whitespace-only string rejection (R4.10)
- Name length limits — max 100 chars (R4.1)
- Description length limits — max 1000 chars (R4.1)
- UUID validation for ID fields (R4.3)
- Magic byte verification for each supported type (R4.4, R4.8)
- File size limit enforcement (R4.5)
- MIME allowlist rejection for unsupported types (R4.4)

Validates: Requirements R4.1, R4.2, R4.3, R4.4, R4.5, R4.8, R4.9, R4.10
"""

from __future__ import annotations

import io
import os
import sys
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

# Ensure backend/ is on path so `from app.` imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from app.schemas.common import BaseResponseSchema, PaginatedResponse
from app.schemas.file_upload import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE_MB,
    validate_file_upload,
    verify_magic_bytes,
)
from app.schemas.validation import (
    DescriptionStr,
    FreeTextStr,
    NameStr,
    NonEmptyStr,
)
from fastapi import HTTPException, UploadFile


# =============================================================================
# Helper models for testing custom types
# =============================================================================


class NonEmptyModel(BaseModel):
    value: NonEmptyStr


class NameModel(BaseModel):
    name: NameStr


class DescriptionModel(BaseModel):
    description: DescriptionStr


class FreeTextModel(BaseModel):
    content: FreeTextStr


class IDModel(BaseModel):
    id: UUID
    org_id: UUID


# =============================================================================
# Tests: Whitespace-only string rejection (R4.10)
# =============================================================================


class TestWhitespaceRejection:
    """Whitespace-only strings must be rejected with 422."""

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NonEmptyModel(value="")
        assert "Field must not be empty" in str(exc_info.value) or "String should have at least 1 character" in str(exc_info.value)

    def test_spaces_only_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NonEmptyModel(value="   ")
        assert "whitespace" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()

    def test_tabs_only_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NonEmptyModel(value="\t\t")

    def test_newlines_only_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NonEmptyModel(value="\n\n\n")

    def test_mixed_whitespace_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NonEmptyModel(value=" \t \n ")

    def test_valid_string_accepted(self) -> None:
        result = NonEmptyModel(value="hello")
        assert result.value == "hello"

    def test_string_with_inner_whitespace_accepted(self) -> None:
        result = NonEmptyModel(value="hello world")
        assert result.value == "hello world"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        result = NonEmptyModel(value="  hello  ")
        assert result.value == "hello"


# =============================================================================
# Tests: Name length limits — max 100 chars (R4.1)
# =============================================================================


class TestNameStr:
    """NameStr enforces max 100 characters and whitespace rejection."""

    def test_valid_name(self) -> None:
        result = NameModel(name="Valid Name")
        assert result.name == "Valid Name"

    def test_name_at_max_length(self) -> None:
        name = "a" * 100
        result = NameModel(name=name)
        assert result.name == name

    def test_name_exceeds_max_length(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NameModel(name="a" * 101)
        assert "at most 100 characters" in str(exc_info.value).lower() or "max_length" in str(exc_info.value).lower() or "100" in str(exc_info.value)

    def test_name_whitespace_only_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NameModel(name="   ")

    def test_name_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NameModel(name="")

    def test_name_single_char(self) -> None:
        result = NameModel(name="A")
        assert result.name == "A"


# =============================================================================
# Tests: Description length limits — max 1000 chars (R4.1)
# =============================================================================


class TestDescriptionStr:
    """DescriptionStr enforces max 1000 characters and whitespace rejection."""

    def test_valid_description(self) -> None:
        result = DescriptionModel(description="A valid description")
        assert result.description == "A valid description"

    def test_description_at_max_length(self) -> None:
        desc = "x" * 1000
        result = DescriptionModel(description=desc)
        assert result.description == desc

    def test_description_exceeds_max_length(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            DescriptionModel(description="x" * 1001)
        assert "1000" in str(exc_info.value)

    def test_description_whitespace_only_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DescriptionModel(description="    ")


class TestFreeTextStr:
    """FreeTextStr enforces max 5000 characters."""

    def test_valid_free_text(self) -> None:
        result = FreeTextModel(content="Some content here")
        assert result.content == "Some content here"

    def test_free_text_at_max_length(self) -> None:
        text = "z" * 5000
        result = FreeTextModel(content=text)
        assert result.content == text

    def test_free_text_exceeds_max_length(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FreeTextModel(content="z" * 5001)
        assert "5000" in str(exc_info.value)


# =============================================================================
# Tests: UUID validation for ID fields (R4.3)
# =============================================================================


class TestUUIDValidation:
    """All ID fields must use UUID type, rejecting non-UUID strings."""

    def test_valid_uuid(self) -> None:
        uid = uuid4()
        result = IDModel(id=uid, org_id=uid)
        assert result.id == uid

    def test_valid_uuid_string(self) -> None:
        uid = uuid4()
        result = IDModel(id=str(uid), org_id=str(uid))
        assert result.id == uid

    def test_invalid_uuid_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            IDModel(id="not-a-uuid", org_id=str(uuid4()))
        assert "uuid" in str(exc_info.value).lower() or "value" in str(exc_info.value).lower()

    def test_empty_string_uuid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IDModel(id="", org_id=str(uuid4()))

    def test_integer_uuid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IDModel(id=12345, org_id=str(uuid4()))


# =============================================================================
# Tests: Magic byte verification (R4.4, R4.8)
# =============================================================================


class TestMagicByteVerification:
    """Magic bytes must match the declared content type."""

    def test_jpeg_valid_magic_bytes(self) -> None:
        header = b"\xff\xd8\xff\xe0" + b"\x00" * 8
        assert verify_magic_bytes(header, "image/jpeg") is True

    def test_jpeg_invalid_magic_bytes(self) -> None:
        header = b"\x00\x00\x00\x00" + b"\x00" * 8
        assert verify_magic_bytes(header, "image/jpeg") is False

    def test_png_valid_magic_bytes(self) -> None:
        header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4
        assert verify_magic_bytes(header, "image/png") is True

    def test_png_invalid_magic_bytes(self) -> None:
        header = b"\xff\xd8\xff" + b"\x00" * 9
        assert verify_magic_bytes(header, "image/png") is False

    def test_webp_valid_magic_bytes(self) -> None:
        header = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP"
        assert verify_magic_bytes(header, "image/webp") is True

    def test_webp_invalid_no_webp_marker(self) -> None:
        header = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE"
        assert verify_magic_bytes(header, "image/webp") is False

    def test_gif87a_valid(self) -> None:
        header = b"GIF87a" + b"\x00" * 6
        assert verify_magic_bytes(header, "image/gif") is True

    def test_gif89a_valid(self) -> None:
        header = b"GIF89a" + b"\x00" * 6
        assert verify_magic_bytes(header, "image/gif") is True

    def test_gif_invalid(self) -> None:
        header = b"NOTGIF" + b"\x00" * 6
        assert verify_magic_bytes(header, "image/gif") is False

    def test_mp4_valid_ftyp(self) -> None:
        header = b"\x00\x00\x00\x1c" + b"ftyp" + b"isom"
        assert verify_magic_bytes(header, "video/mp4") is True

    def test_mp4_valid_zero_prefix(self) -> None:
        header = b"\x00\x00\x00" + b"\x00" * 9
        assert verify_magic_bytes(header, "video/mp4") is True

    def test_mp4_invalid(self) -> None:
        header = b"\xff\xff\xff\xff" + b"nope" + b"\x00" * 4
        assert verify_magic_bytes(header, "video/mp4") is False

    def test_mpeg_valid_id3(self) -> None:
        header = b"ID3" + b"\x00" * 9
        assert verify_magic_bytes(header, "audio/mpeg") is True

    def test_mpeg_valid_sync_byte(self) -> None:
        header = b"\xff\xfb" + b"\x00" * 10
        assert verify_magic_bytes(header, "audio/mpeg") is True

    def test_mpeg_invalid(self) -> None:
        header = b"\x00\x00" + b"\x00" * 10
        assert verify_magic_bytes(header, "audio/mpeg") is False

    def test_wav_valid(self) -> None:
        header = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE"
        assert verify_magic_bytes(header, "audio/wav") is True

    def test_wav_invalid_no_wave_marker(self) -> None:
        header = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP"
        assert verify_magic_bytes(header, "audio/wav") is False

    def test_ogg_valid(self) -> None:
        header = b"OggS" + b"\x00" * 8
        assert verify_magic_bytes(header, "audio/ogg") is True

    def test_ogg_invalid(self) -> None:
        header = b"XXXX" + b"\x00" * 8
        assert verify_magic_bytes(header, "audio/ogg") is False

    def test_unknown_type_passes(self) -> None:
        """Content types with no magic byte mapping pass verification."""
        header = b"\x00" * 12
        assert verify_magic_bytes(header, "application/octet-stream") is True


# =============================================================================
# Tests: File upload validation — size limits (R4.5) and MIME allowlist (R4.4)
# =============================================================================


def _make_upload_file(
    content: bytes,
    content_type: str,
    filename: str = "test_file",
) -> MagicMock:
    """Create a mock UploadFile for testing."""
    file_obj = io.BytesIO(content)
    mock_file = MagicMock(spec=UploadFile)
    mock_file.content_type = content_type
    mock_file.filename = filename
    mock_file.file = file_obj

    # Make read/seek async
    async def mock_read(size: int = -1) -> bytes:
        if size == -1:
            return file_obj.read()
        return file_obj.read(size)

    async def mock_seek(offset: int, whence: int = 0) -> None:
        file_obj.seek(offset, whence)

    mock_file.read = mock_read
    mock_file.seek = mock_seek

    return mock_file


class TestFileUploadValidation:
    """Test validate_file_upload function."""

    @pytest.mark.asyncio
    async def test_valid_jpeg_upload(self) -> None:
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        file = _make_upload_file(content, "image/jpeg", "photo.jpg")
        # Should not raise
        await validate_file_upload(file, "image")

    @pytest.mark.asyncio
    async def test_valid_png_upload(self) -> None:
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        file = _make_upload_file(content, "image/png", "image.png")
        await validate_file_upload(file, "image")

    @pytest.mark.asyncio
    async def test_unsupported_mime_type_rejected(self) -> None:
        content = b"\x00" * 100
        file = _make_upload_file(content, "application/pdf", "doc.pdf")
        with pytest.raises(HTTPException) as exc_info:
            await validate_file_upload(file, "image")
        assert exc_info.value.status_code == 422
        assert "not allowed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_unknown_asset_type_rejected(self) -> None:
        content = b"\x00" * 100
        file = _make_upload_file(content, "image/jpeg", "photo.jpg")
        with pytest.raises(HTTPException) as exc_info:
            await validate_file_upload(file, "unknown_type")
        assert exc_info.value.status_code == 422
        assert "Unknown asset type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_magic_bytes_mismatch_rejected(self) -> None:
        # Declare JPEG but provide PNG bytes
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        file = _make_upload_file(content, "image/jpeg", "fake.jpg")
        with pytest.raises(HTTPException) as exc_info:
            await validate_file_upload(file, "image")
        assert exc_info.value.status_code == 422
        assert "Magic byte verification failed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_empty_file_rejected(self) -> None:
        content = b""
        file = _make_upload_file(content, "image/jpeg", "empty.jpg")
        with pytest.raises(HTTPException) as exc_info:
            await validate_file_upload(file, "image")
        assert exc_info.value.status_code == 422
        assert "empty" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_file_exceeds_size_limit(self) -> None:
        # Create a file that exceeds the 50 MB image limit
        max_bytes = MAX_FILE_SIZE_MB["image"] * 1024 * 1024
        # We use valid JPEG header to pass magic byte check
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        file_obj = io.BytesIO(content)

        mock_file = MagicMock(spec=UploadFile)
        mock_file.content_type = "image/jpeg"
        mock_file.filename = "large.jpg"

        read_count = [0]

        async def mock_read(size: int = -1) -> bytes:
            read_count[0] += 1
            if size == -1:
                return file_obj.read()
            return file_obj.read(size)

        async def mock_seek(offset: int, whence: int = 0) -> None:
            file_obj.seek(offset, whence)

        mock_file.read = mock_read
        mock_file.seek = mock_seek

        # Make file.file.tell() report a size exceeding the limit
        fake_inner = MagicMock()
        fake_inner.tell.return_value = max_bytes + 1
        mock_file.file = fake_inner

        with pytest.raises(HTTPException) as exc_info:
            await validate_file_upload(mock_file, "image")
        assert exc_info.value.status_code == 413
        assert "exceeds maximum" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_model_file_skips_magic_bytes(self) -> None:
        """Model files (application/octet-stream) skip magic byte verification."""
        content = b"\x00" * 100  # Any content
        file = _make_upload_file(content, "application/octet-stream", "model.safetensors")
        await validate_file_upload(file, "model")

    @pytest.mark.asyncio
    async def test_video_mp4_valid(self) -> None:
        content = b"\x00\x00\x00\x1c" + b"ftyp" + b"isom" + b"\x00" * 88
        file = _make_upload_file(content, "video/mp4", "clip.mp4")
        await validate_file_upload(file, "video")

    @pytest.mark.asyncio
    async def test_audio_ogg_valid(self) -> None:
        content = b"OggS" + b"\x00" * 100
        file = _make_upload_file(content, "audio/ogg", "track.ogg")
        await validate_file_upload(file, "audio")


# =============================================================================
# Tests: PaginatedResponse and common schemas (R4.1, R22.1)
# =============================================================================


class TestPaginatedResponse:
    """Test the generic PaginatedResponse schema."""

    def test_valid_paginated_response(self) -> None:
        resp = PaginatedResponse[dict](items=[{"a": 1}], total=50, limit=20, offset=0)
        assert resp.items == [{"a": 1}]
        assert resp.total == 50
        assert resp.has_more is True

    def test_no_more_pages(self) -> None:
        resp = PaginatedResponse[dict](items=[], total=5, limit=20, offset=0)
        assert resp.has_more is False

    def test_exact_last_page(self) -> None:
        resp = PaginatedResponse[dict](items=[], total=20, limit=20, offset=0)
        assert resp.has_more is False

    def test_negative_total_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginatedResponse[dict](items=[], total=-1, limit=20, offset=0)

    def test_limit_exceeds_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginatedResponse[dict](items=[], total=0, limit=101, offset=0)

    def test_negative_offset_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginatedResponse[dict](items=[], total=0, limit=20, offset=-1)


class TestBaseResponseSchema:
    """Test BaseResponseSchema includes required fields."""

    def test_valid_response(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        uid = uuid4()
        org = uuid4()
        resp = BaseResponseSchema(id=uid, org_id=org, created_at=now, updated_at=now)
        assert resp.id == uid
        assert resp.org_id == org

    def test_invalid_id_rejected(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        with pytest.raises(ValidationError):
            BaseResponseSchema(id="bad", org_id=str(uuid4()), created_at=now, updated_at=now)


# =============================================================================
# Tests: Extra fields rejected with 422 (R4.1 — extra="forbid")
# =============================================================================


class TestExtraFieldsRejected:
    """Schemas with extra='forbid' must reject unknown fields."""

    def test_talent_create_rejects_extra_field(self) -> None:
        """TalentCreate rejects unexpected fields."""
        from app.schemas.talent import TalentCreate

        with pytest.raises(ValidationError) as exc_info:
            TalentCreate(name="Valid Name", unknown_field="oops")
        errors = exc_info.value.errors()
        assert any("extra" in str(e).lower() for e in errors)

    def test_talent_update_rejects_extra_field(self) -> None:
        """TalentUpdate rejects unexpected fields."""
        from app.schemas.talent import TalentUpdate

        with pytest.raises(ValidationError) as exc_info:
            TalentUpdate(name="Valid", hack="injection")
        errors = exc_info.value.errors()
        assert any("extra" in str(e).lower() for e in errors)

    def test_job_create_rejects_extra_field(self) -> None:
        """JobCreate rejects unexpected fields."""
        from app.schemas.job import JobCreate

        with pytest.raises(ValidationError) as exc_info:
            JobCreate(job_type="image_generation", org_id=str(uuid4()))
        errors = exc_info.value.errors()
        assert any("extra" in str(e).lower() for e in errors)

    def test_project_create_rejects_extra_field(self) -> None:
        """ProjectCreate rejects unexpected fields."""
        from backend.app.schemas.project import ProjectCreate

        with pytest.raises(ValidationError) as exc_info:
            ProjectCreate(name="My Project", hacker="evil")
        errors = exc_info.value.errors()
        assert any("extra" in str(e).lower() for e in errors)

    def test_base_schema_rejects_extra_field(self) -> None:
        """BaseSchema subclass rejects extra fields."""
        from app.schemas.base import BaseSchema

        class TestModel(BaseSchema):
            name: str

        with pytest.raises(ValidationError) as exc_info:
            TestModel(name="ok", evil="field")
        errors = exc_info.value.errors()
        assert any("extra" in str(e).lower() for e in errors)


# =============================================================================
# Tests: Project schemas (R4.1, R15.1)
# =============================================================================


class TestProjectSchemas:
    """Test Project create/update/response schemas."""

    def test_project_create_valid(self) -> None:
        """Valid project creation succeeds."""
        from backend.app.schemas.project import ProjectCreate

        project = ProjectCreate(name="Summer Campaign")
        assert project.name == "Summer Campaign"
        assert project.status == "active"
        assert project.description is None
        assert project.talent_id is None

    def test_project_create_with_all_fields(self) -> None:
        """Project creation with all optional fields."""
        from backend.app.schemas.project import ProjectCreate

        tid = uuid4()
        project = ProjectCreate(
            name="Winter Campaign",
            description="A winter photoshoot campaign",
            status="draft",
            talent_id=tid,
        )
        assert project.name == "Winter Campaign"
        assert project.description == "A winter photoshoot campaign"
        assert project.status == "draft"
        assert project.talent_id == tid

    def test_project_create_empty_name_rejected(self) -> None:
        """Empty project name is rejected."""
        from backend.app.schemas.project import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(name="")

    def test_project_create_whitespace_name_rejected(self) -> None:
        """Whitespace-only project name is rejected."""
        from backend.app.schemas.project import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(name="   ")

    def test_project_create_name_too_long_rejected(self) -> None:
        """Project name exceeding 100 chars is rejected."""
        from backend.app.schemas.project import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(name="x" * 101)

    def test_project_create_description_too_long_rejected(self) -> None:
        """Project description exceeding 1000 chars is rejected."""
        from backend.app.schemas.project import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(name="Valid", description="x" * 1001)

    def test_project_create_invalid_status_rejected(self) -> None:
        """Invalid project status is rejected with 422."""
        from backend.app.schemas.project import ProjectCreate

        with pytest.raises(ValidationError) as exc_info:
            ProjectCreate(name="Valid", status="invalid_status")
        assert "status" in str(exc_info.value).lower() or "input" in str(exc_info.value).lower()

    def test_project_create_invalid_talent_id_rejected(self) -> None:
        """Invalid UUID for talent_id is rejected."""
        from backend.app.schemas.project import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(name="Valid", talent_id="not-a-uuid")

    def test_project_update_partial(self) -> None:
        """Partial update with only name."""
        from backend.app.schemas.project import ProjectUpdate

        update = ProjectUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.description is None
        assert update.status is None

    def test_project_update_all_none(self) -> None:
        """Update with no fields is valid (empty PATCH)."""
        from backend.app.schemas.project import ProjectUpdate

        update = ProjectUpdate()
        assert update.name is None
        assert update.description is None
        assert update.status is None

    def test_project_response(self) -> None:
        """Project response schema validates correctly."""
        from datetime import datetime, timezone

        from backend.app.schemas.project import ProjectResponse

        now = datetime.now(tz=timezone.utc)
        uid = uuid4()
        org = uuid4()
        resp = ProjectResponse(
            id=uid,
            org_id=org,
            name="Test Project",
            description="A description",
            status="active",
            talent_id=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.id == uid
        assert resp.org_id == org
        assert resp.name == "Test Project"
        assert resp.status == "active"


# =============================================================================
# Tests: Talent schemas (R4.1, R10.1)
# =============================================================================


class TestTalentSchemas:
    """Test Talent create/update schemas with validation."""

    def test_talent_create_valid(self) -> None:
        """Valid talent creation succeeds."""
        from app.schemas.talent import TalentCreate

        talent = TalentCreate(name="Luna")
        assert talent.name == "Luna"
        assert talent.is_active is True

    def test_talent_create_all_fields(self) -> None:
        """Talent creation with all optional fields."""
        from app.schemas.talent import TalentCreate

        talent = TalentCreate(
            name="Nova",
            description="A digital fashion model",
            talent_type="model",
            identity_classification="FICTIONAL",
            is_active=True,
        )
        assert talent.name == "Nova"
        assert talent.description == "A digital fashion model"
        assert talent.talent_type == "model"
        assert talent.identity_classification == "FICTIONAL"

    def test_talent_create_whitespace_name_rejected(self) -> None:
        """Whitespace-only talent name is rejected."""
        from app.schemas.talent import TalentCreate

        with pytest.raises(ValidationError):
            TalentCreate(name="    ")

    def test_talent_create_name_too_long(self) -> None:
        """Talent name exceeding 100 chars is rejected."""
        from app.schemas.talent import TalentCreate

        with pytest.raises(ValidationError):
            TalentCreate(name="a" * 101)

    def test_talent_update_partial(self) -> None:
        """Partial update with single field."""
        from app.schemas.talent import TalentUpdate

        update = TalentUpdate(name="NewName")
        assert update.name == "NewName"
        assert update.description is None


# =============================================================================
# Tests: Job schemas (R4.1, R21.1)
# =============================================================================


class TestJobSchemas:
    """Test Job create schema with validation."""

    def test_job_create_valid(self) -> None:
        """Valid job creation with required fields only."""
        from app.schemas.job import JobCreate

        job = JobCreate(job_type="image_generation")
        assert job.job_type == "image_generation"
        assert job.priority == 5
        assert job.max_duration_seconds == 1800

    def test_job_create_invalid_type_rejected(self) -> None:
        """Invalid job type is rejected."""
        from app.schemas.job import JobCreate

        with pytest.raises(ValidationError):
            JobCreate(job_type="nonexistent_type")

    def test_job_create_priority_out_of_range(self) -> None:
        """Priority outside 1-10 is rejected."""
        from app.schemas.job import JobCreate

        with pytest.raises(ValidationError):
            JobCreate(job_type="image_generation", priority=0)
        with pytest.raises(ValidationError):
            JobCreate(job_type="image_generation", priority=11)

    def test_job_create_max_duration_bounds(self) -> None:
        """Max duration outside 60-14400 is rejected."""
        from app.schemas.job import JobCreate

        with pytest.raises(ValidationError):
            JobCreate(job_type="image_generation", max_duration_seconds=30)
        with pytest.raises(ValidationError):
            JobCreate(job_type="image_generation", max_duration_seconds=15000)

    def test_job_create_with_talent_id(self) -> None:
        """Job with valid talent UUID."""
        from app.schemas.job import JobCreate

        tid = uuid4()
        job = JobCreate(job_type="lora_training", talent_id=tid)
        assert job.talent_id == tid

    def test_job_create_invalid_talent_uuid(self) -> None:
        """Job with invalid talent UUID is rejected."""
        from app.schemas.job import JobCreate

        with pytest.raises(ValidationError):
            JobCreate(job_type="image_generation", talent_id="bad-id")


# =============================================================================
# Tests: Numeric bounds validation (R4.1)
# =============================================================================


class TestNumericBounds:
    """Test ge/le bounds on numeric fields."""

    def test_progress_percent_zero_valid(self) -> None:
        from app.schemas.validation import ProgressPercent
        from pydantic import BaseModel

        class M(BaseModel):
            p: ProgressPercent

        m = M(p=0)
        assert m.p == 0

    def test_progress_percent_100_valid(self) -> None:
        from app.schemas.validation import ProgressPercent
        from pydantic import BaseModel

        class M(BaseModel):
            p: ProgressPercent

        m = M(p=100)
        assert m.p == 100

    def test_progress_percent_negative_rejected(self) -> None:
        from app.schemas.validation import ProgressPercent
        from pydantic import BaseModel

        class M(BaseModel):
            p: ProgressPercent

        with pytest.raises(ValidationError):
            M(p=-1)

    def test_progress_percent_over_100_rejected(self) -> None:
        from app.schemas.validation import ProgressPercent
        from pydantic import BaseModel

        class M(BaseModel):
            p: ProgressPercent

        with pytest.raises(ValidationError):
            M(p=101)

    def test_page_limit_zero_rejected(self) -> None:
        from app.schemas.validation import PageLimit
        from pydantic import BaseModel

        class M(BaseModel):
            limit: PageLimit

        with pytest.raises(ValidationError):
            M(limit=0)

    def test_page_limit_101_rejected(self) -> None:
        from app.schemas.validation import PageLimit
        from pydantic import BaseModel

        class M(BaseModel):
            limit: PageLimit

        with pytest.raises(ValidationError):
            M(limit=101)

    def test_page_offset_negative_rejected(self) -> None:
        from app.schemas.validation import PageOffset
        from pydantic import BaseModel

        class M(BaseModel):
            offset: PageOffset

        with pytest.raises(ValidationError):
            M(offset=-1)
