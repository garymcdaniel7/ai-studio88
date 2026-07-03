"""Video Director — recommends motion, camera, and timing for video content."""
from __future__ import annotations

from backend.intelligence_engine.agents.base import BaseAgent, AgentOutput
from backend.intelligence_engine.context import IntelligenceContext


class VideoDirector(BaseAgent):

    @property
    def name(self) -> str:
        return "Video Director"

    @property
    def role(self) -> str:
        return "Recommends motion, camera moves, timing, and audio for video content"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        content_type = context.content_type
        idea = context.user_idea.lower()
        recs = []

        if content_type not in ("video", "reel", "talking_head"):
            return AgentOutput(
                agent=self.name,
                recommendations=[{
                    "title": "Not Applicable",
                    "content": "Video direction not needed for static content.",
                    "type": "skip",
                }],
                reasoning="Content is not video type",
                confidence=0.3,
            )

        # Camera movement
        if "cinematic" in idea or "travel" in idea:
            camera = "Slow dolly push-in with subtle parallax. Handheld micro-movement for organic feel."
        elif "editorial" in idea or "fashion" in idea:
            camera = "Static tripod with subject movement. Clean, controlled framing."
        else:
            camera = "Gentle pan or slow orbit around subject. Keep movement minimal and intentional."

        recs.append({"title": "Camera", "content": camera, "type": "camera_move"})

        # Duration and timing
        recs.append({
            "title": "Timing",
            "content": "5 seconds at 24fps. Hook in first 0.5s. Main action 1-4s. Resolve by 5s.",
            "type": "timing",
            "duration_seconds": 5,
            "fps": 24,
        })

        # Motion guidance
        recs.append({
            "title": "Subject Motion",
            "content": f"Subtle movement: hair in breeze, fabric flow, gentle head turn. "
                       f"Avoid large movements that cause AI artifacts.",
            "type": "motion",
        })

        # Audio (future)
        recs.append({
            "title": "Audio (Future)",
            "content": "Consider ambient sound design. Music BPM should match edit rhythm.",
            "type": "audio_note",
        })

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=f"Video direction for '{context.content_type}' content",
            confidence=0.75,
        )
