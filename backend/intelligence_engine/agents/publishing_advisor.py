"""Publishing Advisor — recommends platform, format, and posting strategy."""
from __future__ import annotations

from backend.intelligence_engine.agents.base import BaseAgent, AgentOutput
from backend.intelligence_engine.context import IntelligenceContext


class PublishingAdvisor(BaseAgent):

    @property
    def name(self) -> str:
        return "Publishing Advisor"

    @property
    def role(self) -> str:
        return "Recommends platform strategy, format, captions, and posting schedule"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        platform = context.platform
        content_type = context.content_type
        talent = context.talent_name
        recs = []

        # Format recommendations per platform
        formats = {
            "instagram": {"aspect": "4:5", "max_duration": "90s", "caption_length": "2200 chars"},
            "tiktok": {"aspect": "9:16", "max_duration": "60s", "caption_length": "2200 chars"},
            "youtube": {"aspect": "16:9", "max_duration": "unlimited", "caption_length": "5000 chars"},
            "pinterest": {"aspect": "2:3", "max_duration": "60s", "caption_length": "500 chars"},
            "website": {"aspect": "custom", "max_duration": "unlimited", "caption_length": "unlimited"},
        }
        fmt = formats.get(platform, formats["instagram"])

        recs.append({
            "title": f"Format: {platform.capitalize()}",
            "content": f"Aspect ratio: {fmt['aspect']} | Max duration: {fmt['max_duration']} | "
                       f"Caption limit: {fmt['caption_length']}",
            "type": "format",
            **fmt,
        })

        # Caption suggestion
        recs.append({
            "title": "Caption Strategy",
            "content": f"Lead with hook question or statement. "
                       f"Tag relevant hashtags (5-10 for {platform}). "
                       f"Include CTA in final line.",
            "type": "caption",
        })

        # Posting time (simplified recommendation)
        best_times = {
            "instagram": "Tue/Thu 10am-1pm EST",
            "tiktok": "Tue-Thu 7-9pm EST",
            "youtube": "Fri-Sat 2-4pm EST",
            "pinterest": "Sat 8-11pm EST",
        }
        recs.append({
            "title": "Best Posting Time",
            "content": best_times.get(platform, "Weekday evenings"),
            "type": "schedule",
        })

        # Cross-posting
        if content_type == "image":
            recs.append({
                "title": "Cross-Post",
                "content": "Adapt for Pinterest (2:3 crop) and Stories (9:16 crop) for maximum reach.",
                "type": "cross_post",
            })

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=f"Platform={platform}, type={content_type}",
            confidence=0.75,
        )
