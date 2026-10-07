"""Intelligence Center — AI reasoning, recommendations, and learning insights."""
import streamlit as st
import requests
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
from dashboard.api_client import list_talent

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Intelligence Center", page_icon="🧠", layout="wide")
st.title("🧠 Intelligence Center")
st.markdown("*10 specialized AI agents think before generating.*")
st.markdown("---")

# ── Input ─────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

try:
    talent_list = list_talent()
    talent_map = {t["name"]: t["id"] for t in talent_list}
except Exception:
    talent_map = {}

with col1:
    selected_talent = st.selectbox("Talent", ["Select..."] + list(talent_map.keys()))
    platform = st.selectbox("Platform", ["instagram", "tiktok", "youtube", "pinterest", "website"])

with col2:
    content_type = st.selectbox("Content Type", ["image", "video", "carousel", "story", "reel", "ad"])
    campaign = st.text_input("Campaign (optional)")

user_idea = st.text_area("Creative Idea", placeholder="e.g. luxury travel reel, cinematic rooftop editorial, old money fashion...")

if st.button("🧠 Think", type="primary") and user_idea:
    talent_id = talent_map.get(selected_talent)

    with st.spinner("10 agents are thinking..."):
        try:
            resp = requests.post(f"{API}/api/v1/intelligence/plan", json={
                "user_idea": user_idea,
                "talent_id": talent_id,
                "platform": platform,
                "content_type": content_type,
                "campaign": campaign,
            }, timeout=30)

            if resp.ok:
                plan = resp.json()

                # ── Overall Plan ──────────────────────────────────────────────
                st.markdown("---")
                st.subheader("Creative Plan")
                st.metric("Confidence", f"{plan['confidence']:.0%}")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Prompt**")
                    st.code(plan["prompt"], language="text")
                    if plan["negative_prompt"]:
                        st.markdown("**Negative**")
                        st.code(plan["negative_prompt"], language="text")
                with col2:
                    st.markdown(f"**Model:** {plan['model']}")
                    st.markdown(f"**Settings:** {plan['settings']}")
                    st.markdown(f"**Time:** {plan['estimated_time']}")
                    st.markdown(f"**Cost:** {plan['estimated_cost']}")
                    if plan["workflow_steps"]:
                        st.markdown(f"**Workflow:** {' → '.join(s.get('name','?') for s in plan['workflow_steps'])}")

                # ── Agent Reasoning ───────────────────────────────────────────
                st.markdown("---")
                st.subheader("Agent Reasoning")

                for agent_data in plan["agents"]:
                    confidence = agent_data["confidence"]
                    icon = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.5 else "🔴"

                    with st.expander(f"{icon} {agent_data['agent']} ({confidence:.0%})"):
                        st.caption(f"*{agent_data['reasoning']}*")
                        for rec in agent_data["recommendations"]:
                            st.markdown(f"**{rec.get('title', '?')}**")
                            st.markdown(rec.get("content", ""))
                            st.markdown("---")

                # ── Publishing ────────────────────────────────────────────────
                if plan.get("publishing"):
                    st.markdown("---")
                    st.subheader("Publishing Plan")
                    for key, value in plan["publishing"].items():
                        st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")

            else:
                st.error(f"Failed: {resp.json().get('detail', resp.text)}")

        except Exception as e:
            st.error(f"Error: {e}")
