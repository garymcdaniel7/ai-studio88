"""Creative Director — elevates concepts into production-ready briefs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.intelligence_engine.agents.base import AgentOutput, BaseAgent

if TYPE_CHECKING:
    from backend.intelligence_engine.context import IntelligenceContext


class CreativeDirector(BaseAgent):
    @property
    def name(self) -> str:
        return "Creative Director"

    @property
    def role(self) -> str:
        return "Elevates creative concepts, suggests composition, maintains brand identity"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        idea = context.user_idea
        talent = context.talent_name or "talent"
        platform = context.platform

        recs = []
        reasoning_parts = []

        # Scene composition based on idea keywords
        if any(w in idea.lower() for w in ["luxury", "hotel", "resort", "villa"]):
            scene = (
                f"Position {talent} in a luxury environment with warm golden-hour lighting. "
                f"Shallow depth of field. 3/4 angle showing setting and subject."
            )
            reasoning_parts.append(
                "Detected luxury/hospitality theme → warm lighting, elegant framing"
            )
        elif any(w in idea.lower() for w in ["editorial", "rooftop", "city", "urban"]):
            scene = (
                f"Position {talent} against city skyline at blue hour. "
                f"Dramatic side lighting, strong geometric lines from architecture."
            )
            reasoning_parts.append(
                "Detected editorial/urban theme → dramatic lighting, architectural framing"
            )
        elif any(w in idea.lower() for w in ["travel", "beach", "nature", "outdoor"]):
            scene = (
                f"{talent} in a natural environment with organic textures. "
                f"Golden hour backlighting for a warm, aspirational feel."
            )
            reasoning_parts.append(
                "Detected travel/nature theme → natural light, organic composition"
            )
        else:
            scene = (
                f"Feature {talent} as focal point with complementary environment. "
                f"Natural lighting for authenticity."
            )
            reasoning_parts.append("General composition → talent-centered, natural light")

        recs.append({"title": "Scene Direction", "content": scene, "type": "composition"})

        # Platform-specific direction
        platform_direction = {
            "instagram": {
                "aspect": "4:5 portrait or 1:1 square",
                "style": "Bold colors, high contrast, scroll-stopping",
            },
            "tiktok": {
                "aspect": "9:16 portrait",
                "style": "High energy, movement-oriented, first-frame hook",
            },
            "youtube": {"aspect": "16:9 landscape", "style": "Cinematic, room for text overlays"},
            "pinterest": {
                "aspect": "2:3 portrait",
                "style": "Lifestyle aesthetic, soft tones, aspirational",
            },
            "website": {
                "aspect": "Custom/landscape",
                "style": "High resolution, hero-section quality",
            },
        }
        pd = platform_direction.get(platform, {"aspect": "1:1", "style": "Standard"})
        recs.append(
            {
                "title": f"Platform: {platform.capitalize()}",
                "content": f"Aspect ratio: {pd['aspect']}. Style: {pd['style']}.",
                "type": "platform",
            }
        )
        reasoning_parts.append(f"Platform={platform} → {pd['aspect']}")

        # Creative DNA integration
        if context.preferred_styles:
            style_note = f"Lean into: {', '.join(context.preferred_styles[:3])}"
            recs.append({"title": "Brand DNA", "content": style_note, "type": "dna"})
            reasoning_parts.append(f"DNA preferred styles: {context.preferred_styles[:3]}")

        if context.avoided_styles:
            avoid_note = f"Avoid: {', '.join(context.avoided_styles[:3])}"
            recs.append({"title": "Avoid", "content": avoid_note, "type": "dna_avoid"})

        # Continuity check
        if context.previous_generations:
            last = context.previous_generations[0]
            last_meta = last.get("metadata", {})
            if last_meta.get("prompt"):
                recs.append(
                    {
                        "title": "Continuity",
                        "content": f"Previous generation used: '{last_meta['prompt'][:60]}...'. "
                        f"Maintain visual consistency with established look.",
                        "type": "continuity",
                    }
                )
                reasoning_parts.append("Previous work exists → maintain visual consistency")

        reasoning = " | ".join(reasoning_parts)

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=reasoning,
            confidence=0.85,
        )
