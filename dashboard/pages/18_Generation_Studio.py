"""Generation Studio — Create AI images and videos.

The main creative interface. Select a model, write a prompt, generate content.
"""
import os
import time
import base64
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Generation Studio", page_icon="🎨", layout="wide")
st.title("🎨 Generation Studio")

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
COMFYUI_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")


def api_get(path):
    try:
        return requests.get(f"{API_URL}{path}", timeout=15).json()
    except:
        return None


# =============================================================================
# Sidebar — Model Selection & Worker Status
# =============================================================================

with st.sidebar:
    st.markdown("### Worker Status")
    infra = api_get("/api/v1/infrastructure/status")
    if infra:
        worker = infra.get("worker", {})
        status = worker.get("status", "no_session")
        if status == "ready":
            st.success(f"🟢 {worker.get('gpu_name', 'GPU')} online")
            st.caption(f"${worker.get('hourly_rate', 0):.2f}/hr | {worker.get('uptime_seconds', 0)/60:.0f}min")
        elif status == "no_session":
            st.warning("⚪ No worker running")
            if st.button("🚀 Launch Worker"):
                with st.spinner("Launching..."):
                    resp = requests.post(f"{API_URL}/api/v1/infrastructure/launch",
                        json={"max_price": 1.50, "min_vram_gb": 24, "num_candidates": 3},
                        timeout=700)
                    if resp.ok and resp.json().get("status") == "success":
                        st.success("Worker launched!")
                        st.rerun()
                    else:
                        st.error(f"Failed: {resp.json().get('error', 'unknown')}")
        else:
            st.info(f"🟡 {status}")

    st.markdown("---")
    st.markdown("### Model")

    # Get available models
    models_data = api_get("/api/v1/generation/available-models")
    if models_data:
        model_names = [m["id"] for m in models_data]
        model_map = {m["id"]: m for m in models_data}
    else:
        model_names = ["sdxl-turbo", "sd15", "flux-dev"]
        model_map = {}

    selected_model = st.selectbox("Select Model", model_names, index=0)

    if selected_model in model_map:
        m = model_map[selected_model]
        st.caption(m.get("description", ""))
        cached = "✅ Cached" if m.get("cached_in_b2") else "⚠️ Not cached"
        st.caption(f"{cached} | {m.get('required_vram_gb', '?')}GB VRAM")
        defaults = m.get("defaults", {})
    else:
        defaults = {"steps": 20, "cfg": 7.0, "width": 1024, "height": 1024}


# =============================================================================
# Main — Prompt & Generation
# =============================================================================

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### Prompt")
    prompt = st.text_area("Describe what you want to create",
        value="a luxury penthouse apartment overlooking a modern city skyline at golden hour sunset, photorealistic, architectural photography",
        height=120)

    negative_prompt = st.text_input("Negative prompt (what to avoid)",
        value="ugly, blurry, low quality, artifacts")

    # Advanced settings
    with st.expander("⚙️ Advanced Settings"):
        adv_col1, adv_col2, adv_col3 = st.columns(3)
        with adv_col1:
            width = st.number_input("Width", 256, 2048, defaults.get("width", 1024), 64)
            height = st.number_input("Height", 256, 2048, defaults.get("height", 1024), 64)
        with adv_col2:
            steps = st.number_input("Steps", 1, 50, defaults.get("steps", 20))
            cfg = st.number_input("CFG Scale", 0.1, 20.0, float(defaults.get("cfg", 7.0)), 0.5)
        with adv_col3:
            seed = st.number_input("Seed (-1 = random)", -1, 999999999, -1)
            guidance = st.number_input("Guidance (Flux)", 0.0, 10.0, float(defaults.get("guidance", 3.5)), 0.5)

    # Generate button
    generate_clicked = st.button("✨ Generate", type="primary", use_container_width=True)

with col2:
    st.markdown("### Result")
    result_placeholder = st.empty()
    status_placeholder = st.empty()

# =============================================================================
# Generation Logic
# =============================================================================

