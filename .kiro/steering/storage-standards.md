---
inclusion: always
---

# Storage Standards (Backblaze B2)

## Overview

All persistent file storage uses Backblaze B2 via the S3-compatible API. B2 is ~75% cheaper than AWS S3 with an identical API surface.

## Storage key structure

```
/{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}
```

Examples:
```
/org_abc123/images/talent_xyz/job_456/output_001.webp
/org_abc123/videos/talent_xyz/job_789/clip_001.mp4
/org_abc123/models/talent_xyz/lora_v3.safetensors
/org_abc123/training/talent_xyz/dataset/photo_001.jpg
```

## Asset management rules

1. **Never return raw B2 URLs** — always return signed URLs or CDN URLs
2. **Storage keys are immutable** — once assigned, never change a key
3. **Delete via soft delete** — mark asset as deleted in DB first, then schedule B2 deletion
4. **Large files** — use multipart upload for files > 100 MB
5. **CDN** — if `B2_CDN_URL` is set, use it for public/cacheable assets
6. **Metadata** — always store `org_id`, `job_id`, `content_type` as B2 object metadata

## MIME type validation

```python
ALLOWED_CONTENT_TYPES = {
    "image": ["image/jpeg", "image/png", "image/webp", "image/gif"],
    "video": ["video/mp4"],
    "audio": ["audio/mpeg", "audio/wav", "audio/ogg"],
    "model": ["application/octet-stream"],  # .safetensors
}
```

## Cost management

- Set lifecycle rules to move old assets to B2's cold storage after 90 days
- Monitor storage usage per org for quota enforcement
- Log upload sizes and cumulative org storage in job records
