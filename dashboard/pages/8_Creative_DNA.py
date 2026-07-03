"""Creative DNA — View and manage learned talent preferences."""
import streamlit as st
import sys
sys.path.insert(0, ".")
from dashboard.api_client import list_talent

import requests
import os
from dotenv import load_dotenv
load_dotenv()

API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Creative DNA", page_icon="🧬", layout="wide")
st.title("🧬 Creative DNA")
st.markdown("*Learned preferences that improve future generations per talent.*")
st.markdown("---")

try:
    talent_list = list_talent()
    talent_map = {t["name"]: t["id"] for t in talent_list}
except Exception:
    talent_list = []
    talent_map = {}

# ── Select talent ─────────────────────────────────────────────────────────────
selected = st.selectbox("Select Talent", ["Select..."] + list(talent_map.keys()))

if selected != "Select...":
    talent_id = talent_map[selected]

    # Try to load existing DNA
    try:
        resp = requests.get(f"{API}/api/v1/creative-dna/{talent_id}")
        if resp.ok:
            dna = resp.json()
            st.success(f"Creative DNA loaded for {selected}")
        else:
            dna = None
            st.info(f"No Creative DNA yet for {selected}. Create one below.")
    except Exception:
        dna = None

    # ── View existing DNA ─────────────────────────────────────────────────────
    if dna:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Preferred Styles**")
            st.write(dna.get("preferred_styles", []))
            st.markdown("**Color Palette**")
            st.write(dna.get("color_palette", []))
            st.markdown("**Camera Preferences**")
            st.json(dna.get("camera_preferences", {}))
        with col2:
            st.markdown("**Avoided Styles**")
            st.write(dna.get("avoided_styles", []))
            st.markdown("**Prompt Rules**")
            st.write(dna.get("prompt_rules", []))
            st.markdown("**Negative Prompt Rules**")
            st.write(dna.get("negative_prompt_rules", []))

        with st.expander("Full Creative DNA JSON"):
            st.json(dna)

    # ── Create/Update DNA ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Edit Creative DNA")

    with st.form("dna_form"):
        preferred = st.text_input("Preferred Styles (comma-sep)", value=", ".join(dna.get("preferred_styles", [])) if dna else "")
        avoided = st.text_input("Avoided Styles (comma-sep)", value=", ".join(dna.get("avoided_styles", [])) if dna else "")
        colors = st.text_input("Color Palette (comma-sep)", value=", ".join(dna.get("color_palette", [])) if dna else "")
        prompt_rules = st.text_input("Prompt Rules (comma-sep phrases to always include)", value=", ".join(dna.get("prompt_rules", [])) if dna else "")
        neg_rules = st.text_input("Negative Prompt Rules (comma-sep phrases to always avoid)", value=", ".join(dna.get("negative_prompt_rules", [])) if dna else "")
        notes = st.text_area("Notes", value=dna.get("notes", "") if dna else "")

        submitted = st.form_submit_button("Save Creative DNA")

    if submitted:
        payload = {
            "talent_id": talent_id,
            "preferred_styles": [s.strip() for s in preferred.split(",") if s.strip()],
            "avoided_styles": [s.strip() for s in avoided.split(",") if s.strip()],
            "color_palette": [s.strip() for s in colors.split(",") if s.strip()],
            "prompt_rules": [s.strip() for s in prompt_rules.split(",") if s.strip()],
            "negative_prompt_rules": [s.strip() for s in neg_rules.split(",") if s.strip()],
            "notes": notes,
        }
        try:
            if dna:
                resp = requests.put(f"{API}/api/v1/creative-dna/{dna['id']}", json=payload)
            else:
                resp = requests.post(f"{API}/api/v1/creative-dna", json=payload)
            if resp.ok:
                st.success("Creative DNA saved!")
                st.rerun()
            else:
                st.error(f"Failed: {resp.text}")
        except Exception as e:
            st.error(f"Error: {e}")

    # ── Recent Feedback ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Recent Feedback")
    try:
        resp = requests.get(f"{API}/api/v1/feedback", params={"talent_id": talent_id})
        if resp.ok:
            feedback = resp.json()
            if feedback:
                for fb in feedback[:10]:
                    stars = "⭐" * fb.get("rating", 0)
                    problems = fb.get("problems", [])
                    prob_str = f" — Issues: {', '.join(problems)}" if problems else ""
                    st.markdown(f"{stars}{prob_str}")
                    if fb.get("notes"):
                        st.caption(fb["notes"])
            else:
                st.info("No feedback yet for this talent.")
    except Exception:
        st.info("Feedback not available.")

except Exception as e:
    st.error(f"Error: {e}")
