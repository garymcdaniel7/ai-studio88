"""Story Engine — Universes, characters, episodes, scenes, and shots."""
import streamlit as st
import requests
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Story Engine", page_icon="🎬", layout="wide")
st.title("🎬 Story Engine")
st.markdown("*Think in narratives: universes, characters, episodes, scenes, shots.*")
st.markdown("---")

# ── Create Universe ───────────────────────────────────────────────────────────
with st.expander("Create New Universe", expanded=False):
    with st.form("create_universe"):
        u_name = st.text_input("Universe Name", placeholder="e.g. Luxury Lives")
        u_desc = st.text_area("Description", placeholder="The world these characters inhabit")
        u_genre = st.text_input("Genre", placeholder="e.g. Luxury Lifestyle, Drama, Travel")
        u_tone = st.text_input("Tone", placeholder="e.g. Aspirational, Cinematic, Glamorous")
        submitted = st.form_submit_button("Create Universe")
    if submitted and u_name:
        resp = requests.post(f"{API}/api/v1/universes", json={
            "name": u_name, "description": u_desc, "genre": u_genre, "tone": u_tone,
        })
        if resp.ok:
            st.success(f"Universe created: {resp.json().get('id', '?')[:8]}...")
            st.rerun()
        else:
            st.error(resp.json().get("detail", "Failed"))

# ── List Universes ────────────────────────────────────────────────────────────
st.subheader("Universes")
try:
    resp = requests.get(f"{API}/api/v1/universes", timeout=5)
    universes = resp.json() if resp.ok else []
except Exception:
    universes = []

if not universes:
    st.info("No universes yet. Create one above.")
else:
    for u in universes:
        with st.expander(f"🌍 {u['name']} — {u.get('genre', '')}"):
            st.markdown(f"*{u.get('description', '')}*")
            st.markdown(f"Tone: {u.get('tone', '?')} | Genre: {u.get('genre', '?')}")

            # Characters
            st.markdown("---")
            st.markdown("**Characters**")
            try:
                chars = requests.get(f"{API}/api/v1/universes/{u['id']}/characters", timeout=5).json()
                for c in chars:
                    st.markdown(f"  👤 **{c['name']}** — {c.get('personality', '')[:60]}")
            except Exception:
                st.caption("No characters yet")

            # Add character
            with st.form(f"add_char_{u['id']}"):
                c_name = st.text_input("Character Name", key=f"cn_{u['id']}")
                c_desc = st.text_input("Description", key=f"cd_{u['id']}")
                c_personality = st.text_input("Personality", key=f"cp_{u['id']}")
                if st.form_submit_button("Add Character"):
                    requests.post(f"{API}/api/v1/characters", json={
                        "universe_id": u["id"], "name": c_name,
                        "description": c_desc, "personality": c_personality,
                    })
                    st.rerun()

            # Episodes
            st.markdown("---")
            st.markdown("**Episodes**")
            try:
                eps = requests.get(f"{API}/api/v1/universes/{u['id']}/episodes", timeout=5).json()
                for ep in eps:
                    st.markdown(f"  📺 Ep {ep.get('episode_number', '?')}: **{ep['title']}** [{ep.get('status', '?')}]")
            except Exception:
                st.caption("No episodes yet")

            # Add episode
            with st.form(f"add_ep_{u['id']}"):
                ep_title = st.text_input("Episode Title", key=f"et_{u['id']}")
                ep_num = st.number_input("Episode #", 1, 100, 1, key=f"en_{u['id']}")
                if st.form_submit_button("Add Episode"):
                    requests.post(f"{API}/api/v1/episodes", json={
                        "universe_id": u["id"], "title": ep_title, "episode_number": ep_num,
                    })
                    st.rerun()

            # Memory
            st.markdown("---")
            st.markdown("**Story Memory**")
            try:
                mem = requests.get(f"{API}/api/v1/universes/{u['id']}/memory", timeout=5).json()
                for m in mem[:5]:
                    st.markdown(f"  📝 [{m.get('category', '?')}] {m.get('event', '')}")
            except Exception:
                st.caption("No story memories yet")

            with st.form(f"add_mem_{u['id']}"):
                mem_event = st.text_input("Event", key=f"me_{u['id']}", placeholder="e.g. Melissa bought a yacht")
                mem_cat = st.selectbox("Category", ["event", "relationship", "possession", "location", "injury", "death"], key=f"mc_{u['id']}")
                if st.form_submit_button("Record Event"):
                    requests.post(f"{API}/api/v1/memory", json={
                        "universe_id": u["id"], "event": mem_event, "category": mem_cat,
                    })
                    st.rerun()
