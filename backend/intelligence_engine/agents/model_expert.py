"""Model Expert — recommends checkpoints, LoRAs, and generation settings."""
from __future__ import annotations

from backend.intelligence_engine.agents.base import BaseAgent, AgentOutput
from backend.intelligence_engine.context import IntelligenceContext


class ModelExpert(BaseAgent):

    @property
    def name(self) -> str:
        return "Model Expert"

    @property
    def role(self) -> str:
        return "Recommends models, LoRAs, samplers, and generation settings"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        content_type = context.content_type
        idea = context.user_idea.lower()
        recs = []
        reasoning_parts = []

        # Model selection
        if content_type == "video" or content_type == "reel":
            model = "WAN 2.1"
            reason = "Best for short-form video with natural motion"
            vram = 24
        elif any(w in idea for w in ["realistic", "photo", "luxury", "portrait", "editorial"]):
            model = "FLUX.1-dev"
            reason = "Superior photorealism, best prompt adherence for editorial work"
            vram = 24
        elif any(w in idea for w in ["anime", "illustration", "cartoon", "stylized"]):
            model = "SDXL 1.0"
            reason = "Excellent for stylized content, faster generation"
            vram = 12
        else:
            model = "FLUX.1-dev"
            reason = "Default: highest quality for general content"
            vram = 24

        # Override with DNA model preference
        dna_model = context.model_preferences.get("primary_model")
        if dna_model:
            model = dna_model
            reason = f"DNA preference: {dna_model}"
            reasoning_parts.append(f"DNA model override: {dna_model}")

        recs.append({
            "title": f"Model: {model}",
            "content": f"{reason}. Requires {vram}GB VRAM.",
            "type": "model",
            "model_id": model.lower().replace(" ", "-").replace(".", ""),
            "vram_required": vram,
        })

        # Generation settings
        if "flux" in model.lower():
            settings = {"steps": 20, "cfg_scale": 3.5, "sampler": "euler", "scheduler": "normal"}
        elif "sdxl" in model.lower():
            settings = {"steps": 30, "cfg_scale": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras"}
        elif "wan" in model.lower():
            settings = {"steps": 30, "cfg_scale": 6.0, "sampler": "euler", "scheduler": "normal"}
        else:
            settings = {"steps": 20, "cfg_scale": 7.0, "sampler": "euler", "scheduler": "normal"}

        recs.append({
            "title": "Settings",
            "content": f"Steps: {settings['steps']} | CFG: {settings['cfg_scale']} | "
                       f"Sampler: {settings['sampler']} | Scheduler: {settings['scheduler']}",
            "type": "settings",
            **settings,
        })
        reasoning_parts.append(f"Model={model} → optimized settings")

        # LoRA recommendation
        if context.talent_name:
            lora_strength = context.lora_preferences.get("strength", 0.7)
            # Adjust based on feedback
            if "face_drift" in context.recent_problems:
                lora_strength = max(lora_strength - 0.1, 0.4)
                reasoning_parts.append(f"face_drift in feedback → reduced LoRA to {lora_strength}")
            recs.append({
                "title": "LoRA",
                "content": f"If trained LoRA exists for {context.talent_name}, "
                           f"apply at strength {lora_strength}.",
                "type": "lora",
                "lora_strength": lora_strength,
            })

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=" | ".join(reasoning_parts) or f"Selected {model} for {content_type}",
            confidence=0.85,
            metadata={"model": model, "settings": settings},
        )
