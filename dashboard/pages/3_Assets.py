"""Assets — Upload and manage files."""
import streamlit as st
import sys
sys.path.insert(0, ".")
from dashboard.api_client import list_assets, upload_asset, delete_asset

st.set_page_config(page_title="Assets", page_icon="📁", layout="wide")
st.title("📁 Assets")
st.markdown("---")

try:
    # Upload form
    with st.expander("Upload New Asset", expanded=False):
        uploaded_file = st.file_uploader("Choose a file", type=["png", "jpg", "jpeg", "webp", "mp4", "pdf", "txt"])
        asset_type = st.selectbox("Asset Type", ["image", "video", "document", "model", "audio", "general"])
        tags = st.text_input("Tags (comma-separated)", placeholder="portrait, flux, generated")

        if uploaded_file and st.button("Upload"):
            with st.spinner("Uploading to Backblaze B2..."):
                result = upload_asset(
                    file_bytes=uploaded_file.getvalue(),
                    filename=uploaded_file.name,
                    content_type=uploaded_file.type or "application/octet-stream",
                    asset_type=asset_type,
                    tags=tags,
                )
                st.success(f"Uploaded: {result.get('original_filename')}")
                st.json(result)
                st.rerun()

    # List assets
    st.subheader("All Assets")
    assets = list_assets()

    if not assets:
        st.info("No assets yet. Upload one above.")
    else:
        for a in assets:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                col1.markdown(f"**{a.get('original_filename', 'unnamed')}**")
                col2.markdown(f"`{a.get('mime_type', '?')}`")
                size_kb = (a.get("size_bytes", 0) or 0) / 1024
                col3.markdown(f"{size_kb:.1f} KB")

                if col4.button("Delete", key=f"del_{a['id']}"):
                    delete_asset(a["id"])
                    st.success("Deleted")
                    st.rerun()

                with st.expander(f"Metadata: {a.get('original_filename', '')}"):
                    st.json(a)

except Exception as e:
    st.error(f"API error: {e}")
