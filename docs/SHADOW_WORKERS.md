# AI Studio — Shadow PC Workers

> Placeholder. Shadow PC worker integration is planned for a future priority.

---

## Overview

Shadow PC provides persistent cloud gaming PCs with GPU access.
AI Studio will support Shadow as a worker provider for always-on generation
without per-hour billing.

---

## Planned Features

- Persistent worker (always online, no per-job startup cost)
- ComfyUI running as a service on Shadow PC
- Automatic registration on Shadow PC boot
- Heartbeat via scheduled task / systemd timer

---

## Advantages over Vast.ai

- Fixed monthly cost (no per-hour billing)
- Always available (no provisioning delay)
- Consistent environment (models stay downloaded)
- Good for development and low-volume production

---

## Limitations

- Limited GPU options (usually RTX 4090 or equivalent)
- Single worker per Shadow subscription
- Not suitable for burst/parallel workloads

---

## Implementation Notes

Same Worker Manager interface as Vast.ai/RunPod.
Worker registers on boot, sends heartbeats, accepts jobs via ComfyUI API.
