"""IntelligenceContext — shared state passed to all agents.

This is the single source of truth agents reason over. It aggregates
project, talent, DNA, history, feedback, models, and GPU state into
one coherent context object. Agents read from it; they never mutate it directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntelligenceContext:
    """Complete context for all AI agents to reason over."""

    # ── User Intent ───────────────────────────────────────────────────────────
    user_idea: str = ""
    content_type: str = "image"  # image, video, carousel, story, reel, ad, campaign
    platform: str = "instagram"
    target_audience: str = ""

    # ── Project / Talent ──────────────────────────────────────────────────────
    project_id: str | None = None
    project_name: str = ""
    talent_id: str | None = None
    talent_name: str = ""
    talent_bio: str = ""
    campaign: str = ""

    # ── Creative DNA ──────────────────────────────────────────────────────────
    creative_dna: dict = field(default_factory=dict)
    # Extracted from DNA for convenience:
    preferred_styles: list[str] = field(default_factory=list)
    avoided_styles: list[str] = field(default_factory=list)
    color_palette: list[str] = field(default_factory=list)
    camera_preferences: dict = field(default_factory=dict)
    wardrobe_preferences: dict = field(default_factory=dict)
    setting_preferences: dict = field(default_factory=dict)
    prompt_rules: list[str] = field(default_factory=list)
    negative_prompt_rules: list[str] = field(default_factory=list)
    lora_preferences: dict = field(default_factory=dict)
    model_preferences: dict = field(default_factory=dict)

    # ── History ───────────────────────────────────────────────────────────────
    previous_generations: list[dict] = field(default_factory=list)
    recent_feedback: list[dict] = field(default_factory=list)
    recent_problems: list[str] = field(default_factory=list)
    average_rating: float | None = None
    prompt_history: list[dict] = field(default_factory=list)

    # ── Available Resources ───────────────────────────────────────────────────
    available_models: list[dict] = field(default_factory=list)
    available_loras: list[dict] = field(default_factory=list)
    gpu_status: dict = field(default_factory=dict)

    # ── Story / Continuity ────────────────────────────────────────────────────
    story_context: dict = field(default_factory=dict)
    continuity_notes: list[str] = field(default_factory=list)
    series_assets: list[dict] = field(default_factory=list)

    # ── Session ───────────────────────────────────────────────────────────────
    session_id: str = ""


def build_context_from_request(
    user_idea: str,
    talent_id: str | None = None,
    project_id: str | None = None,
    platform: str = "instagram",
    content_type: str = "image",
    campaign: str = "",
    target_audience: str = "",
) -> IntelligenceContext:
    """Build a full IntelligenceContext from a user request, loading data from DB.

    This is the main entry point for populating context before running agents.
    """
    import uuid
    ctx = IntelligenceContext(
        user_idea=user_idea,
        content_type=content_type,
        platform=platform,
        campaign=campaign,
        target_audience=target_audience,
        project_id=project_id,
        talent_id=talent_id,
        session_id=uuid.uuid4().hex[:12],
    )

    if not talent_id:
        return ctx

    # Load talent info
    try:
        from backend.database import supabase
        talent_result = supabase.table("talent").select("*").eq("id", talent_id).single().execute()
        talent = talent_result.data
        ctx.talent_name = talent.get("name", "")
        ctx.talent_bio = talent.get("bio", "")
    except Exception:
        pass

    # Load project info
    if project_id:
        try:
            from backend.database import supabase
            proj = supabase.table("projects").select("*").eq("id", project_id).single().execute()
            ctx.project_name = proj.data.get("name", "")
        except Exception:
            pass

    # Load Creative DNA
    try:
        from backend.database import get_creative_dna_by_talent
        dna = get_creative_dna_by_talent(talent_id).data
        ctx.creative_dna = dna
        ctx.preferred_styles = dna.get("preferred_styles", [])
        ctx.avoided_styles = dna.get("avoided_styles", [])
        ctx.color_palette = dna.get("color_palette", [])
        ctx.camera_preferences = dna.get("camera_preferences", {})
        ctx.wardrobe_preferences = dna.get("wardrobe_preferences", {})
        ctx.setting_preferences = dna.get("setting_preferences", {})
        ctx.prompt_rules = dna.get("prompt_rules", [])
        ctx.negative_prompt_rules = dna.get("negative_prompt_rules", [])
        ctx.lora_preferences = dna.get("lora_preferences", {})
        ctx.model_preferences = dna.get("model_preferences", {})
    except Exception:
        pass

    # Load recent feedback / problems
    try:
        from backend.database import get_recent_problems, get_average_rating, get_feedback
        ctx.recent_problems = get_recent_problems(talent_id, limit=20)
        ctx.average_rating = get_average_rating(talent_id)
        fb = get_feedback(talent_id=talent_id, limit=10)
        ctx.recent_feedback = fb.data if fb.data else []
    except Exception:
        pass

    # Load previous generations (from assets with generation tags)
    try:
        from backend.database import supabase
        gens = (
            supabase.table("assets")
            .select("*")
            .eq("talent_id", talent_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        ctx.previous_generations = gens.data or []
    except Exception:
        pass

    # Load available models from engine
    try:
        from backend.engine.generation_engine import get_model_registry, get_gpu_status
        ctx.available_models = [
            {"id": m.id, "name": m.name, "type": m.type, "vram": m.required_vram_gb}
            for m in get_model_registry()
        ]
        gpu = get_gpu_status()
        ctx.gpu_status = {
            "name": gpu.name,
            "vram_total_gb": gpu.vram_total_gb,
            "vram_free_gb": gpu.vram_free_gb,
            "status": gpu.status,
            "utilization_pct": gpu.utilization_pct,
        }
    except Exception:
        pass

    return ctx
