"""Preset Packs — Curated generation presets that bundle workflow + model + tuning.

Each preset encapsulates:
- A ComfyUI workflow template
- Default generation parameters optimized for the use case
- The required model/checkpoint
- Example prompt structure
- VRAM requirements for GPU compatibility badges

Users pick a preset from the browser → it pre-fills all settings → they just change the prompt.
This is the SimpliGen "style packs" equivalent for AI Studio.
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# Preset Pack Definitions
# =============================================================================

PRESET_PACKS: list[dict[str, Any]] = [
    # ── Core 10 ──────────────────────────────────────────────────────────────
    {
        "id": "cinematic-portrait",
        "name": "Cinematic Portrait",
        "category": "image",
        "description": "High-quality cinematic portraits with dramatic lighting. Perfect for talent headshots and editorial content.",
        "model": "flux-dev",
        "workflow": "flux_dev",
        "defaults": {
            "steps": 25,
            "cfg": 1.0,
            "guidance": 3.5,
            "width": 1024,
            "height": 1024,
            "sampler": "euler",
        },
        "prompt_template": "{subject}, cinematic portrait, dramatic lighting, shallow depth of field, 85mm lens, studio quality",
        "negative_prompt": "blurry, low quality, deformed, watermark, text, bad anatomy",
        "supports_lora": True,
        "required_vram_gb": 32,
        "badge": "Best Quality",
        "tags": ["portrait", "cinematic", "editorial", "headshot"],
    },
    {
        "id": "product-shot",
        "name": "Product Shot",
        "category": "image",
        "description": "Clean product photography on white/gradient backgrounds. E-commerce ready.",
        "model": "flux-dev",
        "workflow": "flux_dev",
        "defaults": {
            "steps": 20,
            "cfg": 1.0,
            "guidance": 4.0,
            "width": 1024,
            "height": 1024,
            "sampler": "euler",
        },
        "prompt_template": "{product}, professional product photography, white background, studio lighting, high detail, commercial quality",
        "negative_prompt": "blurry, dark, shadow, person, hand",
        "supports_lora": False,
        "required_vram_gb": 32,
        "badge": "E-Commerce",
        "tags": ["product", "ecommerce", "white-background", "commercial"],
    },
    {
        "id": "fast-draft",
        "name": "Fast Draft",
        "category": "image",
        "description": "Lightning-fast previews for storyboard thumbnails. 1 step, instant results.",
        "model": "sdxl-turbo",
        "workflow": "sdxl_turbo",
        "defaults": {"steps": 1, "cfg": 1.0, "width": 512, "height": 512, "sampler": "euler"},
        "prompt_template": "{description}",
        "negative_prompt": "",
        "supports_lora": False,
        "required_vram_gb": 8,
        "badge": "Instant",
        "tags": ["fast", "preview", "storyboard", "draft"],
    },
    {
        "id": "anime-illustration",
        "name": "Anime / Illustration",
        "category": "image",
        "description": "Stylized anime and illustration art. Great for character design and concept art.",
        "model": "sdxl-turbo",
        "workflow": "sdxl_turbo",
        "defaults": {"steps": 4, "cfg": 2.0, "width": 1024, "height": 1024, "sampler": "euler"},
        "prompt_template": "{character}, anime style, illustration, vibrant colors, detailed, clean lines",
        "negative_prompt": "photorealistic, blurry, low quality",
        "supports_lora": True,
        "required_vram_gb": 8,
        "badge": "Creative",
        "tags": ["anime", "illustration", "character", "concept-art"],
    },
    {
        "id": "landscape-environment",
        "name": "Landscape / Environment",
        "category": "image",
        "description": "Photorealistic landscapes and environments. Ideal for backgrounds and scene-setting.",
        "model": "flux-dev",
        "workflow": "flux_dev",
        "defaults": {
            "steps": 20,
            "cfg": 1.0,
            "guidance": 3.5,
            "width": 1536,
            "height": 1024,
            "sampler": "euler",
        },
        "prompt_template": "{scene}, landscape photography, golden hour, photorealistic, wide angle, high detail",
        "negative_prompt": "person, text, watermark, blurry",
        "supports_lora": False,
        "required_vram_gb": 32,
        "badge": "Scenic",
        "tags": ["landscape", "environment", "background", "scenic"],
    },
    {
        "id": "text-to-video-short",
        "name": "Text-to-Video (Short)",
        "category": "video",
        "description": "Generate 2-4 second video clips from text descriptions using WAN 2.1.",
        "model": "wan-2.1-t2v",
        "workflow": "wan21_t2v_simple",
        "defaults": {"duration": 3, "fps": 24, "width": 832, "height": 480},
        "prompt_template": "{action}, cinematic, smooth motion, high quality",
        "negative_prompt": "static, blurry, glitch",
        "supports_lora": False,
        "required_vram_gb": 80,
        "badge": "Video",
        "tags": ["video", "t2v", "short-clip", "motion"],
    },
    {
        "id": "image-to-video-animate",
        "name": "Image-to-Video (Animate)",
        "category": "video",
        "description": "Animate any still image into a video clip. Bring photos to life.",
        "model": "wan-2.1-i2v",
        "workflow": "wan21_i2v_simple",
        "defaults": {"duration": 3, "fps": 24},
        "prompt_template": "subtle motion, cinematic, natural movement",
        "negative_prompt": "static, sudden movement, glitch",
        "supports_lora": False,
        "required_vram_gb": 80,
        "badge": "Animate",
        "tags": ["video", "i2v", "animate", "motion"],
    },
    {
        "id": "upscale-4x",
        "name": "Upscale 4x",
        "category": "utility",
        "description": "Upscale any image to 4x resolution using AI super-resolution.",
        "model": "sdxl-turbo",
        "workflow": "sdxl_turbo",
        "defaults": {"steps": 10, "cfg": 7.0, "width": 2048, "height": 2048, "sampler": "euler"},
        "prompt_template": "high resolution, ultra detailed, sharp, 4k",
        "negative_prompt": "blurry, pixelated, noise, artifacts",
        "supports_lora": False,
        "required_vram_gb": 12,
        "badge": "Enhance",
        "tags": ["upscale", "enhance", "resolution", "4k"],
    },
    {
        "id": "inpaint-edit",
        "name": "Inpaint / Edit",
        "category": "utility",
        "description": "Edit specific regions of an existing image. Requires mask input.",
        "model": "flux-dev",
        "workflow": "flux_dev",
        "defaults": {
            "steps": 20,
            "cfg": 1.0,
            "guidance": 3.5,
            "width": 1024,
            "height": 1024,
            "sampler": "euler",
        },
        "prompt_template": "{edit_description}",
        "negative_prompt": "blurry, inconsistent, visible seam",
        "supports_lora": True,
        "required_vram_gb": 32,
        "badge": "Edit",
        "tags": ["inpaint", "edit", "mask", "modify"],
    },
    {
        "id": "lora-portrait",
        "name": "LoRA Portrait",
        "category": "image",
        "description": "Identity-locked generation using a trained LoRA. Maintains character consistency.",
        "model": "flux-dev",
        "workflow": "flux_dev",
        "defaults": {
            "steps": 25,
            "cfg": 1.0,
            "guidance": 3.5,
            "width": 1024,
            "height": 1024,
            "sampler": "euler",
        },
        "prompt_template": "{trigger_word}, portrait, professional photography, high quality",
        "negative_prompt": "blurry, deformed, low quality, bad anatomy",
        "supports_lora": True,
        "required_vram_gb": 32,
        "badge": "Identity",
        "tags": ["lora", "portrait", "identity", "character-lock"],
    },
    # ── Advanced 6 ───────────────────────────────────────────────────────────
    {
        "id": "controlnet-pose",
        "name": "ControlNet Pose",
        "category": "advanced",
        "description": "Match a specific pose from a reference image using ControlNet.",
        "model": "sdxl-turbo",
        "workflow": "sdxl_turbo",
        "defaults": {"steps": 20, "cfg": 7.0, "width": 1024, "height": 1024, "sampler": "euler"},
        "prompt_template": "{subject}, matching pose, high quality",
        "negative_prompt": "different pose, blurry",
        "supports_lora": True,
        "required_vram_gb": 12,
        "badge": "Pose",
        "tags": ["controlnet", "pose", "reference", "advanced"],
    },
    {
        "id": "ip-adapter-style",
        "name": "IP-Adapter Style Transfer",
        "category": "advanced",
        "description": "Copy the visual style from a reference image to new content.",
        "model": "sdxl-turbo",
        "workflow": "sdxl_turbo",
        "defaults": {"steps": 20, "cfg": 7.0, "width": 1024, "height": 1024, "sampler": "euler"},
        "prompt_template": "{subject}, in the style of reference",
        "negative_prompt": "different style, inconsistent",
        "supports_lora": False,
        "required_vram_gb": 12,
        "badge": "Style",
        "tags": ["ip-adapter", "style-transfer", "reference", "advanced"],
    },
    {
        "id": "long-video",
        "name": "Long Video (10s+)",
        "category": "video",
        "description": "Extended video generation for longer clips. Uses WAN 2.1 with extended frames.",
        "model": "wan-2.1-t2v",
        "workflow": "wan21_t2v_native",
        "defaults": {"duration": 10, "fps": 24, "width": 832, "height": 480},
        "prompt_template": "{scene_description}, cinematic, smooth continuous motion",
        "negative_prompt": "jump cut, static, glitch, repetitive",
        "supports_lora": False,
        "required_vram_gb": 80,
        "badge": "Extended",
        "tags": ["video", "long", "extended", "10-seconds"],
    },
    {
        "id": "fashion-lookbook",
        "name": "Fashion Lookbook",
        "category": "image",
        "description": "Multi-angle fashion and clothing shots. Editorial quality.",
        "model": "flux-dev",
        "workflow": "flux_dev",
        "defaults": {
            "steps": 25,
            "cfg": 1.0,
            "guidance": 3.5,
            "width": 1024,
            "height": 1536,
            "sampler": "euler",
        },
        "prompt_template": "{model_description} wearing {outfit}, fashion editorial, full body, studio lighting, lookbook style",
        "negative_prompt": "blurry, cropped, low quality, bad proportions",
        "supports_lora": True,
        "required_vram_gb": 32,
        "badge": "Fashion",
        "tags": ["fashion", "lookbook", "editorial", "full-body"],
    },
    {
        "id": "film-grain-vintage",
        "name": "Film Grain / Vintage",
        "category": "image",
        "description": "Vintage film look with grain, color shift, and analog feel.",
        "model": "sdxl-turbo",
        "workflow": "sdxl_turbo",
        "defaults": {"steps": 8, "cfg": 5.0, "width": 1024, "height": 1024, "sampler": "euler"},
        "prompt_template": "{subject}, vintage film photography, film grain, analog, 35mm, kodak portra",
        "negative_prompt": "digital, clean, modern, sharp",
        "supports_lora": True,
        "required_vram_gb": 8,
        "badge": "Vintage",
        "tags": ["vintage", "film-grain", "analog", "retro"],
    },
    {
        "id": "hdr-luxury",
        "name": "HDR / Luxury",
        "category": "image",
        "description": "Ultra-sharp luxury and real estate photography with HDR look.",
        "model": "flux-dev",
        "workflow": "flux_dev",
        "defaults": {
            "steps": 30,
            "cfg": 1.0,
            "guidance": 5.0,
            "width": 1536,
            "height": 1024,
            "sampler": "euler",
        },
        "prompt_template": "{subject}, luxury photography, HDR, ultra sharp, golden hour, high dynamic range, commercial quality",
        "negative_prompt": "flat, dull, low contrast, amateur",
        "supports_lora": False,
        "required_vram_gb": 32,
        "badge": "Luxury",
        "tags": ["hdr", "luxury", "real-estate", "commercial"],
    },
]


# =============================================================================
# Public API
# =============================================================================


def get_all_presets() -> list[dict]:
    """Get all preset packs."""
    return PRESET_PACKS


def get_presets_by_category(category: str) -> list[dict]:
    """Get presets filtered by category (image, video, utility, advanced)."""
    return [p for p in PRESET_PACKS if p["category"] == category]


def get_preset_by_id(preset_id: str) -> dict | None:
    """Get a single preset by its ID."""
    for p in PRESET_PACKS:
        if p["id"] == preset_id:
            return p
    return None
