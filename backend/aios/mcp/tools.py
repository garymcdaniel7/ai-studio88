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
    provider: str = "ai_studio"
    required_capabilities: tuple[str, ...] = ()
    risk: str = "read"
    allowed_roles: tuple[str, ...] = ("viewer", "editor", "admin", "owner")
    requires_approval: bool = False


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
                "model": {"type": "string", "description": "Model to use: flux-dev, flux-dev-basic, sdxl-turbo, sd15", "default": "flux-dev"},
                "workflow": {"type": "string", "description": "Specific workflow template (overrides model default). Use 'auto' to auto-select from model."},
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
        description="Generate an AI video clip. Enqueues a real video_generation job on the GPU worker (ComfyUI/WAN, Wan 2.2 local preferred, H3 hosted). Returns a job_id to poll with get_training_status.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Video generation prompt"},
                "negative_prompt": {"type": "string", "description": "What to avoid in the video"},
                "duration_seconds": {"type": "integer", "description": "Duration in seconds", "default": 5},
                "model": {"type": "string", "description": "Model: wan-2.1-t2v, wan-2.1-i2v, wan-2.2-t2v, wan-2.2-14b, wan-2.2-remix", "default": "wan-2.2-t2v"},
                "workflow": {"type": "string", "description": "Specific workflow template (overrides model default). Use 'auto' to auto-select from model."},
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
    MCPTool(
        name="list_models",
        description="List available image or video models for generation. Returns model names, workflow templates, and notes.",
        parameters={
            "type": "object",
            "properties": {
                "lane": {"type": "string", "description": "image, video, or all", "default": "all"},
            },
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
    # ── Phase 2 authenticated WRITE/MAKE/PUBLISH contracts ─────────────────
    MCPTool(
        name="create_episode",
        description="Create a tenant-owned story episode.",
        parameters={"type": "object", "properties": {"universe_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}, "episode_number": {"type": "integer"}}, "required": ["universe_id", "title"]},
        category="story", provider="story_engine", required_capabilities=("create_episode",), risk="write", requires_approval=True,
    ),
    MCPTool(
        name="create_scene",
        description="Create a tenant-owned scene under an episode.",
        parameters={"type": "object", "properties": {"episode_id": {"type": "string"}, "scene_number": {"type": "integer"}, "title": {"type": "string"}, "location": {"type": "string"}}, "required": ["episode_id"]},
        category="story", provider="story_engine", required_capabilities=("create_scene",), risk="write", requires_approval=True,
    ),
    MCPTool(
        name="create_shot",
        description="Create a tenant-owned storyboard shot.",
        parameters={"type": "object", "properties": {"scene_id": {"type": "string"}, "shot_number": {"type": "integer"}, "shot_type": {"type": "string"}, "description": {"type": "string"}}, "required": ["scene_id"]},
        category="story", provider="story_engine", required_capabilities=("create_shot",), risk="write", requires_approval=True,
    ),
    MCPTool(
        name="update_shot_prompt",
        description="Update a storyboard shot prompt and continuity context.",
        parameters={"type": "object", "properties": {"shot_id": {"type": "string"}, "prompt": {"type": "string"}, "description": {"type": "string"}, "generation_params": {"type": "object"}, "metadata": {"type": "object"}}, "required": ["shot_id"]},
        category="story", provider="story_engine", required_capabilities=("update_shot_prompt",), risk="write", requires_approval=True,
    ),
    MCPTool(
        name="get_storyboard",
        description="Read a tenant-owned episode storyboard with scenes and shots.",
        parameters={"type": "object", "properties": {"episode_id": {"type": "string"}, "universe_id": {"type": "string"}}},
        category="story", provider="story_engine", required_capabilities=("get_storyboard",),
    ),
    MCPTool(
        name="list_episodes",
        description="List tenant-owned episodes for a story universe.",
        parameters={"type": "object", "properties": {"universe_id": {"type": "string"}, "limit": {"type": "integer"}, "offset": {"type": "integer"}}, "required": ["universe_id"]},
        category="story", provider="story_engine", required_capabilities=("list_episodes",),
    ),
    MCPTool(
        name="upload_shot_reference",
        description="Create a short-lived signed upload URL for a tenant-owned shot reference image.",
        parameters={"type": "object", "properties": {"shot_id": {"type": "string"}, "filename": {"type": "string"}, "content_type": {"type": "string"}, "talent_id": {"type": "string"}}, "required": ["shot_id", "filename", "content_type"]},
        category="story", provider="backblaze_b2", required_capabilities=("upload_shot_reference",), risk="write", requires_approval=True,
    ),
    MCPTool(
        name="connect_platform",
        description="Connect a publishing platform through OAuth or an API key without returning credentials.",
        parameters={"type": "object", "properties": {"platform": {"type": "string"}, "provider_name": {"type": "string"}, "ownership": {"type": "string"}, "display_name": {"type": "string"}, "api_key": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["platform"]},
        category="publishing", provider="platform_connections", required_capabilities=("connect_platform",), risk="credential", requires_approval=True,
    ),
    MCPTool(
        name="disconnect_platform",
        description="Revoke a tenant-owned platform connection.",
        parameters={"type": "object", "properties": {"connection_id": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["connection_id"]},
        category="publishing", provider="platform_connections", required_capabilities=("disconnect_platform",), risk="destructive", requires_approval=True,
    ),
    MCPTool(
        name="list_connected_platforms",
        description="List connected publishing platforms for the authenticated workspace.",
        parameters={"type": "object", "properties": {}}, category="publishing", provider="platform_connections", required_capabilities=("list_connected_platforms",),
    ),
    MCPTool(
        name="list_platforms",
        description="List platform capabilities, rollout state, and policy requirements.",
        parameters={"type": "object", "properties": {}}, category="publishing", provider="platform_registry", required_capabilities=("list_platforms",),
    ),
    MCPTool(
        name="check_platform_policy",
        description="Check platform capability, content, AI-label, age, consent, moderation, and confirmation gates.",
        parameters={"type": "object", "properties": {"platform": {"type": "string"}, "is_nsfw": {"type": "boolean"}, "ai_label_present": {"type": "boolean"}, "watermark_present": {"type": "boolean"}, "caption_disclosure_present": {"type": "boolean"}, "age_verified": {"type": "boolean"}, "consent_verified": {"type": "boolean"}, "identity_verified": {"type": "boolean"}, "moderation_passed": {"type": "boolean"}, "publish_confirmed": {"type": "boolean"}}, "required": ["platform"]}, category="publishing", provider="platform_registry", required_capabilities=("check_platform_policy",),
    ),
    MCPTool(
        name="schedule_post",
        description="Schedule a policy-approved tenant-owned publishing post.",
        parameters={"type": "object", "properties": {"platform": {"type": "string"}, "content": {"type": "string"}, "asset_id": {"type": "string"}, "post_id": {"type": "string"}, "scheduled_for": {"type": "string"}, "publish_confirmed": {"type": "boolean"}, "ai_label_present": {"type": "boolean"}, "watermark_present": {"type": "boolean"}, "caption_disclosure_present": {"type": "boolean"}, "age_verified": {"type": "boolean"}, "consent_verified": {"type": "boolean"}, "identity_verified": {"type": "boolean"}, "moderation_passed": {"type": "boolean"}, "is_nsfw": {"type": "boolean"}, "idempotency_key": {"type": "string"}}, "required": ["platform", "content", "scheduled_for"]}, category="publishing", provider="publishing", required_capabilities=("schedule_post",), risk="external_side_effect", requires_approval=True,
    ),
    MCPTool(name="list_scheduled_posts", description="List tenant-owned scheduled posts.", parameters={"type": "object", "properties": {"status": {"type": "string"}}}, category="publishing", provider="publishing", required_capabilities=("list_scheduled_posts",)),
    MCPTool(name="get_publishing_calendar", description="Read the authenticated tenant publishing calendar.", parameters={"type": "object", "properties": {"status": {"type": "string"}}}, category="publishing", provider="publishing", required_capabilities=("get_publishing_calendar",)),
    MCPTool(name="cancel_scheduled_post", description="Cancel a tenant-owned scheduled post idempotently.", parameters={"type": "object", "properties": {"post_id": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["post_id"]}, category="publishing", provider="publishing", required_capabilities=("cancel_scheduled_post",), risk="write", requires_approval=True),
    MCPTool(name="get_publishing_status", description="Read one tenant-owned publishing status.", parameters={"type": "object", "properties": {"post_id": {"type": "string"}}, "required": ["post_id"]}, category="publishing", provider="publishing", required_capabilities=("get_publishing_status",)),
    MCPTool(name="get_connection_status", description="Read a tenant-owned connection status without credentials.", parameters={"type": "object", "properties": {"connection_id": {"type": "string"}}, "required": ["connection_id"]}, category="connections", provider="platform_connections", required_capabilities=("get_connection_status",)),
    MCPTool(name="check_connection_health", description="Check a tenant-owned connection health state.", parameters={"type": "object", "properties": {"connection_id": {"type": "string"}}, "required": ["connection_id"]}, category="connections", provider="platform_connections", required_capabilities=("check_connection_health",)),
    MCPTool(name="reauthorize_connection", description="Start a tenant-owned connection reauthorization flow.", parameters={"type": "object", "properties": {"connection_id": {"type": "string"}}, "required": ["connection_id"]}, category="connections", provider="platform_connections", required_capabilities=("reauthorize_connection",), risk="credential", requires_approval=True),
    MCPTool(name="revoke_connection", description="Revoke a tenant-owned connection and its encrypted credentials.", parameters={"type": "object", "properties": {"connection_id": {"type": "string"}}, "required": ["connection_id"]}, category="connections", provider="platform_connections", required_capabilities=("revoke_connection",), risk="destructive", requires_approval=True),
    MCPTool(name="add_api_key", description="Store a customer API key encrypted and return masked metadata only.", parameters={"type": "object", "properties": {"provider": {"type": "string"}, "api_key": {"type": "string"}, "label": {"type": "string"}, "expires_at": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["provider", "api_key"]}, category="credentials", provider="credential_service", required_capabilities=("add_api_key",), risk="credential", requires_approval=True),
    MCPTool(name="list_api_keys", description="List masked provider credential metadata only.", parameters={"type": "object", "properties": {"provider": {"type": "string"}}}, category="credentials", provider="credential_service", required_capabilities=("list_api_keys",)),
    MCPTool(name="remove_api_key", description="Revoke a tenant-owned provider API key.", parameters={"type": "object", "properties": {"provider": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["provider"]}, category="credentials", provider="credential_service", required_capabilities=("remove_api_key",), risk="destructive", requires_approval=True),
    MCPTool(name="test_api_key", description="Test credential validity and provider metadata without exposing the key.", parameters={"type": "object", "properties": {"provider": {"type": "string"}}, "required": ["provider"]}, category="credentials", provider="credential_service", required_capabilities=("test_api_key",)),
    MCPTool(name="get_default_provider", description="Return configured provider capabilities without secrets.", parameters={"type": "object", "properties": {"workload": {"type": "string"}}}, category="credentials", provider="provider_registry", required_capabilities=("get_default_provider",)),
    MCPTool(name="preview_generation", description="Queue a fixed WRITE preview generation asynchronously.", parameters={"type": "object", "properties": {"prompt": {"type": "string"}, "model": {"type": "string"}, "seed": {"type": "integer"}, "idempotency_key": {"type": "string"}}, "required": ["prompt"]}, category="generation", provider="generation_orchestrator", required_capabilities=("preview_generation",), risk="provider_side_effect", requires_approval=True),
    MCPTool(name="get_generation_status", description="Read one tenant-owned generation job status.", parameters={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}, category="generation", provider="generation_jobs", required_capabilities=("get_generation_status",)),
    MCPTool(name="get_generation_queue", description="List generation jobs for the authenticated MCP session.", parameters={"type": "object", "properties": {"session_id": {"type": "string"}}}, category="generation", provider="generation_jobs", required_capabilities=("get_generation_queue",)),
    MCPTool(name="generate_with_ksampler", description="Queue bounded KSampler generation with cost and provenance gates.", parameters={"type": "object", "properties": {"prompt": {"type": "string"}, "model": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "steps": {"type": "integer"}, "cfg": {"type": "number"}, "sampler": {"type": "string"}, "scheduler": {"type": "string"}, "seed": {"type": "integer"}, "idempotency_key": {"type": "string"}}, "required": ["prompt"]}, category="generation", provider="generation_orchestrator", required_capabilities=("generate_with_ksampler",), risk="provider_side_effect", requires_approval=True),
    MCPTool(name="generate_with_workflow", description="Validate and queue a ComfyUI workflow generation.", parameters={"type": "object", "properties": {"prompt": {"type": "string"}, "workflow_id": {"type": "string"}, "workflow": {"type": "object"}, "model": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["prompt"]}, category="generation", provider="generation_orchestrator", required_capabilities=("generate_with_workflow",), risk="provider_side_effect", requires_approval=True),
    MCPTool(name="list_workflows", description="List safe workflow metadata.", parameters={"type": "object", "properties": {}}, category="generation", provider="workflow_registry", required_capabilities=("list_workflows",)),
    MCPTool(name="switch_workflow", description="Validate a workflow selection for an owned generation job.", parameters={"type": "object", "properties": {"workflow_id": {"type": "string"}, "job_id": {"type": "string"}}, "required": ["workflow_id"]}, category="generation", provider="workflow_registry", required_capabilities=("switch_workflow",), risk="write", requires_approval=True),
    MCPTool(name="get_workflow_schema", description="Read a validated workflow schema.", parameters={"type": "object", "properties": {"workflow_id": {"type": "string"}}, "required": ["workflow_id"]}, category="generation", provider="workflow_registry", required_capabilities=("get_workflow_schema",)),
    MCPTool(name="generate_batch", description="Queue an idempotent bounded generation batch.", parameters={"type": "object", "properties": {"prompt": {"type": "string"}, "variation_count": {"type": "integer"}, "model": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["prompt", "variation_count"]}, category="generation", provider="generation_orchestrator", required_capabilities=("generate_batch",), risk="provider_side_effect", requires_approval=True),
    MCPTool(name="cancel_generation", description="Cancel an owned generation job or batch idempotently.", parameters={"type": "object", "properties": {"job_id": {"type": "string"}, "batch_id": {"type": "string"}},}, category="generation", provider="generation_jobs", required_capabilities=("cancel_generation",), risk="write", requires_approval=True),
]


def get_tool_definitions() -> list[dict]:
    """Get all tool definitions in MCP-compatible format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.parameters,
            "provider": t.provider,
            "requiredCapabilities": list(t.required_capabilities),
            "risk": t.risk,
            "allowedRoles": list(t.allowed_roles),
            "requiresApproval": t.requires_approval,
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
