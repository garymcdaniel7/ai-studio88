# GPU Worker Security Contract (Story 049)

## Runtime User

| Property | Production | Debug |
|----------|:----------:|:-----:|
| ComfyUI process | `comfyui` (UID 1000) | `comfyui` (UID 1000) |
| Ollama process | `comfyui` (UID 1000) | `comfyui` (UID 1000) |
| SSH server | ❌ Not installed | `root` (sshd only) |
| SSH user | N/A | `debuguser` (non-root) |
| Root login | ❌ Impossible | ❌ Disabled in sshd_config |

## Exposed Ports

| Port | Service | Production | Debug |
|------|---------|:----------:|:-----:|
| 8188 | ComfyUI API | ✅ | ✅ |
| 11434 | Ollama LLM | ✅ | ✅ |
| 22 | SSH | ❌ Not exposed | ✅ (key-only) |

## Writable Mounts (explicit)

```
/workspace/ComfyUI/models/    — Downloaded model weights
/workspace/ComfyUI/output/    — Generation output files
/workspace/ComfyUI/input/     — Uploaded input files
/workspace/ComfyUI/temp/      — Temporary processing
/workspace/SimpleTuner/       — Training workspace
/tmp/                         — System temp (tmpfs, noexec, nosuid)
```

Everything else is read-only root filesystem.

## Capabilities

```bash
# Drop ALL capabilities, add only what's needed
--cap-drop ALL
--cap-add SYS_PTRACE  # Required for GPU debugging/profiling
```

## Secrets Injection

| Method | ✅ / ❌ |
|--------|:---:|
| Runtime env vars (`docker run -e KEY=val`) | ✅ Approved |
| Mounted secrets file (`-v ./secrets:/run/secrets:ro`) | ✅ Preferred |
| Baked into Docker layers | ❌ NEVER |
| Passed in Dockerfile ARG/ENV | ❌ NEVER |
| Visible in `docker inspect` | ⚠️ Accepted risk for env vars |

## Network

```
INBOUND:
  8188/tcp — ComfyUI API (from backend SSH tunnel or proxy)
  11434/tcp — Ollama API (localhost or backend tunnel)

OUTBOUND:
  443/tcp — HTTPS to:
    - *.backblazeb2.com (model cache download)
    - huggingface.co (model fallback download)
    - ollama.com (model registry)
    - registry.ollama.ai (model pulls)
```

## Emergency Debug Profile

| Property | Value |
|----------|-------|
| Image target | `docker build --target debug` |
| SSH auth | Public key only (mounted at runtime) |
| Root login | Disabled |
| Session timeout | 10 min idle (ClientAliveInterval=60, Count=10) |
| Max sessions | 2 |
| Login grace | 30 seconds |
| Max auth tries | 3 |
| Audit | Container logs record activation timestamp |

### Usage

```bash
# Build debug image (separate from production)
docker build -f Dockerfile.hardened --target debug -t worker:debug .

# Run with SSH key mounted (time-limited by operator)
docker run --gpus all \
  -v ./operator_key.pub:/home/debuguser/.ssh/authorized_keys:ro \
  -p 8188:8188 -p 2222:22 \
  -e B2_KEY_ID -e B2_APPLICATION_KEY \
  worker:debug
```

## Image Scanning

Run before deployment:

```bash
# Vulnerability scan
docker scout cves garymcdaniel7/ai-studio-worker:hardened

# Secret detection
trivy image --scanners secret garymcdaniel7/ai-studio-worker:hardened

# Layer inspection (verify no secrets baked in)
docker history garymcdaniel7/ai-studio-worker:hardened --no-trunc
```

## Comparison: Old vs Hardened

| Property | Old Image | Hardened |
|----------|:---------:|:--------:|
| Runtime user | root | comfyui (1000) |
| SSH | Always on, root login | ❌ Removed |
| Debug tools | nano, htop always | ❌ Not in production |
| Port 22 | Exposed | ❌ Not exposed |
| Read-only FS | No | Yes (with explicit mounts) |
| Capabilities | All (default) | Drop ALL + SYS_PTRACE |
| Secrets in layers | Not verified | Verified clean |
| Health check | ✅ | ✅ |
| Multi-stage | No | Yes (smaller image) |
