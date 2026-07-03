# AI Studio — RunPod Workers

> Placeholder. RunPod worker integration is planned for a future priority.

---

## Overview

RunPod offers serverless and pod-based GPU compute. AI Studio will support
RunPod workers through the same Worker Manager interface used for Vast.ai.

---

## Planned Features

- Pod provisioning via RunPod API
- Serverless endpoint integration
- Same registration/heartbeat pattern as Vast.ai
- Cost comparison with Vast.ai for job routing

---

## Environment Variables (future)

```
RUNPOD_API_KEY=
RUNPOD_DEFAULT_GPU_TYPE=NVIDIA RTX 4090
```

---

## Implementation Notes

The Worker Manager and GPU routing already support multiple providers.
Adding RunPod requires only:
1. RunPod API client for provisioning
2. Worker startup script for RunPod pods
3. Registration call on pod startup

The generation pipeline, job routing, and dashboard remain unchanged.
