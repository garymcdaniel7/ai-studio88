"""Session-provider boundary for the legacy Streamlit dashboard transport."""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Protocol


class AuthenticationRequiredError(RuntimeError):
    """Raised when a dashboard request cannot establish an authenticated session."""


class SessionProvider(Protocol):
    """Boundary used by the client to obtain and refresh the current session."""

    def get_access_token(self) -> str | None:
        """Return the current access token without reading unsafe browser storage."""

    def refresh_access_token(self) -> Any:
        """Refresh the session and return a token or session-like value."""

    def clear_session(self) -> None:
        """Clear the invalid session."""

    def redirect_to_login(self) -> None:
        """Start the approved login flow without recursively issuing requests."""


def extract_access_token(value: Any) -> str | None:
    """Extract a non-empty access token from a provider result."""
    if value is None:
        return None
    if isinstance(value, str):
        token = value.strip()
        return token or None
    if isinstance(value, Mapping):
        return extract_access_token(value.get("access_token"))
    token = getattr(value, "access_token", None)
    return token.strip() if isinstance(token, str) and token.strip() else None


class _StreamlitSessionProvider:
    """Read session state only through Streamlit's server-side session API."""

    def _state(self) -> Any:
        try:
            import streamlit as st

            return st.session_state
        except Exception:
            return None

    def get_access_token(self) -> str | None:
        """Return the token stored by the dashboard's authenticated session."""
        state = self._state()
        if state is None:
            return None
        token = extract_access_token(state.get("access_token"))
        return token or extract_access_token(state.get("session"))

    def refresh_access_token(self) -> Any:
        """Invoke the session refresh callback, when the dashboard provides one."""
        state = self._state()
        refresh = state.get("refresh_access_token") if state is not None else None
        return refresh() if callable(refresh) else None

    def clear_session(self) -> None:
        """Remove the current access token and session object from Streamlit state."""
        state = self._state()
        if state is not None:
            state.pop("access_token", None)
            state.pop("session", None)

    def redirect_to_login(self) -> None:
        """Mark login as required or invoke the dashboard-provided login callback."""
        state = self._state()
        if state is None or state.get("auth_redirected"):
            return
        state["auth_redirected"] = True
        redirect = state.get("redirect_to_login")
        if callable(redirect):
            redirect()
        else:
            # Streamlit has no shared browser login route yet; this marker lets
            # the legacy surface render its login action without a retry loop.
            state["auth_required"] = True


_session_provider: SessionProvider | None = None


def set_session_provider(provider: SessionProvider | None) -> None:
    """Set the session provider used by requests, primarily for app wiring/tests."""
    global _session_provider
    _session_provider = provider


def get_session_provider() -> SessionProvider:
    """Return the configured provider or the Streamlit server-side provider."""
    return _session_provider or _StreamlitSessionProvider()


def get_current_session_token() -> str | None:
    """Return the current access token from the approved session provider."""
    return extract_access_token(get_session_provider().get_access_token())


def finish_authentication(provider: SessionProvider) -> None:
    """Clear the failed session and trigger login exactly once."""
    try:
        provider.clear_session()
    finally:
        with suppress(Exception):
            provider.redirect_to_login()
