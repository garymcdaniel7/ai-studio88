# Group 16.4 — B2 Storage Staging Runbook

**Status: `STAGING-REQUIRED` / `BLOCKED`**
**Scope:** Phase 2 Close-Out Sprint, Group 16.4 storage staging acceptance only.
**Owner:** Backend/storage owner executes; CTO/release owner authorizes staging; SRE/deployment owner confirms deployment and worker parity.
**Decision rule:** Local mocked evidence is preparation evidence only. Do not mark Group 16.4 accepted until every live check below has a captured staging result and independent sign-off.

## 1. Scope and guardrails

This runbook verifies the Backblaze B2 storage boundary and the AssetService deletion lifecycle without changing application code. It covers signed/CDN delivery, immutable tenant-scoped keys, required object metadata, a strictly-over-100 MiB multipart upload, tenant isolation, soft-delete-first behavior, and worker-owned physical deletion.

**Not executed in this checkout:** no live B2/CDN request, provider upload, multipart operation, worker deletion, database mutation, production request, migration, deployment, or destructive/provider test was run. The commands in Sections 4–8 are **staging-only commands to run after the gates are satisfied**, not evidence that staging acceptance already passed.

Hard guardrails:

- Never target production, the shared development/prod Supabase project, the production B2 bucket, or a shared Vast.ai/provider account. The environment map currently states that no isolated staging environment exists and that local/development shares production Supabase and B2.
- Do not use `.env`, `.env.staging`, `.env.local`, or any checked-in environment file as a staging credential source. Inject short-lived staging credentials from the approved secret manager; do not print them.
- Do not run `aws s3api delete-object`, direct B2 deletion, SQL `DELETE`, or a request-path hard delete. Physical deletion must be caused by the pending-deletion worker after the database soft-delete has been recorded.
- Use two disposable staging organisations only. Use synthetic filenames/content and a dedicated staging bucket prefix. Do not use real user, talent, job, or generated-media data.
- Abort the run immediately if the target bucket, database host, API host, CDN host, deployment SHA, or credential namespace cannot be proven staging-only.
- Preserve request IDs, asset IDs, storage keys, object metadata, worker logs, and read-only database query output as evidence. Redact bearer tokens, access keys, signed query strings, and any secret value before saving evidence.

## 2. Required staging prerequisites

The release owner must attach all of the following before execution:

| Gate | Required evidence | Owner | Current state |
|---|---|---|---|
| Isolated environment | Separate staging API deployment, Supabase/PostgreSQL project, B2 bucket, CDN hostname, and worker/queue | SRE/deployment | **Missing; BLOCKED** |
| Credential safety | Secret-manager references for staging B2, database read-only inspection, and two staging bearer tokens; no values in shell history/logs | CTO/SRE | **Missing; BLOCKED** |
| Deployment parity | API and worker image/build SHA, storage module version, and migrations match the candidate under test | Backend/release | **Unproven; BLOCKED** |
| B2 configuration | Staging endpoint, bucket, region, and optional `B2_CDN_URL`; bucket identity is independently verified | Backend/SRE | **Missing; BLOCKED** |
| Deletion worker | Durable pending-deletion table/repository, worker schedule/command, retry/error visibility, and a kill/rollback procedure | Backend/SRE | **Unproven; BLOCKED** |
| Test identities | Org A and Org B, one talent and job per org, editor/admin token for A, viewer/token for B, all synthetic and disposable | Release owner | **Missing; BLOCKED** |
| Approval | Change/test window and written authorization for staging object creation and deletion | CTO/release owner | **Missing; BLOCKED** |

### Safe preflight (read-only/configuration checks)

Run only after staging variables are injected by the secret manager. These checks must fail closed before any provider or database mutation:

