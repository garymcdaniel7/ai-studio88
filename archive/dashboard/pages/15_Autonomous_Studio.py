"""Autonomous Studio — AI departments, daily briefing, and recommendations."""
import streamlit as st
import requests
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Autonomous Studio", page_icon="🏢", layout="wide")
st.title("🏢 Autonomous Studio")
st.markdown("*Your AI creative agency. 19 departments thinking for you.*")
st.markdown("---")

# ── Daily Briefing ────────────────────────────────────────────────────────────
st.subheader("📋 Daily Briefing")

try:
    resp = requests.get(f"{API}/api/v1/studio/briefing", timeout=10)
    if resp.ok:
        briefing = resp.json()

        # Status row
        col1, col2, col3, col4 = st.columns(4)
        prod = briefing.get("production_status", {})
        col1.metric("Workers Online", prod.get("workers_online", 0))
        col2.metric("Scheduled", briefing.get("publishing_status", {}).get("scheduled", 0))
        col3.metric("Active Campaigns", briefing.get("campaign_health", {}).get("active", 0))
        col4.metric("Recommendations", briefing.get("recommendations_count", 0))

        # Alerts
        alerts = briefing.get("alerts", [])
        if alerts:
            for a in alerts:
                st.error(f"🚨 {a}")

        # Learning
        learning = briefing.get("learning", {})
        if learning.get("total_decisions", 0) > 0:
            st.caption(f"Learning accuracy: {learning['accuracy_pct']}% ({learning['total_decisions']} decisions)")

    else:
        st.error("Briefing unavailable")
except Exception as e:
    st.error(f"Cannot reach studio: {e}")

# ── Top Recommendations ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🤖 AI Recommendations")

try:
    resp = requests.get(f"{API}/api/v1/studio/recommendations", timeout=10)
    if resp.ok:
        recs = resp.json()
        if not recs:
            st.success("No urgent recommendations. System running well.")
        for i, rec in enumerate(recs[:8]):
            priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(rec["priority"], "⚪")
            with st.container():
                col1, col2, col3 = st.columns([1, 5, 2])
                col1.markdown(f"{priority_icon}")
                col2.markdown(f"**{rec['title']}** ({rec['department']})")
                col2.caption(f"{rec['description']}")
                col2.caption(f"*Reasoning: {rec['reasoning']}* | Confidence: {rec['confidence']:.0%}")

                # Approval buttons
                c1, c2, c3 = col3.columns(3)
                if c1.button("✅", key=f"approve_{i}"):
                    requests.post(f"{API}/api/v1/studio/recommendations/{i}/decide", json={"decision": "approved"})
                    st.rerun()
                if c2.button("❌", key=f"reject_{i}"):
                    requests.post(f"{API}/api/v1/studio/recommendations/{i}/decide", json={"decision": "rejected"})
                    st.rerun()
except Exception:
    pass

# ── Department Discussion ─────────────────────────────────────────────────────
st.markdown("---")
st.subheader("💬 Department Discussion")

topic = st.text_input("Ask the studio about...", placeholder="luxury travel campaign for Melissa")
if st.button("Start Discussion") and topic:
    with st.spinner("19 departments discussing..."):
        try:
            resp = requests.post(f"{API}/api/v1/studio/discuss", json={"topic": topic}, timeout=15)
            if resp.ok:
                result = resp.json()
                st.markdown(f"**Topic:** {result['topic']} | **Departments involved:** {result['departments_involved']}")
                for contrib in result["contributions"]:
                    conf = "🟢" if contrib["confidence"] >= 0.7 else "🟡"
                    st.markdown(f"{conf} **{contrib['department']}** ({contrib['role']})")
                    st.markdown(f"  → {contrib['contribution']}")
                    if contrib["detail"]:
                        st.caption(f"  {contrib['detail']}")
        except Exception as e:
            st.error(f"Discussion failed: {e}")

# ── Departments ───────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🏛️ Departments")

try:
    resp = requests.get(f"{API}/api/v1/studio/departments", timeout=5)
    if resp.ok:
        depts = resp.json()
        cols = st.columns(4)
        for i, d in enumerate(depts):
            cols[i % 4].markdown(f"**{d['name']}**")
            cols[i % 4].caption(d["role"])
except Exception:
    pass

# ── Studio Health ─────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("Studio Health"):
    try:
        resp = requests.get(f"{API}/api/v1/studio/health", timeout=5)
        if resp.ok:
            h = resp.json()
            status_icon = {"healthy": "🟢", "warning": "🟡", "critical": "🔴"}.get(h["status"], "❓")
            st.markdown(f"{status_icon} **Status:** {h['status']}")
            st.markdown(f"Departments: {h['departments_healthy']} healthy, {h['departments_warning']} warning, {h['departments_critical']} critical")
            st.markdown(f"Workers: {h['workers_online']} | Pending recommendations: {h['recommendations_pending']}")
    except Exception:
        pass
