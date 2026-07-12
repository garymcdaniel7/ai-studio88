"""MCP Tool Definitions — declares what AI Studio exposes to external clients.

Each tool has:
- name: machine identifier
- description: what it does (shown to the external AI)
- parameters: JSON Schema for inputs
- requires_auth: whether an API key is needed
- governance: whether it goes through the approval queue

External AIs (Claude, ChatGPT) see these tool definitions and can invoke them.
All invocations route through the Intelligence Gateway with full governance.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPTool:
    """An MCP-compatible tool definition."""
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    requires_auth: bool = True
    category: str = "general"


# =============================================================================
# Tool Registry — all tools exposed via MCP
# =============================================================================

MCP_TOOLS: list[MCPTool] = [

    # ── Talent & Creative ─────────────────────────────────────────────────────
    MCPTool(
        name="search_talent",
        description="Search AI talent by name, style, type, or attributes. Returns matching talent profiles.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (name, style, or keywords)"},
                "type_filter": {"type": "string", "description": "Filter by type: model, background, product, wardrobe, voice"},
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
            },
            "required": ["query"],
        },
        category="talent",
    ),
    MCPTool(
        name="get_talent_dna",
        description="Get full Creative DNA for a talent: visual style, preferences, LoRAs, relationships, voice profiles.",
        parameters={
            "type": "object",
            "properties": {
                "talent_id": {"type": "string", "description": "Talent UUID"},
            },
            "required": ["talent_id"],
        },
        category="talent",
    ),
    MCPTool(
        name="create_talent",
        description="Create a new AI talent (person, background, product, wardrobe, or voice).",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Talent name"},
                "type": {"type": "string", "description": "model, background, product, wardrobe, voice"},
                "bio": {"type": "string", "description": "Description/bio"},
                "visual_style": {"type": "string", "description": "Visual style tags"},
            },
            "required": ["name"],
        },
        category="talent",
    ),

    # ── Generation ────────────────────────────────────────────────────────────
    MCPTool(
        name="generate_image",
        description="Generate an AI image using ComfyUI. Supports Flux Dev, SDXL Turbo, SD 1.5. Returns base64 image.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image generation prompt"},
                "negative_prompt": {"type": "string", "description": "What to avoid"},
                "model": {"type": "string", "description": "flux-dev, sdxl-turbo, sd15", "default": "flux-dev"},
                "width": {"type": "integer", "description": "Width in pixels", "default": 1024},
                "height": {"type": "integer", "description": "Height in pixels", "default": 1024},
                "steps": {"type": "integer", "description": "Sampling steps", "default": 20},
                "talent_id": {"type": "string", "description": "Talent to inject DNA/LoRA for"},
            },
            "required": ["prompt"],
        },
        category="generation",
    ),
    MCPTool(
        name="generate_video",
        description="Generate an AI video clip (2-10 seconds). Uses WAN 2.1 or KLING.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video generation prompt"},
                "duration": {"type": "integer", "description": "Duration in seconds (2-10)", "default": 4},
                "model": {"type": "string", "description": "wan-2.1 or kling", "default": "wan-2.1"},
                "talent_id": {"type": "string", "description": "Talent for identity consistency"},
            },
            "required": ["prompt"],
        },
        category="generation",
    ),
    MCPTool(
        name="recommend_workflow",
        description="Get the optimal generation workflow for a request based on Workflow DNA (learned success history).",
        parameters={
            "type": "object",
            "properties": {
                "content_type": {"type": "string", "description": "image, video, or voice"},
                "talent_id": {"type": "string", "description": "Talent context (optional)"},
                "style": {"type": "string", "description": "Style hints (luxury, editorial, cinematic)"},
            },
            "required": ["content_type"],
        },
        category="generation",
    ),

    # ── Story ─────────────────────────────────────────────────────────────────
    MCPTool(
        name="continue_story",
        description="Continue a story universe narrative. Add scenes, episodes, or character developments.",
        parameters={
            "type": "object",
            "properties": {
                "universe_id": {"type": "string", "description": "Story universe ID"},
                "direction": {"type": "string", "description": "What should happen next"},
            },
            "required": ["universe_id", "direction"],
        },
        category="story",
    ),
    MCPTool(
        name="get_story_context",
        description="Get the current state of a story universe: characters, recent events, continuity notes.",
        parameters={
            "type": "object",
            "properties": {
                "universe_id": {"type": "string", "description": "Story universe ID"},
            },
            "required": ["universe_id"],
        },
        category="story",
    ),

    # ── Training ──────────────────────────────────────────────────────────────
    MCPTool(
        name="train_lora",
        description="Train a LoRA model from talent images. Requires approval. Costs ~$2 in GPU time.",
        parameters={
            "type": "object",
            "properties": {
                "talent_id": {"type": "string", "description": "Talent whose images to train on"},
                "trigger_word": {"type": "string", "description": "LoRA trigger word (e.g., 'ohwx')"},
                "steps": {"type": "integer", "description": "Training steps (500-5000)", "default": 1000},
                "base_model": {"type": "string", "description": "Base model (flux-dev, sdxl)", "default": "flux-dev"},
            },
            "required": ["talent_id", "trigger_word"],
        },
        category="training",
    ),
    MCPTool(
        name="get_training_status",
        description="Check the status of a LoRA training job.",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Training job ID"},
            },
            "required": ["job_id"],
        },
        category="training",
    ),

    # ── Assets ────────────────────────────────────────────────────────────────
    MCPTool(
        name="search_assets",
        description="Search generated assets (images, videos, audio) by type, talent, or date.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "type": {"type": "string", "description": "image, video, audio, model"},
                "talent_id": {"type": "string", "description": "Filter by talent"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        category="assets",
    ),

    # ── Publishing ────────────────────────────────────────────────────────────
    MCPTool(
        name="schedule_post",
        description="Schedule a social media post. Requires approval.",
        parameters={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "description": "instagram, tiktok, youtube, twitter"},
                "content": {"type": "string", "description": "Post caption/text"},
                "asset_id": {"type": "string", "description": "Asset to attach"},
                "scheduled_for": {"type": "string", "description": "ISO datetime to publish"},
            },
            "required": ["platform", "content"],
        },
        category="publishing",
    ),

    # ── Infrastructure ────────────────────────────────────────────────────────
    MCPTool(
        name="check_gpu_status",
        description="Check GPU worker status: active, GPU type, VRAM, loaded models, cost per hour.",
        parameters={"type": "object", "properties": {}},
        category="infrastructure",
    ),
    MCPTool(
        name="estimate_cost",
        description="Estimate GPU cost for a generation or training job before executing.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "generate_image, generate_video, train_lora"},
                "model": {"type": "string", "description": "Model to use"},
                "steps": {"type": "integer", "description": "Steps (for generation/training)"},
            },
            "required": ["action"],
        },
        category="infrastructure",
    ),

    # ── Knowledge ─────────────────────────────────────────────────────────────
    MCPTool(
        name="search_knowledge",
        description="Search the AI Studio knowledge graph across all data: talents, models, DNA, stories, workflows.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "sources": {"type": "string", "description": "Comma-separated: talent,model,creative_dna,object_dna,workflow_dna,story"},
            },
            "required": ["query"],
        },
        category="knowledge",
    ),
]


def get_tool_definitions() -> list[dict]:
    """Get all tool definitions in MCP-compatible format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.parameters,
        }
        for t in MCP_TOOLS
    ]


def get_tool(name: str) -> MCPTool | None:
    """Get a specific tool by name."""
    for t in MCP_TOOLS:
        if t.name == name:
            return t
    return None


def list_tools_by_category() -> dict[str, list[dict]]:
    """Group tools by category for display."""
    categories: dict[str, list[dict]] = {}
    for t in MCP_TOOLS:
        if t.category not in categories:
            categories[t.category] = []
        categories[t.category].append({
            "name": t.name,
            "description": t.description,
        })
    return categories
