"""Workflow DNA — learned generation configurations that produce good results.

When a user rates a generation highly (4-5 stars), the workflow config
(model, LoRAs, steps, CFG, sampler, resolution, prompt structure)
is captured as a Workflow DNA recipe.

Over time, this builds a library of "what works" for each:
- Content type (portrait, product, landscape, video)
- Talent (specific talent preferences)
- Style (luxury, editorial, casual, anime)

The system recommends these configs for similar future requests.

Table: workflow_dna
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


@dataclass
class WorkflowRecipe:
    """A learned workflow configuration."""
    id: str = ""
    name: str = ""
    content_type: str = "image"       # image, video, voice
    checkpoint: str = ""              # flux-dev, sdxl-turbo
    loras: list[dict] = field(default_factory=list)  # [{model_id, strength, trigger_words}]
    sampler: str = "euler"
    scheduler: str = "normal"
    cfg: float = 7.0
    steps: int = 20
    width: int = 1024
    height: int = 1024
    negative_prompt: str = ""
    quality_score: float = 0.0        # Average user rating (1-5)
    success_rate: float = 0.0         # % of generations rated 4+
    usage_count: int = 0
    avg_generation_time: float = 0.0
    avg_cost: float = 0.0
    recommended_for: list[str] = field(default_factory=list)  # ["portrait", "luxury"]
    talent_id: str | None = None      # If talent-specific
    source: str = "auto_learned"      # auto_learned, manual, community


def capture_workflow(
    generation_config: dict,
    rating: int,
    talent_id: str | None = None,
    content_type: str = "image",
) -> dict | None:
    """Capture a successful generation config as Workflow DNA.

    Only captures configs rated 4+ stars.
    Updates existing recipe if similar config found.
    """
    if rating < 4:
        return None  # Only learn from good results

    recipe_record = {
        "name": _generate_recipe_name(generation_config),
        "content_type": content_type,
        "checkpoint": generation_config.get("model", ""),
        "loras": generation_config.get("loras", []),
        "sampler": generation_config.get("sampler", "euler"),
        "scheduler": generation_config.get("scheduler", "normal"),
        "cfg": float(generation_config.get("cfg", 7.0)),
        "steps": int(generation_config.get("steps", 20)),
        "width": int(generation_config.get("width", 1024)),
        "height": int(generation_config.get("height", 1024)),
        "negative_prompt": generation_config.get("negative_prompt", ""),
        "quality_score": float(rating),
        "success_rate": 1.0,  # First capture = 100%
        "usage_count": 1,
        "avg_generation_time": float(generation_config.get("generation_time", 0)),
        "avg_cost": float(generation_config.get("cost", 0)),
        "recommended_for": _infer_categories(generation_config),
        "talent_id": talent_id,
        "source": "auto_learned",
        "config_snapshot": generation_config,  # Full config for reproduction
    }

    try:
        result = _db().table("workflow_dna").insert(recipe_record).execute()
        return result.data[0] if result.data else recipe_record
    except Exception as e:
        logger.warning(f"Failed to capture workflow DNA: {e}")
        return None


def recommend_workflow(
    content_type: str = "image",
    talent_id: str | None = None,
    style_hints: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    """Recommend workflow configs based on past success.

    Returns top-rated recipes matching the request context.
    """
    try:
        query = (
            _db().table("workflow_dna")
            .select("*")
            .eq("content_type", content_type)
            .order("quality_score", desc=True)
            .limit(limit * 3)  # Over-fetch for filtering
        )

        if talent_id:
            # Prefer talent-specific recipes
            talent_results = query.eq("talent_id", talent_id).execute().data or []
            # Also get general recipes
            general_results = (
                _db().table("workflow_dna")
                .select("*")
                .eq("content_type", content_type)
                .is_("talent_id", "null")
                .order("quality_score", desc=True)
                .limit(limit)
                .execute().data or []
            )
            all_results = talent_results + general_results
        else:
            all_results = query.execute().data or []

        # Filter by style hints if provided
        if style_hints:
            scored = []
            for r in all_results:
                rec_for = r.get("recommended_for", []) or []
                overlap = len(set(style_hints) & set(rec_for))
                scored.append((r, overlap))
            scored.sort(key=lambda x: (-x[1], -float(x[0].get("quality_score", 0))))
            all_results = [s[0] for s in scored]

        return all_results[:limit]

    except Exception as e:
        logger.warning(f"Workflow DNA recommendation failed: {e}")
        return []


def get_workflow_stats() -> dict:
    """Get aggregate Workflow DNA statistics."""
    try:
        all_recipes = _db().table("workflow_dna").select("content_type,quality_score,usage_count,checkpoint").execute().data or []

        if not all_recipes:
            return {"total_recipes": 0}

        by_type = {}
        by_model = {}
        for r in all_recipes:
            ct = r.get("content_type", "unknown")
            model = r.get("checkpoint", "unknown")
            by_type[ct] = by_type.get(ct, 0) + 1
            by_model[model] = by_model.get(model, 0) + 1

        avg_quality = sum(float(r.get("quality_score", 0)) for r in all_recipes) / len(all_recipes)

        return {
            "total_recipes": len(all_recipes),
            "by_content_type": by_type,
            "by_model": by_model,
            "avg_quality_score": round(avg_quality, 2),
            "total_usage": sum(r.get("usage_count", 0) for r in all_recipes),
        }
    except Exception:
        return {"total_recipes": 0}


def _generate_recipe_name(config: dict) -> str:
    """Generate a human-readable name for a workflow recipe."""
    model = config.get("model", "unknown")
    prompt = config.get("prompt", "")

    # Extract key descriptors from prompt
    keywords = []
    style_words = ["portrait", "landscape", "product", "editorial", "luxury", "cinematic", "anime"]
    for word in style_words:
        if word in prompt.lower():
            keywords.append(word.title())

    if keywords:
        return f"{model} — {', '.join(keywords[:3])}"
    return f"{model} — Custom ({config.get('steps', 20)} steps)"


def _infer_categories(config: dict) -> list[str]:
    """Infer content categories from generation config."""
    prompt = (config.get("prompt") or "").lower()
    categories = []

    category_keywords = {
        "portrait": ["portrait", "face", "headshot", "person", "model"],
        "landscape": ["landscape", "scenery", "nature", "outdoor"],
        "product": ["product", "bottle", "watch", "jewelry", "item"],
        "editorial": ["editorial", "magazine", "vogue", "fashion"],
        "luxury": ["luxury", "gold", "premium", "elegant", "sophisticated"],
        "cinematic": ["cinematic", "film", "movie", "dramatic"],
        "anime": ["anime", "manga", "cartoon", "illustration"],
        "commercial": ["commercial", "ad", "advertisement", "brand"],
    }

    for cat, words in category_keywords.items():
        if any(w in prompt for w in words):
            categories.append(cat)

    return categories or ["general"]
