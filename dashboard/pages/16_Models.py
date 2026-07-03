"""Models & Templates — manage AI models, LoRAs, and workflow templates."""
import streamlit as st
import requests
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Models & Templates", page_icon="🧩", layout="wide")
st.title("🧩 Models & Workflow Templates")
st.markdown("*Central registry for AI models, LoRAs, and ComfyUI workflows.*")
st.markdown("---")

# ── Models ────────────────────────────────────────────────────────────────────
st.subheader("AI Models")

col1, col2 = st.columns(2)
type_filter = col1.selectbox("Filter by Type", ["", "checkpoint", "lora", "vae", "controlnet", "upscaler", "embedding"])
family_filter = col2.selectbox("Filter by Family", ["", "flux", "sdxl", "wan", "hunyuan", "ltx", "pony", "upscaler"])

try:
    params = {}
    if type_filter:
        params["type"] = type_filter
    if family_filter:
        params["family"] = family_filter
    resp = requests.get(f"{API}/api/v1/models", params=params, timeout=5)
    models = resp.json() if resp.ok else []

    if models:
        for m in models:
            status_icon = {"available": "🟢", "downloading": "🟡", "unavailable": "🔴", "deprecated": "⚫"}.get(m.get("status"), "❓")
            st.markdown(f"{status_icon} **{m['name']}** — `{m.get('type')}` | Family: {m.get('family')} | VRAM: {m.get('required_vram_gb', '?')}GB | v{m.get('version', '?')}")
    else:
        st.info("No models registered. Run the seed SQL or add models below.")
except Exception as e:
    st.error(f"Cannot load models: {e}")

with st.expander("Register New Model"):
    with st.form("add_model"):
        m_name = st.text_input("Name", placeholder="e.g. FLUX.1-dev (fp8)")
        m_family = st.selectbox("Family", ["flux", "sdxl", "wan", "hunyuan", "ltx", "pony", "other"])
        m_type = st.selectbox("Type", ["checkpoint", "lora", "vae", "controlnet", "ipadapter", "upscaler", "embedding"])
        m_vram = st.number_input("Required VRAM (GB)", 0.0, 80.0, 12.0)
        m_path = st.text_input("Storage Path", placeholder="model_filename.safetensors")
        if st.form_submit_button("Register") and m_name:
            requests.post(f"{API}/api/v1/models", json={
                "name": m_name, "family": m_family, "type": m_type,
                "required_vram_gb": m_vram, "storage_path": m_path,
            })
            st.rerun()

# ── Workflow Templates ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Workflow Templates")

try:
    resp = requests.get(f"{API}/api/v1/workflow-templates", timeout=5)
    templates = resp.json() if resp.ok else []
    if templates:
        for t in templates:
            st.markdown(f"📋 **{t['name']}** — {t.get('category', '?')} | Provider: {t.get('provider')} | v{t.get('version', '?')}")
            if t.get("description"):
                st.caption(t["description"])
    else:
        st.info("No workflow templates registered. Run seed SQL.")
except Exception as e:
    st.error(f"Cannot load templates: {e}")

# ── Provider Capabilities ──────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Provider Capabilities")

try:
    resp = requests.get(f"{API}/api/v1/provider-capabilities", timeout=5)
    if resp.ok:
        data = resp.json()
        for p in data.get("providers", []):
            st.markdown(f"**{p['provider']}** — Image: {'✅' if p['supports_image'] else '❌'} | "
                        f"Video: {'✅' if p['supports_video'] else '❌'} | "
                        f"Upscale: {'✅' if p['supports_upscale'] else '❌'} | "
                        f"Max: {p['max_resolution']}px | Models: {', '.join(p['supported_models'][:4])}")
except Exception:
    pass

# ── Validation Test ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Generation Validation")

with st.form("validate"):
    v_model = st.text_input("Model ID", value="flux-dev")
    v_provider = st.selectbox("Provider", ["simulation", "comfyui"])
    if st.form_submit_button("Validate"):
        resp = requests.post(f"{API}/api/v1/generation/validate", json={"model": v_model, "provider": v_provider})
        if resp.ok:
            result = resp.json()
            if result["valid"]:
                st.success(f"✅ Valid: {v_model} on {v_provider}")
            else:
                st.warning(f"⚠️ Issues: {result['issues']}")
