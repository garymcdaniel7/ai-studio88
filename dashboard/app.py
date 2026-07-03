"""AI Studio Dashboard — Main entry point.

Run with:
    cd ai-studio88
    uv run streamlit run dashboard/app.py

Requires the FastAPI backend running at API_BASE_URL (default: http://localhost:8000).
"""
import streamlit as st

st.set_page_config(
    page_title="AI Studio",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("AI Studio Dashboard")
st.markdown("---")

# Import pages via Streamlit multipage app pattern
# Pages live in dashboard/pages/ and are auto-discovered by Streamlit.
st.markdown("""
Welcome to **AI Studio** — your AI content production platform.

Use the sidebar to navigate between sections:

- **Dashboard** — Overview metrics
- **Talent** — Manage AI personas
- **Assets** — Upload and manage files
- **Jobs** — Run and monitor generation jobs
- **Workflows** — Create and execute multi-step workflows
- **Settings** — Connection status

---

*Make sure the FastAPI backend is running at `http://localhost:8000` before using this dashboard.*
""")
