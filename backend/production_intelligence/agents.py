"""Production Intelligence Agents.

Specialized AI advisors that continuously improve production quality.
Each agent reads platform state and produces actionable recommendations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Insight:
    """An insight from a production intelligence agent."""
    agent: str
    title: str
    description: str
    reasoning: str
    confidence: float = 0.8
    action: str = ""
    priority: str = "medium"  # low, medium, high, critical
    estimated_impact: str = ""
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Executive Producer
# =============================================================================

class ExecutiveProducer:
    """Chooses best workflow, model, LoRA, GPU, estimates budget and runtime."""

    name = "Executive Producer"

    def analyze(self, context: dict) -> list[Insight]:
        insights = []

        # Workflow recommendation
        insights.append(Insight(
            self.name, "Optimal Workflow",
            "For image content: Generate → Face Fix → Upscale (3 steps). "
            "For video: Generate → Frame Enhance → Audio Mix → Export (4 steps).",
            "Based on production type and historical success rates",
            0.85, action="select_workflow", priority="high",
            estimated_impact="20% quality improvement",
        ))

        # Budget estimate
        workers = context.get("workers_online", 0)
        jobs = context.get("pending_jobs", 0)
        insights.append(Insight(
            self.name, f"Production Budget: ~${jobs * 0.05:.2f}",
            f"{jobs} pending jobs × $0.05/job avg. Workers available: {workers}.",
            "Cost based on GPU time estimates",
            0.7, action="budget_review",
        ))

        # Bottleneck detection
        if workers == 0:
            insights.append(Insight(
                self.name, "Production Bottleneck: No Workers",
                "All workers are offline. Production is stalled.",
                "Zero online workers detected",
                0.95, action="start_worker", priority="critical",
            ))

        return insights


# =============================================================================
# Director
# =============================================================================

class Director:
    """Evaluates scene pacing, camera language, emotional flow, shot order."""

    name = "Director"

    def analyze(self, context: dict) -> list[Insight]:
        insights = []

        insights.append(Insight(
            self.name, "Pacing Recommendation",
            "Social content should hook in 0.5s. Main action 1-4s. Close by 5s. "
            "Vary shot duration for rhythm: short-short-long-short pattern.",
            "Engagement data shows front-loaded pacing works best",
            0.78, action="adjust_pacing",
        ))

        insights.append(Insight(
            self.name, "Camera Language",
            "Use dolly-in for intimacy, wide shots for context, close-ups for emotion. "
            "Maintain consistent screen direction across cuts.",
            "Cinematic best practices + previous production analysis",
            0.75, action="camera_guidance",
        ))

        return insights


# =============================================================================
# Editor
# =============================================================================

class Editor:
    """Recommends cuts, transitions, B-roll, music timing, social cuts."""

    name = "Editor"

    def analyze(self, context: dict) -> list[Insight]:
        insights = []

        insights.append(Insight(
            self.name, "Editing Rhythm",
            "Cut on action or beat. Avoid lingering shots >4s for social. "
            "Add reaction shots between dialogue lines for engagement.",
            "Social video engagement patterns",
            0.72, action="edit_timing",
        ))

        insights.append(Insight(
            self.name, "Social Media Cuts",
            "From every 30s+ piece, extract: 1 hook clip (3s), 1 teaser (8s), "
            "1 full reel (15-30s). Repurpose for maximum platform coverage.",
            "Content repurposing best practices",
            0.8, action="create_cuts", priority="medium",
        ))

        return insights


# =============================================================================
# Model Advisor
# =============================================================================

class ModelAdvisor:
    """Recommends best model based on content, budget, GPU, desired quality."""

    name = "Model Advisor"

    def analyze(self, context: dict) -> list[Insight]:
        insights = []
        content_type = context.get("content_type", "image")

        if content_type in ("video", "reel", "tiktok"):
            insights.append(Insight(
                self.name, "Model: WAN 2.1 for Video",
                "WAN 2.1 produces the most natural motion. Requires 24GB VRAM. "
                "For budget: LTX Video (faster, less natural).",
                "Video model comparison: WAN > Hunyuan > LTX for realism",
                0.82, action="select_model", metadata={"model": "wan-2.1"},
            ))
        else:
            insights.append(Insight(
                self.name, "Model: FLUX.1-dev for Images",
                "Best photorealism. fp8 version fits in 24GB. "
                "For speed: SDXL (faster, slightly less realistic).",
                "Image model comparison: Flux > SDXL > Pony for editorial",
                0.85, action="select_model", metadata={"model": "flux-dev"},
            ))

        return insights


# =============================================================================
# GPU Advisor
# =============================================================================

class GPUAdvisor:
    """Recommends optimal GPU routing based on job requirements."""

    name = "GPU Advisor"

    def analyze(self, context: dict) -> list[Insight]:
        insights = []
        workers = context.get("workers_online", 0)
        vram_free = context.get("vram_free_gb", 0)

        if workers > 0 and vram_free >= 24:
            insights.append(Insight(
                self.name, "GPU Available: Route Immediately",
                f"{workers} worker(s) online with {vram_free:.0f}GB free. Job can start now.",
                "Worker manager reports availability",
                0.9, action="route_now", priority="high",
            ))
        elif workers > 0:
            insights.append(Insight(
                self.name, "GPU: Wait for VRAM",
                f"Workers online but only {vram_free:.0f}GB free. Wait or use smaller model.",
                "VRAM below model requirement",
                0.7, action="wait_or_downgrade",
            ))
        else:
            insights.append(Insight(
                self.name, "GPU: Start Worker",
                "No workers online. Start a Vast.ai instance ($0.40/hr for RTX 4090).",
                "Zero workers available",
                0.9, action="start_worker", priority="high",
            ))

        return insights


# =============================================================================
# Quality Scorer
# =============================================================================

class QualityScorer:
    """Scores generated content on multiple quality dimensions."""

    name = "Quality Scorer"

    def score(self, asset_metadata: dict) -> dict:
        """Generate quality scores for a generated asset (simulated)."""
        import random

        # In production, these would come from actual quality models
        return {
            "identity_consistency": round(random.uniform(0.7, 1.0), 2),
            "prompt_adherence": round(random.uniform(0.6, 1.0), 2),
            "anatomy": round(random.uniform(0.7, 1.0), 2),
            "hands": round(random.uniform(0.5, 1.0), 2),
            "lighting": round(random.uniform(0.7, 1.0), 2),
            "composition": round(random.uniform(0.6, 1.0), 2),
            "cinematic_quality": round(random.uniform(0.6, 1.0), 2),
            "overall": round(random.uniform(0.65, 0.95), 2),
        }

    def analyze(self, context: dict) -> list[Insight]:
        avg = context.get("average_quality", 0.8)
        insights = []

        if avg < 0.7:
            insights.append(Insight(
                self.name, "Quality Below Target",
                f"Average quality score: {avg:.0%}. Consider: stronger LoRA, more steps, face fix.",
                "Quality scores trending below 70%",
                0.8, action="improve_quality", priority="high",
            ))
        else:
            insights.append(Insight(
                self.name, f"Quality Score: {avg:.0%}",
                "Production quality is on target. Continue current approach.",
                "Quality metrics within acceptable range",
                0.7, priority="low",
            ))

        return insights


# =============================================================================
# Self-Healing Workflow Advisor
# =============================================================================

class SelfHealingAdvisor:
    """Detects failed workflows and recommends recovery actions."""

    name = "Self-Healing Advisor"

    def analyze(self, context: dict) -> list[Insight]:
        insights = []
        failed_jobs = context.get("failed_jobs", 0)

        if failed_jobs > 0:
            insights.append(Insight(
                self.name, f"{failed_jobs} Failed Job(s) Detected",
                "Recovery options: retry with same params, change provider, "
                "reduce resolution, skip step, or reassign to different worker.",
                f"{failed_jobs} jobs in failed state",
                0.85, action="auto_recover", priority="high",
                metadata={"recovery_options": ["retry", "change_provider", "reduce_params", "skip", "reassign"]},
            ))

        return insights


# =============================================================================
# Agent Registry
# =============================================================================

PRODUCTION_AGENTS = [
    ExecutiveProducer,
    Director,
    Editor,
    ModelAdvisor,
    GPUAdvisor,
    QualityScorer,
    SelfHealingAdvisor,
]


def run_all_agents(context: dict) -> list[Insight]:
    """Run all production intelligence agents and collect insights."""
    all_insights = []
    for agent_class in PRODUCTION_AGENTS:
        agent = agent_class()
        try:
            insights = agent.analyze(context)
            all_insights.extend(insights)
        except Exception:
            pass
    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_insights.sort(key=lambda i: (priority_order.get(i.priority, 3), -i.confidence))
    return all_insights
