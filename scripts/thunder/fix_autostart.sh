#!/bin/bash
# Update /etc/thunder/client-extra.sh to use the robust Ollama auto-start script.
set -e

BLOCK_START="# ── AI Studio Brain"
# Remove the old AI Studio Brain block if present
if grep -q "AI Studio Brain" /etc/thunder/client-extra.sh; then
  python3 - <<'PY'
path = "/etc/thunder/client-extra.sh"
with open(path) as f:
    lines = f.readlines()
out = []
skip = False
for ln in lines:
    if "AI Studio Brain" in ln:
        skip = True
        continue
    if skip:
        if "────" in ln and "Brain" not in ln:
            skip = False
            continue
        if ln.strip() == "fi":
            skip = False
            continue
        continue
    out.append(ln)
with open(path, "w") as f:
    f.writelines(out)
print("removed old block")
PY
fi

# Append the robust block
cat >> /etc/thunder/client-extra.sh <<'EOF'

# ── AI Studio Brain: auto-start Ollama on boot (robust) ────────────
if ! pgrep -f "ollama serve" > /dev/null 2>&1; then
    sudo -u ubuntu bash /etc/thunder/start_ollama.sh > /tmp/ollama_autostart.log 2>&1 &
fi
# ────────────────────────────────────────────────────────────────────
EOF

echo "--- final client-extra.sh tail: ---"
tail -10 /etc/thunder/client-extra.sh
