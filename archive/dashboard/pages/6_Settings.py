"""Settings — Connection status and configuration."""
import os
import streamlit as st
import requests
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")
st.markdown("---")

# ── API Connection ────────────────────────────────────────────────────────────
st.subheader("API Connection")

api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
st.text(f"API Base URL: {api_url}")

try:
    resp = requests.get(f"{api_url}/", timeout=5)
    if resp.ok:
        st.success(f"FastAPI: Connected ({resp.json().get('status', '?')})")
    else:
        st.error(f"FastAPI: HTTP {resp.status_code}")
except Exception as e:
    st.error(f"FastAPI: Not reachable — {e}")

# ── Supabase Connection ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Supabase")

supabase_url = os.getenv("SUPABASE_URL", "")
if supabase_url:
    # Mask the URL to show project ref only
    project_ref = supabase_url.replace("https://", "").split(".")[0]
    st.text(f"Project: {project_ref}")
    st.text(f"URL: {supabase_url}")

    # Test connection by hitting the API projects endpoint
    try:
        resp = requests.get(f"{api_url}/projects", timeout=5)
        if resp.ok:
            data = resp.json()
            st.success(f"Supabase: Connected ({len(data)} project(s) found)")
        else:
            st.warning(f"Supabase: API returned {resp.status_code}")
    except Exception as e:
        st.error(f"Supabase: Connection test failed — {e}")
else:
    st.warning("SUPABASE_URL not configured in .env")

# Show key status (never show actual values)
srk = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
st.text(f"Service Role Key: {'✓ Set' if srk and srk != 'your-service-role-key' else '✗ Missing'}")
jwt = os.getenv("SUPABASE_JWT_SECRET", "")
st.text(f"JWT Secret: {'✓ Set' if jwt else '✗ Missing'}")

# ── Backblaze B2 Connection ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("Backblaze B2 Storage")

b2_endpoint = os.getenv("B2_ENDPOINT_URL", "")
b2_bucket = os.getenv("B2_BUCKET_NAME", "")
b2_key = os.getenv("B2_KEY_ID", "")

st.text(f"Endpoint: {b2_endpoint or '✗ Not set'}")
st.text(f"Bucket: {b2_bucket or '✗ Not set'}")
st.text(f"Key ID: {'✓ Set' if b2_key else '✗ Missing'}")
st.text(f"App Key: {'✓ Set' if os.getenv('B2_APPLICATION_KEY', '') else '✗ Missing'}")

# Test B2 by trying to list assets
try:
    resp = requests.get(f"{api_url}/api/v1/assets", timeout=5)
    if resp.ok:
        st.success(f"B2: Accessible via API ({len(resp.json())} assets)")
    else:
        st.warning(f"B2: API returned {resp.status_code}")
except Exception as e:
    st.error(f"B2: Test failed — {e}")

# ── Environment Info ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Environment")

st.text(f"APP_ENV: {os.getenv('APP_ENV', 'not set')}")
st.text(f"DEBUG: {os.getenv('DEBUG', 'not set')}")
st.text(f"API_PORT: {os.getenv('API_PORT', '8000')}")

# ── Feature Flags ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Feature Flags")

flags = {
    "Video Generation": os.getenv("FEATURE_VIDEO_GENERATION", "false"),
    "Voice Generation": os.getenv("FEATURE_VOICE_GENERATION", "false"),
    "LoRA Training": os.getenv("FEATURE_LORA_TRAINING", "false"),
    "Analytics": os.getenv("FEATURE_ANALYTICS", "false"),
}

for flag, value in flags.items():
    icon = "✅" if value.lower() == "true" else "⬜"
    st.text(f"{icon} {flag}: {value}")
