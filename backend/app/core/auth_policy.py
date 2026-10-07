"""Authoritative HTTP authentication policy for the backend.

The policy owns the public route matrix, CORS preflight exemption, and the
local-only development fallback. Middleware and route dependencies must use
this policy rather than interpreting authentication environment variables
independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from app.core.logging import get_logger
except ModuleNotFoundError:
    from backend.app.core.logging import get_logger

# Exact public paths. Prefix matching is intentionally not permitted: near
# matches such as /healthz and /auth/callback/extra remain protected.
PUBLIC_PROBE_ALLOWLIST = frozenset(
    {
        "/",
        "/login",
        "/pricing",
        "/health",
        "/ready",
        "/ready/capabilities",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
        "/auth/google",
        "/auth/login",
        "/auth/callback",
        "/auth/logout",
        "/api/v1/health",
        "/api/v1/capabilities",
        "/api/v1/generate/chain-health",
    }
)

PUBLIC_METHOD_ALLOWLIST = frozenset({"OPTIONS"})
_PROTECTED_ENVIRONMENTS = frozenset({"staging", "production"})
_LOCAL_ENVIRONMENTS = frozenset({"local", "test", "development"})
AUTH_ENFORCEMENT_FLIP_ENV = "AUTH_ENFORCEMENT_FLIP"

logger = get_logger(__name__)


def _setting_bool(settings: Any, name: str, default: bool = False) -> bool:
    """Read a boolean setting without treating test doubles as truthy."""
    value = getattr(settings, name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


@dataclass(frozen=True)
class AuthPolicy:
    """Evaluate the single backend authentication policy for one request."""

    app_env: str
    auth_required: bool
    auth_dev_mode: bool
    enforcement_flip: bool = False
    dark_launch: bool = False

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        auth_dev_mode_override: bool | None = None,
    ) -> AuthPolicy:
        """Build a policy from validated application settings.

        ``auth_dev_mode_override`` exists only for compatibility with the
        legacy unit-test seam that monkeypatches ``backend.auth``. The policy
        still applies the same environment and fail-closed rules.
        """
        return cls(
            app_env=str(getattr(settings, "app_env", "local")).lower(),
            auth_required=_setting_bool(settings, "auth_required"),
            auth_dev_mode=(
                bool(auth_dev_mode_override)
                if auth_dev_mode_override is not None
                else _setting_bool(settings, "auth_dev_mode")
            ),
            enforcement_flip=_setting_bool(settings, "auth_enforcement_flip"),
            dark_launch=_setting_bool(settings, "auth_dark_launch"),
        )

    def is_public(self, path: str, method: str) -> bool:
        """Return whether a request is exempt from bearer authentication.

        Path matching is exact. ``OPTIONS`` is the only method exemption and is
        intended for a valid CORS preflight handled by the outer CORS layer.
        """
        return method.upper() in PUBLIC_METHOD_ALLOWLIST or path in PUBLIC_PROBE_ALLOWLIST

    def telemetry(self, *, outcome: str, path: str, method: str, request_id: str) -> None:
        """Emit non-sensitive rollout telemetry for one policy decision."""
        logger.info(
            "auth_policy_decision",
            outcome=outcome,
            path=path,
            method=method,
            request_id=request_id,
            app_env=self.app_env,
            dark_launch=self.dark_launch,
            enforcing=self.enforces_authentication,
        )

    @property
    def allows_dev_fallback(self) -> bool:
        """Return whether the approved local/test fallback may be attempted."""
        return self.auth_dev_mode and self.app_env in _LOCAL_ENVIRONMENTS

    @property
    def observes_only(self) -> bool:
        """Return whether controlled dark launch should observe without rejecting."""
        return self.dark_launch and self.app_env in _LOCAL_ENVIRONMENTS and not self.enforcement_flip

    @property
    def enforces_authentication(self) -> bool:
        """Return whether protected requests require a bearer token."""
        # Production and staging always fail closed, regardless of a stale or
        # permissive flag. Local/test can opt into the approved fallback, but
        # never become anonymous merely because AUTH_REQUIRED is false.
        if self.app_env in _PROTECTED_ENVIRONMENTS:
            return True
        if self.observes_only:
            return False
        return not self.allows_dev_fallback

    def validate_startup(self) -> None:
        """Reject a protected deployment whose authoritative state is unsafe."""
        if self.app_env in _PROTECTED_ENVIRONMENTS and not self.auth_required:
            raise RuntimeError(
                "AUTH_REQUIRED=true is required in staging/production for the "
                "authoritative authentication policy"
            )
        if self.app_env in _PROTECTED_ENVIRONMENTS and not self.enforcement_flip:
            raise RuntimeError(
                f"{AUTH_ENFORCEMENT_FLIP_ENV}=true is required before staging/production startup"
            )
        if self.app_env in _PROTECTED_ENVIRONMENTS and self.auth_dev_mode:
            raise RuntimeError("AUTH_DEV_MODE=true is not permitted in staging/production")
        if self.app_env in _PROTECTED_ENVIRONMENTS and self.dark_launch:
            raise RuntimeError("AUTH_DARK_LAUNCH=true is not permitted in staging/production")


def get_auth_policy(settings: Any, *, auth_dev_mode_override: bool | None = None) -> AuthPolicy:
    """Return the authoritative policy for the supplied settings object."""
    policy = AuthPolicy.from_settings(
        settings,
        auth_dev_mode_override=auth_dev_mode_override,
    )
    policy.validate_startup()
    return policy
