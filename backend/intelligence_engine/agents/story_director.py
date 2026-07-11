"""Story Director — manages narrative arc and content series planning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.intelligence_engine.agents.base import AgentOutput, BaseAgent

if TYPE_CHECKING:
    from backend.intelligence_engine.context import IntelligenceContext


class StoryDirector(BaseAgent):
    @property
    def name(self) -> str:
        return "Story Director"

    @property
    def role(self) -> str:
        return "Plans narrative arcs, content series, and storytelling structure"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        content_type = context.content_type
        idea = context.user_idea
        recs = []

        # Series-aware recommendations
        if content_type in ("carousel", "story", "campaign"):
            recs.append(
                {
                    "title": "Series Structure",
                    "content": f"For '{idea}': Build a 3-5 image series with progression. "
                    f"Start with establishing shot, move to detail, end with hero shot.",
                    "type": "series_structure",
                }
            )
            recs.append(
                {
                    "title": "Narrative Arc",
                    "content": "Each frame should tell a micro-story. Hook → Build → Reveal → CTA.",
                    "type": "narrative",
                }
            )
        elif content_type in ("video", "reel"):
            recs.append(
                {
                    "title": "Video Structure",
                    "content": "5-second reel structure: Hook (0-1s) → Main (1-4s) → End (4-5s). "
                    "Start with motion to stop scroll.",
                    "type": "video_structure",
                }
            )
        else:
            recs.append(
                {
                    "title": "Single Image Story",
                    "content": "Even a single image tells a story. "
                    "Subject should evoke emotion or aspiration.",
                    "type": "single_story",
                }
            )

        # Campaign context
        if context.campaign:
            recs.append(
                {
                    "title": f"Campaign: {context.campaign}",
                    "content": "Ensure this piece fits the campaign's overall narrative. "
                    "Maintain consistent tone and visual language.",
                    "type": "campaign_context",
                }
            )

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=f"Content type={content_type}, campaign={context.campaign or 'none'}",
            confidence=0.7,
        )
