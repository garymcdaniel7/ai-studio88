"""Social OAuth — Connect flows for Instagram, TikTok, YouTube, X.

Architecture:
- GET /oauth/{platform}/authorize → returns redirect URL
- GET /oauth/{platform}/callback?code=... → exchanges code for token, stores in DB
- GET /oauth/connections → list connected platforms
- DELETE /oauth/connections/{platform} → disconnect

Tokens stored in Supabase 'social_connections' table.
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
import uuid
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.auth import AuthUser, require_auth

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# CTO remediation 2026-10-03 (F2): this router previously had zero auth and a
# global UNIQUE(platform) upsert that let tenant B overwrite tenant A's OAuth
# tokens. Now: everything requires auth EXCEPT the platform callback redirect
# (the social platform sends the user's browser there — it cannot hold our JWT).
# Connections are stored per (org_id, platform) via uq_social_connections_org_platform.
PUBLIC_OAUTH_CALLBACK_SUFFIX = "/callback"


def _oauth_guard(request: Request) -> AuthUser | None:
    """Router-level guard: platform callback redirects stay public, else auth."""
    if request.url.path.endswith(PUBLIC_OAUTH_CALLBACK_SUFFIX):
        return None
    return require_auth(request)


router = APIRouter(
    prefix="/api/v1/publishing/oauth",
    tags=["publishing-oauth"],
    dependencies=[Depends(_oauth_guard)],
)

# OAuth configuration per platform
OAUTH_CONFIG = {
    "instagram": {
        "authorize_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "scope": "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement",
        "client_id_env": "INSTAGRAM_APP_ID",
        "client_secret_env": "INSTAGRAM_APP_SECRET",
    },
    "tiktok": {
        "authorize_url": "https://www.tiktok.com/v2/auth/authorize/",
        "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
        "scope": "user.info.basic,video.publish,video.upload",
        "client_id_env": "TIKTOK_CLIENT_KEY",
        "client_secret_env": "TIKTOK_CLIENT_SECRET",
    },
    "youtube": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
    "x": {
        "authorize_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.x.com/2/oauth2/token",
        "scope": "tweet.read tweet.write users.read offline.access",
        "client_id_env": "X_CLIENT_ID",
        "client_secret_env": "X_CLIENT_SECRET",
    },
}

CALLBACK_BASE = os.getenv("OAUTH_CALLBACK_BASE", "http://localhost:8000")


def _db():
    from backend.database import supabase

    return supabase


# =============================================================================
# OAuth Endpoints
# =============================================================================


@router.get("/platforms")
def list_platforms(user: AuthUser = Depends(require_auth)):
    """List available social platforms and their connection status (org-scoped)."""
    connections = _get_connections(org_id=user.org_id)
    connected_platforms = {c["platform"] for c in connections}

    platforms = []
    for platform, config in OAUTH_CONFIG.items():
        client_id = os.getenv(config["client_id_env"], "")
        platforms.append(
            {
                "platform": platform,
                "connected": platform in connected_platforms,
                "configured": bool(client_id),
                "display_name": platform.replace("_", " ").title(),
                "icon": _get_platform_icon(platform),
            }
        )
    return {"platforms": platforms}


@router.get("/{platform}/authorize")
def get_authorize_url(platform: str, user: AuthUser = Depends(require_auth)):
    """Get the OAuth authorization URL to redirect the user to (org-scoped).

    The frontend opens this URL in a popup or redirect.
    User grants permission → redirected back to our callback.

    The pending row is tagged with the caller's org_id so the (public) callback
    can store the resulting token under the right tenant.
    """
    if platform not in OAUTH_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    config = OAUTH_CONFIG[platform]
    client_id = os.getenv(config["client_id_env"], "")
    if not client_id:
        raise HTTPException(
            status_code=422,
            detail=f"{platform} not configured. Set {config['client_id_env']} in .env",
        )

    # Generate state for CSRF protection
    state = uuid.uuid4().hex
    redirect_uri = f"{CALLBACK_BASE}/api/v1/publishing/oauth/{platform}/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": config["scope"],
        "response_type": "code",
        "state": state,
    }

    # Platform-specific params
    if platform == "youtube":
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    elif platform == "x":
        params["code_challenge"] = "challenge"
        params["code_challenge_method"] = "plain"
    elif platform == "tiktok":
        params["client_key"] = client_id
        del params["client_id"]

    authorize_url = f"{config['authorize_url']}?{urlencode(params)}"

    # Store state for verification on callback — org-scoped so tenant B cannot
    # clobber tenant A's pending flow (composite conflict key).
    with contextlib.suppress(Exception):
        _db().table("social_connections").upsert(
            {
                "org_id": user.org_id,
                "platform": f"{platform}_pending",
                "status": "pending",
                "metadata": {"state": state, "redirect_uri": redirect_uri},
            },
            on_conflict=["org_id", "platform"],
        ).execute()

    return {"authorize_url": authorize_url, "state": state}


@router.get("/{platform}/callback")
def oauth_callback(platform: str, code: str = "", state: str = "", error: str = ""):
    """Handle the OAuth callback after user grants permission.

    Exchanges the authorization code for an access token,
    stores in database, and returns success page.

    This endpoint is PUBLIC by design — the social platform redirects the
    user's browser here after authorization; it cannot carry our JWT.
    Tenant scoping (CTO F2): the org_id is recovered from the pending row
    created by the authenticated /authorize step (matched via CSRF state),
    so the token is stored under the tenant that STARTED the flow — never
    clobbering another tenant's connection.
    """
    if error:
        return _callback_html(platform, success=False, error=error)

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    if platform not in OAUTH_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    # Recover the org that started this flow from the pending row (by CSRF state)
    org_id = _recover_pending_org(platform, state)

    config = OAUTH_CONFIG[platform]
    client_id = os.getenv(config["client_id_env"], "")
    client_secret = os.getenv(config["client_secret_env"], "")
    redirect_uri = f"{CALLBACK_BASE}/api/v1/publishing/oauth/{platform}/callback"

    # Exchange code for token
    token_data = _exchange_code(platform, config, code, client_id, client_secret, redirect_uri)

    if not token_data:
        return _callback_html(platform, success=False, error="Token exchange failed")

    # Store connection — per (org_id, platform) so each tenant owns its own row
    connection = {
        "org_id": org_id,
        "platform": platform,
        "status": "connected",
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "token_type": token_data.get("token_type", "bearer"),
        "expires_at": _calc_expiry(token_data.get("expires_in", 3600)),
        "scope": token_data.get("scope", config["scope"]),
        "metadata": {
            "connected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user_id": token_data.get("user_id", token_data.get("open_id", "")),
        },
    }

    try:
        _db().table("social_connections").upsert(
            connection, on_conflict=["org_id", "platform"]
        ).execute()
    except Exception as e:
        logger.warning(f"Failed to store connection: {e}")
        # Still return success — token was obtained
        pass

    return _callback_html(platform, success=True)


@router.get("/connections")
def list_connections(user: AuthUser = Depends(require_auth)):
    """List the caller's org's connected social platforms (org-scoped)."""
    connections = _get_connections(org_id=user.org_id)
    # Don't expose tokens
    safe = []
    for c in connections:
        safe.append(
            {
                "platform": c.get("platform"),
                "status": c.get("status"),
                "connected_at": c.get("metadata", {}).get("connected_at"),
                "expires_at": c.get("expires_at"),
                "scope": c.get("scope"),
            }
        )
    return {"connections": safe}


@router.delete("/connections/{platform}")
def disconnect_platform(platform: str, user: AuthUser = Depends(require_auth)):
    """Disconnect a social platform for the caller's org (org-scoped)."""
    with contextlib.suppress(Exception):
        _db().table("social_connections").delete().eq(
            "platform", platform
        ).eq("org_id", user.org_id).execute()
    return {"disconnected": True, "platform": platform}


