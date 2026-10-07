"""Production Studio — plan, produce, and assemble content."""
import streamlit as st
import requests
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Production Studio", page_icon="🎥", layout="wide")
st.title("🎥 Production Studio")
st.markdown("*Plan and produce content through automated media pipelines.*")
st.markdown("---")

# ── Create Production ─────────────────────────────────────────────────────────
st.subheader("Create Production")

try:
    types_resp = requests.get(f"{API}/api/v1/production/types", timeout=5)
    prod_types = types_resp.json() if types_resp.ok else ["reel", "tiktok", "portrait"]
except Exception:
    prod_types = ["reel", "tiktok", "portrait", "commercial", "fashion_campaign"]

col1, col2 = st.columns(2)
prod_type = col1.selectbox("Production Type", prod_types)
prompt = col2.text_input("Concept", placeholder="luxury rooftop editorial, golden hour")

if st.button("📋 Plan Production") and prompt:
    try:
        resp = requests.post(f"{API}/api/v1/production/plan", json={
            "type": prod_type, "parameters": {"prompt": prompt},
        }, timeout=10)
        if resp.ok:
            plan = resp.json()
            st.success(f"Pipeline: {plan['total_steps']} steps | "
                       f"~{plan['estimated_minutes']} min | ${plan['estimated_cost_usd']}")

            st.markdown("**Production Graph:**")
            for node in plan["graph"]:
                icon = {"generation": "🎨", "voice": "🎙️", "music": "🎵", "editing": "✂️"}.get(node["type"], "⚙️")
                st.markdown(f"  {icon} {node['name']} (`{node['provider']}`)")

            with st.expander("Full Production Plan"):
                st.json(plan)
        else:
            st.error(resp.json().get("detail", "Failed"))
    except Exception as e:
        st.error(f"Error: {e}")

# ── Pipeline Templates ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Pipeline Templates")

try:
    resp = requests.get(f"{API}/api/v1/production/templates", timeout=5)
    if resp.ok:
        templates = resp.json()
        for name, info in templates.items():
            st.markdown(f"**{name}** — {info['steps']} steps: {' → '.join(info['nodes'][:5])}")
except Exception:
    pass

# ── Voice Library ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🎙️ Voice Library")

try:
    resp = requests.get(f"{API}/api/v1/production/voices", timeout=5)
    if resp.ok:
        voices = resp.json()
        for v in voices:
            st.markdown(f"  🗣️ **{v['name']}** — {v['emotion']} | {v['accent']} | {v['style']} | `{v['provider']}`")
except Exception:
    pass

# ── Music Library ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🎵 Music Library")

try:
    resp = requests.get(f"{API}/api/v1/production/music", timeout=5)
    if resp.ok:
        music = resp.json()
        for m in music:
            st.markdown(f"  🎶 **{m['title']}** — {m['mood']} | {m['genre']} | {m['tempo_bpm']} BPM | {m['energy']}")
except Exception:
    pass

# ── Camera System ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📷 Camera System")

col1, col2, col3 = st.columns(3)
try:
    moves = requests.get(f"{API}/api/v1/production/camera/moves", timeout=5).json()
    col1.markdown("**Camera Moves**")
    col1.write(moves[:10])
except Exception:
    pass

try:
    sizes = requests.get(f"{API}/api/v1/production/camera/sizes", timeout=5).json()
    col2.markdown("**Shot Sizes**")
    col2.write(sizes)
except Exception:
    pass

try:
    ops = requests.get(f"{API}/api/v1/production/editing/operations", timeout=5).json()
    col3.markdown("**Edit Operations**")
    col3.write(ops[:10])
except Exception:
    pass
