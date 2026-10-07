"""Talent — Manage AI personas."""
import streamlit as st
import sys
sys.path.insert(0, ".")
from dashboard.api_client import list_talent, create_talent

st.set_page_config(page_title="Talent", page_icon="🧑‍🎤", layout="wide")
st.title("🧑‍🎤 AI Talent")
st.markdown("---")

try:
    # Create talent form
    with st.expander("Create New Talent", expanded=False):
        with st.form("create_talent"):
            name = st.text_input("Name", placeholder="e.g. Melissa")
            bio = st.text_area("Bio", placeholder="Description of the AI persona")
            gender = st.selectbox("Gender", ["", "female", "male", "non-binary"])
            age = st.number_input("Age", min_value=0, max_value=100, value=25)
            ethnicity = st.text_input("Ethnicity", placeholder="e.g. Black, Asian, etc.")
            submitted = st.form_submit_button("Create Talent")

            if submitted and name:
                data = {"name": name, "bio": bio, "status": "active", "is_active": True}
                if gender:
                    data["gender"] = gender
                if age > 0:
                    data["age"] = age
                if ethnicity:
                    data["ethnicity"] = ethnicity
                result = create_talent(data)
                st.success(f"Created talent: {name}")
                st.rerun()

    # List talent
    st.subheader("All Talent")
    talent = list_talent()

    if not talent:
        st.info("No talent records yet. Create one above.")
    else:
        for t in talent:
            with st.container():
                col1, col2, col3 = st.columns([2, 3, 1])
                col1.markdown(f"**{t['name']}**")
                col2.markdown(t.get("bio", "No bio") or "No bio")
                col3.markdown(f"`{t.get('status', 'active')}`")

                with st.expander(f"Details: {t['name']}"):
                    st.json(t)

except Exception as e:
    st.error(f"API error: {e}")
    st.info("Make sure the FastAPI backend is running.")
