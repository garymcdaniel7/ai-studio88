#!/bin/bash
# h3_prep.sh — Pre-H3-batch GPU health ritual for Gary's Thunder box (yejeczdk, A6000).
#
# Run BEFORE every H3 batch (Motion Director chain, Ref2VA, FL2VA, turbo runs).
# Fixes the three known batch killers in one pass:
#   1. Ollama VRAM squat (~6GB) starving H3's ~43GB -> CUDA errors on every clip
#   2. Accumulated CUDA corruption -> glitch garbage / OOMs mid-batch
#   3. ComfyUI dead or wedged -> "model lost" panic that is really a stale process
#
# Deploy + run on box:
#   scp -P 31216 scripts/thunder/h3_prep.sh ubuntu@216.81.200.239:/home/ubuntu/
#   ssh -p 31216 ubuntu@216.81.200.239 "bash /home/ubuntu/h3_prep.sh"
#
# It is IDEMPOTENT and SAFE to run while ComfyUI is idle.
# It will KILL Ollama and ComfyUI main.py by design — do not run mid-generation.
#
# Exit codes: 0 = ready for batch, 1 = something is still wedged (read output).

# Tunable thresholds (all overridable via env):
#   VRAM_IDLE_THRESHOLD_MIB — GPU "clean" threshold after prep (default 300)
#   STALE_VRAM_MIB          — ComfyUI idle but VRAM held => restart (default 5000)
#   COMFY_WAIT_SECS         — how long to wait for ComfyUI to come back (default 30)
#   DISK_MIN_GB             — minimum free /home (default 20)
#   COMFY_HTTPS_PORT        — ComfyUI API port (default 8188)
VRAM_IDLE_THRESHOLD_MIB="${VRAM_IDLE_THRESHOLD_MIB:-300}"
STALE_VRAM_MIB="${STALE_VRAM_MIB:-5000}"
COMFY_WAIT_SECS="${COMFY_WAIT_SECS:-30}"
DISK_MIN_GB="${DISK_MIN_GB:-20}"
COMFY_PORT="${COMFY_PORT:-8188}"

set -u

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }

echo "Thresholds: VRAM_IDLE < ${VRAM_IDLE_THRESHOLD_MIB}MiB | STALE > ${STALE_VRAM_MIB}MiB | COMFY_WAIT ${COMFY_WAIT_SECS}s | DISK_MIN ${DISK_MIN_GB}GB | PORT ${COMFY_PORT}"

FAILED=0

echo "=========================================================="
echo " H3 PREP — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=========================================================="

# ---- 1. Kill Ollama (VRAM squat) -----------------------------------------
if pgrep -f ollama > /dev/null 2>&1; then
  echo "[1/5] Ollama running — killing (VRAM squat ~6GB feeds H3's ~43GB demand)."
  pkill -9 -f ollama 2>/dev/null || true
  sleep 2
  if pgrep -f ollama > /dev/null 2>&1; then
    fail "Ollama still alive after pkill -9"
    FAILED=1
  else
    ok "Ollama killed"
  fi
else
  echo "[1/5] Ollama not running — good."
fi

# ---- 2. Verify GPU is idle (clean VRAM) -----------------------------------
echo "[2/5] Checking GPU VRAM state..."
if command -v nvidia-smi > /dev/null 2>&1; then
  # Used memory on the first GPU, in MiB
  USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
  if [ -n "$USED" ] && [ "$USED" -lt "$VRAM_IDLE_THRESHOLD_MIB" ]; then
    ok "GPU idle (${USED} MiB used, threshold <${VRAM_IDLE_THRESHOLD_MIB})"
  else
    warn "GPU has ${USED:-?} MiB used — if ComfyUI is NOT actively generating, a restart is advised (stale VRAM / corruption)."
  fi
else
  warn "nvidia-smi not found — cannot verify VRAM. (Unusual on the Thunder box.)"
fi

# ---- 3. Clean ComfyUI restart only if stale / wedged -----------------------
echo "[3/5] Checking ComfyUI state..."
COMFY_OK=0
if curl -s -m 3 -o /dev/null http://127.0.0.1:${COMFY_PORT}/system_stats 2>/dev/null; then
  COMFY_OK=1
  ok "ComfyUI answering on :${COMFY_PORT}"
else
  warn "ComfyUI not answering on :${COMFY_PORT}"
fi