```bash
set -euo pipefail
: "${ENVIRONMENT:?must be injected}"
: "${STAGING_API_BASE:?must be injected}"
: "${STAGING_B2_ENDPOINT:?must be injected}"
: "${STAGING_B2_BUCKET:?must be injected}"
: "${STAGING_DB_URL:?must be injected for read-only inspection}"
: "${STAGING_TOKEN_A:?must be injected; do not echo}"
: "${STAGING_TOKEN_B:?must be injected; do not echo}"
: "${STAGING_APPROVAL_ID:?must identify the approved staging window}"

test "$ENVIRONMENT" = "staging"
test -n "$STAGING_APPROVAL_ID"
test "${STAGING_B2_BUCKET}" != "${PRODUCTION_B2_BUCKET:-__unknown__}"
test "${STAGING_DB_URL}" != "${PRODUCTION_DB_URL:-__unknown__}"
printf 'staging preflight variables present; secret values intentionally not printed\n'
```

The release owner must then record the read-only provider/bucket identity and database identity using the staging-only credentials. Do not continue if either identity is shared with production:

```bash
aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api head-bucket \
  --bucket "$STAGING_B2_BUCKET"
psql "$STAGING_DB_URL" -X -v ON_ERROR_STOP=1 -Atc \
  "select current_database(), current_user;"
```

`head-bucket` and the `SELECT` above are preflight reads. They are not a substitute for recording the approved staging resource IDs and deployment SHA.

## 3. Test data and expected key contract

Create synthetic IDs in the staging database or use the release owner's pre-created fixtures; never accept client-supplied organisation identity as authoritative:

```text
ORG_A       = UUID for staging organisation A
ORG_B       = UUID for staging organisation B
TALENT_A    = talent owned by ORG_A
JOB_A       = job owned by ORG_A
TALENT_B    = talent owned by ORG_B
JOB_B       = job owned by ORG_B
ASSET_A     = asset uploaded by ORG_A during this run
```

Use these files:

| Fixture | Content type | Purpose |
|---|---|---|
| `g16-4-small.webp` | `image/webp` | signed/CDN response, metadata, tenant isolation |
| `g16-4-multipart.safetensors` | `application/octet-stream` | exactly `100 * 1024 * 1024 + 1` bytes; multipart threshold crossing |
| `g16-4-invalid.txt` | `text/plain` or mismatched magic bytes | confirm MIME/magic-byte/size boundary rejects invalid content before storage |

For a local synthetic multipart fixture only (no network/provider call), create the file in a temporary directory:

```bash
TMP_DIR="$(mktemp -d -t aios-g16-4.XXXXXX)"
export TMP_DIR
python - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["TMP_DIR"]) / "g16-4-multipart.safetensors"
size = 100 * 1024 * 1024 + 1
chunk = b"g16-4-staging-test\0" * 4096
with path.open("wb") as handle:
    remaining = size
    while remaining:
        block = chunk[: min(len(chunk), remaining)]
        handle.write(block)
        remaining -= len(block)
assert path.stat().st_size == size
print(path)
PY
shasum -a 256 "$TMP_DIR/g16-4-multipart.safetensors"
```

The required key shape for a fixture with all identities present is:

```text
/{ORG_A}/images/{TALENT_A}/{JOB_A}/<unique>_g16-4-small.webp
/{ORG_A}/models/{TALENT_A}/{JOB_A}/<unique>_g16-4-multipart.safetensors
```

Assertions:

- `org_id`, `asset_type`, `talent_id`, `job_id`, and filename are separate path segments; no `..`, slash traversal, or unsanitised path separator is accepted.
- Keys are generated once and persisted. Re-uploading a same-named file creates a new unique key; updating metadata never rewrites the original key.
- A key from ORG_A never contains ORG_B and is never returned for an ORG_B request.
- Optional identity segments may be absent only when the corresponding trusted record is genuinely unavailable; the controlled acceptance fixture must include all four identity segments.

## 4. Upload, metadata, and URL acceptance

Use the authenticated staging asset-upload contract for the small fixture. The caller must not submit an `org_id` selector; the server derives organisation from the validated bearer context. Capture the response without retaining a raw signed query string:

```bash
curl --fail-with-body --silent --show-error \
  -X POST "$STAGING_API_BASE/api/v1/assets" \
  -H "Authorization: Bearer $STAGING_TOKEN_A" \
  -F "file=@$TMP_DIR/g16-4-small.webp;type=image/webp" \
  -F "talent_id=$TALENT_A" \
  -F "asset_type=images" \
  -F "tags=g16-4-staging" \
  -o "$TMP_DIR/upload-a.json"
```

