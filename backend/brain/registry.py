"""Module Registry — every subsystem registers itself with the Brain.

The Brain knows about all capabilities available in the platform.
New modules register automatically; the Brain adapts.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RegisteredModule:
    """A module registered with the Brain."""

    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    api_prefix: str = ""
    status: str = "active"


# =============================================================================
# Auto-registered modules (reflects the actual platform)
# =============================================================================

MODULES: dict[str, RegisteredModule] = {
    "creative_session": RegisteredModule(
        "Creative Session",
        "AI-guided content creation from natural language",
        ["create_content", "build_plan", "recommend"],
        ["plan", "generate"],
        "/api/v1/intelligence/plan",
    ),
    "story_engine": RegisteredModule(
        "Story Engine",
        "Universes, characters, episodes, scenes, shots",
        ["create_story", "create_episode", "create_scene", "plan_shots"],
        ["create", "plan"],
        "/api/v1/universes",
    ),
    "generation_engine": RegisteredModule(
        "Generation Engine",
        "Image and content generation through providers",
        ["generate_image", "generate_content"],
        ["generate", "run"],
        "/api/v1/generation/run",
    ),
    "video_studio": RegisteredModule(
        "Video Studio",
        "Video projects, shots, renders, timelines, exports",
        ["create_video", "generate_video", "render", "export"],
        ["create", "generate", "render"],
        "/api/v1/videos",
    ),
    "voice_studio": RegisteredModule(
        "Voice Studio",
        "TTS, dialogue, narration, voice profiles",
        ["generate_voice", "create_dialogue", "narrate"],
        ["generate", "speak"],
        "/api/v1/audio/tts",
    ),
    "performance_engine": RegisteredModule(
        "Performance Engine",
        "Voice training, songs, performance memory, continuity",
        ["train_voice", "create_song", "record_performance"],
        ["train", "sing", "perform"],
        "/api/v1/songs",
    ),
    "production_studio": RegisteredModule(
        "Production Studio",
        "Media pipelines, camera, editing, packaging",
        ["plan_production", "build_timeline", "edit"],
        ["plan", "produce"],
        "/api/v1/production/plan",
    ),
    "model_manager": RegisteredModule(
        "Model Manager",
        "AI models, LoRAs, workflow templates",
        ["list_models", "validate_model", "register_model"],
        ["models"],
        "/api/v1/models",
    ),
    "training_manager": RegisteredModule(
        "Training Manager",
        "LoRA training datasets, jobs, versions",
        ["create_dataset", "train_lora", "evaluate_lora"],
        ["train"],
        "/api/v1/training/jobs",
    ),
    "worker_manager": RegisteredModule(
        "Worker Manager",
        "GPU workers, routing, heartbeats",
        ["list_workers", "route_job", "check_health"],
        ["workers"],
        "/api/v1/workers/health",
    ),
    "publishing_engine": RegisteredModule(
        "Publishing Engine",
        "Social publishing, scheduling, analytics",
        ["publish", "schedule", "analyze", "repurpose"],
        ["publish", "schedule"],
        "/api/v1/publishing/posts",
    ),
    "creator_os": RegisteredModule(
        "Creator OS",
        "Campaigns, calendar, brands, teams, notifications",
        ["create_campaign", "schedule_content", "manage_brand"],
        ["campaign", "brand"],
        "/api/v1/campaigns",
    ),
    "autonomous_studio": RegisteredModule(
        "Autonomous Studio",
        "19 AI departments, daily briefing, recommendations",
        ["get_briefing", "get_recommendations", "discuss"],
        ["brief", "recommend"],
        "/api/v1/studio/briefing",
    ),
    "asset_manager": RegisteredModule(
        "Asset Manager",
        "Files, images, videos, audio in Backblaze B2",
        ["upload_asset", "list_assets", "delete_asset"],
        ["upload", "browse"],
        "/api/v1/assets",
    ),
    "creative_dna": RegisteredModule(
        "Creative DNA",
        "Talent preferences, feedback, learning",
        ["get_dna", "update_dna", "submit_feedback"],
        ["dna", "feedback"],
        "/api/v1/creative-dna",
    ),
}


def get_module(name: str) -> RegisteredModule | None:
    return MODULES.get(name)


def list_modules() -> list[dict]:
    return [
        {
            "name": m.name,
            "description": m.description,
            "capabilities": m.capabilities,
            "status": m.status,
        }
        for m in MODULES.values()
    ]


def find_modules_for_intent(intent: str) -> list[RegisteredModule]:
    """Find modules that can handle a given intent."""
    intent_lower = intent.lower()
    matches = []
    for module in MODULES.values():
        for cap in module.capabilities:
            if any(word in intent_lower for word in cap.split("_")):
                matches.append(module)
                break
        for action in module.actions:
            if action in intent_lower:
                matches.append(module)
                break
    return list(set(matches))
