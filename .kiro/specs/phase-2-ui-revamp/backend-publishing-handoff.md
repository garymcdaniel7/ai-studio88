# Backend Storage / PUBLISH Handoff — Task 15.6

**Scope:** Phase 2 Close-Out Sprint Task 15.6 only. **Status:** `UNIT-READY` for the mocked compatibility boundary; `STAGING-REQUIRED` for live B2/CDN and external deletion-worker evidence.

## API contract changes

- `backend.storage.upload_file(...)` keeps its existing positional arguments and now accepts additive keyword arguments: `org_id`, `job_id`, `metadata`, and `expires_in`.
- Uploads always persist `ContentType` plus object metadata. New callers should provide the tenant-scoped key and `org_id`/`job_id`; structured keys can supply safe metadata defaults for incremental migration.
- Upload results are delivery URLs only: a configured `B2_CDN_URL` is preferred; otherwise the module returns a validated presigned URL. A raw `B2_ENDPOINT_URL/{bucket}/{key}` URL is rejected before it can enter an API response.
- `generate_storage_key(..., org_id=..., talent_id=..., job_id=...)` produces an immutable tenant-scoped key with the shape `{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}` (optional identity segments are omitted only when unavailable). Existing positional generation remains source-compatible so persisted legacy keys are not rewritten.
- Files strictly larger than 100 MiB use S3-compatible multipart upload. Upload failures abort the multipart session before propagating the provider error.
- `backend.storage.delete_file()` remains callable for compatibility but now fails closed with `StorageDeletionRequiresLifecycleError`; it no longer performs a request-path hard delete.
- Asset deletion must use `AssetService.delete_asset()`: repository soft-delete first, then insert a pending storage-deletion record. `AssetService.process_pending_deletions()` is the worker/service boundary that may call the provider's physical delete operation.

## Evidence

Focused mocked coverage is in `backend/tests/unit/test_storage.py` and covers:

- signed URL and configured CDN URL selection;
- raw B2 URL rejection;
- immutable tenant-scoped key generation;
- `org_id`, `job_id`, and `content_type` object metadata;
- multipart threshold, part completion, and abort-on-error behavior;
- fail-closed direct deletion; and
- provider error propagation without secret logging.

Existing `backend/tests/unit/test_services/test_asset_service.py` covers soft-delete-first scheduling and confirms that storage deletion is not called on the request path. The suite could not collect in this checkout because the pre-existing `backend.app.providers` package has a circular import involving the unrelated BYO provider changes; no provider files were changed for this task.

## Remaining blockers

- Live B2/CDN signed URL and multipart behavior require controlled staging credentials and were not run.
- Durable pending-deletion processing requires the deployed repository/worker wiring and staging evidence; no migration or `.env*` change was made.
- Legacy callers that do not yet pass tenant/job context remain source-compatible, but must be migrated by their owning backend/API checkpoints before repository-wide structured-key and required-metadata acceptance can be claimed. `backend/api_v1.py` was intentionally not edited because it is a serialized mutex and prohibited by this task.
- MIME allowlist, magic-byte, and request-size validation remain at the existing asset/service upload boundaries; this low-level compatibility facade does not bypass or duplicate those checks.

No frontend source, migrations, `.env*` files, `backend/api_v1.py`, old specs, or unrelated dirty files were changed. No commit was created.
