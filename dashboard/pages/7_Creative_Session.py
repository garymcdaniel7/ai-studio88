"""✨ Creative Session — AI-guided content creation experience.

Guides users through natural-language creation rather than technical settings.
Calls the intelligence layer for recommendations, then creates jobs/workflows.
"""
import streamlit as st
import sys
sys.path.insert(0, ".")
from dashboard.api_client import list_talent, list_projects, create_job, create_workflow, run_workflow
from backend.intelligence import (
    CreativeContext,
    get_recommendations,
    build_production_plan,
)

st.set_page_config(page_title="Creative Session", page_icon="✨", layout="wide")
st.title("✨ Creative Session")
st.markdown("*Describe what you want to create. AI Studio handles the technical details.*")
st.markdown("---")

# =============================================================================
# Stage 1: Who
# =============================================================================

st.subheader("1. Who are we creating for?")

col1, col2 = st.columns(2)

try:
    talent_list = list_talent()
    talent_names = [t["name"] for t in talent_list]
except Exception:
    talent_list = []
    talent_names = ["(API not available)"]

try:
    project_list = list_projects()
    project_names = [p["name"] for p in project_list]
except Exception:
    project_list = []
    project_names = ["(API not available)"]

with col1:
    selected_talent = st.selectbox("Talent", ["Select..."] + talent_names)
    selected_project = st.selectbox("Project", ["Select..."] + project_names)

with col2:
    campaign = st.text_input("Campaign (optional)", placeholder="e.g. Summer 2026 Collection")
    platform = st.selectbox("Platform", ["instagram", "tiktok", "youtube", "pinterest", "website"])

st.markdown("---")

# =============================================================================
# Stage 2: What
# =============================================================================

st.subheader("2. What are we creating?")

content_type = st.selectbox(
    "Content Type",
    ["image", "video", "carousel", "story", "reel", "talking_head", "ad", "campaign"],
)

st.markdown("---")

# =============================================================================
# Stage 3: Describe
# =============================================================================

st.subheader("3. Describe your idea")

user_idea = st.text_area(
    "What do you envision?",
    placeholder="Luxury hotel in Dubai, golden hour rooftop, flowing silk dress, "
                "wind in hair, cinematic editorial style...",
    height=120,
)

st.caption("Examples: 'Old money fashion editorial' • 'Cinematic travel reel in Bali' • "
           "'Luxury beauty campaign, close-up portrait'")

st.markdown("---")

# =============================================================================
# Stage 4: Intelligence Panel
# =============================================================================

if user_idea and selected_talent != "Select...":
    st.subheader("4. Intelligence Panel")
    st.caption("AI recommendations based on your creative brief")

    # Resolve talent_id for DNA/feedback lookup
    talent_id = ""
    for t in talent_list:
        if t["name"] == selected_talent:
            talent_id = t["id"]
            break

    context = CreativeContext(
        talent_name=selected_talent,
        talent_id=talent_id,
        project_name=selected_project if selected_project != "Select..." else "",
        platform=platform,
        content_type=content_type,
        user_idea=user_idea,
        campaign=campaign,
    )

    recommendations = get_recommendations(context)

    # Group by agent
    agents = {}
    for rec in recommendations:
        agents.setdefault(rec.agent, []).append(rec)

    # Display in columns
    agent_cols = st.columns(len(agents))
    for i, (agent_name, recs) in enumerate(agents.items()):
        with agent_cols[i]:
            st.markdown(f"**{agent_name}**")
            for rec in recs:
                confidence_bar = "🟢" if rec.confidence >= 0.8 else "🟡" if rec.confidence >= 0.5 else "🔴"
                st.markdown(f"{confidence_bar} **{rec.title}**")
                st.caption(rec.content)

    st.markdown("---")

    # =============================================================================
    # Stage 5: Production Plan
    # =============================================================================

    st.subheader("5. Production Plan")

    plan = build_production_plan(context)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Prompt**")
        st.code(plan.prompt or "(no prompt generated)", language="text")

        if plan.negative_prompt:
            st.markdown("**Negative Prompt**")
            st.code(plan.negative_prompt, language="text")

    with col2:
        st.markdown("**Workflow**")
        if plan.workflow_steps:
            for i, step in enumerate(plan.workflow_steps):
                st.markdown(f"{i + 1}. {step.get('name', '?')} (`{step.get('handler', '?')}`)")
        else:
            st.caption("Single-step generation")

        st.markdown("**Estimates**")
        st.markdown(f"- Runtime: {plan.estimated_runtime or '~1 min'}")
        st.markdown(f"- GPU: {plan.estimated_gpu or 'RTX 4090'}")
        st.markdown(f"- Cost: {plan.estimated_cost or '~$0.02'}")
        st.markdown(f"- Outputs: {', '.join(plan.expected_outputs)}")

    st.markdown("---")

    # =============================================================================
    # Stage 6: Create Job
    # =============================================================================

    st.subheader("6. Launch")

    if st.button("🚀 Generate", type="primary", use_container_width=True):
        with st.spinner("Generating via AI Studio Engine..."):
            try:
                import requests as req
                api_url = os.getenv("API_BASE_URL", "http://localhost:8000") if "os" in dir() else "http://localhost:8000"
                # Use the generation engine endpoint
                gen_data = {
                    "prompt": plan.prompt,
                    "negative_prompt": plan.negative_prompt,
                    "type": "video_generation" if content_type == "video" else "image_generation",
                    "width": 1024,
                    "height": 1024,
                    "steps": 5,
                    "model": "flux-dev",
                    "talent_id": talent_id or None,
                }

                import os as _os
                from dotenv import load_dotenv as _ld
                _ld()
                _api = _os.getenv("API_BASE_URL", "http://localhost:8000")

                resp = req.post(f"{_api}/api/v1/generation/run", json=gen_data, timeout=60)

                if resp.ok:
                    result = resp.json()
                    st.success(f"Generation complete! Job: {result.get('job_id', '?')[:8]}...")
                    st.markdown(f"**Provider:** {result.get('provider')}")

                    asset = result.get("asset", {})
                    if asset:
                        st.markdown(f"**Asset registered:** {asset.get('original_filename', '?')}")
                        st.markdown(f"**Storage:** {asset.get('public_url', 'N/A')}")
                        st.markdown(f"**Size:** {asset.get('size_bytes', 0)} bytes")

                    with st.expander("Full result"):
                        st.json(result)
                else:
                    st.error(f"Generation failed: {resp.json().get('detail', resp.text)}")

            except Exception as e:
                st.error(f"Error: {e}")

elif user_idea:
    st.info("Select a talent to see AI recommendations.")
else:
    st.info("Describe your idea above to see the intelligence panel and production plan.")
