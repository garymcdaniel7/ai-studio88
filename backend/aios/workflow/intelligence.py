"""Workflow Intelligence Engine — auto-configures generation parameters.

The core logic:
1. Analyze the request (what is being generated?)
2. Check Workflow DNA (what configs worked before for similar requests?)
3. Check Talent DNA (what does this talent prefer?)
4. Check model capabilities (what's loaded on the GPU?)
5. Apply model-specific defaults (Flux needs different params than SDXL)
6. Estimate cost and time
7. Return a complete GenerationConfig ready to submit

This replaces manual parameter selection. The user just says what they want,
and Workflow Intelligence figures out how to make it happen optimally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Model Knowledge — what each model is best at and its optimal settings
# =============================================================================

MODEL_PROFILES: dict[str, dict] = {
    "flux-dev": {
        "display_name": "Flux Dev",
        "best_for": ["portrait", "photorealism", "editorial", "luxury"],
        "default_steps": 20,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "default_resolution": (1024, 1024),
        "supports_negative": False,
        "vram_required_gb": 24,
        "avg_time_seconds": 45,
        "avg_cost_usd": 0.003,
        "quality_tier": "high",
    },
    "flux2-klein": {
        "display_name": "Flux 2 Klein",
        "best_for": ["fast_draft", "iteration", "concept"],
        "default_steps": 4,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "simple",
        "default_resolution": (1024, 1024),
        "supports_negative": False,
        "vram_required_gb": 12,
        "avg_time_seconds": 8,
        "avg_cost_usd": 0.0005,
        "quality_tier": "medium",
    },
    "sdxl-turbo": {
        "display_name": "SDXL Turbo",
        "best_for": ["fast_draft", "concept", "iteration"],
        "default_steps": 1,
        "default_cfg": 1.0,
        "default_sampler": "euler",
        "default_scheduler": "normal",
        "default_resolution": (512, 512),
        "supports_negative": True,
        "vram_required_gb": 8,
        "avg_time_seconds": 4,
        "avg_cost_usd": 0.0001,
        "quality_tier": "draft",
    },
    "sdxl": {
        "display_name": "SDXL 1.0",
        "best_for": ["general", "illustration", "anime", "concept"],
        "default_steps": 25,
        "default_cfg": 7.0,
        "default_sampler": "dpmpp_2m",
        "default_scheduler": "karras",
        "default_resolution": (1024, 1024),
        "supports_negative": True,
        "vram_required_gb": 12,
        "avg_time_seconds": 30,
        "avg_cost_usd": 0.002,
        "quality_tier": "high",
    },
    "sd15": {
        "display_name": "SD 1.5",
        "best_for": ["anime", "illustration", "lora_compatible"],
        "default_steps": 20,
        "default_cfg": 7.5,
        "default_sampler": "euler_a",
        "default_scheduler": "normal",
        "default_resolution": (512, 512),
        "supports_negative": True,
        "vram_required_gb": 6,
        "avg_time_seconds": 12,
        "avg_cost_usd": 0.0008,
        "quality_tier": "medium",
    },
    "wan-2.1": {
        "display_name": "WAN 2.1 (Video)",
        "best_for": ["video", "animation", "motion"],
        "default_steps": 20,
        "default_cfg": 5.0,
        "default_sampler": "euler",
        "default_scheduler": "normal",
        "default_resolution": (832, 480),
        "supports_negative": True,
        "vram_required_gb": 24,
        "avg_time_seconds": 120,
        "avg_cost_usd": 0.05,
        "quality_tier": "high",
    },
}


# =============================================================================
# Generation Config — the output of Workflow Intelligence
# =============================================================================


@dataclass
class GenerationConfig:
    """Complete configuration for a generation request."""
    model: str = "flux-dev"
    prompt: str = ""
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 1.0
    sampler: str = "euler"
    scheduler: str = "simple"
    seed: int = -1
    loras: list[dict] = field(default_factory=list)  # [{filename, strength, trigger_words}]
    controlnet: dict | None = None
    estimated_cost_usd: float = 0.0
    estimated_time_seconds: float = 0.0
    quality_tier: str = "high"
    reasoning: list[str] = field(default_factory=list)  # Why each param was chosen


# =============================================================================
# Workflow Intelligence — main entry point
# =============================================================================


def auto_configure(
    prompt: str,
    talent_id: str | None = None,
    content_type: str = "image",
    quality: str = "auto",  # draft, standard, high, auto
    platform: str | None = None,  # instagram, tiktok, youtube
    budget_max_usd: float | None = None,
) -> GenerationConfig:
    """Automatically determine the optimal generation configuration.

    Args:
        prompt: What the user wants to create
        talent_id: Talent context (loads DNA, LoRAs, preferences)
        content_type: image, video, voice
        quality: draft (fastest/cheapest), standard, high, auto (let system decide)
        platform: Target platform (affects resolution)
        budget_max_usd: Max cost allowed for this generation

    Returns:
        Complete GenerationConfig ready to submit to ComfyUI
    """
    config = GenerationConfig(prompt=prompt)
    reasoning = []

    # 1. Select model based on quality preference and content type
    model = _select_model(content_type, quality, budget_max_usd)
    config.model = model
    profile = MODEL_PROFILES.get(model, MODEL_PROFILES["flux-dev"])
    reasoning.append(f"Model: {profile['display_name']} — {profile['quality_tier']} quality, best for {', '.join(profile['best_for'][:3])}")

    # 2. Apply model defaults
    config.steps = profile["default_steps"]
    config.cfg = profile["default_cfg"]
    config.sampler = profile["default_sampler"]
    config.scheduler = profile["default_scheduler"]
    config.width, config.height = profile["default_resolution"]

    # 3. Adjust resolution for target platform
    if platform:
        w, h = _platform_resolution(platform, content_type)
        config.width, config.height = w, h
        reasoning.append(f"Resolution: {w}x{h} (optimized for {platform})")

    # 4. Load Talent DNA and apply preferences
    if talent_id:
        talent_config = _apply_talent_dna(config, talent_id)
        config = talent_config["config"]
        reasoning.extend(talent_config["reasoning"])

    # 5. Build negative prompt (model-specific + talent-specific)
    if profile["supports_negative"]:
        config.negative_prompt = _build_negative_prompt(talent_id, model)
        reasoning.append(f"Negative prompt: model-specific + talent avoidances")

    # 6. Check Workflow DNA for proven configs
    workflow_override = _check_workflow_dna(prompt, talent_id, content_type)
    if workflow_override:
        # Merge proven settings (don't override model selection)
        if workflow_override.get("steps"):
            config.steps = workflow_override["steps"]
        if workflow_override.get("cfg"):
            config.cfg = workflow_override["cfg"]
        reasoning.append(f"Workflow DNA: applied proven config (quality score {workflow_override.get('quality_score', 'N/A')})")

    # 7. Estimate cost and time
    config.estimated_cost_usd = profile["avg_cost_usd"]
    config.estimated_time_seconds = profile["avg_time_seconds"]
    config.quality_tier = profile["quality_tier"]
    config.reasoning = reasoning

    return config


# =============================================================================
# Internal logic
# =============================================================================


def _select_model(content_type: str, quality: str, budget_max: float | None) -> str:
    """Select the best model for the request."""
    if content_type == "video":
        return "wan-2.1"

    if quality == "draft":
        return "sdxl-turbo"
    elif quality == "standard":
        return "sdxl"
    elif quality == "high":
        return "flux-dev"

    # Auto: pick based on budget
    if budget_max is not None and budget_max < 0.001:
        return "sdxl-turbo"

    # Default to high quality
    return "flux-dev"


def _platform_resolution(platform: str, content_type: str) -> tuple[int, int]:
    """Get optimal resolution for a target platform."""
    PLATFORM_RESOLUTIONS = {
        "instagram": {"image": (1080, 1080), "video": (1080, 1920)},
        "tiktok": {"image": (1080, 1920), "video": (1080, 1920)},
        "youtube": {"image": (1920, 1080), "video": (1920, 1080)},
        "twitter": {"image": (1200, 675), "video": (1920, 1080)},
        "linkedin": {"image": (1200, 627), "video": (1920, 1080)},
        "pinterest": {"image": (1000, 1500), "video": (1080, 1920)},
    }
    platform_config = PLATFORM_RESOLUTIONS.get(platform, {})
    return platform_config.get(content_type, (1024, 1024))


def _apply_talent_dna(config: GenerationConfig, talent_id: str) -> dict:
    """Load Talent DNA and apply to config."""
    reasoning = []

    try:
        # Get talent profile
        talent = _db().table("talent").select(
            "name,trigger_words,negative_prompt,visual_style"
        ).eq("id", talent_id).single().execute().data

        if talent:
            # Inject trigger words into prompt
            trigger = talent.get("trigger_words", "")
            if trigger and trigger not in config.prompt:
                config.prompt = f"{trigger}, {config.prompt}"
                reasoning.append(f"Talent: injected trigger words '{trigger}'")

        # Get always-on LoRAs for this talent
        loras = _db().table("talent_loras").select(
            "model_id,name,strength,metadata"
        ).eq("talent_id", talent_id).eq("always_on", True).execute().data or []

        for lora in loras:
            meta = lora.get("metadata") or {}
            config.loras.append({
                "model_id": lora.get("model_id"),
                "name": lora.get("name", ""),
                "strength": float(lora.get("strength", 0.7)),
                "trigger_words": meta.get("trigger_words", []),
            })

        if config.loras:
            reasoning.append(f"LoRAs: {len(config.loras)} always-on ({', '.join(l['name'] for l in config.loras)})")

    except Exception as e:
        logger.debug(f"Talent DNA load failed: {e}")

    return {"config": config, "reasoning": reasoning}


def _build_negative_prompt(talent_id: str | None, model: str) -> str:
    """Build negative prompt from model defaults + talent avoided styles."""
    parts = []

    # Model-specific negatives
    MODEL_NEGATIVES = {
        "sdxl": "low quality, blurry, deformed, ugly, bad anatomy, watermark, text",
        "sdxl-turbo": "low quality, blurry",
        "sd15": "low quality, blurry, deformed, ugly, bad anatomy, extra limbs, watermark",
        "wan-2.1": "low quality, blurry, static, no motion, watermark",
    }
    parts.append(MODEL_NEGATIVES.get(model, ""))

    # Talent-specific avoidances
    if talent_id:
        try:
            talent = _db().table("talent").select("negative_prompt").eq("id", talent_id).single().execute().data
            if talent and talent.get("negative_prompt"):
                parts.append(talent["negative_prompt"])

            # Creative DNA avoided styles
            dna = _db().table("creative_dna").select("avoided_styles,negative_prompt_rules").eq("talent_id", talent_id).execute().data
            if dna:
                d = dna[0]
                avoided = d.get("avoided_styles") or []
                neg_rules = d.get("negative_prompt_rules") or []
                parts.extend(avoided)
                parts.extend(neg_rules)
        except Exception:
            pass

    return ", ".join(p for p in parts if p)


def _check_workflow_dna(prompt: str, talent_id: str | None, content_type: str) -> dict | None:
    """Check if Workflow DNA has a proven config for similar requests."""
    try:
        from backend.aios.knowledge.workflow_dna import recommend_workflow

        # Infer style hints from prompt
        style_hints = []
        prompt_lower = prompt.lower()
        for style in ["portrait", "luxury", "cinematic", "editorial", "anime", "product", "landscape"]:
            if style in prompt_lower:
                style_hints.append(style)

        recommendations = recommend_workflow(
            content_type=content_type,
            talent_id=talent_id,
            style_hints=style_hints,
            limit=1,
        )

        if recommendations and float(recommendations[0].get("quality_score", 0)) >= 4.0:
            return recommendations[0]

    except Exception:
        pass
    return None
