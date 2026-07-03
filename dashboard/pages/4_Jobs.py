"""Jobs — Create and monitor generation jobs."""
import streamlit as st
import sys
sys.path.insert(0, ".")
from dashboard.api_client import list_jobs, create_job, get_job, cancel_job, retry_job, delete_job

st.set_page_config(page_title="Jobs", page_icon="⚙️", layout="wide")
st.title("⚙️ Jobs")
st.markdown("---")

JOB_TYPES = [
    "image_generation",
    "video_generation",
    "lora_training",
    "image_upscale",
    "image_edit",
    "voice_generation",
    "workflow_execution",
    "asset_processing",
    "publishing",
]

try:
    # Create job form
    with st.expander("Create New Job", expanded=False):
        with st.form("create_job"):
            job_type = st.selectbox("Job Type", JOB_TYPES)
            priority = st.slider("Priority", 1, 10, 5)
            prompt = st.text_input("Prompt (optional)", placeholder="luxury portrait of AI influencer")
            steps = st.number_input("Simulation Steps", min_value=1, max_value=20, value=3)
            submitted = st.form_submit_button("Create Job")

            if submitted:
                input_data = {"steps": steps, "step_delay": 0.5}
                if prompt:
                    input_data["prompt"] = prompt
                result = create_job({"type": job_type, "priority": priority, "input": input_data})
                st.success(f"Job created: {result.get('id', '?')[:8]}... ({job_type})")
                st.rerun()

    # Filters
    col1, col2 = st.columns(2)
    status_filter = col1.selectbox("Filter by Status", ["", "queued", "running", "completed", "failed", "cancelled"])
    type_filter = col2.selectbox("Filter by Type", [""] + JOB_TYPES)

    # List jobs
    st.subheader("Jobs")
    jobs = list_jobs(status=status_filter or None, job_type=type_filter or None)

    if not jobs:
        st.info("No jobs found.")
    else:
        for j in jobs:
            status = j.get("status", "?")
            icon = {"queued": "🕐", "running": "🔄", "completed": "✅", "failed": "❌", "cancelled": "⛔"}.get(status, "❓")

            with st.container():
                col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 1, 2])
                col1.markdown(f"{icon}")
                col2.markdown(f"**{j['type']}**")
                col3.markdown(f"Status: `{status}` | Progress: {j.get('progress', 0)}%")
                col4.markdown(f"P{j.get('priority', 5)}")

                # Action buttons
                actions = col5
                if status == "queued":
                    if actions.button("Cancel", key=f"cancel_{j['id']}"):
                        cancel_job(j["id"])
                        st.rerun()
                elif status in ("failed", "cancelled"):
                    c1, c2 = actions.columns(2)
                    if c1.button("Retry", key=f"retry_{j['id']}"):
                        retry_job(j["id"])
                        st.rerun()
                    if c2.button("Delete", key=f"del_{j['id']}"):
                        delete_job(j["id"])
                        st.rerun()
                elif status == "completed":
                    if actions.button("Delete", key=f"del_{j['id']}"):
                        delete_job(j["id"])
                        st.rerun()

                with st.expander(f"Details: {j['id'][:8]}..."):
                    st.json(j)

except Exception as e:
    st.error(f"API error: {e}")
