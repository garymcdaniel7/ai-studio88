"""Execution Platform — Workers, providers, GPU status, and job routing."""
import streamlit as st
import requests
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Execution Platform", page_icon="🖥️", layout="wide")
st.title("🖥️ Execution Platform")
st.markdown("*Workers, providers, GPU discovery, and job routing.*")
st.markdown("---")

# ── System Health ─────────────────────────────────────────────────────────────
st.subheader("System Health")
try:
    resp = requests.get(f"{API}/api/v1/execution/health", timeout=5)
    if resp.ok:
        h = resp.json()
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Workers", h["total_workers"])
        col2.metric("Online", h["online"])
        col3.metric("Busy", h["busy"])
        col4.metric("Offline", h["offline"])
        col5.metric("VRAM Free", f"{h['free_vram_gb']:.0f} GB")

        if h["healthy"]:
            st.success("System healthy")
        else:
            st.error("No workers available!")

        if h.get("newly_offline"):
            st.warning(f"Workers went offline: {', '.join(h['newly_offline'])}")
except Exception as e:
    st.error(f"Cannot reach execution platform: {e}")

# ── Workers ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Workers")

try:
    resp = requests.get(f"{API}/api/v1/execution/workers", timeout=5)
    if resp.ok:
        workers = resp.json()
        if not workers:
            st.info("No workers registered.")
        for w in workers:
            status_icon = {"online": "🟢", "busy": "🟡", "offline": "🔴", "error": "❌"}.get(w["status"], "❓")
            gpu = w.get("gpu", {})

            with st.container():
                col1, col2, col3, col4 = st.columns([2, 3, 2, 1])
                col1.markdown(f"{status_icon} **{w['name']}**")
                col2.markdown(f"`{w['provider']}` | {gpu.get('model', '?')} | VRAM: {gpu.get('vram_free_gb', 0):.0f}/{gpu.get('vram_total_gb', 0):.0f} GB")
                col3.markdown(f"CUDA {gpu.get('cuda_version', '?')} | {gpu.get('temperature_c', 0)}°C | {gpu.get('utilization_pct', 0)}%")
                col4.markdown(f"{'🔵 Job' if w.get('current_job') else '⚪ Idle'}")

                with st.expander(f"Details: {w['name']}"):
                    st.json(w)
except Exception as e:
    st.error(f"Worker list error: {e}")

# ── Providers ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Execution Providers")

try:
    resp = requests.get(f"{API}/api/v1/execution/providers", timeout=5)
    if resp.ok:
        providers = resp.json()
        for p in providers:
            health_icon = "🟢" if p["healthy"] else "⚪"
            st.markdown(
                f"{health_icon} **{p['name']}** ({p['type']}) — "
                f"Status: `{p['status']}` | Models: {', '.join(p.get('supported_models', [])[:4])}"
            )
except Exception as e:
    st.error(f"Provider list error: {e}")

# ── Job Routing Test ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Job Routing Test")

with st.form("route_test"):
    col1, col2, col3 = st.columns(3)
    job_type = col1.selectbox("Job Type", ["image", "video", "training", "audio", "editing"])
    model = col2.text_input("Model", value="flux-dev")
    priority = col3.slider("Priority", 1, 10, 5)
    submitted = st.form_submit_button("Route Job")

if submitted:
    try:
        resp = requests.post(f"{API}/api/v1/execution/route", json={
            "type": job_type, "model": model, "priority": priority,
        }, timeout=5)
        if resp.ok:
            d = resp.json()
            st.success(f"Routed to: **{d['worker_name']}** ({d['provider']}) — {d['reason']}")
            if d["estimated_wait_seconds"] > 0:
                st.info(f"Estimated wait: {d['estimated_wait_seconds']}s")
        else:
            st.error(f"Routing failed: {resp.json().get('detail', resp.text)}")
    except Exception as e:
        st.error(f"Error: {e}")

# ── Register Worker ───────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("Register New Worker"):
    with st.form("register_worker"):
        w_name = st.text_input("Worker Name", placeholder="gpu-server-1")
        w_provider = st.selectbox("Provider", ["local", "comfyui", "vast_ai", "runpod", "shadow_pc"])
        w_url = st.text_input("URL", placeholder="http://192.168.1.100:8188")
        w_vram = st.number_input("VRAM (GB)", 0.0, 80.0, 24.0)
        reg_submit = st.form_submit_button("Register")

    if reg_submit and w_name:
        try:
            resp = requests.post(f"{API}/api/v1/execution/workers/register", json={
                "name": w_name, "provider": w_provider, "url": w_url,
                "gpu": {"model": "User GPU", "vram_total_gb": w_vram, "vram_free_gb": w_vram * 0.85},
            }, timeout=5)
            if resp.ok:
                st.success(f"Registered: {resp.json().get('worker_id')}")
                st.rerun()
            else:
                st.error(resp.json().get("detail", "Failed"))
        except Exception as e:
            st.error(f"Error: {e}")