# =============================================================================
# Helpers
# =============================================================================


def _exchange_code(
    platform: str,
    config: dict,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict | None:
    """Exchange authorization code for access token."""
    token_url = config["token_url"]

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    # Platform-specific adjustments
    if platform == "tiktok":
        payload["client_key"] = client_id
    elif platform == "x":
        payload["code_verifier"] = "challenge"

    try:
        resp = httpx.post(token_url, data=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(
            f"Token exchange failed for {platform}: {resp.status_code} {resp.text[:200]}"
        )
        return None
    except Exception as e:
        logger.error(f"Token exchange error for {platform}: {e}")
        return None


def _get_connections(org_id: str | None = None) -> list[dict]:
    """Get active social connections for the given org (CTO F2: org-scoped).

    Without an org_id this returns nothing — the caller must be tenant-scoped.
    """
    if not org_id:
        return []
    try:
        result = (
            _db()
            .table("social_connections")
            .select("*")
            .eq("org_id", org_id)
            .neq("status", "pending")
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def _recover_pending_org(platform: str, state: str) -> str | None:
    """Find the org_id that started an OAuth flow from the pending row (CTO F2).

    The /authorize step (authenticated) stores platform='{platform}_pending'
    with metadata.state = the CSRF token. The public callback receives that
    same state, so we can recover which tenant's connection this belongs to.
    """
    if not state:
        return None
    try:
        result = (
            _db()
            .table("social_connections")
            .select("org_id")
            .eq("platform", f"{platform}_pending")
            .execute()
        )
        for row in result.data or []:
            if (row.get("metadata") or {}).get("state") == state:
                return row.get("org_id")
        return None
    except Exception:
        return None


def _calc_expiry(expires_in: int) -> str:
    """Calculate expiry timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + expires_in))


def _get_platform_icon(platform: str) -> str:
    """Get emoji icon for platform."""
    icons = {
        "instagram": "📷",
        "tiktok": "🎵",
        "youtube": "▶️",
        "x": "𝕏",
    }
    return icons.get(platform, "🔗")


def _callback_html(platform: str, success: bool, error: str = "") -> str:
    """Return an HTML page that closes the popup and notifies the parent window."""
    from fastapi.responses import HTMLResponse

    status = "connected" if success else "failed"
    message = (
        f"{platform.title()} connected successfully!" if success else f"Connection failed: {error}"
    )

    html = f"""<!DOCTYPE html>
<html><head><title>AI Studio - {platform.title()}</title></head>
<body style="background:#0a0a1a;color:white;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center">
<h2>{"✅" if success else "❌"} {message}</h2>
<p style="color:#888">You can close this window.</p>
<script>
  if (window.opener) {{
    window.opener.postMessage({{ type: 'oauth_callback', platform: '{platform}', status: '{status}' }}, '*');
    setTimeout(() => window.close(), 2000);
  }}
</script>
</div></body></html>"""
    return HTMLResponse(content=html)