Record only `ASSET_A`, the persisted `storage_key`, URL host/path (not URL query credentials), content type, size, checksum, request ID, and deployment SHA. The upload must satisfy all of these:

1. The response contains a CDN URL when `B2_CDN_URL` is configured, or a presigned URL with a verifiable signature and expiry when CDN is not configured.
2. The response never contains the raw `B2_ENDPOINT_URL/{bucket}/{key}` form, a public bucket URL, access key, bearer token, or service-role key.
3. B2 `HeadObject` for the persisted key reports metadata exactly containing `org_id=ORG_A`, `job_id=JOB_A`, and `content_type=image/webp` (plus permitted non-secret metadata). `ContentType` also equals `image/webp`.
4. The persisted key matches the immutable structure in Section 3 and remains unchanged after a second `GET` of the asset.
5. The `content_type` is validated against the asset class and magic bytes; extension-only acceptance is a failure.

Inspect object metadata through the staging endpoint only; never paste signed query parameters into evidence:

```bash
aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api head-object \
  --bucket "$STAGING_B2_BUCKET" \
  --key "$PERSISTED_KEY" \
  --query '{ContentLength:ContentLength,ContentType:ContentType,Metadata:Metadata,ETag:ETag}' \
  --output json
```

CDN/signed URL assertion (run against the URL from the staging response after redacting it from logs):

```bash
python - <<'PY'
import os
from urllib.parse import parse_qs, urlparse

url = os.environ["STAGING_DELIVERY_URL"]
endpoint = os.environ["STAGING_B2_ENDPOINT"].rstrip("/")
bucket = os.environ["STAGING_B2_BUCKET"]
parsed = urlparse(url)
raw_prefixes = (f"{endpoint}/{bucket}/", f"{endpoint}/{bucket}")
assert not any(url.startswith(prefix) for prefix in raw_prefixes), "raw B2 URL exposed"
cdn = os.environ.get("STAGING_CDN_URL", "").rstrip("/")
if cdn:
    assert url.startswith(cdn + "/"), "configured CDN was not selected"
else:
    query = parse_qs(parsed.query)
    assert query.get("X-Amz-Signature") or query.get("Signature"), "missing URL signature"
print("delivery URL assertion passed; URL value not printed")
PY
```

## 5. Strictly-over-100 MiB multipart acceptance

The current legacy `/api/v1/assets` path rejects content larger than 100 MiB before calling storage. Therefore an HTTP upload returning `413` does **not** prove multipart behavior. Until an approved staging worker/storage harness passes the bytes to the storage provider, this gate remains `STAGING-REQUIRED` and `BLOCKED`; do not change `backend/api_v1.py` in this runbook.

Use one of these two approved staging paths, in order:

- the deployed AssetService/worker path that accepts the large fixture and calls the canonical storage provider; or
- a release-approved, staging-only storage harness using the same provider configuration and metadata contract.

If the second path is approved, the following direct S3-compatible multipart sequence is the minimum provider check. It must run only against the isolated staging bucket, with the upload ID captured for cleanup; it is not an application/API acceptance result:

```bash
KEY="$ORG_A/models/$TALENT_A/$JOB_A/g16-4-multipart.safetensors"
UPLOAD_ID="$(aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api create-multipart-upload \
  --bucket "$STAGING_B2_BUCKET" --key "$KEY" \
  --content-type application/octet-stream \
  --metadata "org_id=$ORG_A,job_id=$JOB_A,content_type=application/octet-stream" \
  --query UploadId --output text)"
printf '%s\n' "$UPLOAD_ID" > "$TMP_DIR/multipart-upload-id"

ETAG="$(aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api upload-part \
  --bucket "$STAGING_B2_BUCKET" --key "$KEY" --upload-id "$UPLOAD_ID" \
  --part-number 1 --body "$TMP_DIR/g16-4-multipart.safetensors" \
  --query ETag --output text)"
printf '{"Parts":[{"ETag":%s,"PartNumber":1}]}\n' "$ETAG" > "$TMP_DIR/multipart-parts.json"
aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api complete-multipart-upload \
  --bucket "$STAGING_B2_BUCKET" --key "$KEY" --upload-id "$UPLOAD_ID" \
  --multipart-upload "file://$TMP_DIR/multipart-parts.json"

aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api head-object \
  --bucket "$STAGING_B2_BUCKET" --key "$KEY" \
  --query '{ContentLength:ContentLength,ContentType:ContentType,Metadata:Metadata}' \
  --output json
```

