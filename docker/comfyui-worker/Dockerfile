# AI Studio GPU Worker — Pre-built ComfyUI image
# 
# Deploy to Vast.ai, RunPod, or any Docker-compatible GPU cloud.
# Models are loaded from B2 cache on boot (~3 min cold start).
# If persisted, startup is ~30 seconds.
#
# Build:
#   docker build -t garymcdaniel7/ai-studio-worker:latest .
#   docker push garymcdaniel7/ai-studio-worker:latest
#
# Use on Vast.ai:
#   Image: garymcdaniel7/ai-studio-worker:latest
#   Disk: 80GB
#   Env: HF_TOKEN=hf_xxx, B2_KEY_ID=xxx, B2_APPLICATION_KEY=xxx
#
# Included:
# - ComfyUI 0.28+ with ComfyUI-Manager
# - Python 3.11 + PyTorch 2.6 + CUDA 12.4
# - Ollama (LLM inference)
# - B2 model cache downloader (fast model loading)
# - FFMPEG (video processing)
# - All dependencies pre-installed
#
# NOT included (downloaded on first boot from B2 or HuggingFace):
# - Model weights (~7-20GB depending on config)
# - These persist on the instance disk between sessions

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

LABEL maintainer="AI Studio"
LABEL description="Pre-built ComfyUI + Ollama GPU worker for AI Studio"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl openssh-server nano htop ffmpeg \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# SSH server (Vast.ai compatibility)
RUN mkdir -p /run/sshd && \
    echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && \
    echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config

WORKDIR /workspace

# Install ComfyUI
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git && \
    cd ComfyUI && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir huggingface-hub aiohttp b2sdk && \
    mkdir -p models/checkpoints models/unet models/clip models/vae \
             models/loras models/controlnet models/upscale_models \
             input output custom_nodes

# Install ComfyUI Manager
RUN cd ComfyUI/custom_nodes && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Install Worker utilities
RUN pip install --no-cache-dir fastapi uvicorn httpx

# Copy scripts
COPY start.sh /workspace/start.sh
COPY download_models.py /workspace/download_models.py
RUN chmod +x /workspace/start.sh

# Expose ports
EXPOSE 8188 11434 22

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s \
    CMD curl -f http://localhost:8188/system_stats || exit 1

CMD ["/workspace/start.sh"]
