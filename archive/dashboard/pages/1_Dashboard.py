"""Dashboard — Overview metrics."""
import streamlit as st
import sys
sys.path.insert(0, ".")
from dashboard.api_client import list_projects, list_talent, list_assets, list_jobs, list_workflows

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Dashboard")
st.markdown("---")

try:
    projects = list_projects()
    talent = list_talent()
    assets = list_assets()
    jobs = list_jobs()
    workflows = list_workflows()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Projects", len(projects))
    col2.metric("Talent", len(talent))
    col3.metric("Assets", len(assets))
    col4.metric("Jobs", len(jobs))
    col5.metric("Workflows", len(workflows))

    st.markdown("---")

    # Job status breakdown
    if jobs:
        st.subheader("Job Status")
        statuses = {}
        for j in jobs:
            s = j.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1
        cols = st.columns(len(statuses))
        for i, (status, count) in enumerate(statuses.items()):
            cols[i].metric(status.capitalize(), count)

    # Recent jobs
    if jobs:
        st.subheader("Recent Jobs")
        for j in jobs[:5]:
            st.markdown(f"- **{j['type']}** — {j['status']} (priority {j['priority']})")

except Exception as e:
    st.error(f"Failed to connect to API: {e}")
    st.info("Make sure the FastAPI backend is running at http://localhost:8000")
