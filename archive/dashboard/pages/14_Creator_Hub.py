"""Creator Hub — unified command center for the creator operating system."""
import streamlit as st
import requests
import os
import sys
from enum import Enum
sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000")


class Platform(Enum):
    instagram = "instagram"
    tiktok = "tiktok"
    youtube = "youtube"
    youtube_shorts = "youtube_shorts"
    twitter = "twitter"
    linkedin = "linkedin"
    pinterest = "pinterest"
    facebook = "facebook"

st.set_page_config(page_title="Creator Hub", page_icon="🏠", layout="wide")
st.title("🏠 Creator Hub")
st.markdown("*Your AI-powered creative command center.*")
st.markdown("---")

# ── Hub Summary ───────────────────────────────────────────────────────────────
try:
    resp = requests.get(f"{API}/api/v1/hub/summary", timeout=5)
    if resp.ok:
        hub = resp.json()
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Scheduled", hub["scheduled"])
        col2.metric("Campaigns", hub["campaigns_active"])
        col3.metric("Brands", hub["brands"])
        col4.metric("Team", hub["team_members"])
        col5.metric("Workers", f"{hub['workers_online']}/{hub['workers_total']}")
        col6.metric("Revenue", f"${hub['total_revenue_usd']:.0f}")
except Exception as e:
    st.error(f"Hub unavailable: {e}")

# ── AI Operations Recommendations ────────────────────────────────────────────
st.markdown("---")
st.subheader("🤖 AI Operations Assistant")

try:
    resp = requests.get(f"{API}/api/v1/ops/recommendations", timeout=5)
    if resp.ok:
        recs = resp.json()
        for rec in recs:
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec.get("priority"), "⚪")
            st.markdown(f"{icon} **{rec['title']}** — {rec['message']}")
            if rec.get("action"):
                st.caption(f"Suggested action: {rec['action']}")
except Exception:
    pass

# ── Notifications ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🔔 Notifications")

try:
    resp = requests.get(f"{API}/api/v1/notifications?unread_only=true", timeout=5)
    if resp.ok:
        notes = resp.json()
        if notes:
            for n in notes[:5]:
                st.markdown(f"  📌 **{n.get('title', '?')}** — {n.get('message', '')}")
        else:
            st.caption("No unread notifications")
except Exception:
    st.caption("Notifications not available")

# ── Quick Actions ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("⚡ Quick Actions")

col1, col2, col3, col4 = st.columns(4)
if col1.button("📅 Schedule Content"):
    st.info("Navigate to Calendar page")
if col2.button("🎯 New Campaign"):
    st.info("Navigate to Campaigns section below")
if col3.button("✨ Creative Session"):
    st.info("Navigate to Creative Session page")
if col4.button("🎨 Quick Generate"):
    st.info("Navigate to Generation page")

# ── Campaigns ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🎯 Campaigns")

try:
    resp = requests.get(f"{API}/api/v1/campaigns", timeout=5)
    campaigns = resp.json() if resp.ok else []
    if campaigns:
        for c in campaigns:
            st.markdown(f"  📋 **{c['name']}** — {c.get('status', '?')} | Platforms: {', '.join(c.get('platforms', []))}")
    else:
        st.caption("No campaigns yet")
except Exception:
    pass

with st.expander("Create Campaign"):
    with st.form("create_campaign"):
        c_name = st.text_input("Campaign Name")
        c_obj = st.text_input("Objective", placeholder="Increase brand awareness")
        c_platforms = st.multiselect("Platforms", [p.value for p in Platform])
        c_audience = st.text_input("Target Audience", placeholder="25-35 luxury lifestyle enthusiasts")
        if st.form_submit_button("Create") and c_name:
            requests.post(f"{API}/api/v1/campaigns", json={
                "name": c_name, "objective": c_obj, "platforms": c_platforms,
                "target_audience": c_audience,
            })
            st.rerun()

# ── Calendar Preview ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📅 Upcoming Content")

try:
    resp = requests.get(f"{API}/api/v1/calendar", timeout=5)
    entries = resp.json() if resp.ok else []
    if entries:
        for e in entries[:5]:
            st.markdown(f"  📄 **{e['title']}** → {e['platform']} | {e.get('status', '?')} | {e.get('scheduled_at', 'unscheduled')}")
    else:
        st.caption("No content scheduled")
except Exception:
    pass

with st.expander("Schedule Content"):
    with st.form("schedule"):
        s_title = st.text_input("Title")
        s_platform = st.selectbox("Platform", [p.value for p in Platform])
        s_date = st.text_input("Schedule Date (ISO)", placeholder="2026-07-10T10:00:00Z")
        if st.form_submit_button("Schedule") and s_title:
            requests.post(f"{API}/api/v1/calendar", json={
                "title": s_title, "platform": s_platform, "scheduled_at": s_date, "status": "scheduled",
            })
            st.rerun()

# Import needed
from backend.creator_os.models import Platform
