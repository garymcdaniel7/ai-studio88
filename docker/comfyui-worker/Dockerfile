# AI Studio GPU Worker — Pre-built ComfyUI + Ollama image
# Deploy this to RunPod or any Docker-compatible GPU cloud.
# Models are loaded from B2 persistent volume on first boot.
#
# Build: docker build -t ai-studio-worker:latest .
# RunPod template: Use this image as a custom template
#
# What's included:
# - ComfyUI (latest stable)
# - Ollama (with dolphin-llama3:8b ready to pull)
# - Python 3.11 + PyTorch 2.5 + CUDA 12.4
# - All ComfyUI dependencies pre-installed
# - Startup script that launches all services
#
# What's NOT included (loaded from volume on boot):
# - Model weights (Flux 2 Dev, SDXL Turbo, LoRAs) — too large for image
# - These are downloaded from B2 on first boot, then cached on volume

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

LABEL maintainer="AI Studio <ai-studio@example.com>"
LABEL description="Pre-built ComfyUI + Ollama worker for AI Studio"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl openssh-server nano htop \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# SSH server setup (for Vast.ai compatibility + debugging)
RUN mkdir -p /run/sshd && \
    echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && \
    echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config

WORKDIR /workspace

# Install ComfyUI
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git && \
    cd ComfyUI && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir huggingface-hub aiohttp && \
    mkdir -p models/checkpoints models/loras models/vae models/controlnet \
             models/upscale_models input output custom_nodes

# Install ComfyUI Manager (for easy node management)
RUN cd ComfyUI/custom_nodes && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Install Worker API dependencies
RUN pip install --no-cache-dir fastapi uvicorn httpx

# Copy startup script
COPY start.sh /workspace/start.sh
RUN chmod +x /workspace/start.sh

# Expose ports
# 8188 — ComfyUI
# 11434 — Ollama
# 7860 — Worker API
# 22 — SSH
EXPOSE 8188 11434 7860 22

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:8188/system_stats || exit 1

# Start all services
CMD ["/workspace/start.sh"]
