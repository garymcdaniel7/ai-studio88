"""Continuity Director — maintains visual consistency across generations."""
from __future__ import annotations

from backend.intelligence_engine.agents.base import BaseAgent, AgentOutput
from backend.intelligence_engine.context import IntelligenceContext


class ContinuityDirector(BaseAgent):

    @property
    def name(self) -> str:
        return "Continuity Director"

    @property
    def role(self) -> str:
        return "Maintains character identity, wardrobe, and visual consistency across a series"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        recs = []
        reasoning_parts = []

        # Check previous generations for this talent
        prev = context.previous_generations
        if prev:
            last = prev[0]
            last_meta = last.get("metadata", {})
            last_prompt = last_meta.get("prompt", "")
            last_seed = last_meta.get("seed_used")
            last_model = last_meta.get("model", "")

            recs.append({
                "title": "Identity Lock",
                "content": f"Previous generation used seed {last_seed} with {last_model}. "
                           f"Use same LoRA and similar prompt structure to maintain identity.",
                "type": "identity_lock",
                "reference_seed": last_seed,
                "reference_model": last_model,
            })
            reasoning_parts.append(f"Found {len(prev)} previous generations → identity consistency")

            # Wardrobe continuity
            if context.wardrobe_preferences:
                recs.append({
                    "title": "Wardrobe",
                    "content": f"Maintain consistent wardrobe: {context.wardrobe_preferences}",
                    "type": "wardrobe",
                })
        else:
            recs.append({
                "title": "New Character",
                "content": "No previous generations found. This will establish the baseline look. "
                           "Pay extra attention to defining clear visual identity.",
                "type": "new_character",
            })
            reasoning_parts.append("No history → establishing baseline identity")

        # Series continuity
        if context.continuity_notes:
            for note in context.continuity_notes[:3]:
                recs.append({"title": "Continuity Note", "content": note, "type": "continuity"})

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=" | ".join(reasoning_parts) or "Standard continuity check",
            confidence=0.75 if prev else 0.6,
        )