# ComfyUI answering but GPU VRAM is high + no active job = corruption risk
RESTART_COMFY=0
if [ "$COMFY_OK" -eq 1 ]; then
  ACTIVE=$(curl -s -m 3 http://127.0.0.1:${COMFY_PORT}/prompt 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('prompt_info',{})))" 2>/dev/null || echo "?")
  if [ "${ACTIVE:-?}" = "0" ] && [ -n "${USED:-}" ] && [ "$USED" -gt "$STALE_VRAM_MIB" ]; then
    warn "ComfyUI idle but ${USED} MiB VRAM held — stale state likely. Restarting ComfyUI clean."
    RESTART_COMFY=1
  fi
fi

if [ "$RESTART_COMFY" -eq 1 ] || [ "$COMFY_OK" -eq 0 ]; then
  echo "  Restarting ComfyUI (pkill main.py, drop comfyui.db, relaunch)..."
  pkill -9 -f "main.py" 2>/dev/null || true
  sleep 3
  # DB drop clears accumulated corruption; ComfyUI rebuilds it on boot
  COMFY_DIR="${COMFY_DIR:-/home/ubuntu/ComfyUI}"
  if [ -f "$COMFY_DIR/comfyui.db" ]; then
    rm -f "$COMFY_DIR/comfyui.db"
    ok "Removed $COMFY_DIR/comfyui.db"
  fi
  # Relaunch the same way ComfyUI is normally started on this box
  if [ -f /etc/thunder/client-extra.sh ]; then
    # Box-managed autostart path — trigger login script if it manages comfyui
    warn "Found /etc/thunder/client-extra.sh — relaunching via box autostart conventions."
    sudo -u ubuntu bash /etc/thunder/client-extra.sh >> /tmp/h3_prep_comfy.log 2>&1 || true
  elif [ -f /home/ubuntu/start_comfyui.sh ]; then
    nohup sudo -u ubuntu bash /home/ubuntu/start_comfyui.sh >> /tmp/h3_prep_comfy.log 2>&1 &
  else
    warn "No known ComfyUI start script found — start it manually after this prep."
  fi
  # Give it time, then verify
  sleep "$COMFY_WAIT_SECS"
  if curl -s -m 3 -o /dev/null http://127.0.0.1:${COMFY_PORT}/system_stats 2>/dev/null; then
    ok "ComfyUI back up on :${COMFY_PORT} after clean restart"
  else
    fail "ComfyUI did not come back within ${COMFY_WAIT_SECS}s — check /tmp/h3_prep_comfy.log"
    FAILED=1
  fi
else
  ok "ComfyUI healthy + VRAM clean — no restart needed"
fi

# ---- 4. Disk sanity -------------------------------------------------------
echo "[4/5] Disk check..."
DISK_FREE=$(df -Pk /home 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "$DISK_FREE" ]; then
  DISK_GB=$((DISK_FREE / 1024 / 1024))
  if [ "$DISK_GB" -lt "$DISK_MIN_GB" ]; then
    fail "Only ${DISK_GB} GB free on /home — H3 clips will fill this fast"
    FAILED=1
  else
    ok "${DISK_GB} GB free on /home"
  fi
else
  warn "Could not read disk free space"
fi

# ---- 5. Model presence sanity ----------------------------------------------
echo "[5/5] Key model files..."
MISSING=0
for f in \
  "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
  "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" \
  "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" \
  "diffusion_models/homofidelisKrea2NSFW_v10TURBOINT8Convrot.safetensors" ; do
  # Search both ComfyUI model roots (some boxes nest under ComfyUI/, some under models/)
  FOUND=""
  for base in "$COMFY_DIR" /home/ubuntu/ComfyUI /workspace/ComfyUI; do
    if [ -f "$base/models/$f" ]; then FOUND="$base/models/$f"; break; fi
  done
  if [ -n "$FOUND" ]; then
    ok "$(basename "$f")"
  else
    warn "MISSING: $f (verify path — 'hf download --local-dir' can double-nest loras/loras/)"
    MISSING=1
  fi
done
[ "$MISSING" -eq 1 ] && FAILED=1

echo "=========================================================="
if [ "$FAILED" -eq 0 ]; then
  echo -e "${GREEN}READY FOR H3 BATCH.${NC}"
  exit 0
else
  echo -e "${RED}NOT READY — fix the FAIL lines above, then re-run.${NC}"
  exit 1
fi