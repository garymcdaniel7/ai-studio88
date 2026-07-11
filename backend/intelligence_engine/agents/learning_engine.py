"""Learning Engine — analyzes feedback patterns and suggests improvements."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from backend.intelligence_engine.agents.base import AgentOutput, BaseAgent

if TYPE_CHECKING:
    from backend.intelligence_engine.context import IntelligenceContext


class LearningEngine(BaseAgent):
    @property
    def name(self) -> str:
        return "Learning Engine"

    @property
    def role(self) -> str:
        return "Analyzes feedback patterns and recommends systematic improvements"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        recs = []
        reasoning_parts = []

        # Analyze problem frequency
        problems = context.recent_problems
        if problems:
            counter = Counter(problems)
            total = len(problems)
            top_problems = counter.most_common(3)

            for problem, count in top_problems:
                pct = int((count / total) * 100)
                severity = "Critical" if pct > 40 else "Moderate" if pct > 20 else "Minor"

                fixes = {
                    "face_drift": "Reduce LoRA strength by 0.1, add face restore step",
                    "bad_hands": "Add 'perfect hands' to prompt, use hand-fix ControlNet",
                    "bad_lighting": "Specify lighting in prompt, add to negative",
                    "too_artificial": "Reduce CFG scale, add 'natural skin texture' to prompt",
                    "poor_composition": "Add composition guide step, specify framing in prompt",
                    "identity_mismatch": "Increase LoRA strength, use reference image (IPAdapter)",
                    "poor_motion": "Reduce motion magnitude, use longer step count",
                    "wrong_outfit": "Specify wardrobe in prompt, update Creative DNA wardrobe",
                    "prompt_mismatch": "Simplify prompt, reduce conflicting keywords",
                }
                fix = fixes.get(problem, "Review generation parameters")

                recs.append(
                    {
                        "title": f"{severity}: {problem.replace('_', ' ').title()} ({pct}%)",
                        "content": f"Occurring in {count}/{total} recent outputs. Fix: {fix}",
                        "type": "problem_analysis",
                        "problem": problem,
                        "frequency": pct,
                        "fix": fix,
                    }
                )

            reasoning_parts.append(
                f"Analyzed {total} feedback entries → {len(top_problems)} top issues"
            )
        else:
            recs.append(
                {
                    "title": "No Issues Detected",
                    "content": "No recent feedback problems. System performing well.",
                    "type": "all_clear",
                }
            )

        # Rating trend
        if context.average_rating is not None:
            trend = (
                "improving"
                if context.average_rating >= 4.0
                else "needs attention"
                if context.average_rating < 3.0
                else "stable"
            )
            recs.append(
                {
                    "title": f"Quality Score: {context.average_rating:.1f}/5 ({trend})",
                    "content": f"Average rating across recent generations. "
                    f"{'Consider reviewing generation settings.' if trend == 'needs attention' else 'Keep current approach.'}",
                    "type": "rating_trend",
                    "average": context.average_rating,
                    "trend": trend,
                }
            )
            reasoning_parts.append(f"Avg rating={context.average_rating:.1f} → {trend}")

        # DNA completeness check
        dna = context.creative_dna
        if dna:
            empty_fields = []
            for field in ["preferred_styles", "avoided_styles", "color_palette", "prompt_rules"]:
                if not dna.get(field):
                    empty_fields.append(field)
            if empty_fields:
                recs.append(
                    {
                        "title": "DNA Improvement",
                        "content": f"Fill in: {', '.join(empty_fields)} for better recommendations.",
                        "type": "dna_improvement",
                    }
                )
        else:
            recs.append(
                {
                    "title": "Create Creative DNA",
                    "content": "No Creative DNA found. Create one to enable personalized learning.",
                    "type": "dna_missing",
                }
            )

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=" | ".join(reasoning_parts) or "No feedback data available",
            confidence=0.7 if problems else 0.5,
        )