Expected multipart evidence:

- source size is exactly `104857601` bytes (strictly greater than 100 MiB);
- `create-multipart-upload`, `upload-part`, and `complete-multipart-upload` all succeed;
- final `HeadObject` size, content type, and `org_id`/`job_id`/`content_type` metadata match the source;
- a forced part/upload failure in a separate authorized staging attempt causes `abort-multipart-upload`, leaves no completed object, and leaves no orphaned multipart upload;
- the application/worker evidence identifies the same persisted key and job, rather than only proving a direct provider call.

## 6. Tenant isolation and immutable-key checks

Run the following with the two staging tokens and record status codes, response bodies after redaction, and database/provider side-effect checks:

```bash
curl --silent --show-error -o "$TMP_DIR/org-b-get-a.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer $STAGING_TOKEN_B" \
  "$STAGING_API_BASE/api/v1/assets/$ASSET_A"

curl --silent --show-error -o "$TMP_DIR/org-b-list.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer $STAGING_TOKEN_B" \
  "$STAGING_API_BASE/api/v1/assets?limit=100&offset=0"

curl --silent --show-error -o "$TMP_DIR/org-a-selector.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer $STAGING_TOKEN_A" \
  "$STAGING_API_BASE/api/v1/assets?org_id=$ORG_B"
```

Expected results are a canonical `404`/denial for the foreign asset, no ORG_A rows in the ORG_B list, and `422`/canonical rejection for a client organisation selector. A successful foreign read, foreign list row, or client-selected organisation is a release blocker.

Read-only database/provider checks must confirm:

- `ASSET_A.org_id = ORG_A`, `ASSET_A.job_id = JOB_A`, and the persisted key is unchanged across reads;
- no ORG_B asset or pending deletion record was created by ORG_A requests;
- B2 object metadata and database metadata agree; neither source is allowed to override the trusted JWT organisation.

## 7. Soft-delete-first and worker physical deletion

Use the authenticated asset-delete endpoint against `ASSET_A` only after all read/URL/metadata evidence is captured. The deletion request is intentionally destructive to a disposable staging object and requires the approval ID from Section 2:

```bash
test -n "$STAGING_APPROVAL_ID"
curl --fail-with-body --silent --show-error \
  -X DELETE "$STAGING_API_BASE/api/v1/assets/$ASSET_A" \
  -H "Authorization: Bearer $STAGING_TOKEN_A" \
  -o "$TMP_DIR/delete-a.json"
```

Immediately after the request, before the deletion worker runs, prove soft-delete-first:

```bash
psql "$STAGING_DB_URL" -X -v ON_ERROR_STOP=1 -Atc \
  "select id, org_id, storage_key, deleted_at from assets where id = '$ASSET_A';"
psql "$STAGING_DB_URL" -X -v ON_ERROR_STOP=1 -Atc \
  "select asset_id, org_id, storage_key, storage_provider, processed_at, error from pending_deletions where asset_id = '$ASSET_A';"
aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api head-object \
  --bucket "$STAGING_B2_BUCKET" --key "$PERSISTED_KEY" \
  --query '{ContentLength:ContentLength,Metadata:Metadata}' --output json
```

Expected pre-worker result: `deleted_at` is non-null; exactly one pending deletion row contains the same org/key/provider; and the object still exists. Any provider deletion before the database soft-delete/pending record is visible fails the gate.

Run the existing staging deletion worker once with its documented bounded/batch option and capture the worker run ID, count, key, and error state. Do not substitute a direct B2 delete:

```bash
# The exact worker command is deployment-specific and must be supplied by SRE.
# Required shape: one bounded batch, staging environment, no production queue.
<STAGING_PENDING_DELETION_WORKER_COMMAND> --limit 1 --environment staging
```

After the worker completes, verify:

```bash
psql "$STAGING_DB_URL" -X -v ON_ERROR_STOP=1 -Atc \
  "select asset_id, processed_at, error from pending_deletions where asset_id = '$ASSET_A';"
aws --endpoint-url "$STAGING_B2_ENDPOINT" s3api head-object \
  --bucket "$STAGING_B2_BUCKET" --key "$PERSISTED_KEY"
```

Expected post-worker result: the pending record is marked processed with no error and `HeadObject` returns the provider's not-found response. If deletion fails transiently, the record must retain an actionable error/retry state and the worker must not report success. Capture both success and one controlled provider-error/retry result if the staging window permits; do not manufacture a failure by targeting production or an unrelated object.

## 8. Rollback and cleanup

Rollback is limited to the isolated staging fixtures and is owned by the release owner:

1. Stop the bounded staging worker if it loops, exceeds its run window, or targets an unexpected key. Preserve the worker run ID and logs.
2. If a multipart upload fails before completion, abort **only the captured staging upload ID** and verify `list-multipart-uploads` has no matching orphan. Never use a bucket-wide abort or delete.
3. If a soft-delete is recorded but the worker fails, leave the durable pending record for the approved retry path; do not bypass it with direct storage deletion or SQL mutation.
4. If an upload leaves an unreferenced staging object, quarantine the key in the evidence record and have the storage owner remove it through the approved staging cleanup workflow only. Do not delete an object whose org/key ownership is not proven.
5. After the run, remove only the temporary local fixture directory and redact tokens/signatures from evidence. Local cleanup is safe and does not touch B2 or the database:

```bash
rm -rf -- "$TMP_DIR"
unset STAGING_TOKEN_A STAGING_TOKEN_B STAGING_DB_URL STAGING_B2_ENDPOINT STAGING_B2_BUCKET
```

6. Attach the final object inventory, pending-deletion inventory, worker result, and cleanup confirmation to the release record. No production rollback is authorized by this runbook.

## 9. Acceptance record

The acceptance record must include, for each check, the staging environment/build SHA, operator, UTC timestamp, request ID or worker run ID, fixture IDs, expected result, observed result, and evidence location:

| Check | Expected output | Result |
|---|---|---|
| Staging identity/preflight | Isolated API/DB/B2/CDN/worker; no shared production resource | `BLOCKED — no isolated staging` |
| Signed URL without CDN | Presigned URL, signature/expiry, no raw endpoint/bucket URL | `STAGING-REQUIRED` |
| CDN preference | CDN URL selected; no B2 endpoint in response | `STAGING-REQUIRED` |
| Required metadata | `org_id`, `job_id`, `content_type` on object and matching DB record | `STAGING-REQUIRED` |
| Immutable key | Required tenant/talent/job path; unchanged after reads/updates | `STAGING-REQUIRED` |
| >100 MiB multipart | `104857601` bytes, multipart complete, metadata preserved | `STAGING-REQUIRED`; API path currently caps at 100 MiB |
| Multipart abort | Failed staging upload aborted; no completed object/orphan | `STAGING-REQUIRED` |
| Tenant A/B | Foreign read/list/mutation denied; no cross-org side effect | `STAGING-REQUIRED` |
| Soft-delete first | DB `deleted_at` and pending row precede object deletion | `STAGING-REQUIRED` |
| Worker physical deletion | Worker processes pending row; object then not found | `STAGING-REQUIRED` |
| Rollback/cleanup | Only disposable staging fixtures cleaned; no direct delete | `STAGING-REQUIRED` |

**Acceptance status:** `STAGING-REQUIRED` / `BLOCKED` until the missing isolated staging prerequisites and every live result above are supplied. Local green/mock evidence must not be promoted to release acceptance.

## 10. Existing local evidence and blockers

### Local evidence retained

