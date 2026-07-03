# Skill: Create Backblaze B2 Upload Service

## Purpose

Create or extend the B2 storage service for uploading, retrieving, and managing assets.

## Storage key pattern

```
/{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}
```

## Core service (app/services/storage_service.py)

```python
import boto3
from botocore.exceptions import ClientError
from app.core.config import get_settings

class StorageService:
    def __init__(self):
        s = get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=s.b2_endpoint_url,
            aws_access_key_id=s.b2_key_id,
            aws_secret_access_key=s.b2_application_key,
            region_name=s.b2_region,
        )
        self._bucket = s.b2_bucket_name
        self._cdn_url = s.b2_cdn_url

    def build_key(self, org_id, asset_type, filename, talent_id=None, job_id=None):
        parts = [str(org_id), asset_type]
        if talent_id: parts.append(str(talent_id))
        if job_id:    parts.append(str(job_id))
        parts.append(filename)
        return "/".join(parts)

    def upload(self, content, key, content_type, metadata=None):
        self._client.upload_fileobj(
            BytesIO(content) if isinstance(content, bytes) else content,
            self._bucket, key,
            ExtraArgs={"ContentType": content_type, "Metadata": metadata or {}},
        )
        return key

    def get_signed_url(self, key, expires_in=3600):
        if self._cdn_url:
            return f"{self._cdn_url.rstrip('/')}/{key}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete(self, key):
        self._client.delete_object(Bucket=self._bucket, Key=key)
```

## Usage in endpoint

```python
storage = get_storage()
key = storage.build_key(org_id, "images", file.filename, talent_id, job_id)
storage.upload(await file.read(), key, file.content_type)
url = storage.get_signed_url(key)
```
