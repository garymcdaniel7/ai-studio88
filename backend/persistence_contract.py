"""Persistence Boundary Contract — Story 043.

Defines which entities are server-authoritative vs allowed in browser storage.
This is the canonical reference for ALL persistence decisions in AI Studio.

Principle: Server is truth. Browser is cache.

Server-Authoritative Entities (Supabase):
    These MUST be persisted server-side. Browser copies are read-through
    cache only — stale local data is never authoritative.

    - Sessions (aios_sessions): conversation containers
    - Messages (aios_messages): conversation content
    - Collections (brain_collections): conversation groupings
    - Conversations (brain_conversations): conversation metadata
    - Plans (brain_plans): execution plans
    - Memory (brain_memory): learned preferences
    - Embeddings (brain_embeddings): RAG vectors
    - Approvals (durable_approvals): governance decisions
    - Commands (action_commands): durable action state

Browser-Allowed Storage (localStorage):
    These may live in localStorage as the primary store because they are:
    - Non-sensitive UI preferences
    - Disposable (loss is inconvenient, not data loss)
    - User-specific display state (not workspace-shared)

    ALLOWED keys:
    - talent_favorites: UI sort preference (list of IDs)
    - favorite_prompts: saved prompt snippets (convenience)
    - theme_preference: dark/light mode
    - sidebar_collapsed: UI layout state
    - last_mode: most recently used Brain mode

    CACHE-ONLY keys (server is truth, local is read-through cache):
    - brain_sessions_cache: optimistic display while server loads
    - brain_messages_draft_{sessionId}: unsent message draft
    - brain_collections_cache: optimistic display while server loads

    PROHIBITED keys (must never be in browser storage):
    - Access tokens (managed by Supabase SDK cookie, not localStorage)
    - Refresh tokens
    - API keys or credentials
    - Workspace/org membership data used for authorization
    - Execution results, job outputs, or asset data
    - Other users' data

Reconciliation Rules:
    1. Server always wins for authoritative entities
    2. Local cache includes `_cached_at` timestamp
    3. On page load: show cache immediately (optimistic), fetch server, replace
    4. If server version is newer: discard local, update display
    5. If local has unsent draft: preserve draft, do NOT overwrite with server
    6. Multi-tab: no localStorage events for authoritative state (server is sync point)
    7. Login/logout: clear ALL brain_* cache keys (prevent cross-user leakage)
    8. Storage quota failure: degrade gracefully (server still works)

Migration Rules (for existing localStorage data):
    1. On first load after upgrade: check for legacy `brain_sessions` key
    2. If found AND server has no sessions: offer one-time migration prompt
    3. If found AND server HAS sessions: discard local (server is truth)
    4. After migration/discard: delete legacy keys
    5. `brain_messages_{id}` keys: delete on session load (server messages are truth)
    6. Never silently lose data — show migration notice if local-only data exists
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Storage Authority Classification
# =============================================================================


class StorageAuthority(str, Enum):
    """Who owns the truth for an entity."""

    SERVER = "server"              # Supabase is authoritative
    BROWSER_PREFERENCE = "browser_preference"  # localStorage is primary (non-critical)
    BROWSER_CACHE = "browser_cache"  # localStorage is read-through cache of server
    BROWSER_DRAFT = "browser_draft"  # Temporary unsent content (migrates to server on send)
    PROHIBITED = "prohibited"      # Must NEVER be in browser storage


@dataclass(frozen=True)
class StorageEntry:
    """Classification of a single storage key or entity."""

    key_pattern: str
    authority: StorageAuthority
    description: str
    sensitive: bool = False
    max_age_seconds: int = 0  # 0 = no expiry for preferences, >0 = cache TTL
    clear_on_logout: bool = True


# =============================================================================
# Complete Storage Map
# =============================================================================

STORAGE_MAP: list[StorageEntry] = [
    # Server-authoritative (these keys should NOT exist in localStorage long-term)
    StorageEntry("brain_sessions", StorageAuthority.BROWSER_CACHE,
                 "Session list cache — server is truth", max_age_seconds=300,
                 clear_on_logout=True),
    StorageEntry("brain_collections", StorageAuthority.BROWSER_CACHE,
                 "Collections cache — server is truth", max_age_seconds=300,
                 clear_on_logout=True),
    StorageEntry("brain_messages_*", StorageAuthority.BROWSER_CACHE,
                 "Message cache per session — server is truth", max_age_seconds=600,
                 clear_on_logout=True),

    # Browser preferences (primary in localStorage — non-critical)
    StorageEntry("talent_favorites", StorageAuthority.BROWSER_PREFERENCE,
                 "Talent sort order preference", clear_on_logout=False),
    StorageEntry("favorite_prompts", StorageAuthority.BROWSER_PREFERENCE,
                 "Saved prompt snippets", clear_on_logout=False),
    StorageEntry("theme_preference", StorageAuthority.BROWSER_PREFERENCE,
                 "Dark/light mode", clear_on_logout=False),
    StorageEntry("sidebar_collapsed", StorageAuthority.BROWSER_PREFERENCE,
                 "UI layout state", clear_on_logout=False),
    StorageEntry("last_mode", StorageAuthority.BROWSER_PREFERENCE,
                 "Most recently used Brain mode", clear_on_logout=True),

    # Drafts (temporary, migrate to server on send)
    StorageEntry("brain_draft_*", StorageAuthority.BROWSER_DRAFT,
                 "Unsent message draft", max_age_seconds=86400,  # 24h
                 clear_on_logout=True),

    # Prohibited (must never appear)
    StorageEntry("access_token", StorageAuthority.PROHIBITED,
                 "Auth tokens must not be in readable localStorage", sensitive=True),
    StorageEntry("refresh_token", StorageAuthority.PROHIBITED,
                 "Refresh tokens must not be in readable localStorage", sensitive=True),
    StorageEntry("api_key", StorageAuthority.PROHIBITED,
                 "API keys must never be in browser storage", sensitive=True),
    StorageEntry("ai_studio_session", StorageAuthority.PROHIBITED,
                 "Legacy auth cookie pattern — removed in Story 006", sensitive=True),
    StorageEntry("org_id", StorageAuthority.PROHIBITED,
                 "Workspace identity must come from server, not localStorage", sensitive=True),
]


def get_storage_authority(key: str) -> StorageAuthority:
    """Determine the authority classification for a localStorage key.

    Keys matching wildcard patterns (brain_messages_*) are matched by prefix.
    Unknown keys default to PROHIBITED (deny-by-default).
    """
    for entry in STORAGE_MAP:
        if entry.key_pattern.endswith("*"):
            prefix = entry.key_pattern[:-1]
            if key.startswith(prefix):
                return entry.authority
        elif entry.key_pattern == key:
            return entry.authority

    # Unknown key — deny by default
    return StorageAuthority.PROHIBITED


def is_key_allowed(key: str) -> bool:
    """Check if a localStorage key is permitted by the contract."""
    authority = get_storage_authority(key)
    return authority != StorageAuthority.PROHIBITED


def get_keys_to_clear_on_logout() -> list[str]:
    """Get key patterns that must be cleared on logout."""
    return [
        entry.key_pattern for entry in STORAGE_MAP
        if entry.clear_on_logout
    ]


# =============================================================================
# Cache Metadata
# =============================================================================


@dataclass
class CacheRecord:
    """Wrapper for cached data with freshness metadata."""

    key: str
    data: Any
    cached_at: str  # ISO timestamp
    server_version: str = ""  # Optional server version/etag for comparison
    is_stale: bool = False

    def to_storage(self) -> dict:
        """Serialize for localStorage."""
        return {
            "_authority": "cache",
            "_cached_at": self.cached_at,
            "_server_version": self.server_version,
            "data": self.data,
        }

    @staticmethod
    def from_storage(key: str, raw: dict) -> "CacheRecord | None":
        """Deserialize from localStorage. Returns None if invalid."""
        if not isinstance(raw, dict) or "_authority" not in raw:
            return None
        return CacheRecord(
            key=key,
            data=raw.get("data"),
            cached_at=raw.get("_cached_at", ""),
            server_version=raw.get("_server_version", ""),
        )


# =============================================================================
# Reconciliation
# =============================================================================


class ReconciliationAction(str, Enum):
    """What to do when local and server state differ."""

    USE_SERVER = "use_server"           # Server wins (default for authoritative)
    USE_LOCAL = "use_local"             # Local wins (drafts only)
    MERGE = "merge"                     # Combine (not implemented — UNVERIFIED)
    MIGRATE_TO_SERVER = "migrate_to_server"  # One-time upload of local-only data
    DISCARD_LOCAL = "discard_local"     # Delete local, use server


def determine_reconciliation(
    *,
    key: str,
    has_local: bool,
    has_server: bool,
    local_newer: bool = False,
    is_draft: bool = False,
) -> ReconciliationAction:
    """Determine reconciliation action for a storage conflict.

    Rules:
    1. Drafts: local wins (preserve unsent work)
    2. Server has data + local has data: server wins
    3. Server has NO data + local has data: offer migration
    4. Server has data + local has NO data: use server
    5. Neither has data: no action needed
    """
    authority = get_storage_authority(key)

    # Drafts always stay local until explicitly sent
    if is_draft or authority == StorageAuthority.BROWSER_DRAFT:
        return ReconciliationAction.USE_LOCAL

    # Preferences stay local (they ARE the primary)
    if authority == StorageAuthority.BROWSER_PREFERENCE:
        return ReconciliationAction.USE_LOCAL

    # Cache/server-authoritative entities:
    if has_server and has_local:
        return ReconciliationAction.USE_SERVER  # Server always wins

    if has_server and not has_local:
        return ReconciliationAction.USE_SERVER

    if not has_server and has_local:
        return ReconciliationAction.MIGRATE_TO_SERVER  # Offer migration

    return ReconciliationAction.DISCARD_LOCAL  # Neither — clean slate


# =============================================================================
# Security Validation
# =============================================================================


def validate_no_secrets_in_storage(storage_keys: list[str]) -> list[str]:
    """Check a list of localStorage keys for prohibited entries.

    Returns list of violations (keys that should not exist).
    """
    violations = []
    for key in storage_keys:
        if get_storage_authority(key) == StorageAuthority.PROHIBITED:
            violations.append(key)
    return violations
