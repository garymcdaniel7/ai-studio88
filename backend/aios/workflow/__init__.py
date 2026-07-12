"""AIOS Workflow Intelligence — automatic generation parameter selection.

Given a request (prompt, talent, content type), determines the optimal:
- Checkpoint model
- LoRA selection + strength balancing
- Sampler/scheduler
- CFG, steps, resolution
- Negative prompt (model-specific + DNA-specific)
- Cost/quality tradeoff

Learns from Workflow DNA (successful past configs) and Talent DNA (preferences).
"""
