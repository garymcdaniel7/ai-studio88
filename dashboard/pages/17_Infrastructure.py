"""Infrastructure — GPU Workers, Service Connections, and Cost Dashboard.

Live control panel for:
- Worker launch/stop (Connection Race Mode)
- Real-time worker status and GPU info
- Service connection health
- Model cache inventory
- Cost tracking
- Fleet management
"""
import os
import time
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Infrastructure", page_icon="🖥️", layout="wide")
st.title("🖥️ Infrastructure Control")

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def api_get(path: str) -> dict | list | None:
    """GET from the backend API."""
    try:
        resp = requests.get(f"{API_URL}{path}", timeout=15)
        return resp.json() if resp.ok else None
    except Exception:
        return None


def api_post(path: str, data: dict = None) -> dict | None:
    """POST to the backend API."""
    try:
        resp = requests.post(f"{API_URL}{path}", json=data or {}, timeout=30)
        return resp.json() if resp.ok else {"error": resp.text[:200]}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# Service Connections
# =============================================================================

st.markdown("## Service Connections")

services = api_get("/api/v1/infrastructure/admin/services")
if services:
    summary = services.get("summary", {})
    cols = st.columns(4)
    cols[0].metric("Total Services", summary.get("total_services", 0))
    cols[1].metric("Connected", summary.get("connected", 0))
    cols[2].metric("Disconnected", summary.get("disconnected", 0))
    cols[3].metric("Health", summary.get("health", "unknown"))

    st.markdown("---")

    for name, info in services.get("services", {}).items():
        connected = info.get("connected", False)
        icon = "🟢" if connected else "🔴"
        ms = info.get("response_ms", 0)

        with st.expander(f"{icon} {name.replace('_', ' ').title()} ({ms:.0f}ms)", expanded=False):
            if connected:
                # Show relevant details per service
                if name == "vast_ai":
                    st.write(f"**User:** {info.get('username', '?')}")
                    st.write(f"**Balance:** ${info.get('balance', 0):.2f}")
                elif name == "backblaze_b2":
                    st.write(f"**Bucket:** {info.get('bucket', '?')}")
                elif name == "supabase":
                    st.write(f"**URL:** {info.get('url', '?')}")
                elif name == "huggingface":
                    st.write(f"**User:** {info.get('username', '?')}")
                elif name == "model_cache":
                    st.write(f"**Cached:** {info.get('cached_models', 0)} models ({info.get('total_cached_gb', 0)} GB)")
                    files = info.get("files", [])
                    if files:
                        for f in files:
                            st.write(f"  • {f}")
                elif name == "comfyui":
                    st.write(f"**Version:** {info.get('version', '?')}")
                    st.write(f"**GPU:** {info.get('gpu', '?')}")
                    st.write(f"**VRAM:** {info.get('vram_gb', 0)} GB")
            else:
                st.error(info.get("error", "Not connected"))
else:
    st.error("Cannot reach backend API. Is the server running?")


# =============================================================================
# GPU Worker
# =============================================================================

st.markdown("---")
st.markdown("## GPU Worker")