- `uv run pytest backend/tests/unit/test_storage.py -q -m unit -rA` — **PASS, 8 passed**. The eight tests cover signed URL selection, CDN selection, raw B2 URL rejection, tenant-scoped key generation, required metadata, multipart threshold/completion, multipart abort, fail-closed direct deletion, and provider error propagation.
- `.kiro/specs/phase-2-ui-revamp/backend-publishing-handoff.md` records the same Task 15.6 mocked boundary as `UNIT-READY`, while live B2/CDN and external deletion-worker evidence remain `STAGING-REQUIRED`.
- `backend/tests/unit/test_services/test_asset_service.py` contains soft-delete-first, no-request-path-delete, pending-worker-success, and pending-worker-error tests. It is evidence of intended behavior, not live worker evidence.
- `tests/unit/test_storage_provider.py` contains provider-level mocked tests for key structure, URL selection, multipart threshold, abort, delete, and error mapping.

### Validation/blockers observed in this checkout

- `uv run pytest backend/tests/unit/test_storage.py tests/unit/test_storage_provider.py -q -m unit` — **BLOCKED during collection** by the pre-existing circular import in `backend.app.providers` involving BYO provider modules; no provider-level tests ran in that combined command.
- `uv run pytest backend/tests/unit/test_services/test_asset_service.py -q -m unit` — **BLOCKED during collection** by the same pre-existing circular import; no AssetService test ran.
- The current legacy `/api/v1/assets` route rejects files larger than 100 MiB before storage, while the low-level storage/provider contract uses multipart for strictly larger files. A staging API acceptance path for the large fixture is therefore not currently evidenced; use an approved worker/provider harness or leave the gate blocked.
- `docs/ENVIRONMENT_MAP.md` states **no staging environment exists** and local/development shares the production Supabase project and B2 bucket. This alone prevents live acceptance.
- Current `git status` contains extensive unrelated dirty application paths, including pre-existing `backend/storage.py`; this runbook does not attribute or modify them.

No application code, `.env*`, migrations, `backend/api_v1.py`, frontend, old specs, or unrelated files were changed for this runbook. No commit was created.

## 11. Group 17.4 executable local checklist

The safe local runner below is the only executable portion of this runbook. It uses
mocked S3 clients and an in-memory `AssetService` repository/provider; it does not
load staging credentials or contact B2, a CDN, Supabase, an API, or a worker.
Run it from the repository root:

```bash
uv run python scripts/storage/run_group_17_4_checklist.py
```

The runner must report these local checks as `LOCAL-MOCK-PASS`:

- signed URL selection and configured CDN preference;
- raw B2 URL rejection before delivery;
- `org_id`, `job_id`, and `content_type` metadata;
- unique immutable tenant/talent/job key structure and filename sanitisation;
- a synthetic payload of exactly `104857601` bytes selecting multipart without allocating or uploading a real object;
- multipart part failure causing abort and no completion;
- Org A/B foreign read/list isolation at the service boundary;
- soft-delete and pending-deletion persistence before any provider delete;
- bounded pending-deletion worker processing after the soft delete; and
- local temporary-fixture cleanup plus direct request-path deletion refusal.

The runner also prints these non-promotable results as
`STAGING-REQUIRED/BLOCKED`, with prerequisite errors: live B2/CDN delivery and
metadata, a real >100 MiB object and provider-side multipart abort, staging API
Org A/B isolation, deletion-worker evidence, and staging rollback/cleanup. An
empty prerequisite environment intentionally reports every required secret-manager
variable (`ENVIRONMENT`, staging API/B2/database values, both staging tokens, and
approval ID) as missing. It also refuses a non-`staging` environment or matching
staging/production bucket/database identity. No staging result may be inferred from
the local green checks.

Expected local command result:

```text
Group 17.4 local checklist
[LOCAL-MOCK-PASS] ...
[STAGING-REQUIRED/BLOCKED] ...
No live B2/CDN/API/database/worker calls were attempted.
```

A non-zero exit means a local mocked check failed. A zero exit means only that the
local preparation checks passed; it does not change the acceptance status above.
