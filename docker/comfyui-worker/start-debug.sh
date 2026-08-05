#!/bin/bash
# =============================================================================
# AI Studio GPU Worker — Emergency Debug Startup (Story 049)
# =============================================================================
# This script is ONLY used in the debug profile image.
# It starts SSH for emergency diagnostics alongside ComfyUI.
#
# SECURITY NOTES:
# - SSH key MUST be mounted: -v ./key.pub:/home/debuguser/.ssh/authorized_keys
# - Root login is DISABLED
# - Session timeout: 10 minutes idle
# - This profile should ONLY be deployed when actively debugging
# - Usage is audited via container logs
# =============================================================================

set -e

echo "╔══════════════════════════════════════════════╗"
echo "║  AI Studio GPU Worker (EMERGENCY DEBUG)     ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  ⚠️  SSH ENABLED — For diagnostics only     ║"
echo "║  ⚠️  Do NOT use in production workloads     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Reason:    Emergency debug profile activated"
echo ""

# Verify SSH key is mounted
if [ ! -f /home/debuguser/.ssh/authorized_keys ]; then
    echo "ERROR: No SSH key mounted at /home/debuguser/.ssh/authorized_keys"
    echo "       Mount with: -v ./debug_key.pub:/home/debuguser/.ssh/authorized_keys:ro"
    exit 1
fi

# Fix permissions (may be wrong from mount)
chmod 600 /home/debuguser/.ssh/authorized_keys
chown debuguser:debuguser /home/debuguser/.ssh/authorized_keys

# Start SSH (as root — only in debug profile)
echo "[DEBUG] Starting SSH server on port 22..."
/usr/sbin/sshd -D &
echo "        SSH ready (user: debuguser, key-only auth)"
echo ""

# Now drop to comfyui user for application
echo "[APP] Starting ComfyUI as comfyui user..."

# Download models
MODELS=${MODELS:-"sdxl-turbo"}
su comfyui -c "python3 /workspace/download_models.py --models '$MODELS'" 2>&1 || echo "[WARN] Model download had errors"

# Start Ollama
su comfyui -c "ollama serve > /tmp/ollama.log 2>&1 &"

# Start ComfyUI (foreground)
echo ""
echo "  READY — ComfyUI: http://0.0.0.0:8188 | SSH: port 22 (debuguser)"
echo ""

cd /workspace/ComfyUI
exec su comfyui -c "python3 main.py --listen 0.0.0.0 --port 8188 --preview-method auto"
