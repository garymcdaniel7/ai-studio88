"""Workflow Optimizer — recommends multi-step workflows and processing order."""
from __future__ import annotations

from backend.intelligence_engine.agents.base import BaseAgent, AgentOutput
from backend.intelligence_engine.context import IntelligenceContext


class WorkflowOptimizer(BaseAgent):

    @property
    def name(self) -> str:
        return "Workflow Optimizer"

    @property
    def role(self) -> str:
        return "Designs optimal multi-step workflows for content production"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        content_type = context.content_type
        recs = []
        reasoning_parts = []
        steps = []

        # Base workflow depends on content type
        if content_type == "image":
            steps = [
                {"name": "Generate Image", "handler": "image_generation"},
                {"name": "Face Restore", "handler": "image_edit"},
                {"name": "Upscale 2x", "handler": "image_upscale"},
            ]
            reasoning_parts.append("image → generate + face fix + upscale")
        elif content_type in ("video", "reel"):
            steps = [
                {"name": "Generate Video", "handler": "video_generation"},
                {"name": "Frame Enhancement", "handler": "image_upscale"},
            ]
            reasoning_parts.append("video → generate + frame enhancement")
        elif content_type in ("carousel", "story"):
            steps = [
                {"name": "Generate Image 1", "handler": "image_generation"},
                {"name": "Generate Image 2", "handler": "image_generation"},
                {"name": "Generate Image 3", "handler": "image_generation"},
                {"name": "Batch Upscale", "handler": "image_upscale"},
            ]
            reasoning_parts.append("carousel → 3 images + batch upscale")
        else:
            steps = [{"name": "Generate Content", "handler": "image_generation"}]

        # Feedback-driven step additions
        if "face_drift" in context.recent_problems:
            # Add face fix if not already present
            has_face_fix = any("face" in s["name"].lower() for s in steps)
            if not has_face_fix:
                steps.insert(1, {"name": "Face Restore", "handler": "image_edit"})
                reasoning_parts.append("face_drift in feedback → added face restore step")

        if "poor_composition" in context.recent_problems:
            steps.insert(0, {"name": "Composition Guide", "handler": "asset_processing"})
            reasoning_parts.append("poor_composition → added composition pre-step")

        step_summary = " → ".join(s["name"] for s in steps)
        recs.append({
            "title": "Recommended Workflow",
            "content": f"{len(steps)} steps: {step_summary}",
            "type": "workflow",
            "steps": steps,
        })

        # Time estimate
        time_per_step = {"image_generation": 30, "video_generation": 120,
                         "image_upscale": 15, "image_edit": 20, "asset_processing": 5}
        total_seconds = sum(time_per_step.get(s["handler"], 30) for s in steps)
        recs.append({
            "title": "Estimated Time",
            "content": f"~{total_seconds // 60}m {total_seconds % 60}s total",
            "type": "time_estimate",
            "total_seconds": total_seconds,
        })

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=" | ".join(reasoning_parts),
            confidence=0.82,
            metadata={"steps": steps, "total_seconds": total_seconds},
        )