if generate_clicked:
    # Check ComfyUI connectivity
    try:
        comfy_health = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        if not comfy_health.ok:
            st.error("ComfyUI not reachable. Launch a worker first.")
            st.stop()
    except:
        st.error(f"ComfyUI not reachable at {COMFYUI_URL}. Launch a worker and set up SSH tunnel.")
        st.stop()

    # Build workflow based on model
    actual_seed = seed if seed >= 0 else int(time.time()) % 999999999

    if selected_model == "flux-dev":
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp16.safetensors", "type": "flux"}},
            "3": {"class_type": "CLIPTextEncodeFlux", "inputs": {"clip": ["2", 0], "clip_l": prompt[:77], "t5xxl": prompt, "guidance": guidance}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": actual_seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
            "6": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["6", 0]}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "studio_flux"}},
        }
    elif selected_model == "sdxl-turbo":
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": actual_seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "studio_sdxl"}},
        }
    else:  # sd15 or other standard models
        ckpt_map = {"sd15": "v1-5-pruned-emaonly.safetensors"}
        ckpt = ckpt_map.get(selected_model, "v1-5-pruned-emaonly.safetensors")
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": actual_seed, "steps": steps, "cfg": cfg, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "studio_gen"}},
        }

    # Submit to ComfyUI
    status_placeholder.info("Submitting to ComfyUI...")
    try:
        resp = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        if not resp.ok:
            st.error(f"ComfyUI rejected the prompt: {resp.text[:200]}")
            st.stop()
        prompt_id = resp.json().get("prompt_id")
        status_placeholder.info(f"Generating... (prompt: {prompt_id[:8]})")
    except Exception as e:
        st.error(f"Failed to submit: {e}")
        st.stop()

    # Poll for result
    start_time = time.time()
    max_wait = 300  # 5 minutes max

    progress_bar = st.progress(0)
    while time.time() - start_time < max_wait:
        time.sleep(3)
        elapsed = time.time() - start_time
        progress_bar.progress(min(int(elapsed / max_wait * 100), 95))
        status_placeholder.info(f"Generating... ({elapsed:.0f}s)")

        try:
            hist_resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            if hist_resp.ok:
                hist = hist_resp.json()
                if prompt_id in hist:
                    entry = hist[prompt_id]
                    status = entry.get("status", {})

                    if status.get("completed"):
                        progress_bar.progress(100)
                        # Find the output image
                        for nid, out in entry.get("outputs", {}).items():
                            for img in out.get("images", []):
                                # Download the image
                                img_resp = requests.get(
                                    f"{COMFYUI_URL}/view",
                                    params={"filename": img["filename"], "type": img.get("type", "output")},
                                    timeout=30
                                )
                                if img_resp.ok:
                                    result_placeholder.image(img_resp.content, caption=img["filename"], use_container_width=True)
                                    status_placeholder.success(f"Generated in {elapsed:.1f}s! ({img['filename']})")

                                    # Save locally
                                    save_path = os.path.expanduser(f"~/Desktop/{img['filename']}")
                                    with open(save_path, "wb") as f:
                                        f.write(img_resp.content)
                                    st.caption(f"Saved to: {save_path}")
                                break
                        break

                    elif status.get("status_str") == "error":
                        msgs = status.get("messages", [])
                        err_msg = "Unknown error"
                        for m in msgs:
                            if m[0] == "execution_error":
                                err_msg = m[1].get("exception_message", "")[:300]
                        progress_bar.progress(0)
                        status_placeholder.error(f"Generation failed: {err_msg}")
                        break
        except:
            pass
    else:
        status_placeholder.error("Generation timed out (5 minutes)")


# =============================================================================
# Model Manager Section
# =============================================================================

st.markdown("---")
st.markdown("## Model Manager")

models_tab, cache_tab = st.tabs(["Available Models", "B2 Cache"])

with models_tab:
    if models_data:
        for m in models_data:
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.write(f"**{m['id']}** — {m.get('description', '')}")
            col2.write(f"{m.get('required_vram_gb', '?')}GB VRAM")
            cached = m.get("cached_in_b2", False)
            col3.write("✅ Cached" if cached else "❌ Not cached")
    else:
        st.info("Cannot load model list from API")

with cache_tab:
    if infra:
        models_info = infra.get("models", {})
        cached_files = models_info.get("cached_in_b2", [])
        if cached_files:
            st.write(f"**{len(cached_files)} model(s) in Backblaze B2:**")
            for f in cached_files:
                st.write(f"  ✅ {f}")
        else:
            st.info("No models cached. Use `python scripts/vast/upload_model.py --known sdxl-turbo` to seed.")

    st.markdown("---")
    st.markdown("### Download Model to B2")
    st.caption("Downloads from HuggingFace via a Vast.ai worker and uploads to B2 cache.")
    dl_model = st.selectbox("Model to cache", ["sdxl-turbo", "sd15-pruned", "sdxl-vae", "flux-dev"])
    if st.button("📥 Download to B2 Cache"):
        st.info(f"Run in terminal: `python scripts/vast/upload_model.py --known {dl_model}`")
        st.caption("(Automated in-app download coming soon)")
