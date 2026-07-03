"""Generation — Monitor generation engine, queue, and GPU status."""
import streamlit as st
import requests
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
from dashboard.api_client import list_jobs, list_assets

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Generation", page_icon="🎨", layout="wide")
st.title("🎨 Generation Engine")
st.markdown("---")

# ── Provider Health + GPU Status ──────────────────────────────────────────────
st.subheader("Provider Status")

try:
    resp = requests.get(f"{API}/api/v1/generation/health", timeout=5)
    if resp.ok:
        health = resp.json()
        col1, col2, col3 = st.columns(3)

        with col1:
            status_icon = "🟢" if health["healthy"] else "🔴"
            st.markdown(f"{status_icon} **Provider:** {health['provider']}")
            st.caption(health["message"])

        gpu = health.get("gpu", {})
        with col2:
            st.markdown(f"**GPU:** {gpu.get('name', '?')}")
            st.markdown(f"VRAM: {gpu.get('vram_free_gb', 0):.1f} / {gpu.get('vram_total_gb', 0):.1f} GB free")
            st.progress(min(gpu.get("utilization_pct", 0) / 100, 1.0))

        with col3:
            st.markdown(f"**Status:** {gpu.get('status', '?')}")
            st.markdown(f"Queue: {gpu.get('queue_size', 0)} jobs")
            if gpu.get("current_job"):
                st.markdown(f"Running: `{gpu['current_job']}`")
    else:
        st.error(f"Health check failed: {resp.status_code}")
except Exception as e:
    st.error(f"Cannot reach generation engine: {e}")

# ── Available Providers ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Providers")

try:
    resp = requests.get(f"{API}/api/v1/generation/providers", timeout=5)
    if resp.ok:
        providers = resp.json()
        for p in providers:
            default_badge = " ⭐" if p.get("is_default") else ""
            st.markdown(
                f"**{p['name']}**{default_badge} — "
                f"Image: {'✅' if p['supports_image'] else '❌'} | "
                f"Video: {'✅' if p['supports_video'] else '❌'} | "
                f"Upscale: {'✅' if p['supports_upscale'] else '❌'} | "
                f"Max res: {p['max_resolution']}px"
            )
except Exception:
    pass

# ── Model Registry ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Model Registry")

try:
    resp = requests.get(f"{API}/api/v1/generation/models", timeout=5)
    if resp.ok:
        models = resp.json()
        for m in models:
            st.markdown(
                f"**{m['name']}** (`{m['id']}`) — "
                f"Type: {m['type']} | VRAM: {m['required_vram_gb']}GB | "
                f"Status: {m['status']}"
            )
except Exception:
    pass

# ── Quick Generate ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Quick Generate")

with st.form("quick_gen"):
    prompt = st.text_input("Prompt", placeholder="luxury portrait, golden hour, cinematic")
    neg = st.text_input("Negative Prompt", value="blurry, low quality, deformed")
    col1, col2, col3 = st.columns(3)
    steps = col1.number_input("Steps", 1, 50, 5)
    width = col2.number_input("Width", 512, 2048, 1024, step=256)
    height = col3.number_input("Height", 512, 2048, 1024, step=256)
    submitted = st.form_submit_button("Generate")

if submitted and prompt:
    with st.spinner("Generating..."):
        try:
            resp = requests.post(f"{API}/api/v1/generation/run", json={
                "prompt": prompt,
                "negative_prompt": neg,
                "steps": steps,
                "width": width,
                "height": height,
            }, timeout=120)
            if resp.ok:
                result = resp.json()
                st.success(f"Done! Job: {result.get('job_id', '?')[:8]}... | Provider: {result.get('provider')}")
                asset = result.get("asset", {})
                if asset:
                    st.markdown(f"Asset: **{asset.get('original_filename')}** ({asset.get('size_bytes', 0)} bytes)")
                with st.expander("Full result"):
                    st.json(result)
            else:
                st.error(f"Failed: {resp.json().get('detail', resp.text)}")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Recent Generation Jobs ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Recent Generation Jobs")

try:
    jobs = list_jobs(job_type="image_generation")
    if not jobs:
        jobs = list_jobs()
    for j in jobs[:10]:
        icon = {"queued": "🕐", "running": "🔄", "completed": "✅", "failed": "❌"}.get(j["status"], "❓")
        st.markdown(f"{icon} **{j['type']}** — {j['status']} | P{j.get('priority', 5)} | {j.get('created_at', '')[:19]}")
except Exception:
    st.info("No generation jobs yet.")