status = api_get("/api/v1/infrastructure/status")
if status:
    worker = status.get("worker", {})
    worker_status = worker.get("status", "no_session")

    # Status indicator
    status_colors = {
        "no_session": "⚪",
        "connecting": "🟡",
        "booting": "🟡",
        "installing": "🟡",
        "downloading_model": "🟡",
        "starting_comfyui": "🟡",
        "ready": "🟢",
        "generating": "🔵",
        "error": "🔴",
    }
    icon = status_colors.get(worker_status, "⚪")

    cols = st.columns(4)
    cols[0].metric("Status", f"{icon} {worker_status}")
    cols[1].metric("GPU", worker.get("gpu_name") or "—")
    cols[2].metric("Uptime", f"{worker.get('uptime_seconds', 0) / 60:.1f} min")
    cols[3].metric("Cost", f"${worker.get('current_cost', 0):.4f}")

    if worker_status == "ready":
        st.success(f"Worker online: {worker.get('gpu_name')} @ {worker.get('ssh_host')}:{worker.get('ssh_port')}")

    # Launch / Stop buttons
    col1, col2 = st.columns(2)

    with col1:
        if worker_status == "no_session":
            with st.form("launch_form"):
                st.markdown("**Launch Worker**")
                max_price = st.slider("Max $/hr", 0.10, 3.00, 1.50, 0.10)
                min_vram = st.selectbox("Min VRAM", [12, 24, 40, 48, 80], index=1)
                candidates = st.slider("Race candidates", 1, 5, 3)
                submitted = st.form_submit_button("🚀 Launch Worker")
                if submitted:
                    with st.spinner("Launching via Connection Race Mode..."):
                        result = api_post("/api/v1/infrastructure/launch", {
                            "max_price": max_price,
                            "min_vram_gb": min_vram,
                            "num_candidates": candidates,
                        })
                        if result and result.get("status") == "success":
                            st.success(f"Worker launched! Boot time: {result.get('boot_time_seconds', 0):.0f}s")
                            st.rerun()
                        else:
                            st.error(f"Launch failed: {result.get('error', 'Unknown error')}")

    with col2:
        if worker_status not in ("no_session", "error"):
            if st.button("🛑 Stop Worker", type="primary"):
                result = api_post("/api/v1/infrastructure/stop")
                if result and result.get("status") == "stopped":
                    st.success("Worker stopped and destroyed.")
                    st.rerun()
                else:
                    st.error(f"Stop failed: {result}")

    # Connection metrics
    connection = status.get("connection", {})
    if connection.get("total_attempts_lifetime", 0) > 0:
        st.markdown("---")
        st.markdown("### Connection History")
        cols = st.columns(4)
        cols[0].metric("Total Attempts", connection.get("total_attempts_lifetime", 0))
        cols[1].metric("Success Rate", f"{connection.get('success_rate', 0) * 100:.0f}%")
        cols[2].metric("Last Boot", f"{connection.get('last_boot_time_seconds') or 0:.0f}s")
        cols[3].metric("Race Candidates", connection.get("candidates_launched", 0))


# =============================================================================
# Cost Tracking
# =============================================================================

st.markdown("---")
st.markdown("## Cost Tracking")

cost_data = api_get("/api/v1/infrastructure/cost")
if cost_data:
    budget = cost_data.get("budget", {})
    daily = budget.get("daily", {})
    monthly = budget.get("monthly", {})

    cols = st.columns(4)
    cols[0].metric("Today", f"${daily.get('spent', 0):.2f}", f"of ${daily.get('budget', 10):.0f} budget")
    cols[1].metric("This Month", f"${monthly.get('spent', 0):.2f}", f"of ${monthly.get('budget', 200):.0f} budget")
    cols[2].metric("Current Rate", f"${cost_data.get('current', {}).get('hourly_rate', 0):.2f}/hr")
    cols[3].metric("Budget Status", "✅ OK" if budget.get("within_budget") else "⚠️ Over")

    # Cost breakdown
    breakdown = cost_data.get("breakdown", {})
    if breakdown.get("total_sessions", 0) > 0:
        st.markdown("### Breakdown")
        cols = st.columns(3)
        cols[0].write(f"**Total sessions:** {breakdown.get('total_sessions')}")
        cols[1].write(f"**Total hours:** {breakdown.get('total_duration_hours', 0):.1f}")
        cols[2].write(f"**Avg session:** ${breakdown.get('average_session_cost', 0):.3f}")


# =============================================================================
# Model Cache
# =============================================================================

st.markdown("---")
st.markdown("## Model Cache")

models = status.get("models", {}) if status else {}
cached = models.get("cached_in_b2", [])
if cached:
    for model in cached:
        st.write(f"✅ {model}")
else:
    st.info("No models cached in B2. Run `python scripts/vast/upload_model.py --known sdxl-turbo` to seed.")


# =============================================================================
# Render Fleet
# =============================================================================

st.markdown("---")
st.markdown("## Render Fleet")

fleet = api_get("/api/v1/infrastructure/fleet")
if fleet:
    cols = st.columns(4)
    cols[0].metric("Fleet Size", fleet.get("fleet_size", 0))
    cols[1].metric("Available", fleet.get("available_workers", 0))
    cols[2].metric("Queue", fleet.get("queued_jobs", 0))
    cols[3].metric("Fleet Cost", f"${fleet.get('total_running_cost', 0):.3f}")

    workers = fleet.get("workers", [])
    if workers:
        for w in workers:
            icon = "🟢" if w["status"] == "ready" else ("🔵" if w["status"] == "busy" else "🟡")
            st.write(f"{icon} **{w['name']}** — {w['gpu_name']} | ${w['hourly_rate']:.2f}/hr | {w['jobs_completed']} jobs")
    else:
        st.info("No fleet workers running. Add workers via the fleet API.")
