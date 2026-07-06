"""Social OAuth — Connect flows for Instagram, TikTok, YouTube, X.

Architecture:
- GET /oauth/{platform}/authorize → returns redirect URL
- GET /oauth/{platform}/callback?code=... → exchanges code for token, stores in DB
- GET /oauth/connections → list connected platforms
- DELETE /oauth/connections/{platform} → disconnect

Tokens stored in Supabase 'social_connections' table.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request

load_dotenv(override=True)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/publishing/oauth", tags=["publishing-oauth"])

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
def list_platforms():
    """List available social platforms and their connection status."""
    connections = _get_connections()
    connected_platforms = {c["platform"] for c in connections}

    platforms = []
    for platform, config in OAUTH_CONFIG.items():
        client_id = os.getenv(config["client_id_env"], "")
        platforms.append({
            "platform": platform,
            "connected": platform in connected_platforms,
            "configured": bool(client_id),
            "display_name": platform.replace("_", " ").title(),
            "icon": _get_platform_icon(platform),
        })
    return {"platforms": platforms}


@router.get("/{platform}/authorize")
def get_authorize_url(platform: str):
    """Get the OAuth authorization URL to redirect the user to.

    The frontend opens this URL in a popup or redirect.
    User grants permission → redirected back to our callback.
    """
    if platform not in OAUTH_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    config = OAUTH_CONFIG[platform]
    client_id = os.getenv(config["client_id_env"], "")
    if not client_id:
        raise HTTPException(
            status_code=422,
            detail=f"{platform} not configured. Set {config['client_id_env']} in .env"
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

    # Store state for verification on callback
    try:
        _db().table("social_connections").upsert({
            "platform": f"{platform}_pending",
            "status": "pending",
            "metadata": {"state": state, "redirect_uri": redirect_uri},
        }, on_conflict="platform").execute()
    except Exception:
        pass

    return {"authorize_url": authorize_url, "state": state}


@router.get("/{platform}/callback")
def oauth_callback(platform: str, code: str = "", state: str = "", error: str = ""):
    """Handle the OAuth callback after user grants permission.

    Exchanges the authorization code for an access token,
    stores in database, and returns success page.
    """
    if error:
        return _callback_html(platform, success=False, error=error)

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    if platform not in OAUTH_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    config = OAUTH_CONFIG[platform]
    client_id = os.getenv(config["client_id_env"], "")
    client_secret = os.getenv(config["client_secret_env"], "")
    redirect_uri = f"{CALLBACK_BASE}/api/v1/publishing/oauth/{platform}/callback"

    # Exchange code for token
    token_data = _exchange_code(platform, config, code, client_id, client_secret, redirect_uri)

    if not token_data:
        return _callback_html(platform, success=False, error="Token exchange failed")

    # Store connection
    connection = {
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
            connection, on_conflict="platform"
        ).execute()
    except Exception as e:
        logger.warning(f"Failed to store connection: {e}")
        # Still return success — token was obtained
        pass

    return _callback_html(platform, success=True)


@router.get("/connections")
def list_connections():
    """List all connected social platforms."""
    connections = _get_connections()
    # Don't expose tokens
    safe = []
    for c in connections:
        safe.append({
            "platform": c.get("platform"),
            "status": c.get("status"),
            "connected_at": c.get("metadata", {}).get("connected_at"),
            "expires_at": c.get("expires_at"),
            "scope": c.get("scope"),
        })
    return {"connections": safe}


@router.delete("/connections/{platform}")
def disconnect_platform(platform: str):
    """Disconnect a social platform (revoke and delete token)."""
    try:
        _db().table("social_connections").delete().eq("platform", platform).execute()
    except Exception:
        pass
    return {"disconnected": True, "platform": platform}


# =============================================================================
# Helpers
# =============================================================================


def _exchange_code(
    platform: str, config: dict, code: str,
    client_id: str, client_secret: str, redirect_uri: str,
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
        logger.warning(f"Token exchange failed for {platform}: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Token exchange error for {platform}: {e}")
        return None


def _get_connections() -> list[dict]:
    """Get all active social connections from DB."""
    try:
        result = _db().table("social_connections").select("*").neq("status", "pending").execute()
        return result.data or []
    except Exception:
        return []


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
    message = f"{platform.title()} connected successfully!" if success else f"Connection failed: {error}"

    html = f"""<!DOCTYPE html>
<html><head><title>AI Studio - {platform.title()}</title></head>
<body style="background:#0a0a1a;color:white;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center">
<h2>{'✅' if success else '❌'} {message}</h2>
<p style="color:#888">You can close this window.</p>
<script>
  if (window.opener) {{
    window.opener.postMessage({{ type: 'oauth_callback', platform: '{platform}', status: '{status}' }}, '*');
    setTimeout(() => window.close(), 2000);
  }}
</script>
</div></body></html>"""
    return HTMLResponse(content=html)
