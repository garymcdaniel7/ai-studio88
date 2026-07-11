"""AI Intelligence Layer — Recommendation Providers.

Each provider implements the RecommendationProvider interface.
Currently returns simulated recommendations. Future: replace with
LLM-powered agents (GPT, Claude, OpenRouter, local models).

Usage:
    from backend.intelligence import get_recommendations
    recs = get_recommendations(context)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Recommendation:
    """A single recommendation from an agent."""

    agent: str
    title: str
    content: str
    confidence: float = 0.8  # 0.0 to 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class CreativeContext:
    """Context passed to all recommendation providers."""

    talent_name: str = ""
    talent_id: str = ""
    project_name: str = ""
    platform: str = "instagram"
    content_type: str = "image"
    user_idea: str = ""
    campaign: str = ""
    style_tags: list[str] = field(default_factory=list)
    # Populated from Creative DNA and feedback
    creative_dna: dict = field(default_factory=dict)
    recent_problems: list[str] = field(default_factory=list)
    average_rating: float | None = None


@dataclass
class ProductionPlan:
    """Generated production plan from all agent recommendations."""

    prompt: str = ""
    negative_prompt: str = ""
    workflow_steps: list[dict] = field(default_factory=list)
    estimated_runtime: str = ""
    estimated_gpu: str = ""
    estimated_cost: str = ""
    expected_outputs: list[str] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)


# =============================================================================
# Provider Interface
# =============================================================================


class RecommendationProvider(ABC):
    """Base interface for all recommendation providers.

    Implement this to add a new agent (LLM-powered or rule-based).
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Agent identifier."""
        ...

    @abstractmethod
    def recommend(self, context: CreativeContext) -> list[Recommendation]:
        """Generate recommendations for the given context."""
        ...


# =============================================================================
# Simulated Providers (will be replaced by LLM agents)
# =============================================================================


class SimulatedCreativeDirector(RecommendationProvider):
    """Simulates the Creative Director agent."""

    @property
    def agent_name(self) -> str:
        return "Creative Director"

    def recommend(self, context: CreativeContext) -> list[Recommendation]:
        idea = context.user_idea or "content"
        talent = context.talent_name or "talent"
        platform = context.platform

        recs = []

        # Scene composition
        if "luxury" in idea.lower() or "hotel" in idea.lower():
            recs.append(
                Recommendation(
                    agent=self.agent_name,
                    title="Scene Composition",
                    content=f"Shoot {talent} in a luxury environment with warm golden-hour lighting. "
                    f"Use a shallow depth of field to separate subject from background. "
                    f"Consider a 3/4 angle to show both the setting and the subject's outfit.",
                    confidence=0.85,
                )
            )
        elif "editorial" in idea.lower() or "rooftop" in idea.lower():
            recs.append(
                Recommendation(
                    agent=self.agent_name,
                    title="Scene Composition",
                    content=f"Position {talent} against a city skyline at blue hour. "
                    f"Use dramatic side lighting for an editorial feel. "
                    f"Strong geometric lines from architecture create visual tension.",
                    confidence=0.82,
                )
            )
        else:
            recs.append(
                Recommendation(
                    agent=self.agent_name,
                    title="Scene Composition",
                    content=f"For '{idea}', position {talent} as the focal point with complementary "
                    f"environment. Use natural lighting where possible for authenticity.",
                    confidence=0.75,
                )
            )

        # Platform-specific advice
        platform_tips = {
            "instagram": "Square 1:1 or portrait 4:5 crop. Bold colours perform well.",
            "tiktok": "Portrait 9:16. Movement-oriented, high energy first frame.",
            "youtube": "Landscape 16:9. Cinematic framing with room for text overlays.",
            "pinterest": "Portrait 2:3. Lifestyle aesthetic, soft tones, aspirational.",
            "website": "Landscape or custom ratio. High resolution for hero sections.",
        }
        recs.append(
            Recommendation(
                agent=self.agent_name,
                title=f"Platform: {platform.capitalize()}",
                content=platform_tips.get(platform, "Standard composition recommended."),
                confidence=0.9,
            )
        )

        return recs


class SimulatedPromptEngineer(RecommendationProvider):
    """Simulates the Prompt Engineer agent."""

    @property
    def agent_name(self) -> str:
        return "Prompt Engineer"

    def recommend(self, context: CreativeContext) -> list[Recommendation]:
        idea = context.user_idea or "professional photo"
        talent = context.talent_name or "woman"
        content_type = context.content_type
        dna = context.creative_dna
        problems = context.recent_problems

        # Build a prompt based on context
        style_hints = []
        if "luxury" in idea.lower():
            style_hints = [
                "luxury fashion",
                "haute couture",
                "editorial lighting",
                "vogue magazine",
            ]
        elif "cinematic" in idea.lower():
            style_hints = ["cinematic", "film grain", "anamorphic", "dramatic lighting"]
        elif "editorial" in idea.lower():
            style_hints = ["high fashion editorial", "studio lighting", "sharp focus"]
        else:
            style_hints = ["professional photography", "natural lighting", "sharp focus"]

        # Rule-based learning: incorporate Creative DNA preferred styles
        if dna.get("preferred_styles"):
            for style in dna["preferred_styles"]:
                if style not in style_hints:
                    style_hints.append(style)

        # Rule-based learning: add prompt rules from DNA
        extra_positive = []
        if dna.get("prompt_rules"):
            extra_positive = dna["prompt_rules"]

        prompt_parts = [talent, idea] + style_hints + extra_positive + ["8k uhd", "highly detailed"]
        prompt = ", ".join(prompt_parts)

        # Build negative prompt — start with defaults
        negative_parts = [
            "blurry",
            "low quality",
            "deformed",
            "extra limbs",
            "bad hands",
            "watermark",
            "text",
        ]

        # Rule-based learning: add negative rules from DNA
        if dna.get("negative_prompt_rules"):
            negative_parts.extend(dna["negative_prompt_rules"])

        # Rule-based learning: add negatives from frequent problems
        problem_to_negative = {
            "face_drift": "face deformation, inconsistent face",
            "bad_hands": "malformed hands, extra fingers",
            "bad_lighting": "harsh lighting, overexposed",
            "too_artificial": "plastic skin, uncanny valley, CGI look",
            "poor_composition": "cluttered background, bad framing",
            "identity_mismatch": "wrong person, different face",
        }
        for problem in set(problems):
            neg = problem_to_negative.get(problem)
            if neg and neg not in ", ".join(negative_parts):
                negative_parts.append(neg)

        # Rule-based learning: avoid styles from DNA
        if dna.get("avoided_styles"):
            negative_parts.extend(dna["avoided_styles"])

        negative = ", ".join(negative_parts)

        recs = [
            Recommendation(
                agent=self.agent_name,
                title="Optimized Prompt",
                content=prompt,
                confidence=0.85,
                metadata={"type": "positive_prompt"},
            ),
            Recommendation(
                agent=self.agent_name,
                title="Negative Prompt",
                content=negative,
                confidence=0.9,
                metadata={"type": "negative_prompt"},
            ),
        ]

        # Feedback-based warnings
        if problems:
            from collections import Counter

            top_problems = Counter(problems).most_common(3)
            problem_summary = ", ".join(f"{p} ({c}x)" for p, c in top_problems)
            recs.append(
                Recommendation(
                    agent=self.agent_name,
                    title="⚠️ Learned from Feedback",
                    content=f"Recent issues: {problem_summary}. Prompt adjusted to avoid these.",
                    confidence=0.7,
                    metadata={"type": "feedback_warning"},
                )
            )

        if content_type == "video":
            recs.append(
                Recommendation(
                    agent=self.agent_name,
                    title="Motion Description",
                    content=f"Slow camera push-in on {talent}. Subtle hair movement from breeze. "
                    f"Gentle ambient particles in the air. 5 seconds, 24fps.",
                    confidence=0.75,
                    metadata={"type": "motion_prompt"},
                )
            )

        return recs


class SimulatedWorkflowOptimizer(RecommendationProvider):
    """Simulates the Workflow Optimizer agent."""

    @property
    def agent_name(self) -> str:
        return "Workflow Optimizer"

    def recommend(self, context: CreativeContext) -> list[Recommendation]:
        content_type = context.content_type
        steps = []

        if content_type == "image":
            steps = [
                {
                    "name": "Generate Image",
                    "handler": "image_generation",
                    "config": {"steps": 20, "width": 1024, "height": 1024},
                },
                {"name": "Face Fix", "handler": "image_edit", "config": {"mode": "face_restore"}},
                {"name": "Upscale 2x", "handler": "image_upscale", "config": {"scale_factor": 2}},
            ]
        elif content_type == "video":
            steps = [
                {
                    "name": "Generate Video",
                    "handler": "video_generation",
                    "config": {"duration": 5, "fps": 24},
                },
                {
                    "name": "Upscale Frames",
                    "handler": "image_upscale",
                    "config": {"scale_factor": 2},
                },
            ]
        elif content_type in ("carousel", "story"):
            steps = [
                {
                    "name": "Generate Image 1",
                    "handler": "image_generation",
                    "config": {"steps": 20},
                },
                {
                    "name": "Generate Image 2",
                    "handler": "image_generation",
                    "config": {"steps": 20},
                },
                {
                    "name": "Generate Image 3",
                    "handler": "image_generation",
                    "config": {"steps": 20},
                },
            ]
        else:
            steps = [
                {
                    "name": "Generate Content",
                    "handler": "image_generation",
                    "config": {"steps": 20},
                },
            ]

        step_names = " → ".join(s["name"] for s in steps)
        return [
            Recommendation(
                agent=self.agent_name,
                title="Recommended Workflow",
                content=f"{len(steps)} steps: {step_names}",
                confidence=0.8,
                metadata={"steps": steps},
            ),
        ]


class SimulatedModelExpert(RecommendationProvider):
    """Simulates the Model Expert agent."""

    @property
    def agent_name(self) -> str:
        return "Model Expert"

    def recommend(self, context: CreativeContext) -> list[Recommendation]:
        content_type = context.content_type
        idea = context.user_idea.lower()

        if content_type == "video":
            model = "WAN 2.1"
            reason = "Best for short-form AI video with natural motion"
            vram = "24 GB"
        elif "realistic" in idea or "photo" in idea or "luxury" in idea:
            model = "Flux.1-dev"
            reason = "Photorealistic output, best prompt adherence"
            vram = "24 GB"
        else:
            model = "SDXL 1.0"
            reason = "Fast generation, good for stylised content"
            vram = "12 GB"

        recs = [
            Recommendation(
                agent=self.agent_name,
                title=f"Model: {model}",
                content=f"Recommended: **{model}**. {reason}. Requires {vram} VRAM.",
                confidence=0.85,
                metadata={"model": model, "vram_gb": int(vram.split()[0])},
            ),
        ]

        if context.talent_name:
            recs.append(
                Recommendation(
                    agent=self.agent_name,
                    title="LoRA Recommendation",
                    content=f"If a trained LoRA exists for {context.talent_name}, apply at strength 0.7. "
                    f"Reduce to 0.5 if face drift occurs.",
                    confidence=0.7,
                    metadata={"lora_strength": 0.7},
                )
            )

        return recs


class SimulatedGPUOptimizer(RecommendationProvider):
    """Simulates the GPU Optimizer agent."""

    @property
    def agent_name(self) -> str:
        return "GPU Optimizer"

    def recommend(self, context: CreativeContext) -> list[Recommendation]:
        content_type = context.content_type

        if content_type == "video":
            provider = "Vast.ai A100 80GB"
            cost = "$0.85/hr"
            time_est = "~3 minutes"
        elif content_type in ("carousel", "story"):
            provider = "Vast.ai RTX 4090"
            cost = "$0.40/hr"
            time_est = "~2 minutes (parallel)"
        else:
            provider = "Vast.ai RTX 4090"
            cost = "$0.40/hr"
            time_est = "~45 seconds"

        return [
            Recommendation(
                agent=self.agent_name,
                title=f"GPU: {provider}",
                content=f"Route to **{provider}** at {cost}. Estimated time: {time_est}.",
                confidence=0.8,
                metadata={"provider": provider, "cost_per_hour": cost, "estimated_time": time_est},
            ),
        ]


# =============================================================================
# Provider Registry
# =============================================================================
# Replace individual providers with LLM-backed implementations when ready.
# The interface stays the same — only the implementation changes.

RECOMMENDATION_PROVIDERS: list[type[RecommendationProvider]] = [
    SimulatedCreativeDirector,
    SimulatedPromptEngineer,
    SimulatedWorkflowOptimizer,
    SimulatedModelExpert,
    SimulatedGPUOptimizer,
]


# =============================================================================
# Main Entry Point
# =============================================================================


def enrich_context(context: CreativeContext) -> CreativeContext:
    """Enrich context with Creative DNA and recent feedback from the database.

    Call this before get_recommendations() to enable rule-based learning.
    """
    if not context.talent_id:
        return context

    try:
        from backend.database import (
            get_average_rating,
            get_creative_dna_by_talent,
            get_recent_problems,
        )
    except ImportError:
        return context

    # Load Creative DNA
    try:
        dna_result = get_creative_dna_by_talent(context.talent_id)
        context.creative_dna = dna_result.data or {}
    except Exception:
        context.creative_dna = {}

    # Load recent problems from feedback
    try:
        context.recent_problems = get_recent_problems(context.talent_id, limit=20)
    except Exception:
        context.recent_problems = []

    # Load average rating
    try:
        context.average_rating = get_average_rating(context.talent_id)
    except Exception:
        context.average_rating = None

    return context


def get_recommendations(context: CreativeContext) -> list[Recommendation]:
    """Get recommendations from all registered providers."""
    # Enrich with DNA/feedback if talent_id is set
    context = enrich_context(context)

    all_recs = []
    for provider_class in RECOMMENDATION_PROVIDERS:
        provider = provider_class()
        try:
            recs = provider.recommend(context)
            all_recs.extend(recs)
        except Exception as e:
            all_recs.append(
                Recommendation(
                    agent=provider.agent_name,
                    title="Error",
                    content=f"Failed to generate recommendation: {e}",
                    confidence=0.0,
                )
            )
    return all_recs


def build_production_plan(context: CreativeContext) -> ProductionPlan:
    """Build a complete production plan from all agent recommendations."""
    recs = get_recommendations(context)

    plan = ProductionPlan(recommendations=recs)

    for rec in recs:
        if rec.metadata.get("type") == "positive_prompt":
            plan.prompt = rec.content
        elif rec.metadata.get("type") == "negative_prompt":
            plan.negative_prompt = rec.content
        elif rec.metadata.get("steps"):
            plan.workflow_steps = rec.metadata["steps"]
        elif rec.metadata.get("estimated_time"):
            plan.estimated_runtime = rec.metadata["estimated_time"]
            plan.estimated_gpu = rec.metadata.get("provider", "")
            plan.estimated_cost = rec.metadata.get("cost_per_hour", "")

    # Default expected outputs
    if context.content_type == "image":
        plan.expected_outputs = ["1x high-res image (2048x2048)"]
    elif context.content_type == "video":
        plan.expected_outputs = ["1x 5-second video clip (1080p)"]
    elif context.content_type in ("carousel", "story"):
        plan.expected_outputs = ["3x images for carousel/story"]
    else:
        plan.expected_outputs = ["1x generated output"]

    return plan
