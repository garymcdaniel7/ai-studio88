"""Property-based tests for credential scope isolation.

**Validates: Requirements R8.1, R8.5, A2-018**

Property 12: Credential Scope Isolation
- For ANY job credential issued for job_A in org_A, accessing paths belonging
  to org_B or job_B MUST raise CredentialScopeViolationError.
- This holds for ALL possible org_ids and job_ids.

Property 26: External Storage Credential Scope
- For ANY credential with allowed_paths=["/org_X/images/talent_Y/job_Z"],
  the credential NEVER grants access to paths outside that scope — including
  other orgs, other asset types, other talents, or other jobs.
- The credential ONLY grants access to paths that are children of the allowed paths.

Run with:
    pytest tests/unit/test_services/test_credential_broker_properties.py -v
"""

from __future__ import annotations

import string
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.credential_broker import (
    CredentialBroker,
    CredentialScopeViolationError,
)

# =============================================================================
# Strategies
# =============================================================================

# Strategy for generating path-safe segments (lowercase alphanumeric + _ and -)
path_segment_st = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_-",
    min_size=1,
    max_size=20,
)

# Strategy for UUIDs
uuid_st = st.uuids()

# Strategy for storage provider selection
provider_st = st.sampled_from(["b2", "s3", "r2"])


# =============================================================================
# Property 12: Credential Scope Isolation
# =============================================================================


