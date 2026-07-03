# Skill: Create Vast.ai Worker Integration

## Purpose

Provision and manage Vast.ai GPU instances for generation or training jobs.

## Key pattern

```python
from app.services.vastai_service import VastAiService

vastai = VastAiService(api_key=settings.vastai_api_key)
instance_id = None

try:
    offers = await vastai.search_offers(
        gpu_name=settings.vastai_default_gpu_type,
        num_gpus=1,
        min_disk_gb=50,
        max_price_usd=0.80,
    )
    if not offers:
        raise VastAiProvisionError("No suitable GPU offers available")

    instance = await vastai.create_instance(
        offer_id=offers[0].id,
        image="vastai/comfyui:latest",
        disk_gb=50,
        env={"JOB_ID": job_id},
    )
    instance_id = instance.id
    instance = await vastai.wait_for_ready(instance.id, timeout=300)

    # ... do work ...

finally:
    if instance_id:
        await vastai.destroy_instance(instance_id)  # ALWAYS in finally
```

## VastAiService methods

- `search_offers(gpu_name, num_gpus, min_disk_gb, max_price_usd)` → list of offers
- `create_instance(offer_id, image, disk_gb, env, onstart)` → instance
- `wait_for_ready(instance_id, timeout=300)` → instance when running
- `destroy_instance(instance_id)` → None (safe to call even if already gone)
- `get_instance(instance_id)` → current instance state

## Cost tracking

Always record on the job after completion:
- `cost_usd`, `gpu_provider`, `gpu_type`, `instance_id`, `runtime_seconds`
