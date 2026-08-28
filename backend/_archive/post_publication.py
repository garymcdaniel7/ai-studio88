"""Post-Publication Actions — Story 129.

Governed actions on already-published content: correction, replacement,
archive, unpublish, takedown, and deletion. Local state NEVER claims
external removal without verified provider confirmation.

Actions:
    CORRECT     — Edit/update existing post (if provider supports)
    REPLACE     — Delete + re-publish with new content
    ARCHIVE     — Hide from feeds (provider-dependent)
    UNPUBLISH   — Remove from public view (soft)
    TAKEDOWN    — Legal/policy removal request
    DELETE      — Permanent removal from provider

Action States:
    REQUESTED   → Action initiated
    EXECUTING   → Provider call in flight
    CONFIRMED   → Provider confirmed the action
    FAILED      → Provider rejected or error occurred
    UNSUPPORTED → Provider does not support this action
    RECONCILING → Outcome unknown, needs verification
    TOMBSTONE   → Historical record preserved after confirmed deletion

Invariants:
1. Local DB never claims external deletion without provider confirmation
2. Unsupported actions are labeled truthfully (not faked)
3. Each action references exact remote object (receipt_id from publication)
4. Required audit lineage preserved as tombstone even after deletion
5. Partial destination outcomes tracked independently
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Action Types
# =============================================================================


class PostPubAction(StrEnum):
    CORRECT = "correct"
    REPLACE = "replace"
    ARCHIVE = "archive"
    UNPUBLISH = "unpublish"
    TAKEDOWN = "takedown"
    DELETE = "delete"


class ActionState(StrEnum):
    REQUESTED = "requested"
    EXECUTING = "executing"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    RECONCILING = "reconciling"
    TOMBSTONE = "tombstone"

    @property
    def is_terminal(self) -> bool:
        return self in (
            ActionState.CONFIRMED, ActionState.FAILED,
            ActionState.UNSUPPORTED, ActionState.TOMBSTONE,
        )


# =============================================================================
# Provider Capability
# =============================================================================

# What each provider supports (DECISION-REQUIRED for full matrix)
PROVIDER_CAPABILITIES: dict[str, set[PostPubAction]] = {
    "instagram": {PostPubAction.DELETE},
    "tiktok": {PostPubAction.DELETE},
    "youtube": {PostPubAction.CORRECT, PostPubAction.DELETE, PostPubAction.UNPUBLISH},
    "twitter": {PostPubAction.DELETE},
    "facebook": {PostPubAction.CORRECT, PostPubAction.DELETE, PostPubAction.ARCHIVE},
    # UNVERIFIED providers get empty set (all actions unsupported until confirmed)
}


def is_action_supported(platform: str, action: PostPubAction) -> bool:
    """Check if a platform supports a specific post-publication action."""
    caps = PROVIDER_CAPABILITIES.get(platform, set())
    return action in caps


# =============================================================================
# Action Record
# =============================================================================


@dataclass
class PostPublicationAction:
    """A governed post-publication action record."""

    # Identity
    action_id: str = field(default_factory=lambda: f"ppa-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""

    # What published content this affects
    publish_job_id: str = ""        # Original publishing job
    provider_receipt_id: str = ""   # Remote object identifier
    platform: str = ""
    destination_id: str = ""

    # Action
    action_type: PostPubAction = PostPubAction.DELETE
    state: ActionState = ActionState.REQUESTED
    reason: str = ""                # Why this action is being taken

    # Provider interaction
    provider_confirmation_id: str = ""  # Provider's confirmation of the action
    provider_response: str = ""         # Sanitized response (no secrets)
    error_message: str = ""

    # Governance
    approval_id: str | None = None      # If action requires approval
    credential_valid: bool = True

    # Timing
    requested_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    executed_at: str | None = None
    confirmed_at: str | None = None

    # Tombstone (preserved after deletion for audit)
    tombstone_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "org_id": self.org_id,
            "action_type": self.action_type.value,
            "state": self.state.value,
            "platform": self.platform,
            "provider_receipt_id": self.provider_receipt_id,
            "provider_confirmation_id": self.provider_confirmation_id,
            "reason": self.reason,
            "error_message": self.error_message,
            "requested_at": self.requested_at,
            "confirmed_at": self.confirmed_at,
        }


# =============================================================================
# Errors
# =============================================================================


class PostPubError(Exception):
    def __init__(self, message: str, code: str = "POST_PUB_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class UnsupportedActionError(PostPubError):
    def __init__(self, platform: str, action: PostPubAction):
        super().__init__(
            f"Platform '{platform}' does not support '{action.value}' action",
            code="UNSUPPORTED_ACTION",
        )


class ConfirmationRequiredError(PostPubError):
    def __init__(self):
        super().__init__(
            "Cannot mark action complete without provider confirmation",
            code="CONFIRMATION_REQUIRED",
        )


class CredentialRequiredError(PostPubError):
    def __init__(self, platform: str):
        super().__init__(
            f"Valid credential required for {platform} post-publication action",
            code="CREDENTIAL_REQUIRED",
        )


# =============================================================================
# Store
# =============================================================================

_action_store: dict[str, PostPublicationAction] = {}


def clear_store() -> None:
    _action_store.clear()


def get_action(action_id: str) -> PostPublicationAction | None:
    return _action_store.get(action_id)


# =============================================================================
# Request Action
# =============================================================================


def request_action(
    *,
    org_id: str,
    user_id: str,
    publish_job_id: str,
    provider_receipt_id: str,
    platform: str,
    destination_id: str,
    action_type: PostPubAction,
    reason: str,
    credential_valid: bool = True,
    approval_id: str | None = None,
) -> PostPublicationAction:
    """Request a post-publication action.

    Checks:
    1. Platform supports the action (or marks UNSUPPORTED)
    2. Credential is valid
    3. Original receipt exists (remote object reference)
    """
    # Credential check
    if not credential_valid:
        raise CredentialRequiredError(platform)

    # Receipt reference required
    if not provider_receipt_id:
        raise PostPubError(
            "Cannot act on content without original provider_receipt_id",
            code="NO_RECEIPT",
        )

    action = PostPublicationAction(
        org_id=org_id,
        user_id=user_id,
        publish_job_id=publish_job_id,
        provider_receipt_id=provider_receipt_id,
        platform=platform,
        destination_id=destination_id,
        action_type=action_type,
        reason=reason,
        credential_valid=credential_valid,
        approval_id=approval_id,
    )

    # Check provider support
    if not is_action_supported(platform, action_type):
        action.state = ActionState.UNSUPPORTED
        action.error_message = f"Platform '{platform}' does not support '{action_type.value}'"
        _action_store[action.action_id] = action
        return action

    action.state = ActionState.REQUESTED
    _action_store[action.action_id] = action
    return action


# =============================================================================
# Execution
# =============================================================================


def start_execution(action_id: str) -> PostPublicationAction | None:
    """Mark action as executing (provider call in flight)."""
    action = _action_store.get(action_id)
    if not action or action.state != ActionState.REQUESTED:
        return action
    action.state = ActionState.EXECUTING
    action.executed_at = datetime.now(UTC).isoformat()
    return action


def confirm_action(
    action_id: str,
    *,
    provider_confirmation_id: str,
    provider_response: str = "",
) -> PostPublicationAction:
    """Confirm the action was completed by the provider.

    Confirmation ID is REQUIRED — local DB never claims external action without it.
    """
    action = _action_store.get(action_id)
    if not action:
        raise PostPubError(f"Action {action_id} not found")

    if action.state == ActionState.CONFIRMED:
        return action  # Idempotent

    if not provider_confirmation_id:
        raise ConfirmationRequiredError()

    action.state = ActionState.CONFIRMED
    action.provider_confirmation_id = provider_confirmation_id
    action.provider_response = provider_response
    action.confirmed_at = datetime.now(UTC).isoformat()

    # If deletion confirmed, create tombstone
    if action.action_type in (PostPubAction.DELETE, PostPubAction.TAKEDOWN):
        action.tombstone_data = {
            "original_receipt_id": action.provider_receipt_id,
            "platform": action.platform,
            "deleted_at": action.confirmed_at,
            "reason": action.reason,
            "confirmation_id": provider_confirmation_id,
        }
        action.state = ActionState.TOMBSTONE

    return action


def fail_action(action_id: str, *, error: str) -> PostPublicationAction | None:
    """Record action failure."""
    action = _action_store.get(action_id)
    if not action or action.state.is_terminal:
        return action
    action.state = ActionState.FAILED
    action.error_message = error
    return action


def mark_reconciling(action_id: str) -> PostPublicationAction | None:
    """Mark action as needing reconciliation (provider outcome unknown)."""
    action = _action_store.get(action_id)
    if not action or action.state.is_terminal:
        return action
    action.state = ActionState.RECONCILING
    return action


# =============================================================================
# Already-Missing Handling
# =============================================================================


def handle_already_missing(action_id: str) -> PostPublicationAction | None:
    """Handle case where remote content is already gone.

    Marks as CONFIRMED with note — the desired outcome is achieved.
    """
    action = _action_store.get(action_id)
    if not action:
        return None

    action.state = ActionState.CONFIRMED
    action.provider_confirmation_id = "already_missing"
    action.provider_response = "Content was already removed from platform"
    action.confirmed_at = datetime.now(UTC).isoformat()

    if action.action_type in (PostPubAction.DELETE, PostPubAction.TAKEDOWN):
        action.tombstone_data = {
            "original_receipt_id": action.provider_receipt_id,
            "platform": action.platform,
            "deleted_at": action.confirmed_at,
            "reason": f"{action.reason} (already missing)",
            "confirmation_id": "already_missing",
        }
        action.state = ActionState.TOMBSTONE

    return action


# =============================================================================
# Queries
# =============================================================================


def get_actions_for_content(
    publish_job_id: str,
    org_id: str,
) -> list[PostPublicationAction]:
    """Get all post-publication actions for a published content (tenant-scoped)."""
    return [
        a for a in _action_store.values()
        if a.publish_job_id == publish_job_id and a.org_id == org_id
    ]


def get_tombstones(org_id: str) -> list[PostPublicationAction]:
    """Get all tombstone records for an org."""
    return [
        a for a in _action_store.values()
        if a.state == ActionState.TOMBSTONE and a.org_id == org_id
    ]
