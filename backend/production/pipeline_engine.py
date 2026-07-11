"""Pipeline Engine — builds and executes production graphs.

Given a production type and content, constructs the appropriate pipeline
of generation/voice/music/editing steps as a directed graph. Each node
becomes a job dispatched through the Execution Platform.
"""

from __future__ import annotations

import uuid

# =============================================================================
# Pipeline Templates
# =============================================================================

PIPELINE_TEMPLATES: dict[str, list[dict]] = {
    "instagram_reel": [
        {"type": "generation", "name": "Generate Key Frame", "provider": "image"},
        {"type": "generation", "name": "Animate to Video", "provider": "video"},
        {"type": "voice", "name": "Generate Voiceover", "provider": "audio"},
        {"type": "music", "name": "Add Background Music", "provider": "music"},
        {"type": "editing", "name": "Mix Audio + Video", "provider": "editing"},
        {"type": "editing", "name": "Add Captions", "provider": "editing"},
        {"type": "editing", "name": "Export 9:16", "provider": "editing"},
    ],
    "tiktok": [
        {"type": "generation", "name": "Generate Visual", "provider": "image"},
        {"type": "generation", "name": "Animate", "provider": "video"},
        {"type": "editing", "name": "Trim to 15-60s", "provider": "editing"},
        {"type": "editing", "name": "Add Music", "provider": "editing"},
        {"type": "editing", "name": "Export 9:16 TikTok", "provider": "editing"},
    ],
    "youtube_short": [
        {"type": "generation", "name": "Generate Scenes", "provider": "image"},
        {"type": "generation", "name": "Animate Scenes", "provider": "video"},
        {"type": "voice", "name": "Narration", "provider": "audio"},
        {"type": "editing", "name": "Assemble", "provider": "editing"},
        {"type": "editing", "name": "Export 9:16 60s", "provider": "editing"},
    ],
    "fashion_campaign": [
        {"type": "generation", "name": "Hero Image", "provider": "image"},
        {"type": "generation", "name": "Detail Shot 1", "provider": "image"},
        {"type": "generation", "name": "Detail Shot 2", "provider": "image"},
        {"type": "generation", "name": "Behind the Scenes", "provider": "image"},
        {"type": "editing", "name": "Color Grade All", "provider": "editing"},
        {"type": "editing", "name": "Package Campaign", "provider": "editing"},
    ],
    "talking_head": [
        {"type": "generation", "name": "Generate Portrait", "provider": "image"},
        {"type": "voice", "name": "Generate Speech", "provider": "audio"},
        {"type": "generation", "name": "Lip Sync Animation", "provider": "video"},
        {"type": "editing", "name": "Final Mix", "provider": "editing"},
    ],
    "commercial": [
        {"type": "generation", "name": "Product Shot", "provider": "image"},
        {"type": "generation", "name": "Lifestyle Shot", "provider": "image"},
        {"type": "generation", "name": "Animate Sequence", "provider": "video"},
        {"type": "voice", "name": "Voiceover", "provider": "audio"},
        {"type": "music", "name": "Jingle/Music", "provider": "music"},
        {"type": "editing", "name": "Assemble 30s", "provider": "editing"},
        {"type": "editing", "name": "Add CTA", "provider": "editing"},
        {"type": "editing", "name": "Export Formats", "provider": "editing"},
    ],
    "portrait": [
        {"type": "generation", "name": "Generate Portrait", "provider": "image"},
        {"type": "editing", "name": "Face Restore", "provider": "editing"},
        {"type": "editing", "name": "Upscale 2x", "provider": "editing"},
    ],
    "short_film": [
        {"type": "generation", "name": "Generate All Shots", "provider": "image"},
        {"type": "generation", "name": "Animate Shots", "provider": "video"},
        {"type": "voice", "name": "Dialogue", "provider": "audio"},
        {"type": "voice", "name": "Narration", "provider": "audio"},
        {"type": "music", "name": "Score", "provider": "music"},
        {"type": "editing", "name": "Assemble Timeline", "provider": "editing"},
        {"type": "editing", "name": "Sound Design", "provider": "editing"},
        {"type": "editing", "name": "Color Grade", "provider": "editing"},
        {"type": "editing", "name": "Final Export", "provider": "editing"},
    ],
}


def get_pipeline_template(production_type: str) -> list[dict]:
    """Get the pipeline template for a production type."""
    # Map production types to pipeline templates
    type_to_template = {
        "reel": "instagram_reel",
        "instagram_post": "portrait",
        "portrait": "portrait",
        "tiktok": "tiktok",
        "youtube_short": "youtube_short",
        "fashion_campaign": "fashion_campaign",
        "talking_head": "talking_head",
        "commercial": "commercial",
        "short_film": "short_film",
        "advertisement": "commercial",
        "music_video": "short_film",
    }
    template_key = type_to_template.get(production_type, "portrait")
    return PIPELINE_TEMPLATES.get(template_key, PIPELINE_TEMPLATES["portrait"])


def build_production_graph(
    production_type: str,
    parameters: dict | None = None,
) -> list[dict]:
    """Build a production graph (list of nodes) from a template.

    Each node represents a step that becomes a job. Dependencies
    are sequential by default (each step depends on the previous).
    """
    template = get_pipeline_template(production_type)
    params = parameters or {}
    nodes = []

    for i, step in enumerate(template):
        node_id = uuid.uuid4().hex[:12]
        node = {
            "id": node_id,
            "type": step["type"],
            "name": step["name"],
            "provider": step["provider"],
            "status": "pending",
            "depends_on": [nodes[i - 1]["id"]] if i > 0 else [],
            "parameters": {**params},
        }
        nodes.append(node)

    return nodes


def estimate_production_time(graph: list[dict]) -> dict:
    """Estimate total production time from graph.

    Returns estimated seconds and cost based on step types.
    """
    time_per_type = {
        "generation": 30,
        "voice": 15,
        "music": 10,
        "editing": 20,
    }
    total_seconds = sum(time_per_type.get(n.get("type", ""), 20) for n in graph)
    cost_per_step = 0.02  # Simulated cost

    return {
        "estimated_seconds": total_seconds,
        "estimated_minutes": round(total_seconds / 60, 1),
        "estimated_cost_usd": round(len(graph) * cost_per_step, 2),
        "total_steps": len(graph),
    }


def build_timeline_from_shots(shots: list[dict], fps: int = 24) -> dict:
    """Build a timeline structure from a list of shots.

    Each shot becomes a clip on the video track.
    Returns timeline dict ready for storage.
    """
    video_clips = []
    current_time = 0.0

    for shot in shots:
        clip = {
            "shot_id": shot.get("id", ""),
            "asset_id": shot.get("asset_id"),
            "start_time": current_time,
            "duration": shot.get("duration_seconds", 3.0),
            "transition_in": "cut" if current_time == 0 else shot.get("transition", "cut"),
        }
        video_clips.append(clip)
        current_time += shot.get("duration_seconds", 3.0)

    return {
        "duration_seconds": current_time,
        "fps": fps,
        "tracks": [
            {"name": "Video", "type": "video", "order": 0, "clips": video_clips},
            {"name": "Voice", "type": "voice", "order": 1, "clips": []},
            {"name": "Music", "type": "music", "order": 2, "clips": []},
            {"name": "Effects", "type": "effects", "order": 3, "clips": []},
            {"name": "Subtitles", "type": "subtitle", "order": 4, "clips": []},
        ],
    }
