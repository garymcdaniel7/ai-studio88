"""File upload validation with magic byte verification, MIME allowlist, and size limits.

Validates: Requirements R4.4, R4.5, R4.8, R4.9
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status


# =============================================================================
# MIME Type Allowlist (per storage-standards rule)
# =============================================================================

ALLOWED_CONTENT_TYPES: dict[str, list[str]] = {
    "image": ["image/jpeg", "image/png", "image/webp", "image/gif"],
    "video": ["video/mp4"],
    "audio": ["audio/mpeg", "audio/wav", "audio/ogg"],
    "model": ["application/octet-stream"],
}

# =============================================================================
# Magic Bytes Map — first N bytes that identify file type
# =============================================================================

MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],  # additionally check bytes 8-12 for "WEBP"
    "image/gif": [b"GIF87a", b"GIF89a"],
    "video/mp4": [b"\x00\x00\x00", b"ftyp"],  # ftyp typically at offset 4
    "audio/mpeg": [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"ID3"],
    "audio/wav": [b"RIFF"],  # additionally check bytes 8-12 for "WAVE"
    "audio/ogg": [b"OggS"],
}

# =============================================================================
# Size Limits (in MB) per asset type
# =============================================================================

MAX_FILE_SIZE_MB: dict[str, int] = {
    "image": 50,
    "video": 2048,  # 2 GB
    "audio": 500,
    "model": 20480,  # 20 GB
}

# Maximum JSON request body size (non-file endpoints)
MAX_JSON_BODY_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB


def _bytes_to_mb(size_bytes: int) -> float:
    """Convert bytes to megabytes."""
    return size_bytes / (1024 * 1024)


def verify_magic_bytes(header: bytes, declared_content_type: str) -> bool:
    """Verify that file header bytes match the declared content type.

    Args:
        header: The first 12 bytes of the file.
        declared_content_type: The MIME type declared by the client.

    Returns:
        True if magic bytes match, False otherwise.
    """
    signatures = MAGIC_BYTES.get(declared_content_type)
    if signatures is None:
        # No magic byte check configured for this type (e.g., model files)
        return True

    for sig in signatures:
        if declared_content_type == "image/webp":
            # WEBP: starts with "RIFF" and bytes 8-12 are "WEBP"
            if header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
                return True
        elif declared_content_type == "audio/wav":
            # WAV: starts with "RIFF" and bytes 8-12 are "WAVE"
            if header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WAVE":
                return True
        elif declared_content_type == "video/mp4":
            # MP4: "ftyp" typically at offset 4, or starts with \x00\x00\x00
            if len(header) >= 8 and header[4:8] == b"ftyp":
                return True
            if header[:3] == b"\x00\x00\x00":
                return True
        else:
            if header[: len(sig)] == sig:
                return True

    return False


async def validate_file_upload(file: UploadFile, asset_type: str) -> None:
    """Validate an uploaded file against MIME allowlist, magic bytes, and size limits.

    Args:
        file: The uploaded file from FastAPI.
        asset_type: One of "image", "video", "audio", "model".

    Raises:
        HTTPException 422: If content type is not in the allowlist or magic bytes mismatch.
        HTTPException 413: If file exceeds the size limit for the asset type.
    """
    # Validate asset_type is recognized
    if asset_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown asset type: '{asset_type}'. "
            f"Allowed types: {list(ALLOWED_CONTENT_TYPES.keys())}",
        )

    # Validate MIME type against allowlist
    content_type = file.content_type or ""
    allowed = ALLOWED_CONTENT_TYPES[asset_type]
    if content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Content type '{content_type}' is not allowed for asset type '{asset_type}'. "
            f"Allowed: {allowed}",
        )

    # Read file header for magic byte verification (first 12 bytes)
    header = await file.read(12)
    await file.seek(0)  # Reset file position

    if len(header) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    # Verify magic bytes match declared content type
    if not verify_magic_bytes(header, content_type):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File content does not match declared content type '{content_type}'. "
            f"Magic byte verification failed.",
        )

    # Validate file size
    max_size_mb = MAX_FILE_SIZE_MB[asset_type]
    max_size_bytes = max_size_mb * 1024 * 1024

    # Get file size — read to end and check
    await file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    await file.seek(0)  # Reset

    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({_bytes_to_mb(file_size):.1f} MB) exceeds maximum "
            f"for asset type '{asset_type}' ({max_size_mb} MB)",
        )
