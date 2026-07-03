"""Workflows — Create and execute multi-step workflows."""
import json
import streamlit as st
import sys
sys.path.insert(0, ".")
from dashboard.api_client import list_workflows, create_workflow, run_workflow, delete_workflow

st.set_page_config(page_title="Workflows", page_icon="🔀", layout="wide")
st.title("🔀 Workflows")
st.markdown("---")

HANDLER_OPTIONS = [
    "image_generation",
    "video_generation",
    "lora_training",
    "image_upscale",
    "image_edit",
    "voice_generation",
    "asset_processing",
    "publishing",
]

try:
    # Create workflow
    with st.expander("Create New Workflow", expanded=False):
        with st.form("create_workflow"):
            name = st.text_input("Workflow Name", placeholder="e.g. Luxury Portrait Pipeline")
            description = st.text_area("Description", placeholder="What this workflow does")
            num_steps = st.number_input("Number of Steps", min_value=1, max_value=10, value=3)
            submitted = st.form_submit_button("Configure Steps")

        if submitted and name:
            st.session_state["wf_name"] = name
            st.session_state["wf_desc"] = description
            st.session_state["wf_num_steps"] = num_steps

    # Step configuration
    if "wf_name" in st.session_state:
        st.subheader(f"Configure: {st.session_state['wf_name']}")
        steps = []
        num = st.session_state["wf_num_steps"]

        with st.form("workflow_steps"):
            for i in range(num):
                st.markdown(f"**Step {i + 1}**")
                c1, c2, c3 = st.columns([2, 2, 2])
                step_name = c1.text_input(f"Name", key=f"sn_{i}", value=f"Step {i + 1}")
                handler = c2.selectbox(f"Handler", HANDLER_OPTIONS, key=f"sh_{i}")
                deps = c3.text_input(f"Depends on (comma-sep indices)", key=f"sd_{i}", value="" if i == 0 else str(i - 1))
                steps.append({"name": step_name, "handler": handler, "deps": deps})

            create_btn = st.form_submit_button("Create Workflow")

        if create_btn:
            workflow_steps = []
            for s in steps:
                dep_list = [int(d.strip()) for d in s["deps"].split(",") if d.strip().isdigit()]
                workflow_steps.append({
                    "name": s["name"],
                    "handler": s["handler"],
                    "config": {"steps": 2, "step_delay": 0.3},
                    "depends_on": dep_list,
                })

            result = create_workflow({
                "name": st.session_state["wf_name"],
                "description": st.session_state["wf_desc"],
                "status": "active",
                "steps": workflow_steps,
            })
            st.success(f"Workflow created: {result.get('id', '?')[:8]}...")
            del st.session_state["wf_name"]
            del st.session_state["wf_desc"]
            del st.session_state["wf_num_steps"]
            st.rerun()

    # List workflows
    st.markdown("---")
    st.subheader("All Workflows")
    workflows = list_workflows()

    if not workflows:
        st.info("No workflows yet. Create one above.")
    else:
        for w in workflows:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 1, 2])
                col1.markdown(f"**{w['name']}** (v{w.get('version', 1)})")
                col2.markdown(f"{len(w.get('steps', []))} steps | `{w.get('status', '?')}`")
                col3.markdown(f"`{w.get('trigger_type', 'manual')}`")

                actions = col4
                c1, c2 = actions.columns(2)
                if c1.button("Run", key=f"run_{w['id']}"):
                    with st.spinner("Executing workflow..."):
                        result = run_workflow(w["id"])
                    st.success(f"Run completed: {result.get('status', '?')}")
                    with st.expander("Run Result"):
                        st.json(result)

                if c2.button("Delete", key=f"del_{w['id']}"):
                    delete_workflow(w["id"])
                    st.rerun()

                with st.expander(f"Steps: {w['name']}"):
                    for i, step in enumerate(w.get("steps", [])):
                        deps = step.get("depends_on", [])
                        dep_str = f" (after step {deps})" if deps else " (no deps)"
                        st.markdown(f"{i}. **{step.get('name', '?')}** — `{step.get('handler')}`{dep_str}")

except Exception as e:
    st.error(f"API error: {e}")
