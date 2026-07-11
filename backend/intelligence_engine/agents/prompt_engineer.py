"""Prompt Engineer — builds optimized prompts from context and DNA."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from backend.intelligence_engine.agents.base import AgentOutput, BaseAgent

if TYPE_CHECKING:
    from backend.intelligence_engine.context import IntelligenceContext


class PromptEngineer(BaseAgent):
    @property
    def name(self) -> str:
        return "Prompt Engineer"

    @property
    def role(self) -> str:
        return "Converts creative direction into model-optimized prompts"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        idea = context.user_idea or "professional portrait"
        talent = context.talent_name or "woman"
        recs = []
        reasoning_parts = []

        # ── Build positive prompt ─────────────────────────────────────────────
        parts = [talent, idea]

        # Style keywords from idea
        if "luxury" in idea.lower():
            parts += ["luxury fashion", "haute couture", "editorial lighting", "vogue"]
        elif "cinematic" in idea.lower():
            parts += ["cinematic", "film grain", "anamorphic lens", "dramatic lighting"]
        elif "editorial" in idea.lower():
            parts += ["high fashion editorial", "studio lighting", "sharp focus"]
        elif "travel" in idea.lower():
            parts += ["travel photography", "golden hour", "wanderlust aesthetic"]
        else:
            parts += ["professional photography", "natural lighting"]

        # DNA preferred styles
        if context.preferred_styles:
            parts += context.preferred_styles[:4]
            reasoning_parts.append(f"Added DNA styles: {context.preferred_styles[:4]}")

        # DNA prompt rules (always-include phrases)
        if context.prompt_rules:
            parts += context.prompt_rules
            reasoning_parts.append(f"Applied prompt rules: {context.prompt_rules}")

        # Color palette influence
        if context.color_palette:
            palette_str = f"{', '.join(context.color_palette[:3])} color palette"
            parts.append(palette_str)
            reasoning_parts.append(f"Color palette: {context.color_palette[:3]}")

        parts += ["8k uhd", "highly detailed", "masterpiece"]
        positive_prompt = ", ".join(parts)

        # ── Build negative prompt ─────────────────────────────────────────────
        neg_parts = [
            "blurry",
            "low quality",
            "deformed",
            "extra limbs",
            "bad hands",
            "watermark",
            "text",
            "oversaturated",
        ]

        # DNA avoided styles → negative
        if context.avoided_styles:
            neg_parts += context.avoided_styles
            reasoning_parts.append(f"Avoided styles → negative: {context.avoided_styles}")

        # DNA negative rules
        if context.negative_prompt_rules:
            neg_parts += context.negative_prompt_rules

        # Feedback-driven negatives
        problem_to_neg = {
            "face_drift": "face deformation, inconsistent face, morphing features",
            "bad_hands": "malformed hands, extra fingers, fused fingers",
            "bad_lighting": "harsh lighting, overexposed, blown highlights",
            "too_artificial": "plastic skin, uncanny valley, CGI look, airbrushed",
            "poor_composition": "cluttered background, bad framing, centered subject",
            "identity_mismatch": "wrong person, different face, identity swap",
            "poor_motion": "jerky motion, frame interpolation artifacts",
            "wrong_outfit": "inappropriate clothing, mismatched outfit",
        }
        added_from_feedback = []
        for problem in set(context.recent_problems):
            neg = problem_to_neg.get(problem)
            if neg:
                neg_parts.append(neg)
                added_from_feedback.append(problem)

        negative_prompt = ", ".join(neg_parts)

        recs.append(
            {
                "title": "Positive Prompt",
                "content": positive_prompt,
                "type": "positive_prompt",
            }
        )
        recs.append(
            {
                "title": "Negative Prompt",
                "content": negative_prompt,
                "type": "negative_prompt",
            }
        )

        # Feedback learning summary
        if added_from_feedback:
            top = Counter(context.recent_problems).most_common(3)
            summary = ", ".join(f"{p} ({c}x)" for p, c in top)
            recs.append(
                {
                    "title": "Learned from Feedback",
                    "content": f"Addressed recent issues: {summary}",
                    "type": "feedback_learning",
                }
            )
            reasoning_parts.append(f"Feedback-driven negatives for: {added_from_feedback}")

        # Model-specific prompt advice
        model_pref = context.model_preferences.get("primary_model", "flux-dev")
        if "flux" in model_pref:
            recs.append(
                {
                    "title": "Model Note",
                    "content": "Flux uses natural language — emphasis via context, not weight syntax.",
                    "type": "model_note",
                }
            )
        elif "sdxl" in model_pref:
            recs.append(
                {
                    "title": "Model Note",
                    "content": "SDXL responds to (word:1.3) weight syntax and comma-separated tags.",
                    "type": "model_note",
                }
            )

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=" | ".join(reasoning_parts) or "Standard prompt assembly",
            confidence=0.88,
            metadata={"positive_prompt": positive_prompt, "negative_prompt": negative_prompt},
        )
