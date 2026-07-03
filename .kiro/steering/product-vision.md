---
inclusion: always
---

# AI Studio — Product Vision

## What we are building

AI Studio is a **commercial multi-tenant SaaS platform** for AI-powered content production. Its core purpose is to let brands and creators produce, manage, and deploy AI influencer content at scale — without needing to understand the underlying ML infrastructure.

## Target users

1. **Content creators and agencies** — managing multiple AI personas, brands, and campaigns
2. **Brands** — commissioning AI influencer content tied to products and campaigns
3. **Platform operators** — internal admin and multi-tenant management

## Key value propositions

- One platform from character creation → training → generation → publishing
- GPU cost efficiency via spot instance arbitrage (Vast.ai, RunPod)
- ComfyUI workflow portability — any workflow runs through the API
- Multi-tenant SaaS — strict per-organisation data isolation

## Core entities

```
Organisation → AiTalent → LoraModel
           → Brand → Product → Campaign → ContentJob → Asset
           → Workflow
```

## Non-negotiables

- Per-tenant data isolation is absolute (no cross-tenant leakage ever)
- All GPU jobs must have a cost estimate before dispatching
- Generated content must be attributable to a specific job, workflow, and model version
- The API must be the single source of truth — no side-channel state mutations
