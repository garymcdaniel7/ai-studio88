#!/bin/bash
# Cleanly make ALL comfy_kitchen imports fail-soft so ComfyUI boots without it.
set -e
cd /root/ComfyUI

echo "=== wrap every bare 'import comfy_kitchen' in try/except ==="
python3 - <<'PYEOF'
import re, glob

FILES = [
    "comfy/float.py",
    "comfy/ldm/joyimage/model.py",
    "comfy/ldm/lightricks/vae/na_diffusion_decoder.py",
    "comfy/ldm/modules/attention.py",
    "comfy/text_encoders/llama.py",
    "comfy/model_management.py",
    "comfy/quant_ops.py",
]

for p in FILES:
    try:
        src = open(p).read()
    except FileNotFoundError:
        continue

    # Wrap bare "import comfy_kitchen as ck" and "import comfy_kitchen"
    src2 = re.sub(
        r"(?m)^(\s*)import comfy_kitchen( as \w+)?\s*$",
        r"try:\n\1    import comfy_kitchen\2\ntry:\n    pass\nexcept Exception:\n\1    pass",
        src,
    )
    # Cleaner: revert to a proper guard pattern
    src2 = src
    src2 = re.sub(
        r"(?m)^(\s*)import comfy_kitchen( as ck)?\s*$",
        r"try:\n\1    import comfy_kitchen\2\n\1    _CK_OK = True\nexcept Exception:\n\1    _CK_OK = False",
        src2,
    )
    src2 = re.sub(
        r"(?m)^(\s*)from comfy_kitchen import .*\s*$",
        r"try:\n\1    _LINE = r'''\g<0>'''\n\1    exec(_LINE)\n\1    _CK_OK = True\nexcept Exception:\n\1    _CK_OK = False",
        src2,
    )
    if src2 != src:
        open(p, "w").write(src2)
        print(f"patched {p}")
    else:
        print(f"no change {p}")
PYEOF

echo "=== check remaining bare imports at top level ==="
grep -rnE "^(import comfy_kitchen|from comfy_kitchen)" comfy/ --include="*.py" 2>/dev/null | head

echo "=== restart ComfyUI ==="
pkill -f "main.py" 2>/dev/null || true
sleep 2
setsid bash /root/start_comfyui.sh
sleep 45
echo "---COMFYUI PROCESS COUNT---"
ps aux | grep "[m]ain.py" | grep -v grep | wc -l
echo "---LOG (last 18)---"
tail -18 /root/comfyui.log 2>/dev/null