@pytest.mark.unit
class TestCredentialScopeIsolation:
    """Property 12: Job credential never grants access to other jobs or orgs.

    **Validates: Requirements R8.1, R8.5**

    For any pair of (org_A, org_B) where org_A != org_B, a credential
    issued for org_A's path MUST reject paths starting with org_B's prefix.

    For any pair of (job_A, job_B) where job_A != job_B within the same org,
    a credential issued for job_A's path MUST reject job_B's paths.
    """

    @given(
        org_a=path_segment_st,
        org_b=path_segment_st,
        talent=path_segment_st,
        job_a=path_segment_st,
        filename=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_cross_org_access_always_rejected(
        self,
        org_a: str,
        org_b: str,
        talent: str,
        job_a: str,
        filename: str,
        provider: str,
    ) -> None:
        """A credential for org_A NEVER grants access to org_B's paths.

        **Validates: Requirements R8.1, R8.5**

        Given: credential issued with allowed_paths=["/org_A/images/talent/job_A"]
        When: accessing any path starting with "/org_B/..."
        Then: CredentialScopeViolationError is raised (org_A != org_B)
        """
        # Ensure org_a and org_b are actually different
        if org_a == org_b:
            org_b = org_b + "_other"

        broker = CredentialBroker()
        allowed_path = f"/{org_a}/images/{talent}/{job_a}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        # Attempt access to org_B's path — must be rejected
        other_org_path = f"/{org_b}/images/{talent}/{job_a}/{filename}.png"

        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, other_org_path)

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job_a=path_segment_st,
        job_b=path_segment_st,
        filename=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_cross_job_access_always_rejected(
        self,
        org: str,
        talent: str,
        job_a: str,
        job_b: str,
        filename: str,
        provider: str,
    ) -> None:
        """A credential for job_A NEVER grants access to job_B's paths.

        **Validates: Requirements R8.1, R8.5**

        Given: credential issued with allowed_paths=["/org/images/talent/job_A"]
        When: accessing path "/org/images/talent/job_B/file"
        Then: CredentialScopeViolationError is raised (job_A != job_B)
        """
        # Ensure job_a and job_b are actually different
        if job_a == job_b:
            job_b = job_b + "_other"

        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job_a}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        # Attempt access to job_B's path — must be rejected
        other_job_path = f"/{org}/images/{talent}/{job_b}/{filename}.png"

        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, other_job_path)

    @given(
        org_a_id=uuid_st,
        org_b_id=uuid_st,
        talent_id=uuid_st,
        job_id=uuid_st,
        filename=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_uuid_based_cross_org_isolation(
        self,
        org_a_id: UUID,
        org_b_id: UUID,
        talent_id: UUID,
        job_id: UUID,
        filename: str,
        provider: str,
    ) -> None:
        """Cross-org isolation holds with UUID-based path segments.

        **Validates: Requirements R8.1, R8.5**

        Real storage keys use UUIDs. This verifies isolation with realistic
        path structures like /org_abc123/images/talent_xyz/job_456/file.
        """
        # Ensure different orgs
        if org_a_id == org_b_id:
            return  # Skip trivial case — hypothesis will generate others

        broker = CredentialBroker()
        allowed_path = f"/{org_a_id}/images/{talent_id}/{job_id}"

        cred = broker.issue_job_credential(
            job_id=job_id,
            org_id=org_a_id,
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        # Attempt access to org_B's equivalent path — must be rejected
        other_org_path = f"/{org_b_id}/images/{talent_id}/{job_id}/{filename}.webp"

        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, other_org_path)

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job=path_segment_st,
        subpath=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_valid_child_path_always_granted(
        self,
        org: str,
        talent: str,
        job: str,
        subpath: str,
        provider: str,
    ) -> None:
        """Access to child paths of allowed_paths is always granted.

        **Validates: Requirements R8.1**

        Sanity check: the isolation property does not over-restrict.
        Paths that ARE within the credential's scope must succeed.
        """
        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        # Access to a valid child path — must succeed
        valid_path = f"/{org}/images/{talent}/{job}/{subpath}.png"
        result = broker.validate_access(cred.credential_id, valid_path)
        assert result is True


# =============================================================================
# Property 26: External Storage Credential Scope
# =============================================================================


@pytest.mark.unit
class TestExternalStorageCredentialScope:
    """Property 26: Customer-managed storage credential limited to job's scope.

    **Validates: Requirements R8.1, R8.5, A2-018**

    For any credential with allowed_paths=["/org_X/images/talent_Y/job_Z"],
    the credential NEVER grants access to:
    - Paths outside the org prefix ("/other_org/...")
    - Paths in same org but different asset type ("/org_X/models/...")
    - Paths in same org same type but different talent ("/org_X/images/other_talent/...")
    - Paths in same org same type same talent but different job
    """

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job=path_segment_st,
        other_org=path_segment_st,
        filename=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_rejects_different_org_prefix(
        self,
        org: str,
        talent: str,
        job: str,
        other_org: str,
        filename: str,
        provider: str,
    ) -> None:
        """Credential rejects paths outside its org prefix.

        **Validates: Requirements R8.5, A2-018**
        """
        if org == other_org:
            other_org = other_org + "_x"

        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        bad_path = f"/{other_org}/images/{talent}/{job}/{filename}.webp"
        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, bad_path)

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job=path_segment_st,
        other_asset_type=path_segment_st,
        filename=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_rejects_different_asset_type(
        self,
        org: str,
        talent: str,
        job: str,
        other_asset_type: str,
        filename: str,
        provider: str,
    ) -> None:
        """Credential rejects paths with a different asset type in the same org.

        **Validates: Requirements R8.5, A2-018**

        Given: allowed_paths=["/org/images/talent/job"]
        Then: "/org/models/talent/job/file" is rejected (different asset type)
        """
        # Ensure other_asset_type differs from "images"
        if other_asset_type == "images":
            other_asset_type = "models"

        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        bad_path = f"/{org}/{other_asset_type}/{talent}/{job}/{filename}.safetensors"
        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, bad_path)

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job=path_segment_st,
        other_talent=path_segment_st,
        filename=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_rejects_different_talent(
        self,
        org: str,
        talent: str,
        job: str,
        other_talent: str,
        filename: str,
        provider: str,
    ) -> None:
        """Credential rejects paths with a different talent in same org/type.

        **Validates: Requirements R8.5, A2-018**

        Given: allowed_paths=["/org/images/talent_Y/job"]
        Then: "/org/images/other_talent/job/file" is rejected
        """
        if talent == other_talent:
            other_talent = other_talent + "_alt"

        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        bad_path = f"/{org}/images/{other_talent}/{job}/{filename}.png"
        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, bad_path)

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job=path_segment_st,
        other_job=path_segment_st,
        filename=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_rejects_different_job_same_talent(
        self,
        org: str,
        talent: str,
        job: str,
        other_job: str,
        filename: str,
        provider: str,
    ) -> None:
        """Credential rejects paths for a different job in same org/type/talent.

        **Validates: Requirements R8.1, R8.5, A2-018**

        Given: allowed_paths=["/org/images/talent/job_Z"]
        Then: "/org/images/talent/other_job/file" is rejected
        """
        if job == other_job:
            other_job = other_job + "_diff"

        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        bad_path = f"/{org}/images/{talent}/{other_job}/{filename}.mp4"
        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, bad_path)

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job=path_segment_st,
        nested_path=st.lists(path_segment_st, min_size=1, max_size=3),
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_allows_any_child_within_scope(
        self,
        org: str,
        talent: str,
        job: str,
        nested_path: list[str],
        provider: str,
    ) -> None:
        """Credential grants access to ANY child path within its scope.

        **Validates: Requirements R8.1, A2-018**

        Given: allowed_paths=["/org/images/talent/job"]
        Then: "/org/images/talent/job/<any nested child>" is allowed.
        This ensures the scope enforcement is not overly restrictive.
        """
        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        # Build a nested child path
        child_suffix = "/".join(nested_path)
        valid_path = f"/{org}/images/{talent}/{job}/{child_suffix}"

        result = broker.validate_access(cred.credential_id, valid_path)
        assert result is True

    @given(
        org=path_segment_st,
        talent=path_segment_st,
        job=path_segment_st,
        prefix_extension=path_segment_st,
        provider=provider_st,
    )
    @settings(max_examples=100)
    def test_rejects_prefix_sharing_attack(
        self,
        org: str,
        talent: str,
        job: str,
        prefix_extension: str,
        provider: str,
    ) -> None:
        """Credential rejects paths that share a prefix but escape scope.

        **Validates: Requirements R8.5, A2-018**

        Given: allowed_paths=["/org/images/talent/job"]
        Then: "/org/images/talent/job_evil/file" is rejected.
        This verifies that prefix-matching uses path boundary (/) correctly.
        """
        broker = CredentialBroker()
        allowed_path = f"/{org}/images/{talent}/{job}"

        cred = broker.issue_job_credential(
            job_id=uuid4(),
            org_id=uuid4(),
            allowed_paths=[allowed_path],
            storage_provider=provider,
            max_timeout_seconds=1800,
        )

        # Create a path that starts with the same prefix but adds characters
        # before the next "/" — this is a prefix-sharing attack
        evil_path = f"/{org}/images/{talent}/{job}{prefix_extension}/stolen.png"

        with pytest.raises(CredentialScopeViolationError):
            broker.validate_access(cred.credential_id, evil_path)
