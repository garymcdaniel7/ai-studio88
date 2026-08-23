"""Supabase Auth entry points for the web application's Google sign-in flow.

The browser completes the PKCE code exchange in the frontend callback route,
which owns the Supabase SSR session cookies. This router provides backend
entry points and a compatibility callback/logout proxy without handling
browser sessions or exposing service-role credentials.
"""

from __future__ import annotations

from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from backend.app.core.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

_ALLOWED_CALLBACK_PARAMS = (
    "code",
    "error",
    "error_code",
    "error_description",
    "state",
)


def _validated_next(next_path: str | None) -> str:
    """Validate a post-login path and reject external redirect targets."""
    if not next_path:
        return "/"

    parsed = urlsplit(next_path)
    if (
        not next_path.startswith("/")
        or next_path.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "next must be a relative application path",
                "code": "INVALID_REDIRECT_TARGET",
            },
        )
    return next_path


def _frontend_origin(settings: Settings) -> str:
    """Return the explicitly configured frontend origin for auth redirects."""
    value = settings.auth_frontend_url.strip().rstrip("/")
    if not value:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "AUTH_FRONTEND_URL is not configured",
                "code": "AUTH_CONFIGURATION_MISSING",
            },
        )

    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "message": "AUTH_FRONTEND_URL must be an origin",
                "code": "AUTH_CONFIGURATION_INVALID",
            },
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _frontend_callback_url(settings: Settings, next_path: str) -> str:
    """Build the frontend callback URL used after Supabase completes OAuth."""
    callback_url = f"{_frontend_origin(settings)}/auth/callback"
    if next_path != "/":
        callback_url = f"{callback_url}?{urlencode({'next': next_path})}"
    return callback_url


def _require_supabase_auth(settings: Settings) -> None:
    """Ensure the public Supabase Auth configuration is available."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Supabase Auth is not configured",
                "code": "AUTH_CONFIGURATION_MISSING",
            },
        )


def _google_authorize_url(next_path: str | None) -> str:
    """Build Supabase's Google authorization URL."""
    settings = get_settings()
    _require_supabase_auth(settings)
    safe_next = _validated_next(next_path)
    query = {
        "provider": "google",
        "redirect_to": _frontend_callback_url(settings, safe_next),
    }
    return f"{settings.supabase_url.rstrip('/')}/auth/v1/authorize?{urlencode(query)}"


@router.get("/google", name="auth_google")
def google_login(next: str | None = None) -> RedirectResponse:
    """Redirect the browser to Supabase Auth's Google provider."""
    return RedirectResponse(_google_authorize_url(next))


@router.get("/login", name="auth_login")
def login(next: str | None = None) -> RedirectResponse:
    """Compatibility alias for the Google login entry point."""
    return google_login(next)


@router.get("/callback", name="auth_callback")
def callback(
    code: str | None = None,
    next: str | None = None,
    error: str | None = None,
    error_code: str | None = None,
    error_description: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Forward an OAuth callback to the frontend's canonical code exchanger.

    Supabase normally redirects directly to the frontend callback. This route
    remains available for deployments configured with the backend callback.
    """
    settings = get_settings()
    params: dict[str, str] = {}
    values = {
        "code": code,
        "error": error,
        "error_code": error_code,
        "error_description": error_description,
        "state": state,
    }
    for key in _ALLOWED_CALLBACK_PARAMS:
        value = values[key]
        if value:
            params[key] = value
    if next:
        params["next"] = _validated_next(next)

    target = f"{_frontend_origin(settings)}/auth/callback"
    if params:
        target = f"{target}?{urlencode(params)}"
    return RedirectResponse(target)


@router.api_route("/logout", methods=["GET", "POST"], name="auth_logout")
def logout() -> RedirectResponse:
    """Redirect to the frontend route that clears the Supabase session cookies."""
    settings = get_settings()
    return RedirectResponse(f"{_frontend_origin(settings)}/auth/logout")
